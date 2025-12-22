"""
Engage360 Device Activation File Processing Workflow
====================================================

Implementation for processing Device Activation CSV files.
Follows modular architecture with staging → core table flow and comprehensive validation.

BusinessCaseID: BC-TBD (Device Activation System)

This module processes CSV files containing device activation data:
- Member information (salesforce_account_id, names, contact info)
- Device information (UDI, brand, device status)
- Campaign enrollment with business day calculations


Key Features:
- 5-phase ETL: Extract → Load Staging → Validate → Transform → Audit
- Business day calculations using business_hours_utils
- Dual-timezone business hours validation
- Device status tracking (fall detection, powersaver mode)
- 90-day campaign lifecycle from enrollment_ts
"""

import os
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import logging
import uuid
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import pymssql
from pathlib import Path

try:
    import pandera as pa
    from pandera import Column, DataFrameSchema, Check

    PANDERA_AVAILABLE = True
except ImportError:
    PANDERA_AVAILABLE = False
    pa = None
    Column = None
    DataFrameSchema = None
    Check = None

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from azure.storage.blob import BlobServiceClient

    AZURE_STORAGE_AVAILABLE = True
except ImportError:
    BlobServiceClient = None
    AZURE_STORAGE_AVAILABLE = False

from io import BytesIO
import re

# Import shared utilities
from af_code.shared.language_mapper import map_language_code
from af_code.shared.business_hours_utils import add_business_days, is_business_day

# Module load verification
logger = logging.getLogger(__name__)
logger.info("🔄 [MODULE-LOAD] af_device_activation_logic.py loading - VERSION: 2025-12-07")
logger.info("🔄 [MODULE-LOAD] Device Activation file processing with business day calculations")


# ============================================================================
# BLOB STORAGE UTILITIES
# ============================================================================


def get_blob_service_client():
    """Get Azure Blob Storage client using Key Vault credentials"""
    key_vault_url = os.environ.get("KEY_VAULT_URL")
    secret_name_storage = "AzureStorageConnectionString"  # nosec B105

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=key_vault_url, credential=credential)
    secret_storage = client.get_secret(secret_name_storage)
    secure_connection_string_storage = secret_storage.value
    return BlobServiceClient.from_connection_string(secure_connection_string_storage)


def download_blob_as_dataframe(blob_name: str, container_name: str) -> pd.DataFrame:
    """Download blob and parse as DataFrame"""
    blob_service = get_blob_service_client()
    blob_client = blob_service.get_container_client(container_name).get_blob_client(blob_name)
    stream = BytesIO()
    blob_data = blob_client.download_blob()
    blob_data.readinto(stream)
    stream.seek(0)
    return pd.read_csv(stream, dtype=str, keep_default_na=False)


def move_blob(blob_name: str, source_folder: str, target_folder: str, container_name: str):
    """Move blob from source folder to target folder"""
    blob_service = get_blob_service_client()
    container_client = blob_service.get_container_client(container_name)
    source_blob = f"{source_folder}/{blob_name}"
    target_blob = f"{target_folder}/{blob_name}"

    source_blob_client = container_client.get_blob_client(source_blob)
    target_blob_client = container_client.get_blob_client(target_blob)

    # Copy then delete
    target_blob_client.start_copy_from_url(source_blob_client.url)
    source_blob_client.delete_blob()


def handle_blob_movement_with_error_handling(
    source_filename: str, source_folder: str, target_folder: str, container_name: str, logger
):
    """Safely move blob with error handling and fallback logic"""
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(container_name)
        source_blob_path = f"{source_folder}/{source_filename}"

        try:
            source_blob_client = container_client.get_blob_client(source_blob_path)
            source_blob_client.get_blob_properties()

            move_blob(source_filename, source_folder, target_folder, container_name)
            logger.info(
                f"✅ Successfully moved {source_filename} from {source_folder} to {target_folder}"
            )

        except Exception as blob_check_error:
            if "BlobNotFound" in str(blob_check_error) or "does not exist" in str(blob_check_error):
                logger.warning(
                    f"⚠️ Source blob {source_blob_path} not found, checking other locations..."
                )

                for check_folder in ["landing", "staging", "processed"]:
                    if check_folder == source_folder:
                        continue

                    try:
                        check_blob_path = f"{check_folder}/{source_filename}"
                        check_blob_client = container_client.get_blob_client(check_blob_path)
                        check_blob_client.get_blob_properties()

                        move_blob(source_filename, check_folder, target_folder, container_name)
                        logger.info(
                            f"✅ Found and moved {source_filename} from {check_folder} to {target_folder}"
                        )
                        return

                    except Exception:  # nosec B112
                        continue

                logger.error(f"❌ Could not find {source_filename} in any folder")
            else:
                logger.error(f"❌ Unexpected error checking blob: {blob_check_error}")
                raise blob_check_error

    except Exception as e:
        logger.error(f"❌ Error moving blob: {e}")
        raise


# ============================================================================
# DATABASE CONNECTION UTILITIES
# ============================================================================


def get_db_connection_string():
    """Retrieve database connection string from Key Vault"""
    key_vault_url = os.environ.get("KEY_VAULT_URL")
    secret_name = "SqlConnectionStringIOE"  # nosec B105

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=key_vault_url, credential=credential)
    secret = client.get_secret(secret_name)
    return secret.value


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(pymssql.OperationalError),
)
def get_db_connection():
    """Get database connection with retry logic"""
    conn_str = get_db_connection_string()

    # Parse connection string
    parts = dict(item.split("=", 1) for item in conn_str.split(";") if "=" in item)

    return pymssql.connect(
        server=parts.get("Server", "").replace("tcp:", "").split(",")[0],
        user=parts.get("User ID", ""),
        password=parts.get("Password", ""),
        database=parts.get("Initial Catalog", ""),
        port=int(parts.get("Server", "").split(",")[1]) if "," in parts.get("Server", "") else 1433,
        timeout=30,
        login_timeout=30,
    )


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class ProcessingResult:
    """Result of a processing operation"""

    success: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None


@dataclass
class ProcessingContext:
    """Context for file processing operations"""

    file_batch_id: str
    source_filename: str
    container_name: str = "fs-ops"
    uploaded_by_user: str = "AzureFunction"
    error_threshold_pct: float = 10.0
    log_level: str = "INFO"
    correlation_id: Optional[str] = None
    campaign_id: Optional[str] = None  # Explicit campaign UUID for Operations flow
    campaign_name: Optional[str] = None  # Campaign display name
    blob_content: Optional[bytes] = None  # Raw CSV bytes from blob trigger

    def __post_init__(self):
        if self.correlation_id is None:
            self.correlation_id = str(uuid.uuid4())


# ============================================================================
# VALIDATION UTILITIES
# ============================================================================


def get_org_id_for_partner(partner_name: str) -> Optional[str]:
    """
    Look up org_id from engage360.orgs table based on partner name.
    Specifically looks up DTC org_type for Device Activation operations.

    Args:
        partner_name: Partner organization name (e.g., "Medical Guardian")

    Returns:
        org_id as string UUID for DTC org, or None if not found
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
        SELECT org_id
        FROM engage360.orgs
        WHERE org_name = %s
          AND org_type = 'DTC'
        """

        cursor.execute(query, (partner_name,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            org_id = str(result[0])  # Convert UUID to string
            logger.info(f"✅ [ORG-LOOKUP] Found DTC org_id for '{partner_name}': {org_id}")
            return org_id
        else:
            logger.error(f"❌ [ORG-LOOKUP] No DTC org_id found for partner: '{partner_name}'")
            return None
    except Exception as e:
        logger.error(f"❌ [ORG-LOOKUP] Error looking up org_id: {e}")
        return None


def standardize_phone(phone: str) -> Optional[str]:
    """
    Standardize phone number to E.164 format (+1XXXXXXXXXX)

    Args:
        phone: Phone number in various formats

    Returns:
        E.164 formatted phone or None if invalid
    """
    if not phone or pd.isna(phone):
        return None

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", str(phone))

    # Handle different lengths
    if len(digits) == 10:
        # US number without country code
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        # US number with country code
        return f"+{digits}"
    elif len(digits) >= 10:
        # International or other format - take last 10 digits and add +1
        return f"+1{digits[-10:]}"

    return None


def validate_email(email: str) -> bool:
    """Validate email format"""
    if not email or pd.isna(email):
        return False

    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, str(email)))


def proper_case(name: str) -> str:
    """Convert name to proper case"""
    if not name or pd.isna(name):
        return ""

    return str(name).strip().title()


def map_timezone_to_iana(tz: str) -> str:
    """
    Map timezone abbreviations to IANA format.
    Keep IANA format if already provided.

    Args:
        tz: Timezone string (abbreviation or IANA format)

    Returns:
        IANA timezone string
    """
    if not tz or pd.isna(tz):
        return "America/New_York"  # Default to EST

    tz_str = str(tz).strip()

    # If already IANA format, keep as-is
    if tz_str.startswith("America/"):
        return tz_str

    # Map abbreviations to IANA format
    tz_mapping = {
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "MST": "America/Denver",
        "MDT": "America/Denver",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        "AKST": "America/Anchorage",
        "AKDT": "America/Anchorage",
        "HST": "America/Honolulu",
        "AST": "America/Puerto_Rico",
    }

    return tz_mapping.get(tz_str.upper(), tz_str)  # Return original if not found


def validate_timezone(tz: str) -> bool:
    """Validate timezone is valid IANA format"""
    if not tz or pd.isna(tz):
        return False

    valid_timezones = [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "America/Anchorage",
        "America/Honolulu",
        "America/Puerto_Rico",
        "America/Detroit",
        "America/Indiana/Indianapolis",
        "America/Kentucky/Louisville",
    ]

    return str(tz) in valid_timezones


def validate_device_status(status: str, field_name: str) -> Tuple[bool, str]:
    """
    Validate device status fields

    Args:
        status: Status value
        field_name: 'fall_detection_status' or 'battery_status'

    Returns:
        (is_valid, normalized_value)
    """
    if not status or pd.isna(status):
        return (True, "Unknown")

    status_str = str(status).strip().title()

    if field_name == "fall_detection_status":
        valid_values = ["Active", "Inactive", "Not Applicable", "Unknown"]
        if status_str in valid_values:
            return (True, status_str)
        return (False, status_str)

    elif field_name == "battery_status":
        valid_values = ["Good", "Low", "Critical", "Charging", "Unknown"]
        if status_str in valid_values:
            return (True, status_str)
        return (False, status_str)

    return (False, status_str)


def validate_customer_type(customer_type: str) -> Tuple[bool, str]:
    """
    Validate customer type

    Args:
        customer_type: Customer type string

    Returns:
        (is_valid, normalized_value)
    """
    if not customer_type or pd.isna(customer_type):
        return (True, "DTC")  # Default to DTC

    customer_type_upper = str(customer_type).strip().upper()

    if customer_type_upper in ["DTC", "MS"]:
        return (True, customer_type_upper)

    return (False, customer_type_upper)


# ============================================================================
# PANDERA SCHEMA VALIDATION
# ============================================================================


def get_device_activation_schema() -> Optional[DataFrameSchema]:
    """
    Get Pandera schema for Device Activation CSV files

    Returns:
        DataFrameSchema if Pandera available, None otherwise
    """
    if not PANDERA_AVAILABLE:
        logger.warning("⚠️ Pandera not available, skipping schema validation")
        return None

    return DataFrameSchema(
        {
            # Campaign metadata (first in actual CSV)
            "partner_name": Column(str, nullable=False),
            "campaign_name_source": Column(str, nullable=True),  # NEW
            # Member identity
            "salesforce_account_number": Column(str, nullable=True),
            "salesforce_account_id": Column(str, nullable=False),
            "member_first_name": Column(str, nullable=False),
            "member_last_name": Column(str, nullable=False),
            # Contact
            "member_phone_number": Column(str, nullable=False),
            "member_email": Column(str, nullable=True),
            # Address (5 separate fields - will be combined)
            "member_address_street": Column(str, nullable=True),  # NEW
            "member_address_city": Column(str, nullable=True),  # NEW
            "member_address_state": Column(str, nullable=True),  # NEW
            "member_address_zip": Column(str, nullable=True),  # NEW
            "member_address_country": Column(str, nullable=True),  # NEW
            # Demographics
            "member_dob": Column(str, nullable=True),  # RENAMED from dob
            "member_timezone": Column(str, nullable=False),  # RENAMED from customer_timezone
            "language_pref": Column(str, nullable=True),
            # Device info
            "device_udi": Column(str, nullable=False),
            "device_name": Column(str, nullable=True),
            "member_brand": Column(str, nullable=True),  # RENAMED from brand
            # NOTE: is_device_callable NOT in CSV - inferred from device_phone_number during validation
            "device_phone_number": Column(str, nullable=True),
            # Device status (NEW format: numeric 1/0 instead of text)
            "fall_detection": Column(str, nullable=True),  # CHANGED from fall_detection_status
            "powersaver_mode": Column(str, nullable=True),  # CHANGED from battery_status
            # Campaign tracking
            "campaign_parameters": Column(str, nullable=True),  # NEW
            "monitoring_system_id": Column(str, nullable=True),  # NEW
            "enrollment_status": Column(str, nullable=True),
            "unenrollment_reason": Column(str, nullable=True),  # NEW
        },
        strict=False,  # Allow extra columns
        coerce=True,  # Coerce types
    )


# ============================================================================
# ROW-LEVEL VALIDATION
# ============================================================================


def validate_and_cleanse_data_before_insert(
    df: pd.DataFrame, context: ProcessingContext
) -> pd.DataFrame:
    """
    Validate and cleanse data row-by-row before insertion to staging

    This function performs comprehensive validation on each row:
    1. Partner name validation
    2. Salesforce ID validation
    3. Phone number standardization
    4. Name proper casing
    5. Timezone validation
    6. Language mapping
    7. Date validation
    8. Email validation
    9. Device UDI validation
    10. Device status validation
    11. Delivery date validation
    12. Customer type validation
    13. is_device_callable boolean conversion

    Args:
        df: DataFrame to validate
        context: Processing context

    Returns:
        DataFrame with validation_status and error_message columns
    """
    logger.info(f"📋 [VALIDATION] Starting row-by-row validation for {len(df)} rows")

    # Add validation columns
    df["validation_status"] = "PENDING"
    df["error_message"] = ""
    df["error_details"] = ""

    # Add org_id column (will be populated during partner validation)
    df["org_id"] = None

    # Add clean columns
    df["first_name_clean"] = ""
    df["last_name_clean"] = ""
    df["primary_phone_clean"] = ""
    df["device_phone_clean"] = ""
    df["is_device_callable_clean"] = None
    df["dob_clean"] = None
    df["language_pref_clean"] = ""
    df["timezone_clean"] = ""
    df["service_address_clean"] = ""
    df["brand_clean"] = ""  # For member brand (members.member_brand)
    df["device_name_clean"] = ""  # For device brand (member_devices.brand)
    df["fall_detection_status_clean"] = ""
    df["battery_status_clean"] = ""

    validation_errors_count = 0

    for idx, row in df.iterrows():
        row_errors = []

        # ===================================================================
        # 1. Partner Name Validation + org_id Lookup
        # ===================================================================
        partner_name = str(row.get("partner_name", "")).strip()
        if partner_name != "Medical Guardian":
            row_errors.append(
                f"Invalid partner_name: '{partner_name}' (expected 'Medical Guardian')"
            )
        else:
            # NEW: Look up org_id for this partner (CRITICAL - Required for MERGE)
            org_id = get_org_id_for_partner(partner_name)
            if org_id:
                df.at[idx, "org_id"] = org_id
            else:
                row_errors.append(
                    f"Could not find org_id for partner: '{partner_name}'"
                )

        # ===================================================================
        # 2. Salesforce Account ID Validation (REQUIRED - NEW FIELD)
        # ===================================================================
        salesforce_account_id = str(row.get("salesforce_account_id", "")).strip()
        if not salesforce_account_id or salesforce_account_id == "":
            row_errors.append("salesforce_account_id is required")

        str(row.get("salesforce_account_number", "")).strip()
        # Account number is optional but useful for matching

        # ===================================================================
        # 3. Phone Number Validation and Standardization
        # ===================================================================
        # Support both column names (pre and post column mapping)
        member_phone = row.get("primary_phone", "") or row.get("member_phone_number", "")
        standardized_phone = standardize_phone(member_phone)
        if not standardized_phone:
            row_errors.append(f"Invalid member_phone_number: '{member_phone}'")
        else:
            df.at[idx, "primary_phone_clean"] = standardized_phone

        # Device phone (optional)
        device_phone = row.get("device_phone", "") or row.get("device_phone_number", "")
        if device_phone and str(device_phone).strip():
            standardized_device_phone = standardize_phone(device_phone)
            if standardized_device_phone:
                df.at[idx, "device_phone_clean"] = standardized_device_phone

        # ===================================================================
        # 4. Name Validation and Proper Casing
        # ===================================================================
        # Support both column names (pre and post column mapping)
        first_name = row.get("first_name", "") or row.get("member_first_name", "")
        last_name = row.get("last_name", "") or row.get("member_last_name", "")

        if not first_name or str(first_name).strip() == "":
            row_errors.append("member_first_name is required")
        else:
            df.at[idx, "first_name_clean"] = proper_case(first_name)

        if not last_name or str(last_name).strip() == "":
            row_errors.append("member_last_name is required")
        else:
            df.at[idx, "last_name_clean"] = proper_case(last_name)

        # ===================================================================
        # 5. Timezone Validation and Mapping
        # ===================================================================
        # Support both column names (pre and post column mapping)
        timezone_val = row.get("timezone", "") or row.get(
            "member_timezone", ""
        )  # CHANGED from customer_timezone
        # Map abbreviations (EST, CST, etc.) to IANA format
        mapped_timezone = map_timezone_to_iana(timezone_val)

        # Validate the mapped timezone
        if not validate_timezone(mapped_timezone):
            row_errors.append(
                f"Invalid member_timezone: '{timezone_val}' (mapped to '{mapped_timezone}')"
            )
        else:
            # Store mapped timezone for later use
            df.at[idx, "timezone_clean"] = mapped_timezone

        # ===================================================================
        # 6. Language Preference Mapping (FIX ISSUE #8)
        # ===================================================================
        # Support full language names like "English", "Spanish" in addition to ISO codes
        language_pref_raw = str(row.get("language_pref", "EN")).strip()

        # Map common full names to ISO codes before passing to map_language_code()
        language_name_mapping = {
            "ENGLISH": "EN",
            "SPANISH": "ES",
            "EN": "EN",
            "ES": "ES",
            "OTHER": "Other"
        }

        language_pref_normalized = language_name_mapping.get(language_pref_raw.upper(), language_pref_raw)

        try:
            mapped_language = map_language_code(language_pref_normalized)
            df.at[idx, "language_pref_clean"] = mapped_language
            # Log warning for unmapped full names
            if language_pref_raw.upper() not in language_name_mapping and language_pref_raw:
                logger.warning(
                    f"[VALIDATION] Row {idx+1}: Unmapped language_pref '{language_pref_raw}' "
                    f"defaulted to EN"
                )
        except Exception as e:
            logger.error(f"[VALIDATION] Row {idx+1}: Error mapping language_pref: {e}")
            df.at[idx, "language_pref_clean"] = "EN"  # Default to English

        # ===================================================================
        # 7. Date of Birth Validation (Auto-detect format, convert to YYYY-MM-DD)
        # ===================================================================
        # Support both column names (pre and post column mapping)
        dob = row.get("dob", "") or row.get("member_dob", "")
        if dob and str(dob).strip():
            dob_parsed = None
            # Try multiple date formats (most common first)
            date_formats = [
                "%m/%d/%Y",  # 12/16/1935 (US format - most common)
                "%Y-%m-%d",  # 1935-12-16 (ISO format)
                "%m-%d-%Y",  # 12-16-1935
                "%d/%m/%Y",  # 16/12/1935 (EU format)
                "%Y/%m/%d",  # 1935/12/16
                "%m/%d/%y",  # 12/16/35 (2-digit year)
                "%d-%m-%Y",  # 16-12-1935
            ]

            for date_format in date_formats:
                try:
                    dob_parsed = datetime.strptime(str(dob), date_format).date()
                    df.at[idx, "dob_clean"] = dob_parsed  # Stored as date object (auto YYYY-MM-DD)
                    break  # Success - stop trying other formats
                except ValueError:
                    continue  # Try next format

            if dob_parsed is None:
                row_errors.append(
                    f"Invalid member_dob format: '{dob}' "
                    f"(supported: MM/DD/YYYY, YYYY-MM-DD, DD/MM/YYYY, etc.)"
                )

        # ===================================================================
        # 7.5. Address Combination (NEW - Combine 5 fields into 1)
        # ===================================================================
        # Support both column names (pre and post column mapping)
        street = str(row.get("service_address", "") or row.get("member_address_street", "")).strip()
        city = str(row.get("city", "") or row.get("member_address_city", "")).strip()
        state = str(row.get("state", "") or row.get("member_address_state", "")).strip()
        zip_code = str(row.get("zip", "") or row.get("member_address_zip", "")).strip()

        # Combine address fields
        if street and city and state and zip_code:
            service_address = f"{street}, {city}, {state} {zip_code}"
            df.at[idx, "service_address_clean"] = service_address
        elif street or city:
            # Partial address - combine what we have
            parts = [p for p in [street, city, state, zip_code] if p]
            df.at[idx, "service_address_clean"] = ", ".join(parts)

        # ===================================================================
        # 8. Email Validation (optional)
        # ===================================================================
        # Support both column names (pre and post column mapping)
        email = row.get("email", "") or row.get("member_email", "")
        if email and str(email).strip():
            if not validate_email(email):
                row_errors.append(f"Invalid email format: '{email}'")

        # ===================================================================
        # 9. Device UDI Validation (REQUIRED) + Scientific Notation Conversion
        # ===================================================================
        device_udi = str(row.get("device_udi", "")).strip()
        if not device_udi or device_udi == "":
            row_errors.append("device_udi is required")
        else:
            # FIX ISSUE #2: Convert scientific notation to full number string
            # Example: "9.17E+11" → "917000000000"
            try:
                if "E" in device_udi.upper():
                    original_udi = device_udi
                    device_udi = str(int(float(device_udi)))
                    logger.info(
                        f"[VALIDATION] Row {idx+1}: Converted scientific notation device_udi "
                        f"from '{original_udi}' to '{device_udi}'"
                    )
                    # Update the dataframe with converted value
                    df.at[idx, "device_udi"] = device_udi
            except (ValueError, OverflowError) as e:
                row_errors.append(f"Invalid device_udi format: '{row.get('device_udi')}' - {e}")
                device_udi = ""

            # Validate length after conversion
            if device_udi and (len(device_udi) < 5 or len(device_udi) > 50):
                row_errors.append(f"device_udi length must be 5-50 characters: '{device_udi}'")

        # ===================================================================
        # 10. Device Status Validation and Conversion (UPDATED FORMAT)
        # ===================================================================
        # Fall Detection: Convert 1/0 to Active/Inactive
        # Support both column names (pre and post column mapping)
        fall_detection = row.get("fall_detection_status", "") or row.get("fall_detection", "")
        if fall_detection and str(fall_detection).strip():
            fall_str = str(fall_detection).strip()
            if fall_str in ["1", "1.0", "True", "true", "Y", "Yes"]:
                df.at[idx, "fall_detection_status_clean"] = "Active"
            elif fall_str in ["0", "0.0", "False", "false", "N", "No"]:
                df.at[idx, "fall_detection_status_clean"] = "Inactive"
            else:
                # Try to use the existing validation if it's already text
                is_valid, normalized = validate_device_status(
                    fall_detection, "fall_detection_status"
                )
                if is_valid:
                    df.at[idx, "fall_detection_status_clean"] = normalized
                else:
                    df.at[idx, "fall_detection_status_clean"] = "Unknown"

        # Battery Mode: Map "Standard" and "Powersaver" to "Good"
        # Support both column names (pre and post column mapping)
        battery = row.get("battery_status", "") or row.get("powersaver_mode", "")
        if battery and str(battery).strip():
            battery_str = str(battery).strip().title()
            if battery_str in ["Standard", "Powersaver"]:
                df.at[idx, "battery_status_clean"] = "Good"
            else:
                # Validate against known battery statuses
                is_valid, normalized = validate_device_status(battery, "battery_status")
                if is_valid:
                    df.at[idx, "battery_status_clean"] = normalized
                else:
                    df.at[idx, "battery_status_clean"] = "Unknown"
        else:
            # Default to Unknown if not provided
            df.at[idx, "battery_status_clean"] = "Unknown"

        # Member Brand: Map member_brand to brand_clean (for members.member_brand)
        # Support both column names (pre and post column mapping)
        member_brand = row.get("brand", "") or row.get("member_brand", "")
        if member_brand and str(member_brand).strip():
            df.at[idx, "brand_clean"] = str(member_brand).strip()

        # Device Brand: Map device_name to device_name_clean (for member_devices.brand)
        device_name = row.get("device_name", "")
        if device_name and str(device_name).strip():
            df.at[idx, "device_name_clean"] = str(device_name).strip()

        # ===================================================================
        # 11. Delivery Date Validation - REMOVED (no longer required)
        # ===================================================================
        # NOTE: activation_start_date is now calculated as:
        #       enrollment_ts + 2 business days
        # No delivery_date field in the CSV

        # ===================================================================
        # 12. Enrollment Status Validation and Normalization with Flexible Mapping
        # ===================================================================
        # FIX: Accept both present tense (ENROLL) and past tense (enrolled) forms
        # CSV may have "enrolled", "ENROLL", "Enrolled", etc. - all should map to "ENROLL"
        enrollment_status_mapping = {
            # Present tense forms
            "ENROLL": "ENROLL",
            "UPDATE": "UPDATE",
            "UNENROLL": "UNENROLL",

            # Past tense forms (common in operational CSV files)
            "ENROLLED": "ENROLL",
            "UPDATED": "UPDATE",
            "UNENROLLED": "UNENROLL"
        }

        enrollment_status_raw = str(row.get("enrollment_status", "")).strip()
        if enrollment_status_raw:
            enrollment_status_upper = enrollment_status_raw.upper()  # Case-insensitive

            if enrollment_status_upper in enrollment_status_mapping:
                # Valid input - use mapped normalized value
                df.at[idx, "enrollment_status"] = enrollment_status_mapping[enrollment_status_upper]
                logger.debug(
                    f"[VALIDATION] Row {idx+1}: Mapped enrollment_status "
                    f"'{enrollment_status_raw}' → '{enrollment_status_mapping[enrollment_status_upper]}'"
                )
            else:
                # Invalid input - add error and default to ENROLL
                row_errors.append(
                    f"Invalid enrollment_status: '{enrollment_status_raw}'. "
                    f"Must be one of: enrolled/ENROLL, updated/UPDATE, unenrolled/UNENROLL (case-insensitive)"
                )
                df.at[idx, "enrollment_status"] = "ENROLL"
        else:
            # Empty/blank - default to ENROLL
            df.at[idx, "enrollment_status"] = "ENROLL"

        # ===================================================================
        # 13. Customer Type Validation - REMOVED (not in actual CSV)
        # ===================================================================
        # NOTE: customer_type field does not exist in the actual CSV format
        # All members are treated as DTC by default

        # ===================================================================
        # 14. is_device_callable Boolean Conversion (with inference)
        # ===================================================================
        is_callable = row.get("is_device_callable", "")
        device_phone = row.get("device_phone_number", "")

        if is_callable and str(is_callable).strip():
            # Explicit value provided - use it
            callable_str = str(is_callable).strip().upper()
            if callable_str in ["Y", "YES", "1", "TRUE"]:
                df.at[idx, "is_device_callable_clean"] = 1
            elif callable_str in ["N", "NO", "0", "FALSE"]:
                df.at[idx, "is_device_callable_clean"] = 0
            else:
                row_errors.append(f"Invalid is_device_callable: '{is_callable}' (must be Y/N)")
        else:
            # No explicit value - infer from device_phone_number
            if device_phone and str(device_phone).strip():
                df.at[idx, "is_device_callable_clean"] = 1  # TRUE if phone exists
                logger.debug(
                    f"Row {idx}: Inferred is_device_callable=TRUE (device has phone number)"
                )
            else:
                df.at[idx, "is_device_callable_clean"] = 0  # FALSE if no phone
                logger.debug(f"Row {idx}: Inferred is_device_callable=FALSE (no device phone)")

        # ===================================================================
        # Set Validation Status
        # ===================================================================
        if row_errors:
            df.at[idx, "validation_status"] = "VALIDATION_ERROR"
            df.at[idx, "error_message"] = "; ".join(row_errors)
            df.at[idx, "error_details"] = "\n".join(row_errors)
            validation_errors_count += 1

            # Log detailed error for this row
            logger.warning(f"⚠️ [VALIDATION] Row {idx + 1} validation errors:")
            for error in row_errors:
                logger.warning(f"  - {error}")
        else:
            df.at[idx, "validation_status"] = "VALIDATED"
            df.at[idx, "error_message"] = ""

    # ===================================================================
    # Calculate Error Rate and Check Threshold
    # ===================================================================
    total_rows = len(df)
    error_rate = (validation_errors_count / total_rows * 100) if total_rows > 0 else 0

    logger.info(
        f"📊 [VALIDATION] Validation complete: "
        f"{validation_errors_count}/{total_rows} errors ({error_rate:.1f}%)"
    )

    # Log summary of all errors if any exist
    if validation_errors_count > 0:
        logger.warning("📋 [VALIDATION] Summary of all validation errors:")
        error_rows = df[df["validation_status"] == "VALIDATION_ERROR"]
        for idx, row in error_rows.iterrows():
            logger.warning(f"  Row {idx + 1}: {row['error_message']}")

    if error_rate > context.error_threshold_pct:
        logger.error(
            f"❌ [VALIDATION] Error rate {error_rate:.1f}% exceeds threshold "
            f"{context.error_threshold_pct}%"
        )

    return df


# ============================================================================
# PHASE 1: EXTRACT
# ============================================================================


def extract(context: ProcessingContext) -> Tuple[Optional[pd.DataFrame], ProcessingResult]:
    """
    Phase 1: Extract CSV file from blob storage

    Steps:
    1. Download CSV from landing/ folder
    2. Parse into DataFrame
    3. Add metadata columns (file_batch_id, row_number, timestamps)
    4. Validate structure with Pandera schema
    5. Move file to staging/ folder

    Args:
        context: Processing context

    Returns:
        (DataFrame, ProcessingResult)
    """
    logger.info(f"📥 [EXTRACT] Starting Phase 1: Extract for {context.source_filename}")

    try:
        # Add diagnostic logging
        logger.info(f"📥 [EXTRACT] context.blob_content is None: {context.blob_content is None}")
        logger.info(f"📥 [EXTRACT] context.blob_content size: {len(context.blob_content) if context.blob_content else 'N/A'}")

        # Load CSV data
        if context.blob_content:
            # Operations flow: Load from blob content bytes
            logger.info(
                f"📥 [EXTRACT] Loading CSV from blob content ({len(context.blob_content)} bytes)"
            )
            import io

            df = pd.read_csv(io.BytesIO(context.blob_content), dtype=str, keep_default_na=False)
            logger.info(
                f"✅ [EXTRACT] CSV loaded from blob content: {len(df)} rows, {len(df.columns)} columns"
            )
        else:
            # For Operations flow, blob_content should ALWAYS be provided
            # The file has already been moved from landing/ to staging/ by this point
            # Attempting to download from landing/ will cause BlobNotFound error
            error_msg = (
                "blob_content is required for Device Activation processing. "
                "File has already been moved from landing folder. "
                "Please ensure blob_content is passed from blob trigger."
            )
            logger.error(f"❌ [EXTRACT] {error_msg}")
            raise ValueError(error_msg)

        # ===================================================================
        # STEP 1: Pandera validation (on ORIGINAL columns before mapping)
        # ===================================================================
        schema = get_device_activation_schema()
        if schema is not None:
            try:
                schema.validate(df, lazy=True)
                logger.info("✅ [EXTRACT] Pandera schema validation passed")
            except Exception as e:
                logger.warning(f"⚠️ [EXTRACT] Pandera validation errors (continuing): {e}")

        # ===================================================================
        # STEP 2: Column Mapping for Operations Campaigns (member_ prefix)
        # ===================================================================
        # Map CSV columns with 'member_' prefix to staging table column names
        # This supports Operations campaigns (Medicaid, DTC/MA) that use different column naming
        column_mapping = {
            "member_first_name": "first_name",
            "member_last_name": "last_name",
            "member_phone_number": "primary_phone",
            "member_timezone": "timezone",
            "member_dob": "dob",
            "member_email": "email",
            "member_address_street": "service_address",
            "member_address_city": "city",
            "member_address_state": "state",
            "member_address_zip": "zip",
            "member_brand": "brand",
        }

        # Check if any member_ columns exist (indicates Operations campaign CSV)
        has_member_prefix = any(col in df.columns for col in column_mapping.keys())

        if has_member_prefix:
            logger.info("📋 [EXTRACT] Operations campaign CSV detected (member_ prefix columns)")

            # Rename columns if they exist in CSV
            columns_to_rename = {
                old: new for old, new in column_mapping.items() if old in df.columns
            }
            if columns_to_rename:
                df.rename(columns=columns_to_rename, inplace=True)
                logger.info(
                    f"✅ [EXTRACT] Mapped {len(columns_to_rename)} member_ columns to staging columns"
                )

            # Special handling for powersaver_mode → battery_status
            if "powersaver_mode" in df.columns:
                df["battery_status"] = df["powersaver_mode"]
                df.drop(columns=["powersaver_mode"], inplace=True)
                logger.info("✅ [EXTRACT] Mapped powersaver_mode → battery_status")

            # Special handling for fall_detection → fall_detection_status
            if "fall_detection" in df.columns:
                df["fall_detection_status"] = df["fall_detection"]
                df.drop(columns=["fall_detection"], inplace=True)
                logger.info("✅ [EXTRACT] Mapped fall_detection → fall_detection_status")

            # Add member_address_country if not present (default to 'US')
            if "member_address_country" in df.columns:
                df["address_country"] = df["member_address_country"]
                logger.info("✅ [EXTRACT] Mapped member_address_country → address_country")
            elif "address_country" not in df.columns:
                df["address_country"] = "US"
                logger.info("✅ [EXTRACT] Added default address_country = 'US'")

            logger.info(
                f"📋 [EXTRACT] Column mapping complete - final column count: {len(df.columns)}"
            )

        # Add metadata columns
        df["file_batch_id"] = context.file_batch_id
        df["row_number_in_file"] = range(1, len(df) + 1)
        df["uploaded_by_user"] = context.uploaded_by_user
        df["uploaded_ts"] = datetime.now(timezone.utc)
        df["processing_status"] = "PENDING"

        # Move file to staging
        try:
            move_blob(context.source_filename, "landing", "staging", context.container_name)
            logger.info(f"✅ [EXTRACT] Moved {context.source_filename} to staging/")
        except Exception as e:
            logger.warning(f"⚠️ [EXTRACT] Could not move file to staging: {e}")

        return (
            df,
            ProcessingResult(
                success=True,
                message=f"Extracted {len(df)} rows",
                details={"row_count": len(df), "column_count": len(df.columns)},
            ),
        )

    except Exception as e:
        logger.error(f"❌ [EXTRACT] Error in extract phase: {e}", exc_info=True)
        return (None, ProcessingResult(success=False, message=f"Extract failed: {str(e)}", error=e))


# ============================================================================
# PHASE 2: LOAD TO STAGING
# ============================================================================


def load_to_staging(df: pd.DataFrame, context: ProcessingContext) -> ProcessingResult:
    """
    Phase 2: Load data to staging table

    Steps:
    1. Validate and cleanse data (row-by-row validation)
    2. Check error threshold
    3. Filter to VALIDATED rows
    4. Bulk INSERT into stg_device_activation_delta

    Args:
        df: DataFrame to load
        context: Processing context

    Returns:
        ProcessingResult
    """
    logger.info("💾 [LOAD-STAGING] Starting Phase 2: Load to Staging")

    try:
        # Step 1: Validate and cleanse
        logger.info(f"💾 [LOAD-STAGING] Validating {len(df)} rows...")
        df_validated = validate_and_cleanse_data_before_insert(df, context)

        # Step 2: Check error threshold
        total_rows = len(df_validated)
        error_rows = len(df_validated[df_validated["validation_status"] == "VALIDATION_ERROR"])
        error_rate = (error_rows / total_rows * 100) if total_rows > 0 else 0

        if error_rate > context.error_threshold_pct:
            return ProcessingResult(
                success=False,
                message=f"Error rate {error_rate:.1f}% exceeds threshold {context.error_threshold_pct}%",
                details={
                    "total_rows": total_rows,
                    "error_rows": error_rows,
                    "error_rate": error_rate,
                },
            )

        # Step 3: Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 4: Insert all rows (including errors for tracking)
        # Updated to match 27-column CSV format
        insert_query = """
        INSERT INTO engage360_stg.stg_device_activation_delta (
            file_batch_id, row_number_in_file, uploaded_by_user, uploaded_ts,
            processing_status, validation_status, error_message,
            partner_name, campaign_name_source,
            salesforce_account_id, salesforce_account_number, org_id,
            first_name, last_name, primary_phone, email,
            service_address, city, state, zip, address_country,
            dob, timezone, language_pref,
            member_brand,
            device_udi, device_name, brand,
            device_phone_number, is_device_callable,
            fall_detection_status, battery_status,
            campaign_parameters, monitoring_system_id,
            enrollment_status, unenrollment_reason
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s,
            %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s
        )
        """

        inserted_count = 0
        for idx, row in df_validated.iterrows():
            try:
                cursor.execute(
                    insert_query,
                    (
                        context.file_batch_id,
                        row["row_number_in_file"],
                        context.uploaded_by_user,
                        datetime.now(timezone.utc),
                        row["processing_status"],
                        row["validation_status"],
                        row.get("error_message", ""),
                        # Campaign metadata
                        row.get("partner_name", "Medical Guardian"),
                        row.get("campaign_name_source", ""),
                        # Member identity
                        row.get("salesforce_account_id", ""),
                        row.get("salesforce_account_number", ""),
                        row.get("org_id"),  # NEW: org_id from partner lookup
                        row.get("first_name_clean", ""),
                        row.get("last_name_clean", ""),
                        row.get("primary_phone_clean", ""),
                        row.get("email", ""),  # Fixed: was "member_email"
                        # Address (combined)
                        row.get("service_address_clean", ""),
                        row.get("city", ""),  # Fixed: was "member_address_city"
                        row.get("state", ""),  # Fixed: was "member_address_state"
                        row.get("zip", ""),  # Fixed: was "member_address_zip"
                        row.get("address_country", "US"),  # FIX ISSUE #11: Add address_country
                        # Demographics
                        row.get("dob_clean", None),
                        row.get("timezone_clean", ""),
                        row.get("language_pref_clean", "EN"),
                        # Member brand
                        row.get("brand_clean", ""),  # member_brand for staging.member_brand
                        # Device info
                        row.get("device_udi", ""),
                        row.get("device_name", ""),
                        row.get("device_name_clean", ""),  # device brand for staging.brand
                        row.get("device_phone_clean", ""),
                        row.get("is_device_callable_clean", None),
                        # Device status (converted values)
                        row.get("fall_detection_status_clean", ""),
                        row.get("battery_status_clean", ""),
                        # Campaign tracking (FIX ISSUE #4: Convert empty strings to NULL)
                        row.get("campaign_parameters", "") or None,
                        row.get("monitoring_system_id", "") or None,
                        row.get("enrollment_status", "ENROLL"),
                        row.get("unenrollment_reason", "") or None,
                    ),
                )
                inserted_count += 1
            except Exception as e:
                logger.error(f"❌ [LOAD-STAGING] Error inserting row {idx}: {e}")

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"✅ [LOAD-STAGING] Inserted {inserted_count}/{total_rows} rows to staging")

        return ProcessingResult(
            success=True,
            message=f"Loaded {inserted_count} rows to staging",
            details={
                "total_rows": total_rows,
                "inserted_rows": inserted_count,
                "validated_rows": total_rows - error_rows,
                "error_rows": error_rows,
                "error_rate": error_rate,
            },
        )

    except Exception as e:
        logger.error(f"❌ [LOAD-STAGING] Error in load_to_staging: {e}", exc_info=True)
        return ProcessingResult(success=False, message=f"Load to staging failed: {str(e)}", error=e)


# ============================================================================
# PHASE 3: VALIDATE DATA (SQL CLEANSING)
# ============================================================================


def validate_data(context: ProcessingContext) -> ProcessingResult:
    """
    Phase 3: SQL-based data validation and cleansing

    Steps:
    1. UPDATE staging with SQL cleansing functions
    2. Lookup org_id from partner_name
    3. Apply standardization functions
    4. Mark rows as VALIDATED

    Args:
        context: Processing context

    Returns:
        ProcessingResult
    """
    logger.info("🔍 [VALIDATE] Starting Phase 3: SQL Validation")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Update org_id from partner_name
        update_org_query = """
        UPDATE stg
        SET stg.org_id = o.org_id
        FROM engage360_stg.stg_device_activation_delta stg
        INNER JOIN engage360.orgs o ON LTRIM(RTRIM(stg.partner_name)) = o.org_name
        WHERE stg.file_batch_id = %s
        """
        cursor.execute(update_org_query, (context.file_batch_id,))
        logger.info("✅ [VALIDATE] Updated org_id from partner_name")

        conn.commit()
        cursor.close()
        conn.close()

        return ProcessingResult(success=True, message="SQL validation complete")

    except Exception as e:
        logger.error(f"❌ [VALIDATE] Error in validate_data: {e}", exc_info=True)
        return ProcessingResult(success=False, message=f"Validation failed: {str(e)}", error=e)


# ============================================================================
# PHASE 4: TRANSFORM & LOAD CORE TABLES
# ============================================================================


def transform_and_load_core(context: ProcessingContext) -> ProcessingResult:
    """
    Phase 4: Transform and load data into core tables

    Steps:
    1. Get device_activation campaign_id
    2. MERGE INTO members (use salesforce_account_id + salesforce_account_number)
    3. MERGE INTO member_devices (add brand, device status fields)
    4. INSERT INTO member_campaign_enrollments_enhanced
       - activation_start_date = enrollment_ts date (SAME DAY - first call Day 0)
       - Calculate campaign_end_date = activation_start_date + 90 days
    5. Mark staging as PROCESSED

    Args:
        context: Processing context

    Returns:
        ProcessingResult
    """
    logger.info("🔄 [TRANSFORM] Starting Phase 4: Transform & Load Core Tables")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 1: Get or validate campaign_id
        if context.campaign_id:
            # Operations flow: Use explicit campaign_id
            campaign_id = context.campaign_id
            logger.info(f"✅ [TRANSFORM] Using explicit campaign_id: {campaign_id}")
            if context.campaign_name:
                logger.info(f"   Campaign name: {context.campaign_name}")

            # Validate campaign exists and is Active
            validation_query = """
            SELECT campaign_id, name, campaign_type, status
            FROM engage360.campaigns_enhanced
            WHERE campaign_id = %s
            """
            cursor.execute(validation_query, (campaign_id,))
            campaign_result = cursor.fetchone()

            if not campaign_result:
                return ProcessingResult(
                    success=False, message=f"Campaign {campaign_id} not found in database"
                )

            db_name, db_type, db_status = campaign_result[1], campaign_result[2], campaign_result[3]
            if db_status != "Active":
                return ProcessingResult(
                    success=False,
                    message=f"Campaign {campaign_id} is not Active (status: {db_status})",
                )

            logger.info("✅ [TRANSFORM] Campaign validation passed")
            logger.info(f"   Database name: {db_name}")
            logger.info(f"   Campaign type: {db_type}")
            logger.info(f"   Status: {db_status}")

        else:
            # Legacy flow: Auto-discover campaign by type
            logger.info("🔍 [TRANSFORM] Auto-discovering Device Activation campaign")
            legacy_query = """
            SELECT campaign_id, name, campaign_type
            FROM engage360.campaigns_enhanced
            WHERE campaign_type IN ('Operations', 'Device Activation', 'DeviceActivation')
            AND status = 'Active'
            """
            cursor.execute(legacy_query)
            campaign_results = cursor.fetchall()

            if not campaign_results:
                return ProcessingResult(
                    success=False,
                    message="No active Device Activation campaign found (searched campaign_type: 'Operations', 'Device Activation', 'DeviceActivation')",
                )

            if len(campaign_results) > 1:
                logger.warning(
                    f"⚠️ [TRANSFORM] Multiple Device Activation campaigns found ({len(campaign_results)})"
                )
                logger.warning(
                    "   Using first campaign. Consider using explicit campaign_id parameter."
                )
                for idx, row in enumerate(campaign_results):
                    logger.warning(f"   Campaign {idx+1}: {row[0]} - {row[1]} (type: {row[2]})")

            campaign_id = campaign_results[0][0]
            logger.info(f"✅ [TRANSFORM] Auto-discovered campaign_id: {campaign_id}")
            logger.info(f"   Campaign name: {campaign_results[0][1]}")
            logger.info(f"   Campaign type: {campaign_results[0][2]}")

        # Step 2: MERGE INTO members
        merge_members_query = """
        MERGE engage360.members AS tgt
        USING (
            SELECT DISTINCT
                stg.org_id,
                stg.salesforce_account_id,
                stg.salesforce_account_number,
                stg.first_name,
                stg.last_name,
                stg.primary_phone,
                stg.email,
                stg.service_address,
                stg.city AS address_city,
                stg.state AS address_state,
                stg.zip AS address_zip,
                ISNULL(stg.address_country, 'US') AS address_country,
                stg.dob,
                stg.timezone,
                stg.language_pref,
                stg.member_brand
            FROM engage360_stg.stg_device_activation_delta stg
            WHERE stg.file_batch_id = %s
              AND stg.validation_status = 'VALIDATED'
              AND stg.org_id IS NOT NULL
        ) AS src
        ON (tgt.org_id = src.org_id AND tgt.salesforce_account_number = src.salesforce_account_number)
        WHEN MATCHED THEN
            UPDATE SET
                salesforce_account_id = ISNULL(src.salesforce_account_id, tgt.salesforce_account_id),
                first_name = ISNULL(src.first_name, tgt.first_name),
                last_name = ISNULL(src.last_name, tgt.last_name),
                primary_phone = ISNULL(src.primary_phone, tgt.primary_phone),
                email = ISNULL(src.email, tgt.email),
                address_street = ISNULL(src.service_address, tgt.address_street),
                address_city = ISNULL(src.address_city, tgt.address_city),
                address_state = ISNULL(src.address_state, tgt.address_state),
                address_zip = ISNULL(src.address_zip, tgt.address_zip),
                address_country = ISNULL(src.address_country, tgt.address_country),
                dob = ISNULL(src.dob, tgt.dob),
                timezone = ISNULL(src.timezone, tgt.timezone),
                language_pref = ISNULL(src.language_pref, tgt.language_pref),
                member_brand = ISNULL(src.member_brand, tgt.member_brand)
        WHEN NOT MATCHED THEN
            INSERT (
                member_id, org_id, salesforce_account_id, salesforce_account_number,
                first_name, last_name, primary_phone, email,
                address_street, address_city, address_state, address_zip, address_country,
                dob, timezone, language_pref,
                member_brand,
                created_ts
            )
            VALUES (
                NEWID(), src.org_id, src.salesforce_account_id, src.salesforce_account_number,
                src.first_name, src.last_name, src.primary_phone, src.email,
                src.service_address, src.address_city, src.address_state, src.address_zip, src.address_country,
                src.dob, src.timezone, src.language_pref,
                src.member_brand,
                SYSDATETIMEOFFSET()
            );
        """
        cursor.execute(merge_members_query, (context.file_batch_id,))
        logger.info("✅ [TRANSFORM] MERGE INTO members complete")

        # Step 3: MERGE INTO member_devices
        # NOTE: brand, battery_status, fall_detection_status, updated_ts columns
        # NOTE: added via migration: database/add_device_activation_columns_to_member_devices.sql
        merge_devices_query = """
        MERGE engage360.member_devices AS tgt
        USING (
            SELECT DISTINCT
                stg.device_udi,
                m.member_id,
                stg.device_phone_number,
                stg.is_device_callable,
                stg.device_name,
                stg.brand,
                stg.fall_detection_status,
                stg.battery_status
            FROM engage360_stg.stg_device_activation_delta stg
            INNER JOIN engage360.members m
                ON m.org_id = stg.org_id
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.validation_status = 'VALIDATED'
              AND stg.device_udi IS NOT NULL
        ) AS src
        ON tgt.device_id = src.device_udi
        WHEN MATCHED THEN
            UPDATE SET
                brand = ISNULL(src.brand, tgt.brand),
                fall_detection_status = ISNULL(src.fall_detection_status, tgt.fall_detection_status),
                battery_status = ISNULL(src.battery_status, tgt.battery_status),
                device_phone_number = ISNULL(src.device_phone_number, tgt.device_phone_number),
                is_device_callable = ISNULL(src.is_device_callable, tgt.is_device_callable),
                device_name = ISNULL(src.device_name, tgt.device_name),
                updated_ts = SYSDATETIMEOFFSET()
        WHEN NOT MATCHED THEN
            INSERT (
                device_id, member_id, device_name, brand,
                fall_detection_status, battery_status,
                device_phone_number, is_device_callable,
                created_ts
            )
            VALUES (
                src.device_udi, src.member_id, src.device_name, src.brand,
                src.fall_detection_status, src.battery_status,
                src.device_phone_number, src.is_device_callable,
                SYSDATETIMEOFFSET()
            );
        """
        cursor.execute(merge_devices_query, (context.file_batch_id,))
        logger.info("✅ [TRANSFORM] MERGE INTO member_devices complete")

        # Step 4: INSERT INTO member_campaign_enrollments_enhanced
        # Note: activation_start_date and campaign_end_date calculated in Python
        # NEW LOGIC: activation_start_date = enrollment_ts + 2 business days

        # First, get staging data (NO delivery_date - using enrollment_ts instead)
        get_staging_query = """
        SELECT DISTINCT
            m.member_id,
            stg.enrollment_status
        FROM engage360_stg.stg_device_activation_delta stg
        INNER JOIN engage360.members m
            ON m.org_id = stg.org_id
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.validation_status = 'VALIDATED'
          AND stg.enrollment_status = 'ENROLL'
        """
        cursor.execute(get_staging_query, (context.file_batch_id,))
        staging_rows = cursor.fetchall()

        # Update processing status from PENDING to TRANSFORMING
        # This is critical: The MERGE query at line 1565 filters for 'TRANSFORMING' status
        # Without this update, MERGE finds 0 rows → 0 enrollments
        status_update_query = """
        UPDATE engage360_stg.stg_device_activation_delta
        SET processing_status = 'TRANSFORMING'
        WHERE file_batch_id = %s
          AND processing_status = 'PENDING'
        """

        logger.info(f"🔄 [TRANSFORM] Updating rows to TRANSFORMING status for batch {context.file_batch_id}")
        cursor.execute(status_update_query, (context.file_batch_id,))
        logger.info(f"✅ [TRANSFORM] Status updated to TRANSFORMING")

        logger.info(f"📊 [TRANSFORM] Processing {len(staging_rows)} enrollments")

        # Get current timestamp as enrollment_ts
        enrollment_ts = datetime.now(timezone.utc)

        # CORRECTED LOGIC (2025-12-16): activation_start_date = first business day on or after enrollment_ts
        # Files can arrive ANY day (including weekends/holidays)
        # Process data immediately, but delay calls until first business day (Day 0)
        enrollment_date = enrollment_ts.date()

        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date  # Already a business day (Day 0 = same day)
        else:
            # Weekend or holiday - get next business day
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Calculate campaign_end_date = activation_start_date + 90 days
        campaign_end_date = activation_start_date + timedelta(days=90)

        logger.info(
            f"📅 [TRANSFORM] Activation dates for this batch: "
            f"enrollment_ts={enrollment_ts.date()} ({enrollment_ts.strftime('%A')}), "
            f"activation_start={activation_start_date} "
            f"({'SAME DAY' if enrollment_date == activation_start_date else 'NEXT BUSINESS DAY'}), "
            f"campaign_end={campaign_end_date} (activation + 90 days)"
        )

        # MERGE enrollments (UPSERT pattern - handles both INSERT and UPDATE)
        # This allows safe re-processing of files without duplicate key errors
        merge_enrollment_query = """
        MERGE engage360.member_campaign_enrollments_enhanced AS tgt
        USING (
            SELECT
                m.member_id,
                %s AS campaign_id,
                %s AS activation_start_date,
                %s AS campaign_end_date
            FROM engage360_stg.stg_device_activation_delta stg
            JOIN engage360.members m
                ON m.org_id = stg.org_id
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
        ) AS src
        ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id

        WHEN MATCHED THEN
            UPDATE SET
                -- Update activation dates (re-calculated from file upload date)
                activation_start_date = src.activation_start_date,
                campaign_end_date = src.campaign_end_date,

                -- Re-enroll if previously UNENROLLED
                current_status = CASE
                    WHEN tgt.current_status = 'UNENROLLED' THEN 'ENROLLED'
                    ELSE tgt.current_status
                END,

                -- Update enrollment timestamp if re-enrolling
                enrollment_ts = CASE
                    WHEN tgt.current_status = 'UNENROLLED' THEN SYSDATETIMEOFFSET()
                    ELSE tgt.enrollment_ts
                END,

                -- Clear unenrollment reason if re-enrolling
                unenrollment_reason = CASE
                    WHEN tgt.current_status = 'UNENROLLED' THEN NULL
                    ELSE tgt.unenrollment_reason
                END

                -- Keep existing device_activated status (don't reset to 0)
                -- device_activated stays as is (1 = activated, 0 = not activated)

        WHEN NOT MATCHED THEN
            INSERT (
                enrollment_id, member_id, campaign_id, enrollment_ts, current_status,
                activation_start_date, campaign_end_date, device_activated
            )
            VALUES (
                NEWID(),                    -- New UUID only for NEW enrollments
                src.member_id,
                src.campaign_id,
                SYSDATETIMEOFFSET(),        -- enrollment_ts
                'ENROLLED',                 -- current_status
                src.activation_start_date,
                src.campaign_end_date,
                0                           -- device_activated (default: not activated)
            );
        """

        try:
            # Execute MERGE once for ALL members in the batch
            cursor.execute(
                merge_enrollment_query,
                (
                    str(campaign_id),           # Campaign ID
                    activation_start_date,      # activation_start_date
                    campaign_end_date,          # campaign_end_date
                    context.file_batch_id,      # file_batch_id (for WHERE clause)
                ),
            )

            # Get row count (how many enrollments were inserted or updated)
            enrolled_count = cursor.rowcount

            logger.info(f"✅ [TRANSFORM] Enrolled/Updated {enrolled_count} members")

        except Exception as e:
            logger.error(f"❌ [TRANSFORM] Error in enrollment MERGE: {e}")
            raise

        # Step 5: Mark staging as PROCESSED
        update_staging_query = """
        UPDATE engage360_stg.stg_device_activation_delta
        SET processing_status = 'PROCESSED'
        WHERE file_batch_id = %s AND validation_status = 'VALIDATED'
        """
        cursor.execute(update_staging_query, (context.file_batch_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return ProcessingResult(
            success=True,
            message=f"Transformed and loaded {enrolled_count} enrollments",
            details={"enrolled_count": enrolled_count},
        )

    except Exception as e:
        logger.error(f"❌ [TRANSFORM] Error in transform_and_load_core: {e}", exc_info=True)
        return ProcessingResult(success=False, message=f"Transform failed: {str(e)}", error=e)


# ============================================================================
# PHASE 5: AUDIT & LOG
# ============================================================================


def audit_and_log(context: ProcessingContext, details: Dict[str, Any]) -> ProcessingResult:
    """
    Phase 5: Audit and logging

    Steps:
    1. UPDATE file_processing_log
    2. INSERT processing_step_log
    3. Move file to processed/ folder

    Args:
        context: Processing context
        details: Processing details to log

    Returns:
        ProcessingResult
    """
    logger.info("📝 [AUDIT] Starting Phase 5: Audit & Log")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert file processing log
        insert_log_query = """
        INSERT INTO engage360_stg.file_processing_log (
            file_batch_id, source_filename, file_type, uploaded_by_user,
            upload_started_ts, completed_ts, current_status,
            total_records_processed, successful_records, failed_records, enrollments_created,
            error_percentage
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        cursor.execute(
            insert_log_query,
            (
                context.file_batch_id,
                context.source_filename,
                "DEVICE_ACTIVATION",                    # file_type (was workflow_type)
                context.uploaded_by_user,
                datetime.now(timezone.utc),             # upload_started_ts (was upload_ts)
                datetime.now(timezone.utc),             # completed_ts (was processing_end_ts)
                "COMPLETED",                             # current_status (was processing_status)
                details.get("total_rows", 0),           # total_records_processed (was total_rows)
                details.get("validated_rows", 0),       # successful_records (was validated_rows)
                details.get("error_rows", 0),           # failed_records (was error_rows)
                details.get("enrolled_count", 0),       # enrollments_created (was enrolled_rows)
                details.get("error_rate", 0),           # error_percentage (was error_rate_pct)
            ),
        )

        conn.commit()
        cursor.close()
        conn.close()

        # Move file to processed folder
        try:
            handle_blob_movement_with_error_handling(
                context.source_filename, "staging", "processed", context.container_name, logger
            )
        except Exception as e:
            logger.warning(f"⚠️ [AUDIT] Could not move file to processed: {e}")

        return ProcessingResult(success=True, message="Audit complete")

    except Exception as e:
        logger.error(f"❌ [AUDIT] Error in audit_and_log: {e}", exc_info=True)
        return ProcessingResult(success=False, message=f"Audit failed: {str(e)}", error=e)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def process_device_activation_file_complete(
    file_path: str = None,
    blob_name: str = None,
    blob_content: bytes = None,
    campaign_id: str = None,
    campaign_name: str = None,
    connection_string: Optional[str] = None,
    uploaded_by_user: str = "AzureFunction",
    error_threshold_pct: float = 10.0,
    log_level: str = "INFO",
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Complete processing workflow for Device Activation CSV files

    5-Phase ETL Pipeline:
    1. Extract: Download CSV, validate structure
    2. Load to Staging: Row-by-row validation, INSERT to staging
    3. Validate: SQL cleansing, org_id lookup
    4. Transform & Load Core: MERGE members/devices, INSERT enrollments
    5. Audit & Log: File processing log, move to processed

    Args:
        file_path: Path to CSV file (legacy flow - for file-based processing)
        blob_name: Blob path from Azure trigger (Operations flow)
        blob_content: Raw CSV bytes from blob (Operations flow)
        campaign_id: Explicit campaign UUID (Operations flow)
        campaign_name: Campaign display name (Operations flow)
        connection_string: Database connection string (optional, uses Key Vault if None)
        uploaded_by_user: User who uploaded the file
        error_threshold_pct: Error threshold percentage (default 10%)
        log_level: Logging level

    Returns:
        (success, message, details)
    """
    # Setup logging
    logging.basicConfig(level=getattr(logging, log_level.upper()))

    # Validate input: Either (blob_name + blob_content + campaign_id) OR (file_path)
    if blob_name and blob_content:
        # Operations flow - explicit campaign
        if not campaign_id:
            raise ValueError("campaign_id required when using blob_name/blob_content")
        source_filename = blob_name.split("/")[-1]
        file_batch_id = str(uuid.uuid4())
        logger.info(f"🔄 [INIT] Operations flow: blob_name={blob_name}, campaign_id={campaign_id}")
    elif file_path:
        # Legacy flow - auto-discover campaign
        source_filename = Path(file_path).name
        file_batch_id = str(uuid.uuid4())
        campaign_id = None  # Will be looked up in transform phase
        logger.info(f"🔄 [INIT] Legacy flow: file_path={file_path}")
    else:
        raise ValueError(
            "Must provide either (blob_name + blob_content + campaign_id) "
            "or (file_path) parameters"
        )

    logger.info("=" * 80)
    logger.info("🚀 [MAIN] Starting Device Activation File Processing")
    logger.info(f"📄 [MAIN] File: {source_filename}")
    logger.info(f"🆔 [MAIN] Batch ID: {file_batch_id}")
    if campaign_id:
        logger.info(f"🎯 [MAIN] Campaign ID: {campaign_id}")
        if campaign_name:
            logger.info(f"📝 [MAIN] Campaign Name: {campaign_name}")
    logger.info("=" * 80)

    # Create processing context
    context = ProcessingContext(
        file_batch_id=file_batch_id,
        source_filename=source_filename,
        container_name="fs-ops",
        uploaded_by_user=uploaded_by_user,
        error_threshold_pct=error_threshold_pct,
        log_level=log_level,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        blob_content=blob_content,
    )

    processing_details = {}

    try:
        # ====================================================================
        # PHASE 1: EXTRACT
        # ====================================================================
        df, extract_result = extract(context)
        if not extract_result.success:
            return (False, extract_result.message, extract_result.details)

        processing_details.update(extract_result.details)

        # ====================================================================
        # PHASE 2: LOAD TO STAGING
        # ====================================================================
        load_result = load_to_staging(df, context)
        if not load_result.success:
            # Move file to error folder
            try:
                handle_blob_movement_with_error_handling(
                    source_filename, "staging", "error", context.container_name, logger
                )
            except Exception:
                pass
            return (False, load_result.message, load_result.details)

        processing_details.update(load_result.details)

        # ====================================================================
        # PHASE 3: VALIDATE
        # ====================================================================
        validate_result = validate_data(context)
        if not validate_result.success:
            return (False, validate_result.message, validate_result.details)

        # ====================================================================
        # PHASE 4: TRANSFORM & LOAD CORE
        # ====================================================================
        transform_result = transform_and_load_core(context)
        if not transform_result.success:
            return (False, transform_result.message, transform_result.details)

        processing_details.update(transform_result.details)

        # ====================================================================
        # PHASE 5: AUDIT & LOG
        # ====================================================================
        audit_result = audit_and_log(context, processing_details)
        if not audit_result.success:
            logger.warning(
                f"⚠️ [MAIN] Audit failed but processing completed: {audit_result.message}"
            )

        # ====================================================================
        # SUCCESS
        # ====================================================================
        logger.info("=" * 80)
        logger.info("✅ [MAIN] Device Activation File Processing Complete")
        logger.info(f"📊 [MAIN] Total Rows: {processing_details.get('total_rows', 0)}")
        logger.info(f"✅ [MAIN] Validated: {processing_details.get('validated_rows', 0)}")
        logger.info(f"❌ [MAIN] Errors: {processing_details.get('error_rows', 0)}")
        logger.info(f"👥 [MAIN] Enrolled: {processing_details.get('enrolled_count', 0)}")
        logger.info("=" * 80)

        return (
            True,
            f"Successfully processed {source_filename}: {processing_details.get('enrolled_count', 0)} members enrolled",
            processing_details,
        )

    except Exception as e:
        logger.error(f"❌ [MAIN] Unexpected error in processing: {e}", exc_info=True)

        # Try to move file to error folder
        try:
            handle_blob_movement_with_error_handling(
                source_filename, "staging", "error", context.container_name, logger
            )
        except Exception:
            pass

        return (False, f"Processing failed: {str(e)}", {"error": str(e)})


# ============================================================================
# MODULE EXPORT
# ============================================================================

__all__ = [
    "process_device_activation_file_complete",
    "ProcessingContext",
    "ProcessingResult",
]
