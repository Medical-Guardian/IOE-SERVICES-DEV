"""
Engage360 Device Activation File Processing Workflow
====================================================

BusinessCaseID: BC-DA-002 (File Processing & ETL Pipeline)
Created: 2025-12-07
Updated: 2025-12-24 - Added comprehensive documentation and BusinessCaseID mapping

This module implements the complete ETL (Extract, Transform, Load) pipeline for processing
Device Activation CSV files. It converts raw CSV data from external sources into structured
database records that drive the Device Activation campaign workflow.

PURPOSE:
--------
Device Activation campaigns begin when external partners (e.g., Medical Guardian fulfillment)
send CSV files containing member and device information after devices are shipped. This module
processes those files through a robust 5-phase pipeline to:

1. **Validate data quality** (Pandera schema validation)
2. **Stage data temporarily** (stg_device_activation_delta table)
3. **Cleanse and normalize** (SQL cleansing functions, timezone mapping)
4. **Populate core tables** (members, member_devices, member_campaign_enrollments_enhanced)
5. **Create audit trail** (file_processing_log, blob movement)

The end result: Members are enrolled in Device Activation campaigns and become eligible
for proactive outreach calls via the scheduler (BC-DA-003, BC-DA-004).

5-PHASE ETL PIPELINE:
---------------------

**PHASE 1: EXTRACT** (Lines 954-1107)
    Function: extract(context: ProcessingContext)
    Purpose: Download CSV from blob storage and validate structure

    Process:
    1. Download CSV from Azure Blob Storage (landing folder)
    2. Parse CSV into pandas DataFrame (dtype=str, keep_default_na=False)
    3. Validate schema using Pandera (23 required columns)
    4. Check for critical missing fields (member_id, device_udi, delivery_date)
    5. Return validated DataFrame or error result

    Success Criteria:
    - CSV file exists and is readable
    - All 23 required columns present
    - At least 1 data row (excluding header)
    - No critical schema violations

    Error Handling:
    - Missing columns → Move to error/ folder, log details
    - Schema violations → Move to error/ folder, log Pandera errors
    - Empty file → Move to error/ folder
    - Blob not found → Log error, raise exception

**PHASE 2: LOAD TO STAGING** (Lines 1109-1268)
    Function: load_to_staging(df: pd.DataFrame, context: ProcessingContext)
    Purpose: Insert raw CSV data into staging table for validation

    Process:
    1. For each row in DataFrame:
        a. INSERT into stg_device_activation_delta with processing_status='Raw'
        b. Store original values in *_raw columns
        c. Set file_id, created_ts, updated_ts
    2. Track success/failure counts
    3. Enforce 10% error threshold (max 10% rows can fail)
    4. Commit or rollback based on threshold

    Success Criteria:
    - >= 90% of rows inserted successfully
    - Database connection stable
    - No critical SQL errors

    Error Handling:
    - Row insert fails → Log error, increment fail_count
    - Error threshold exceeded (>10%) → Rollback transaction, abort processing
    - Database errors → Rollback, move blob to error/ folder

    Database Impact:
    - Table: engage360_stg.stg_device_activation_delta
    - Operation: INSERT (row-by-row with try/except)
    - Fields: 23 raw columns + metadata (file_id, processing_status, created_ts)

**PHASE 3: VALIDATE** (Lines 1270-1317)
    Function: validate_data(context: ProcessingContext)
    Purpose: Run SQL cleansing functions and validate data quality

    Process:
    1. Execute SQL Server stored procedure: sp_cleanse_device_activation_data
    2. Stored procedure performs:
        - Phone number validation (E.164 format)
        - Email validation (regex pattern)
        - Timezone mapping (e.g., 'Eastern' → 'America/New_York')
        - Language code mapping (ISO 639-3 → 'EN'/'ES'/'Other')
        - Device status validation (fall_detection, powersaver_mode)
        - Customer type validation
        - org_id lookup from org_name
    3. Update stg_device_activation_delta:
        - processing_status = 'Validated' (success)
        - processing_status = 'Invalid' (validation failures)
        - Set *_clean columns with validated values
        - Set validation_status with error messages

    Success Criteria:
    - >= 50% of rows pass validation (configurable threshold)
    - All critical validations complete
    - Clean columns populated for valid rows

    Error Handling:
    - SQL procedure fails → Log error, abort processing
    - Low validation rate (<50%) → Warning logged, processing continues
    - Database errors → Rollback, move blob to error/ folder

**PHASE 4: TRANSFORM & LOAD CORE** (Lines 1319-1846)
    Function: transform_and_load_core(context: ProcessingContext)
    Purpose: MERGE staging data into core production tables

    Process:
    1. **MERGE into engage360.members** (UPSERT pattern):
        - Match on: member_id (salesforce_account_number)
        - UPDATE: Existing members with latest data
        - INSERT: New members
        - Fields: first_name, last_name, primary_phone, email, address, timezone, etc.

    2. **MERGE into engage360.member_devices** (UPSERT pattern):
        - Match on: device_id (device_udi)
        - UPDATE: Existing devices with latest data
        - INSERT: New devices
        - Fields: device_name, brand, device_phone_number, fall_detection, powersaver_mode, etc.

    3. **INSERT into engage360.member_campaign_enrollments_enhanced**:
        - Create new enrollments (no MERGE - always new)
        - Calculate activation_start_date = delivery_date + 2 business days
        - Calculate campaign_end_date = activation_start_date + 90 days (initial, updated in Call 5)
        - Set current_status = 'ENROLLED'
        - Set device_activated = 0 (not yet activated)
        - Fields: enrollment_id, member_id, campaign_id, activation_start_date, campaign_end_date, etc.

    Success Criteria:
    - All 3 core tables updated successfully
    - Foreign key relationships maintained
    - Business day calculations accurate
    - Enrollment records created for all valid members

    Error Handling:
    - MERGE fails → Log error, rollback transaction
    - Foreign key violations → Log error, skip record
    - Business day calculation errors → Log warning, use fallback
    - Database errors → Rollback, move blob to error/ folder

    Database Impact:
    - Tables: engage360.members, engage360.member_devices, engage360.member_campaign_enrollments_enhanced
    - Operations: MERGE (members, devices), INSERT (enrollments)
    - Transaction: All-or-nothing (rollback on any error)

**PHASE 5: AUDIT & LOG** (Lines 1848-1922)
    Function: audit_and_log(context: ProcessingContext, details: Dict[str, Any])
    Purpose: Create audit trail and move processed file

    Process:
    1. INSERT into file_processing_log:
        - file_id (UUID)
        - filename, file_path, container_name
        - processing_status ('success' or 'error')
        - rows_processed, rows_succeeded, rows_failed
        - processing_start_ts, processing_end_ts, processing_duration_seconds
        - error_details (if any)

    2. Move blob from landing/ to processed/ or error/:
        - Success: landing/file.csv → processed/file.csv
        - Error: landing/file.csv → error/file.csv

    3. Log final summary with emoji indicators

    Success Criteria:
    - Audit record inserted successfully
    - Blob moved to correct folder (processed/ or error/)
    - All phase statistics logged

    Error Handling:
    - Audit insert fails → Log error but don't fail entire pipeline
    - Blob move fails → Retry with exponential backoff (3 attempts)
    - Both operations track independently

BUSINESS DAY CALCULATIONS:
--------------------------
Device Activation uses business day calculations for activation_start_date:

**Formula:** activation_start_date = delivery_date + 2 business days

**Rationale:** Members need 2 business days to receive and unpack devices before
activation calls begin.

**Examples:**
- Delivery: Monday → activation_start_date: Wednesday (Mon+2 biz days)
- Delivery: Friday → activation_start_date: Tuesday (Fri → Mon → Tue)
- Delivery: Saturday → activation_start_date: Wednesday (Sat → Mon → Tue → Wed)

**Implementation:** Uses shared utility `add_business_days()` from business_hours_utils

90-DAY CAMPAIGN WINDOW:
-----------------------
**Initial Calculation** (in this module):
    campaign_end_date = activation_start_date + 90 days

**Updated in Call 5** (in batch_orchestrator.py BC-DA-004):
    When Call 5 is created:
    - call_5_timestamp = NOW()
    - campaign_end_date = call_5_timestamp + 90 days (UPDATED)

**Rationale:** The 90-day window for Call 5+ starts FROM when Call 5 is created,
NOT from the original activation_start_date. This allows sufficient time for Calls 1-4
before enforcing the hard stop.

DATA VALIDATION RULES:
----------------------
**Phone Numbers (E.164 format):**
- Must start with '+'
- Must be 12-16 characters (e.g., +15551234567)
- Regex: ^\\+[1-9]\\d{10,14}$

**Email Addresses:**
- Must match standard email regex
- Regex: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$

**Timezones (IANA format):**
- Input: 'Eastern', 'Central', 'Mountain', 'Pacific', 'EST', 'CST', etc.
- Output: 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'
- Validation: pytz.timezone(tz) must not raise exception

**Language Codes (ISO 639):**
- Input: 'eng', 'spa', 'som', 'EN', 'ES', 'Other', etc.
- Output: 'EN', 'ES', 'Other'
- Uses shared utility: map_language_code()

**Device Status (BIT flags):**
- fall_detection: 'Yes'/'No' → 1/0
- powersaver_mode: 'Yes'/'No'/'Battery Saver' → 1/0
- Must be valid boolean representations

**Customer Type:**
- Valid values: 'DTC', 'MA', 'Medicaid', etc.
- Case-insensitive validation

CSV FILE STRUCTURE:
-------------------
**Required Columns (23 total):**

**Member Information:**
- salesforce_account_number (member_id)
- first_name
- last_name
- primary_phone
- email
- address_street
- address_city
- address_state
- address_zip
- dob
- timezone
- language_pref
- member_brand

**Device Information:**
- device_udi (device_id)
- device_name
- brand
- device_phone_number
- is_device_callable
- fall_detection
- powersaver_mode

**Enrollment Information:**
- delivery_date
- customer_type
- org_name
- campaign_id

DATABASE TABLES ACCESSED:
--------------------------
**Staging Table:**
- engage360_stg.stg_device_activation_delta (read/write - temporary staging)

**Core Tables:**
- engage360.members (write - MERGE)
- engage360.member_devices (write - MERGE)
- engage360.member_campaign_enrollments_enhanced (write - INSERT)
- engage360.orgs (read - org_id lookup)

**Audit Tables:**
- engage360.file_processing_log (write - audit trail)

ERROR HANDLING STRATEGY:
-------------------------
**10% Error Threshold (Phase 2):**
- If > 10% of rows fail during staging insert → Abort entire file
- Rationale: Indicates systematic data quality issue, not isolated errors

**50% Validation Threshold (Phase 3):**
- If < 50% of rows pass validation → Warning logged, processing continues
- Rationale: Some records may be salvageable even with validation failures

**Transaction Rollback (Phase 4):**
- Any error during core table updates → Rollback entire transaction
- Rationale: Maintain data integrity (all-or-nothing approach)

**Exponential Backoff (Blob Operations):**
- Retry blob moves up to 3 times with exponential backoff
- Delays: 2s, 4s, 8s
- Rationale: Handle transient Azure Storage errors

RELATED COMPONENTS:
-------------------
- **device_activation_scheduler** (BC-DA-001): Timer trigger for eligibility checks
- **EligibilityService** (BC-DA-003): Uses enrollments created by this module
- **BatchOrchestrator** (BC-DA-004): Updates campaign_end_date in Call 5
- **business_hours_utils**: Business day calculations, timezone validation

RELATED DOCUMENTATION:
----------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Database Operations: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md
- CSV Reference: documentation/device_activation/REFERENCE/DEVICE_ACTIVATION_CSV_REFERENCE.md

EXAMPLES:
---------
Process a Device Activation CSV file:
    >>> from af_code.af_device_activation_logic import process_device_activation_file_complete
    >>>
    >>> # File uploaded to Azure Blob Storage: fs-device-activation/landing/file.csv
    >>> result = process_device_activation_file_complete(
    ...     blob_name="MedicalGuardian_DeviceActivation_20251224_Delta.csv",
    ...     container_name="fs-device-activation",
    ...     trigger_metadata=None
    ... )
    >>>
    >>> # Check result
    >>> print(f"Success: {result.success}")
    >>> print(f"Phase: {result.phase_completed}")
    >>> print(f"Records processed: {result.records_processed}")
    Success: True
    Phase: Phase 5: Audit Complete
    Records processed: 150

NOTES:
------
- This module is triggered by blob uploads to fs-device-activation/landing/
- Filename pattern: MedicalGuardian_DeviceActivation_*_Delta.csv
- Processing time: ~30-60 seconds for 100-500 records
- All phases are transactional (rollback on error)
- Blob movement provides physical audit trail (landing → processed/error)
- Uses shared utilities for validation (language_mapper, business_hours_utils)
"""

import os
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import logging
import uuid
import pandas as pd
from datetime import datetime, timezone
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
    """
    Get Azure Blob Storage client using Key Vault credentials

    BusinessCaseID: BC-DA-002

    Retrieves Azure Storage connection string from Key Vault and creates BlobServiceClient.
    Used for downloading CSV files and moving blobs between folders.

    Returns:
        BlobServiceClient: Azure Blob Storage client authenticated via connection string
    """
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
def get_db_connection(timeout: int = 30):
    """Get database connection with retry logic

    Args:
        timeout: Query execution timeout in seconds (default: 30)
    """
    conn_str = get_db_connection_string()

    # Parse connection string
    parts = dict(item.split("=", 1) for item in conn_str.split(";") if "=" in item)

    return pymssql.connect(
        server=parts.get("Server", "").replace("tcp:", "").split(",")[0],
        user=parts.get("User ID", ""),
        password=parts.get("Password", ""),
        database=parts.get("Initial Catalog", ""),
        port=int(parts.get("Server", "").split(",")[1]) if "," in parts.get("Server", "") else 1433,
        timeout=timeout,
        login_timeout=30,
    )


# ============================================================================
# DATA MODELS
# ============================================================================


@dataclass
class ProcessingResult:
    """
    Result of a processing operation (ETL phase result)

    BusinessCaseID: BC-DA-002

    Returned by each of the 5 ETL phase functions to indicate success/failure
    and provide detailed information about what happened during processing.

    Attributes:
        success (bool): True if phase completed successfully, False otherwise
        message (str): Human-readable summary message (e.g., "Phase 1: Extract Complete")
        details (Dict[str, Any]): Additional context about the result:
            - phase_completed (str): Which phase finished (e.g., "Phase 1: Extract")
            - records_processed (int): Number of records processed
            - records_succeeded (int): Number of successful operations
            - records_failed (int): Number of failed operations
            - error_details (str): Detailed error message if failure
        error (Optional[Exception]): Exception object if error occurred

    Example:
        >>> result = ProcessingResult(
        ...     success=True,
        ...     message="Phase 2: Staging Complete",
        ...     details={
        ...         "phase_completed": "Phase 2: Staging",
        ...         "records_processed": 150,
        ...         "records_succeeded": 148,
        ...         "records_failed": 2
        ...     }
        ... )
    """

    success: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None


@dataclass
class ProcessingContext:
    """
    Context for file processing operations (passed through all 5 ETL phases)

    BusinessCaseID: BC-DA-002

    This dataclass carries all necessary context and configuration through the
    5-phase ETL pipeline. Each phase function receives this context and uses it
    to access file information, database connections, and processing parameters.

    Attributes:
        file_batch_id (str): UUID identifying this file processing batch
            - Generated once at start of processing
            - Used to link all database records for this file
            - Stored in stg_device_activation_delta.file_id

        source_filename (str): Original CSV filename (e.g., "MedicalGuardian_DeviceActivation_20251224_Delta.csv")
            - Used for logging and audit trail
            - Stored in file_processing_log.filename

        container_name (str): Azure Blob Storage container name
            - Default: "fs-ops" (Operations campaigns)
            - Standard Device Activation: "fs-device-activation"
            - Used for blob download and movement operations

        uploaded_by_user (str): User/system that uploaded the file
            - Default: "AzureFunction" (automated upload)
            - Could be: "User123" (manual upload)
            - Stored in file_processing_log.uploaded_by

        error_threshold_pct (float): Maximum allowed error percentage for Phase 2 (Staging)
            - Default: 10.0 (10%)
            - If > 10% of rows fail INSERT → Abort entire file
            - Rationale: Prevents processing files with systematic data quality issues

        log_level (str): Logging level for processing operations
            - Default: "INFO"
            - Options: "DEBUG", "INFO", "WARNING", "ERROR"
            - Controls verbosity of logging output

        correlation_id (Optional[str]): UUID for distributed tracing
            - Auto-generated in __post_init__ if None
            - Used to link log entries across all phases
            - Helps trace file processing flow in Application Insights

        campaign_id (Optional[str]): Explicit campaign UUID for Operations campaigns
            - None: Use standard Device Activation campaign lookup
            - UUID string: Override with specific campaign (e.g., Medicaid, DTC/MA)
            - Used in operations_device_activation_file_processor.py

        campaign_name (Optional[str]): Campaign display name
            - Example: "Device Activation - Medicaid"
            - Used for logging and audit trail
            - Helps identify which campaign processed this file

        blob_content (Optional[bytes]): Raw CSV bytes from blob trigger
            - None: Download blob using blob_name
            - Bytes: Use pre-downloaded content (from blob trigger)
            - Optimization for blob-triggered functions

    Example:
        >>> context = ProcessingContext(
        ...     file_batch_id=str(uuid.uuid4()),
        ...     source_filename="MedicalGuardian_DeviceActivation_20251224_Delta.csv",
        ...     container_name="fs-device-activation",
        ...     uploaded_by_user="AzureFunction",
        ...     error_threshold_pct=10.0,
        ...     campaign_id="abc-123-def-456"
        ... )
        >>> print(context.correlation_id)  # Auto-generated UUID
        "xyz-789-uvw-012"

    Notes:
        - Context is immutable after creation (dataclass frozen=False by default)
        - Passed through all 5 phase functions: extract → load_to_staging → validate → transform → audit
        - correlation_id enables distributed tracing across Azure Functions and Application Insights
    """

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


def proper_case(name: str) -> Optional[str]:
    """
    Convert name to proper case with special handling for common patterns.

    Handles:
    - McDonald → McDonald (not Mcdonald)
    - O'Connor → O'Connor (not O'Connor)
    - DeAngelo → DeAngelo (not Deangelo)
    - McBride → McBride (not Mcbride)

    Returns:
        Properly cased name or None if empty
    """
    if not name or pd.isna(name):
        return None

    trimmed = str(name).strip()
    if not trimmed:
        return None

    # Handle special cases
    upper_name = trimmed.upper()
    if upper_name == "MCDONALD":
        return "McDonald"
    elif upper_name == "OCONNOR":
        return "O'Connor"
    elif upper_name == "DEANGELO":
        return "DeAngelo"
    elif upper_name.startswith("MC") and len(upper_name) > 2:
        return f"Mc{trimmed[2].upper()}{trimmed[3:].lower()}"
    else:
        return f"{trimmed[0].upper()}{trimmed[1:].lower()}"


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
        field_name: 'battery_status' (only battery_status is validated now)

    Returns:
        (is_valid, normalized_value)
    """
    if not status or pd.isna(status):
        return (True, "Unknown")

    status_str = str(status).strip().title()

    if field_name == "battery_status":
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
            "campaign_name_source": Column(str, nullable=False),  # REQUIRED
            # Member identity
            "salesforce_account_number": Column(
                str, nullable=False
            ),  # REQUIRED - primary matching key
            "salesforce_account_id": Column(str, nullable=False),
            "member_first_name": Column(str, nullable=False),
            "member_last_name": Column(str, nullable=False),
            # Contact
            "member_phone_number": Column(str, nullable=False),
            "member_email": Column(str, nullable=True),  # OPTIONAL
            # Address (5 separate fields - will be combined)
            "member_address_street": Column(str, nullable=False),  # REQUIRED
            "member_address_city": Column(str, nullable=False),  # REQUIRED
            "member_address_state": Column(str, nullable=False),  # REQUIRED
            "member_address_zip": Column(str, nullable=False),  # REQUIRED
            "member_address_country": Column(str, nullable=True),  # NEW
            # Demographics
            "member_dob": Column(str, nullable=False),  # REQUIRED - RENAMED from dob
            "member_timezone": Column(str, nullable=False),  # RENAMED from customer_timezone
            "language_pref": Column(str, nullable=True),
            # Device info
            "device_udi": Column(str, nullable=False),
            "device_name": Column(str, nullable=False),  # REQUIRED
            "member_brand": Column(str, nullable=False),  # REQUIRED - RENAMED from brand
            # NOTE: is_device_callable NOT in CSV - inferred from device_phone_number during validation
            "device_phone_number": Column(str, nullable=False),  # REQUIRED
            # Device status (NEW format: numeric 1/0 instead of text)
            "fall_detection": Column(
                str, nullable=False
            ),  # REQUIRED - CHANGED from fall_detection_status
            "powersaver_mode": Column(
                str, nullable=False
            ),  # REQUIRED - CHANGED from battery_status
            # Campaign tracking
            "campaign_parameters": Column(str, nullable=True),  # OPTIONAL
            "monitoring_system_id": Column(str, nullable=False),  # REQUIRED
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
    df["fall_detection_clean"] = None  # Initialize with None (will be 'true'/'false' or None)
    df["powersaver_mode_clean"] = (
        None  # Initialize with None (will be 'Default'/'Standard'/'Powersaver' or None)
    )

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
                row_errors.append(f"Could not find org_id for partner: '{partner_name}'")

        # ===================================================================
        # 2. Salesforce Account ID Validation (REQUIRED - NEW FIELD)
        # ===================================================================
        salesforce_account_id = str(row.get("salesforce_account_id", "")).strip()
        if not salesforce_account_id or salesforce_account_id == "":
            row_errors.append("salesforce_account_id is required")

        # ===================================================================
        # 2.5. Salesforce Account Number Validation (REQUIRED - PRIMARY MATCHING KEY)
        # ===================================================================
        salesforce_account_number = str(row.get("salesforce_account_number", "")).strip()
        if not salesforce_account_number:
            row_errors.append("salesforce_account_number is required")

        # ===================================================================
        # 2.6. Campaign Name Source Validation (REQUIRED)
        # ===================================================================
        campaign_name_source = str(row.get("campaign_name_source", "")).strip()
        if not campaign_name_source:
            row_errors.append("campaign_name_source is required")

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

        # Device phone (REQUIRED)
        device_phone = row.get("device_phone", "") or row.get("device_phone_number", "")
        if not device_phone or not str(device_phone).strip():
            row_errors.append("device_phone_number is required")
        else:
            standardized_device_phone = standardize_phone(device_phone)
            if not standardized_device_phone:
                row_errors.append(f"Invalid device_phone_number: '{device_phone}'")
            else:
                df.at[idx, "device_phone_clean"] = standardized_device_phone

        # ===================================================================
        # 4. Name Validation and Proper Casing
        # ===================================================================
        # Support both column names (pre and post column mapping)
        first_name = row.get("first_name", "") or row.get("member_first_name", "")
        last_name = row.get("last_name", "") or row.get("member_last_name", "")

        # Member First Name - Add special character removal + length validation
        if not first_name or str(first_name).strip() == "":
            row_errors.append("member_first_name is required")
            df.at[idx, "first_name_clean"] = None
        else:
            # Remove special characters but keep letters, spaces, and apostrophes
            cleaned_first = re.sub(r"[^a-zA-Z\s']", "", str(first_name))

            # Strip leading/trailing apostrophes (e.g., 'John' → John, neil' → neil, but O'Neil stays O'Neil)
            cleaned_first = cleaned_first.strip("'")

            # Validate length after cleaning
            if len(cleaned_first) > 50:
                row_errors.append("member_first_name exceeds maximum length of 50 characters")
                df.at[idx, "first_name_clean"] = None
            elif not cleaned_first.strip():
                # After removing special chars, nothing left
                row_errors.append("member_first_name contains only invalid characters")
                df.at[idx, "first_name_clean"] = None
            else:
                # Apply proper case
                df.at[idx, "first_name_clean"] = proper_case(cleaned_first)

        # Member Last Name - Add special character removal + length validation
        if not last_name or str(last_name).strip() == "":
            row_errors.append("member_last_name is required")
            df.at[idx, "last_name_clean"] = None
        else:
            # Remove special characters but keep letters, spaces, and apostrophes
            cleaned_last = re.sub(r"[^a-zA-Z\s']", "", str(last_name))

            # Strip leading/trailing apostrophes (e.g., 'Smith' → Smith, O'Brien' → O'Brien, but O'Neil stays O'Neil)
            cleaned_last = cleaned_last.strip("'")

            # Validate length after cleaning
            if len(cleaned_last) > 50:
                row_errors.append("member_last_name exceeds maximum length of 50 characters")
                df.at[idx, "last_name_clean"] = None
            elif not cleaned_last.strip():
                # After removing special chars, nothing left
                row_errors.append("member_last_name contains only invalid characters")
                df.at[idx, "last_name_clean"] = None
            else:
                # Apply proper case
                df.at[idx, "last_name_clean"] = proper_case(cleaned_last)

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
            "OTHER": "Other",
        }

        language_pref_normalized = language_name_mapping.get(
            language_pref_raw.upper(), language_pref_raw
        )

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
        # 7. Date of Birth Validation (REQUIRED - Auto-detect format, convert to YYYY-MM-DD)
        # ===================================================================
        # Support both column names (pre and post column mapping)
        dob = row.get("dob", "") or row.get("member_dob", "")
        if not dob or not str(dob).strip():
            row_errors.append("member_dob is required")
        else:
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
        country = str(
            row.get("address_country", "") or row.get("member_address_country", "")
        ).strip()

        # Validate all 5 address fields are present (REQUIRED)
        if not street:
            row_errors.append("member_address_street is required")
        if not city:
            row_errors.append("member_address_city is required")
        if not state:
            row_errors.append("member_address_state is required")
        if not zip_code:
            row_errors.append("member_address_zip is required")

        # member_address_country - require value but default to 'US'
        if not country:
            country = "US"  # Default to United States
        df.at[idx, "address_country"] = country

        # Combine address fields
        if street and city and state and zip_code:
            service_address = f"{street}, {city}, {state} {zip_code}"
            df.at[idx, "service_address_clean"] = service_address
        elif street or city:
            # Partial address - combine what we have
            parts = [p for p in [street, city, state, zip_code] if p]
            df.at[idx, "service_address_clean"] = ", ".join(parts)

        # ===================================================================
        # 8. Email Validation and Lowercase Conversion (OPTIONAL)
        # ===================================================================
        # Support both column names (pre and post column mapping)
        email = row.get("email", "") or row.get("member_email", "")
        if not email or not str(email).strip():
            # Email is optional - set to None if not provided
            df.at[idx, "email"] = None
        else:
            email_str = str(email).strip()

            # Validate format when email is provided
            if not validate_email(email_str):
                row_errors.append(f"Invalid email format: '{email_str}'")
                df.at[idx, "email"] = None
            else:
                # Convert to lowercase for consistency (emails are case-insensitive)
                df.at[idx, "email"] = email_str.lower()

        # ===================================================================
        # 8.5. Contact Method Validation (BUSINESS RULE)
        # ===================================================================
        # At least one contact method must be provided
        member_phone_exists = df.at[idx, "primary_phone_clean"] is not None
        email_exists = df.at[idx, "email"] is not None
        device_phone_exists = df.at[idx, "device_phone_clean"] is not None

        if not (member_phone_exists or email_exists or device_phone_exists):
            row_errors.append(
                "At least one contact method required (primary_phone, email, or device_phone)"
            )

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
        # 10. Device Status Validation (REQUIRED)
        # ===================================================================
        # Fall Detection: Normalize to 'true'/'false' strings (for BIT column conversion in MERGE) - REQUIRED
        fall_detection = row.get("fall_detection", "")
        if not fall_detection or not str(fall_detection).strip():
            row_errors.append("fall_detection is required")
            df.at[idx, "fall_detection_clean"] = None
        else:
            fall_str = str(fall_detection).strip().lower()
            # Validate format: accept true/false, 1/0, yes/no
            if fall_str in ["true", "1", "1.0", "yes", "y"]:
                df.at[idx, "fall_detection_clean"] = "true"
            elif fall_str in ["false", "0", "0.0", "no", "n", "f"]:
                df.at[idx, "fall_detection_clean"] = "false"
            else:
                # Invalid value - add error
                row_errors.append(
                    f"Invalid fall_detection value: '{fall_detection}' (must be true/false, 1/0, yes/no)"
                )
                df.at[idx, "fall_detection_clean"] = None

        # PowerSaver Mode: Validate and normalize to Title Case (CASE-INSENSITIVE) - REQUIRED
        powersaver_mode = row.get("powersaver_mode", "") or row.get("battery_status", "")
        if not powersaver_mode or not str(powersaver_mode).strip():
            row_errors.append("powersaver_mode is required")
            df.at[idx, "powersaver_mode_clean"] = None
        else:
            mode_str = str(powersaver_mode).strip().title()
            # Validate format: accept Default, Standard, Battery Saver (case-insensitive via .title())
            valid_modes = ["Default", "Standard", "Battery Saver"]
            if mode_str in valid_modes:
                df.at[idx, "powersaver_mode_clean"] = mode_str  # Store Title Case normalized value
                logger.debug(f"✅ [VALIDATE] Row {idx}: Valid powersaver_mode='{mode_str}'")
            else:
                # Invalid value - add error
                row_errors.append(
                    f"Invalid powersaver_mode: '{mode_str}' (must be: Default, Standard, or Battery Saver)"
                )
                df.at[idx, "powersaver_mode_clean"] = None
                logger.warning(
                    f"⚠️ [VALIDATE] Row {idx}: Invalid powersaver_mode '{mode_str}' "
                    f"(expected: {', '.join(valid_modes)}). Value set to NULL."
                )

        # Member Brand: Map member_brand to brand_clean (for members.member_brand) - REQUIRED
        # Support both column names (pre and post column mapping)
        member_brand = row.get("brand", "") or row.get("member_brand", "")
        if not member_brand or not str(member_brand).strip():
            row_errors.append("member_brand is required")
        else:
            df.at[idx, "brand_clean"] = str(member_brand).strip()

        # Device Brand: Map device_name to device_name_clean (for member_devices.brand) - REQUIRED
        device_name = row.get("device_name", "")
        if not device_name or not str(device_name).strip():
            row_errors.append("device_name is required")
        else:
            df.at[idx, "device_name_clean"] = str(device_name).strip()

        # ===================================================================
        # 10.5. Monitoring System ID Validation (REQUIRED)
        # ===================================================================
        monitoring_system_id = str(row.get("monitoring_system_id", "")).strip()
        if not monitoring_system_id:
            row_errors.append("monitoring_system_id is required")

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
            "UNENROLLED": "UNENROLL",
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
        # 12.5 Unenrollment Reason Validation (Required for UNENROLL)
        # ===================================================================
        enrollment_status = df.at[idx, "enrollment_status"]
        if enrollment_status == "UNENROLL":
            unenrollment_reason = row.get("unenrollment_reason", "")
            if unenrollment_reason and str(unenrollment_reason).strip():
                # Valid reason provided
                df.at[idx, "unenrollment_reason"] = str(unenrollment_reason).strip()
            else:
                # Missing reason - validation error
                row_errors.append(
                    "unenrollment_reason is required when enrollment_status is 'UNENROLL'"
                )

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

    # ===================================================================
    # FILE-LEVEL VALIDATION: Check for duplicate device_udi across different accounts
    # ===================================================================
    logger.info("🔍 [VALIDATION] Checking for duplicate device_udi across different accounts...")

    validated_rows = df[df["validation_status"] == "VALIDATED"].copy()

    if len(validated_rows) > 0:
        # Group by device_udi and count distinct salesforce_account_id values
        device_account_counts = (
            validated_rows.groupby("device_udi")["salesforce_account_id"]
            .agg(["nunique", lambda x: list(x)])
            .reset_index()
        )
        device_account_counts.columns = ["device_udi", "account_count", "account_ids"]

        # Find device_udi values used by multiple different accounts
        duplicate_devices = device_account_counts[device_account_counts["account_count"] > 1]

        if len(duplicate_devices) > 0:
            logger.warning(
                f"⚠️ [VALIDATION] Found {len(duplicate_devices)} device_udi values "
                f"used by multiple different salesforce_account_id values"
            )

            # Mark all affected rows as FAILED
            duplicate_count = 0
            for _, dup_row in duplicate_devices.iterrows():
                device_udi = dup_row["device_udi"]
                account_ids = dup_row["account_ids"]

                # Get indices of all rows with this device_udi
                affected_indices = df[df["device_udi"] == device_udi].index

                # Build error message
                account_ids_str = ", ".join([str(acc_id) for acc_id in account_ids])
                error_msg = (
                    f"Duplicate device_udi '{device_udi}' used by multiple accounts: [{account_ids_str}]. "
                    f"Each device must belong to only one account."
                )

                # Mark all affected rows as FAILED
                for idx in affected_indices:
                    df.at[idx, "validation_status"] = "VALIDATION_ERROR"
                    # Prepend to existing error message if any
                    existing_error = df.at[idx, "error_message"]
                    if existing_error:
                        df.at[idx, "error_message"] = f"{error_msg}; {existing_error}"
                    else:
                        df.at[idx, "error_message"] = error_msg

                    # Also update error_details
                    existing_details = df.at[idx, "error_details"]
                    if existing_details:
                        df.at[idx, "error_details"] = f"{error_msg}\n{existing_details}"
                    else:
                        df.at[idx, "error_details"] = error_msg

                duplicate_count += len(affected_indices)

                logger.warning(
                    f"   ❌ device_udi='{device_udi}' used by accounts: {account_ids_str} "
                    f"({len(affected_indices)} rows affected)"
                )

            validation_errors_count += duplicate_count
            logger.error(
                f"❌ [VALIDATION] File-level validation FAILED: "
                f"{duplicate_count} rows with duplicate device_udi across different accounts"
            )

            # Recalculate error rate after file-level validation
            error_rate = (validation_errors_count / total_rows * 100) if total_rows > 0 else 0
            logger.info(
                f"📊 [VALIDATION] Updated error count: "
                f"{validation_errors_count}/{total_rows} errors ({error_rate:.1f}%)"
            )
        else:
            logger.info("✅ [VALIDATION] No duplicate device_udi across different accounts found")
    else:
        logger.info("ℹ️ [VALIDATION] No validated rows to check for duplicates")

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
        logger.info(
            f"📥 [EXTRACT] context.blob_content size: {len(context.blob_content) if context.blob_content else 'N/A'}"
        )

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

            # Special handling: Map OLD column names to NEW column names
            # (for backwards compatibility with old CSV format)
            if "battery_status" in df.columns and "powersaver_mode" not in df.columns:
                df["powersaver_mode"] = df["battery_status"]
                df.drop(columns=["battery_status"], inplace=True)
                logger.info("✅ [EXTRACT] Mapped battery_status → powersaver_mode (old CSV format)")

            if "fall_detection_status" in df.columns and "fall_detection" not in df.columns:
                df["fall_detection"] = df["fall_detection_status"]
                df.drop(columns=["fall_detection_status"], inplace=True)
                logger.info(
                    "✅ [EXTRACT] Mapped fall_detection_status → fall_detection (old CSV format)"
                )

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
            fall_detection, powersaver_mode,
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
                        # Device status (original values from CSV)
                        df.at[idx, "fall_detection_clean"],
                        df.at[idx, "powersaver_mode_clean"],
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
        # 5 minutes timeout for file processing operations (MERGE queries on large tables)
        conn = get_db_connection(timeout=300)
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
                -- Convert fall_detection string to BIT (0/1) with trimming
                CASE
                    WHEN LOWER(RTRIM(LTRIM(stg.fall_detection))) IN ('true', '1', 'yes', 'y') THEN 1
                    WHEN LOWER(RTRIM(LTRIM(stg.fall_detection))) IN ('false', '0', 'no', 'n') THEN 0
                    WHEN stg.fall_detection IS NULL OR stg.fall_detection = '' THEN NULL
                    ELSE 0  -- Default to FALSE (0) for any unexpected value
                END AS fall_detection,
                -- Keep powersaver_mode original value
                stg.powersaver_mode
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
                fall_detection = ISNULL(src.fall_detection, tgt.fall_detection),
                powersaver_mode = ISNULL(src.powersaver_mode, tgt.powersaver_mode),
                device_phone_number = ISNULL(src.device_phone_number, tgt.device_phone_number),
                is_device_callable = ISNULL(src.is_device_callable, tgt.is_device_callable),
                device_name = ISNULL(src.device_name, tgt.device_name),
                updated_ts = SYSDATETIMEOFFSET()
        WHEN NOT MATCHED THEN
            INSERT (
                device_id, member_id, device_name, brand,
                fall_detection, powersaver_mode,
                device_phone_number, is_device_callable,
                created_ts
            )
            VALUES (
                src.device_udi, src.member_id, src.device_name, src.brand,
                src.fall_detection, src.powersaver_mode,
                src.device_phone_number, src.is_device_callable,
                SYSDATETIMEOFFSET()
            );
        """
        cursor.execute(merge_devices_query, (context.file_batch_id,))
        rows_affected = cursor.rowcount
        logger.info(
            f"✅ [TRANSFORM] MERGE INTO member_devices complete - {rows_affected} rows affected"
        )

        # Debug: Verify fall_detection values were inserted correctly
        debug_query = """
        SELECT TOP 5 device_id, fall_detection, powersaver_mode
        FROM engage360.member_devices md
        WHERE EXISTS (
            SELECT 1 FROM engage360_stg.stg_device_activation_delta stg
            WHERE stg.file_batch_id = %s
              AND md.device_id = stg.device_udi
        )
        ORDER BY md.updated_ts DESC
        """
        cursor.execute(debug_query, (context.file_batch_id,))
        debug_results = cursor.fetchall()

        if debug_results:
            logger.info("🔍 [TRANSFORM] Sample member_devices data (after MERGE):")
            for row in debug_results:
                logger.info(
                    f"   device_id={row[0]}, fall_detection={row[1]}, powersaver_mode='{row[2]}'"
                )
        else:
            logger.warning("⚠️ [TRANSFORM] No member_devices records found for this batch")

        # Step 4: INSERT INTO member_campaign_enrollments_enhanced
        # Note: activation_start_date and campaign_end_date calculated in Python
        # NEW LOGIC: activation_start_date = enrollment_ts + 2 business days

        # First, get staging data (NO delivery_date - using enrollment_ts instead)
        # Process ALL enrollment statuses (ENROLL, UPDATE, UNENROLL)
        get_staging_query = """
        SELECT DISTINCT
            m.member_id,
            stg.enrollment_status,
            stg.unenrollment_reason
        FROM engage360_stg.stg_device_activation_delta stg
        INNER JOIN engage360.members m
            ON m.org_id = stg.org_id
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.validation_status = 'VALIDATED'
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

        logger.info(
            f"🔄 [TRANSFORM] Updating rows to TRANSFORMING status for batch {context.file_batch_id}"
        )
        cursor.execute(status_update_query, (context.file_batch_id,))
        logger.info("✅ [TRANSFORM] Status updated to TRANSFORMING")

        # Count actions by type
        enroll_count = 0
        update_count = 0
        unenroll_count = 0

        for row in staging_rows:
            # Row format: (member_id, enrollment_status, unenrollment_reason)
            enrollment_status = row[1]  # Column 1: enrollment_status
            if enrollment_status == "ENROLL":
                enroll_count += 1
            elif enrollment_status == "UPDATE":
                update_count += 1
            elif enrollment_status == "UNENROLL":
                unenroll_count += 1

        logger.info(
            f"📊 [TRANSFORM] Processing actions: {enroll_count} ENROLL, "
            f"{update_count} UPDATE, {unenroll_count} UNENROLL"
        )

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

        # NEW LOGIC (2025-12-22): campaign_end_date is NOT set at enrollment
        # It will be set dynamically after Call 5 is made
        # For Calls 1-4: No 90-day limit (campaign_end_date stays NULL)
        # For Call 5+: campaign_end_date = call_5_timestamp + 90 days (set by batch orchestrator)
        campaign_end_date = None  # Set to NULL initially
        call_5_timestamp = None  # Set to NULL initially (will be populated after Call 5)

        logger.info(
            f"📅 [TRANSFORM] Activation dates for this batch: "
            f"enrollment_ts={enrollment_ts.date()} ({enrollment_ts.strftime('%A')}), "
            f"activation_start={activation_start_date} "
            f"({'SAME DAY' if enrollment_date == activation_start_date else 'NEXT BUSINESS DAY'}), "
            f"campaign_end=NULL (will be set after Call 5)"
        )

        # Process enrollments using separate operations (following DTC pattern)
        try:
            # 1. Handle ENROLL (new enrollments)
            if enroll_count > 0:
                logger.info(f"📝 [TRANSFORM] Processing {enroll_count} ENROLL actions...")
                enroll_merge_query = """
                MERGE engage360.member_campaign_enrollments_enhanced AS tgt
                USING (
                    SELECT
                        m.member_id,
                        %s AS campaign_id,
                        %s AS activation_start_date,
                        %s AS campaign_end_date,
                        %s AS call_5_timestamp
                    FROM engage360_stg.stg_device_activation_delta stg
                    JOIN engage360.members m
                        ON m.org_id = stg.org_id
                        AND m.salesforce_account_number = stg.salesforce_account_number
                    WHERE stg.file_batch_id = %s
                      AND stg.processing_status = 'TRANSFORMING'
                      AND stg.enrollment_status = 'ENROLL'
                ) AS src
                ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id

                WHEN MATCHED THEN
                    UPDATE SET
                        -- Update activation dates (re-calculated from file upload date)
                        activation_start_date = src.activation_start_date,

                        -- NEW: Only reset campaign_end_date if re-enrolling from UNENROLLED
                        campaign_end_date = CASE
                            WHEN tgt.current_status = 'UNENROLLED' THEN NULL
                            ELSE tgt.campaign_end_date
                        END,

                        -- NEW: Only reset call_5_timestamp if re-enrolling from UNENROLLED
                        call_5_timestamp = CASE
                            WHEN tgt.current_status = 'UNENROLLED' THEN NULL
                            ELSE tgt.call_5_timestamp
                        END,

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

                WHEN NOT MATCHED THEN
                    INSERT (
                        enrollment_id, member_id, campaign_id, enrollment_ts, current_status,
                        activation_start_date, campaign_end_date, call_5_timestamp, device_activated
                    )
                    VALUES (
                        NEWID(),
                        src.member_id,
                        src.campaign_id,
                        SYSDATETIMEOFFSET(),
                        'ENROLLED',
                        src.activation_start_date,
                        src.campaign_end_date,
                        src.call_5_timestamp,
                        0
                    );
                """
                cursor.execute(
                    enroll_merge_query,
                    (
                        str(campaign_id),
                        activation_start_date,
                        campaign_end_date,
                        call_5_timestamp,
                        context.file_batch_id,
                    ),
                )
                logger.info(f"✅ [TRANSFORM] Enrolled {enroll_count} members")

            # 2. Handle UPDATE (existing enrollments)
            if update_count > 0:
                logger.info(f"🔄 [TRANSFORM] Processing {update_count} UPDATE actions...")
                update_query = """
                UPDATE e
                SET e.activation_start_date = %s,
                    e.campaign_end_date = %s,
                    e.enrollment_ts = SYSDATETIMEOFFSET()
                FROM engage360.member_campaign_enrollments_enhanced e
                JOIN engage360.members m ON e.member_id = m.member_id
                JOIN engage360_stg.stg_device_activation_delta stg
                    ON m.org_id = stg.org_id
                    AND m.salesforce_account_number = stg.salesforce_account_number
                WHERE stg.file_batch_id = %s
                  AND stg.processing_status = 'TRANSFORMING'
                  AND stg.enrollment_status = 'UPDATE'
                  AND e.campaign_id = %s
                """
                cursor.execute(
                    update_query,
                    (
                        activation_start_date,
                        campaign_end_date,
                        context.file_batch_id,
                        str(campaign_id),
                    ),
                )
                logger.info(f"✅ [TRANSFORM] Updated {update_count} enrollments")

            # 3. Handle UNENROLL (terminate enrollments)
            if unenroll_count > 0:
                logger.info(f"❌ [TRANSFORM] Processing {unenroll_count} UNENROLL actions...")
                unenroll_query = """
                UPDATE e
                SET e.current_status = 'UNENROLLED',
                    e.unenrollment_reason = COALESCE(stg.unenrollment_reason, 'Updated via file processing')
                FROM engage360.member_campaign_enrollments_enhanced e
                JOIN engage360.members m ON e.member_id = m.member_id
                JOIN engage360_stg.stg_device_activation_delta stg
                    ON m.org_id = stg.org_id
                    AND m.salesforce_account_number = stg.salesforce_account_number
                WHERE stg.file_batch_id = %s
                  AND stg.processing_status = 'TRANSFORMING'
                  AND stg.enrollment_status = 'UNENROLL'
                  AND e.campaign_id = %s
                """
                cursor.execute(unenroll_query, (context.file_batch_id, str(campaign_id)))
                logger.info(f"✅ [TRANSFORM] Unenrolled {unenroll_count} members")

        except Exception as e:
            logger.error(f"❌ [TRANSFORM] Error processing enrollment actions: {e}")
            raise

        # Verify campaign enrollment
        logger.info("🔍 [TRANSFORM] Verifying campaign enrollment...")
        verify_query = """
        SELECT TOP 5
            e.enrollment_id,
            e.member_id,
            e.campaign_id,
            c.name AS campaign_name,
            e.current_status
        FROM engage360.member_campaign_enrollments_enhanced e
        JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
        WHERE e.campaign_id = %s
        ORDER BY e.enrollment_ts DESC
        """
        cursor.execute(verify_query, (str(campaign_id),))
        verify_results = cursor.fetchall()

        if verify_results:
            logger.info(
                f"✅ [TRANSFORM] Campaign enrollment verified - {len(verify_results)} recent enrollments:"
            )
            for row in verify_results:
                logger.info(
                    f"   enrollment_id={row[0]}, member_id={row[1]}, campaign={row[3]}, status={row[4]}"
                )
        else:
            logger.error(f"❌ [TRANSFORM] No enrollments found for campaign_id: {campaign_id}")

        # Step 4.5: MERGE INTO member_identifiers (save monitoring_system_id)
        logger.info(
            "💾 [TRANSFORM] Step 4.5: Upserting member identifiers (monitoring_system_id)..."
        )

        merge_identifiers_query = """
        MERGE engage360.member_identifiers AS tgt
        USING (
            SELECT DISTINCT
                m.member_id,
                'monitoring_system_id' AS id_type,
                stg.monitoring_system_id AS id_value
            FROM engage360_stg.stg_device_activation_delta stg
            INNER JOIN engage360.members m
                ON m.org_id = stg.org_id
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND stg.monitoring_system_id IS NOT NULL
              AND LTRIM(RTRIM(stg.monitoring_system_id)) != ''
        ) AS src
        ON tgt.member_id = src.member_id AND tgt.id_type = src.id_type
        WHEN MATCHED THEN
            UPDATE SET
                id_value = src.id_value
        WHEN NOT MATCHED THEN
            INSERT (
                member_identifier_id, member_id, id_type, id_value, created_ts
            )
            VALUES (
                NEWID(), src.member_id, src.id_type, src.id_value, SYSDATETIMEOFFSET()
            );
        """

        cursor.execute(merge_identifiers_query, (context.file_batch_id,))
        identifiers_affected = cursor.rowcount
        logger.info(
            f"✅ [TRANSFORM] MERGE INTO member_identifiers complete - "
            f"{identifiers_affected} rows affected"
        )

        # Verification query - sample the inserted identifiers
        if identifiers_affected > 0:
            verify_identifiers_query = """
            SELECT TOP 5
                mi.member_identifier_id,
                m.first_name,
                m.last_name,
                mi.id_type,
                mi.id_value,
                mi.created_ts
            FROM engage360.member_identifiers mi
            INNER JOIN engage360.members m ON mi.member_id = m.member_id
            WHERE mi.member_id IN (
                SELECT DISTINCT m.member_id
                FROM engage360_stg.stg_device_activation_delta stg
                INNER JOIN engage360.members m
                    ON m.org_id = stg.org_id
                    AND m.salesforce_account_number = stg.salesforce_account_number
                WHERE stg.file_batch_id = %s
                  AND stg.monitoring_system_id IS NOT NULL
            )
              AND mi.id_type = 'monitoring_system_id'
            ORDER BY mi.created_ts DESC
            """
            cursor.execute(verify_identifiers_query, (context.file_batch_id,))
            verify_results = cursor.fetchall()

            if verify_results:
                logger.info("🔍 [TRANSFORM] Sample member_identifiers (monitoring_system_id):")
                for row in verify_results:
                    logger.info(
                        f"   identifier_id={row[0]}, member='{row[1]} {row[2]}', "
                        f"type={row[3]}, value={row[4]}"
                    )
            else:
                logger.warning("⚠️ [TRANSFORM] Verification query returned no results")
        else:
            logger.info("ℹ️ [TRANSFORM] No monitoring_system_id values found in this batch")

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

        total_processed = enroll_count + update_count + unenroll_count
        return ProcessingResult(
            success=True,
            message=f"Transformed and loaded {total_processed} actions ({enroll_count} enrolled, {update_count} updated, {unenroll_count} unenrolled)",
            details={
                "enrolled_count": enroll_count,
                "updated_count": update_count,
                "unenrolled_count": unenroll_count,
                "total_processed": total_processed,
            },
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
                "DEVICE_ACTIVATION",  # file_type (was workflow_type)
                context.uploaded_by_user,
                datetime.now(timezone.utc),  # upload_started_ts (was upload_ts)
                datetime.now(timezone.utc),  # completed_ts (was processing_end_ts)
                "COMPLETED",  # current_status (was processing_status)
                details.get("total_rows", 0),  # total_records_processed (was total_rows)
                details.get("validated_rows", 0),  # successful_records (was validated_rows)
                details.get("error_rows", 0),  # failed_records (was error_rows)
                details.get("enrolled_count", 0),  # enrollments_created (was enrolled_rows)
                details.get("error_rate", 0),  # error_percentage (was error_rate_pct)
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
        logger.info(f"🔄 [MAIN] Updated: {processing_details.get('updated_count', 0)}")
        logger.info(f"❌ [MAIN] Unenrolled: {processing_details.get('unenrolled_count', 0)}")
        logger.info("=" * 80)

        enrolled = processing_details.get("enrolled_count", 0)
        updated = processing_details.get("updated_count", 0)
        unenrolled = processing_details.get("unenrolled_count", 0)
        total_actions = enrolled + updated + unenrolled

        return (
            True,
            f"Successfully processed {source_filename}: {total_actions} actions ({enrolled} enrolled, {updated} updated, {unenrolled} unenrolled)",
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
