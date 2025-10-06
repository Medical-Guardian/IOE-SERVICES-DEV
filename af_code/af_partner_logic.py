"""
Engage360 Partner Campaign File Processing Workflow
==================================================

Educational implementation for processing Partner Campaign CSV files.
Follows modular architecture with comprehensive validation and database logging.
"""

import os
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import logging
import time
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field
import pymssql
import json
import re
try:
    from azure.storage.blob import BlobServiceClient
    AZURE_STORAGE_AVAILABLE = True
except ImportError:
    BlobServiceClient = None
    AZURE_STORAGE_AVAILABLE = False
from io import BytesIO


# ================================================================
# EDUCATIONAL SECTION 1: CONFIGURATION CLASSES
# This section defines all business rules in one place for easy maintenance
# ================================================================


class ValidationSeverity:
    """Educational: Defines different levels of validation issues"""

    ERROR = "Error"  # Blocks processing
    WARNING = "Warning"  # Allows processing but logs issue
    INFO = "Info"  # Informational only


class ValidationStatus:
    """Educational: Defines the validation outcome for each row"""

    VALID = "Valid"  # Row passed all validations
    INVALID = "Invalid"  # Row has blocking errors
    WARNING = "Warning"  # Row has warnings but can proceed


class ProcessingStatus:
    """Educational: Defines file processing states"""

    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    REJECTED = "Rejected"


@dataclass
class PartnerCampaignConfig:
    """
    Educational: Central configuration for partner campaign processing.
    This makes the system easily configurable without code changes.
    """

    connection_string: str

    # Database table names
    file_log_table: str = "engage360.partner_file_processing_log"
    row_results_table: str = "engage360.partner_row_validation_results"
    file_errors_table: str = "engage360.partner_validation_error_details_file"
    row_errors_table: str = "engage360.partner_validation_error_details_row"
    care_gap_stats_table: str = "engage360.partner_file_care_gap_stats"

    # Processing thresholds
    error_threshold_pct: float = 15.0  # Allow up to 15% row errors
    max_retries: int = 3
    timeout_seconds: int = 600  # 10 minutes max processing time

    # Filename validation
    expected_filename_pattern: str = (
        r"^([A-Za-z0-9]+)_([A-Za-z0-9\/\s]+)_(\d{8})(_[A-Za-z0-9]+)?\.csv$"
    )


@dataclass
class ValidationError:
    """Educational: Represents a single validation issue with complete context"""

    category: str  # e.g., "FileName", "Format", "CareGap"
    error_type: str  # Specific error within category
    message: str  # Human-readable error description
    severity: str  # ERROR, WARNING, or INFO
    field: Optional[str] = None  # Column name if applicable
    error_value: Optional[str] = None  # The actual invalid value
    expected_value: Optional[str] = None  # What was expected
    row_number: Optional[int] = None  # Row number if row-level error


@dataclass
class ProcessingResult:
    """Educational: Standard result format for all processing operations"""

    success: bool
    message: str
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    duration_seconds: float = 0.0
    error_details: Optional[str] = None
    validation_errors: List[ValidationError] = field(default_factory=list)


# ================================================================
# NEW SECTION: DATA CLEANING AND VALIDATION LOGIC
# This new class handles all transformations and row-level validation
# ================================================================


class DataCleanerAndValidator:
    """
    Handles data cleaning, transformation, and row-level validation based on the new rules.
    "Fixable" issues generate Warnings; unfixable issues generate Errors.
    """

    @staticmethod
    def _to_e164_phone(
        phone_str: str, row_number: int, field_name: str
    ) -> Tuple[Optional[str], Optional[ValidationError]]:
        """Attempts to convert a phone number to E.164 format."""
        if not phone_str:
            return None, None

        # Strip all non-digit characters
        digits = re.sub(r"\D", "", phone_str)

        # Handle US numbers
        if len(digits) == 10:
            e164_phone = f"+1{digits}"
            # If original wasn't already in E.164, it was reformatted -> Warning
            if phone_str != e164_phone:
                warning = ValidationError(
                    category="Format",
                    error_type="PhoneNumberReformatted",
                    message=f"Row {row_number}: {field_name} was reformatted to E.164.",
                    severity=ValidationSeverity.WARNING,
                    field=field_name,
                    row_number=row_number,
                )
                return e164_phone, warning
            return e164_phone, None

        if len(digits) == 11 and digits.startswith("1"):
            e164_phone = f"+{digits}"
            if phone_str != e164_phone:
                warning = ValidationError(
                    category="Format",
                    error_type="PhoneNumberReformatted",
                    message=f"Row {row_number}: {field_name} was reformatted to E.164.",
                    severity=ValidationSeverity.WARNING,
                    field=field_name,
                    row_number=row_number,
                )
                return e164_phone, warning
            return e164_phone, None

        # If it's another format that already matches E.164 (e.g., international)
        if re.match(r"^\+\d{7,15}$", phone_str):
            return phone_str, None

        # If all attempts fail, it's an unfixable error
        error = ValidationError(
            category="Format",
            error_type="InvalidPhoneNumber",
            message=f"Row {row_number}: {field_name} is not a valid phone number.",
            severity=ValidationSeverity.ERROR,
            field=field_name,
            error_value=phone_str,
            row_number=row_number,
        )
        return None, error

    @staticmethod
    def _to_iso8601_date(
        date_str: str, row_number: int, field_name: str
    ) -> Tuple[Optional[str], Optional[ValidationError]]:
        """Attempts to parse and convert a date to ISO 8601 format (YYYY-MM-DD)."""
        if not date_str:
            return None, None

        # If already in the correct format, do nothing
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                return date_str, None
            except ValueError:  # e.g., 2025-13-40
                pass  # Fall through to the error

        # Attempt to parse common alternative formats
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
            try:
                dt_obj = datetime.strptime(date_str, fmt)
                iso_date = dt_obj.strftime("%Y-%m-%d")
                warning = ValidationError(
                    category="Format",
                    error_type="DateReformatted",
                    message=f"Row {row_number}: {field_name} was reformatted to ISO 8601.",
                    severity=ValidationSeverity.WARNING,
                    field=field_name,
                    row_number=row_number,
                )
                return iso_date, warning
            except ValueError:
                continue

        # If all parsing fails, it's an unfixable error
        error = ValidationError(
            category="Format",
            error_type="InvalidDate",
            message=f"Row {row_number}: {field_name} is not a valid or recognized date.",
            severity=ValidationSeverity.ERROR,
            field=field_name,
            error_value=date_str,
            row_number=row_number,
        )
        return None, error

    def clean_and_validate_dataframe(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[ValidationError]]:
        """
        Applies all cleaning and validation rules to the DataFrame.
        Returns a cleaned DataFrame and a list of all found errors and warnings.
        """
        all_errors = []
        cleaned_df = df.copy()

        # --- PRE-VALIDATION: Check for NULLS in mandatory fields ---
        # This is a new, critical check.
        for idx, row in cleaned_df.iterrows():
            row_number = idx + 2
            for col in PartnerCampaignRules.NON_NULLABLE_COLUMNS:
                # Check for None, NaN, or empty strings after stripping whitespace
                if pd.isna(row.get(col)) or str(row.get(col, "")).strip() == "":
                    all_errors.append(
                        ValidationError(
                            category="Data",
                            error_type="MissingRequiredValue",
                            message=f"Row {row_number}: Mandatory field '{col}' cannot be empty.",
                            severity=ValidationSeverity.ERROR,
                            field=col,
                            row_number=row_number,
                        )
                    )

        # --- DATA CLEANING & TRANSFORMATION ---
        name_columns = [
            "member_first_name",
            "member_last_name",
            "caregiver_first_name",
            "caregiver_last_name",
        ]
        for col in name_columns:
            cleaned_df[col] = cleaned_df[col].str.strip().str.title()

        phone_columns = ["member_phone_number", "caregiver_phone_number", "device_phone_number"]
        for col in phone_columns:
            results = [
                self._to_e164_phone(val, idx + 2, col)
                for idx, val in cleaned_df[col].astype(str).items()
            ]
            cleaned_df[col] = [res[0] for res in results]
            all_errors.extend([res[1] for res in results if res[1] is not None])

        results = [
            self._to_iso8601_date(val, idx + 2, "member_dob")
            for idx, val in cleaned_df["member_dob"].astype(str).items()
        ]
        cleaned_df["member_dob"] = [res[0] for res in results]
        all_errors.extend([res[1] for res in results if res[1] is not None])

        # --- STRICT VALIDATION (remaining rules) ---
        for idx, row in cleaned_df.iterrows():
            row_number = idx + 2

            if not str(row.get("salesforce_account_number", "")).isdigit():
                all_errors.append(
                    ValidationError(
                        category="Format",
                        error_type="InvalidSalesforceNumber",
                        message=f"Row {row_number}: salesforce_account_number must contain only digits.",
                        severity=ValidationSeverity.ERROR,
                        field="salesforce_account_number",
                        error_value=str(row.get("salesforce_account_number")),
                        row_number=row_number,
                    )
                )

            if not re.match(r"^America\/[A-Za-z_]+$", str(row.get("member_timezone", ""))):
                all_errors.append(
                    ValidationError(
                        category="Format",
                        error_type="InvalidTimezone",
                        message=f"Row {row_number}: member_timezone is not a valid Olson timezone string.",
                        severity=ValidationSeverity.ERROR,
                        field="member_timezone",
                        error_value=str(row.get("member_timezone")),
                        row_number=row_number,
                    )
                )

            lang = str(row.get("language_pref", "")).upper()
            if lang and lang not in ["EN", "ES"]:
                all_errors.append(
                    ValidationError(
                        category="Format",
                        error_type="InvalidLanguage",
                        message=f"Row {row_number}: language_pref must be EN or ES.",
                        severity=ValidationSeverity.ERROR,
                        field="language_pref",
                        error_value=str(row.get("language_pref")),
                        row_number=row_number,
                    )
                )

            email_fields = ["member_email", "caregiver_email", "healthcare_email"]
            for email_field in email_fields:
                email = str(row.get(email_field, ""))
                if email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
                    all_errors.append(
                        ValidationError(
                            category="Format",
                            error_type="InvalidEmail",
                            message=f"Row {row_number}: {email_field} is not a valid email address.",
                            severity=ValidationSeverity.ERROR,
                            field=email_field,
                            error_value=email,
                            row_number=row_number,
                        )
                    )

        return cleaned_df, all_errors


# ================================================================
# EDUCATIONAL SECTION 2: BUSINESS RULES CONFIGURATION
# All validation rules are defined here - modify this class to change rules
# ================================================================


class PartnerCampaignRules:
    """
    Educational: Central location for all business validation rules.
    Defines all expected, mandatory, and non-nullable columns.
    """

    # The full set of 30 columns the system recognizes as valid.
    EXPECTED_COLUMNS = [
        "partner_name",
        "campaign_name_source",
        "language_pref",
        "salesforce_account_number",
        "healthcare_member_id",
        "member_first_name",
        "member_last_name",
        "member_phone_number",
        "member_timezone",
        "member_dob",
        "member_email",
        "member_address_street",
        "member_address_city",
        "member_address_state",
        "member_address_zip",
        "member_address_country",
        "caregiver_first_name",
        "caregiver_last_name",
        "caregiver_phone_number",
        "caregiver_email",
        "channel_type",
        "device_udi",
        "device_name",
        "is_device_callable",
        "device_phone_number",
        "checkin_time",
        "medscope_contact_id",
        "mco_id",
        "campaign_parameters",
        "healthcare_email",
    ]

    # The 15 columns that MUST exist in every file. File is rejected if any are missing.
    MANDATORY_COLUMNS = [
        "partner_name",
        "campaign_name_source",
        "salesforce_account_number",
        "member_first_name",
        "member_last_name",
        "member_phone_number",
        "member_timezone",
        "member_dob",
        "member_email",
        "caregiver_first_name",
        "caregiver_last_name",
        "caregiver_phone_number",
        "caregiver_email",
        "campaign_parameters",
        "healthcare_email",
    ]

    # The subset of mandatory columns that cannot contain NULL or empty values.
    # Rows will fail validation if any of these are empty.
    NON_NULLABLE_COLUMNS = MANDATORY_COLUMNS  # In this case, it's the same list as mandatory.

    # Filename pattern for partner campaign files
    FILENAME_PATTERN = r"^([A-Za-z0-9]+)_([A-Za-z0-9\/\s]+)_(\d{8})(_[A-Za-z0-9]+)?\.csv$"


# ================================================================
# EDUCATIONAL SECTION 3: AZURE BLOB STORAGE UTILITIES
# These functions handle file operations in Azure - same pattern as DTC
# ================================================================


def get_blob_service_client():
    """
    Educational: Gets authenticated connection to Azure Blob Storage.
    This follows the same secure pattern as your DTC processor.
    """
    try:
        # LOGGING: Added detailed logging for Key Vault access
        logging.info("Attempting to get Azure Storage connection string from Key Vault...")
        key_vault_url = os.environ.get("KEY_VAULT_URL")
        secret_name_storage = "AzureStorageConnectionString"  # nosec B105 - This is a Key Vault secret name, not a password

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=key_vault_url, credential=credential)
        secret_storage = client.get_secret(secret_name_storage)
        secure_connection_string_storage = secret_storage.value
        logging.info("Successfully retrieved Azure Storage connection string.")

        return BlobServiceClient.from_connection_string(secure_connection_string_storage)
    except Exception as e:
        logging.error(f"Failed to get BlobServiceClient: {e}")
        raise


def download_blob_as_dataframe(blob_name: str, container_name: str) -> pd.DataFrame:
    """
    Educational: Downloads CSV file from blob storage directly into pandas DataFrame.
    This eliminates the need to create temporary local files.
    """
    # LOGGING: Added detailed logging for blob download
    logging.info(f"Attempting to download blob '{blob_name}' from container '{container_name}'...")
    blob_service = get_blob_service_client()
    blob_client = blob_service.get_container_client(container_name).get_blob_client(blob_name)

    stream = BytesIO()
    blob_data = blob_client.download_blob()
    blob_data.readinto(stream)
    stream.seek(0)

    # LOGGING: Log success and size
    file_size_mb = stream.getbuffer().nbytes / (1024 * 1024)
    logging.info(
        f"Successfully downloaded blob '{blob_name}' ({file_size_mb:.2f} MB). Now parsing into DataFrame."
    )

    return pd.read_csv(stream, dtype=str, keep_default_na=False)


def move_blob(blob_name: str, source_folder: str, target_folder: str, container_name: str):
    """
    Educational: Moves files between folders in blob storage.
    This is how we implement the file movement workflow.
    """
    blob_service = get_blob_service_client()
    container_client = blob_service.get_container_client(container_name)
    source_blob_path = f"{source_folder}/{blob_name}"
    target_blob_path = f"{target_folder}/{blob_name}"

    # LOGGING: Added detailed logging for blob move operation
    logging.info(
        f"Attempting to move blob from '{source_blob_path}' to '{target_blob_path}' in container '{container_name}'."
    )

    source_blob_client = container_client.get_blob_client(source_blob_path)
    target_blob_client = container_client.get_blob_client(target_blob_path)

    # Copy then delete (Azure's move operation)
    logging.info(f"Step 1/2: Copying blob to '{target_blob_path}'...")
    target_blob_client.start_copy_from_url(source_blob_client.url)

    # Wait for copy to complete (optional but good practice)
    copy_props = target_blob_client.get_blob_properties().copy
    while copy_props.status == "pending":
        time.sleep(1)
        copy_props = target_blob_client.get_blob_properties().copy

    logging.info(f"Step 2/2: Deleting source blob '{source_blob_path}'...")
    source_blob_client.delete_blob()
    logging.info("Blob move completed successfully.")


# ================================================================
# EDUCATIONAL SECTION 4: MODULAR VALIDATION COMPONENTS
# Each validator is independent and focuses on one type of validation
# ================================================================


class FileNameValidator:
    """
    Educational: Validates partner campaign file names.
    This validator only cares about filename patterns - nothing else.
    """

    @staticmethod
    def validate(
        file_name: str,
    ) -> Tuple[bool, Optional[ValidationError], Optional[Dict[str, str]]]:
        """
        Educational: Validates file name against partner campaign pattern.

        Pattern: PartnerName_CampaignName_YYYYMMDD[_Suffix].csv

        Returns:
            - success: True if filename is valid
            - error: ValidationError if invalid, None if valid
            - components: Extracted parts (partner_name, campaign_name, date, suffix)
        """
        match = re.match(PartnerCampaignRules.FILENAME_PATTERN, file_name)

        if not match:
            error = ValidationError(
                category="FileName",
                error_type="InvalidPattern",
                message=f"File name '{file_name}' does not match required pattern",
                severity=ValidationSeverity.ERROR,
                field="file_name",
                error_value=file_name,
                expected_value="PartnerName_CampaignName_YYYYMMDD[_Suffix].csv",
            )
            return False, error, None

        # Extract and validate components
        components = {
            "partner_name": match.group(1),
            "campaign_name": match.group(2),
            "date": match.group(3),
            "suffix": match.group(4)[1:] if match.group(4) else None,
        }

        # Validate date format
        try:
            datetime.strptime(components["date"], "%Y%m%d")
        except ValueError:
            error = ValidationError(
                category="FileName",
                error_type="InvalidDate",
                message=f"Date '{components['date']}' in filename is not valid YYYYMMDD format",
                severity=ValidationSeverity.ERROR,
                field="file_name",
                error_value=components["date"],
                expected_value="YYYYMMDD",
            )
            return False, error, None

        return True, None, components


class ColumnValidator:
    """
    Educational: Validates CSV column structure.
    This validator checks for required columns and identifies extra columns.
    """

    @staticmethod
    def validate(headers: List[str]) -> Tuple[List[ValidationError], List[str]]:
        """
        Validates the file's column headers.
        Returns a list of errors/warnings and a list of missing mandatory columns.
        """
        errors = []
        headers_set = set(headers)

        # Rule 1: Check for missing MANDATORY columns (Blocking Error)
        mandatory_set = set(PartnerCampaignRules.MANDATORY_COLUMNS)
        missing_mandatory = list(mandatory_set - headers_set)
        if missing_mandatory:
            for column in missing_mandatory:
                errors.append(
                    ValidationError(
                        category="Schema",
                        error_type="MissingMandatoryColumn",
                        message=f"Mandatory column '{column}' is missing from the file.",
                        severity=ValidationSeverity.ERROR,
                        field=column,
                    )
                )
            return errors, missing_mandatory

        # Rule 2: Check for missing OPTIONAL columns (Non-Blocking Warning)
        expected_set = set(PartnerCampaignRules.EXPECTED_COLUMNS)
        missing_optional = list(expected_set - mandatory_set - headers_set)
        for column in missing_optional:
            errors.append(
                ValidationError(
                    category="Schema",
                    error_type="MissingOptionalColumn",
                    message=f"Optional column '{column}' was not found. It will be treated as null.",
                    severity=ValidationSeverity.WARNING,
                    field=column,
                )
            )

        # Rule 3: Check for completely UNEXPECTED columns (Non-Blocking Warning)
        unexpected_columns = list(headers_set - expected_set)
        for column in unexpected_columns:
            errors.append(
                ValidationError(
                    category="Schema",
                    error_type="UnexpectedColumn",
                    message=f"An unexpected column '{column}' was found in the file and will be ignored.",
                    severity=ValidationSeverity.WARNING,
                    field=column,
                )
            )

        return errors, []


class FormatValidator:
    """
    Educational: Validates data formats using regular expressions.
    This validator focuses only on format patterns - not business logic.
    """

    # FIX: The original method had the wrong implementation and an incorrect signature.
    # It has been completely replaced with the correct logic for format validation.
    @staticmethod
    def validate_row(row_data: Dict[str, str], row_number: int) -> List[ValidationError]:
        """
        Educational: Validates data formats for a single row based on regex patterns and allowed values.
        """
        errors = []

        # 1. Validate against regex patterns
        for field_name, rules in PartnerCampaignRules.FORMAT_PATTERNS.items():
            value = str(row_data.get(field_name, "")).strip()

            # The regex itself determines if an empty string is allowed (e.g., using `?` or `*`)
            if not re.match(rules["pattern"], value):
                errors.append(
                    ValidationError(
                        category="Format",
                        error_type="InvalidFormat",
                        message=f"Row {row_number}: {rules['description']}",
                        severity=rules["severity"],
                        field=field_name,
                        error_value=value[:100],  # Truncate long values
                        expected_value=f"Pattern: {rules['pattern']}",
                        row_number=row_number,
                    )
                )

        # 2. Validate against allowed value lists
        for field_name, rules in PartnerCampaignRules.ALLOWED_VALUES.items():
            value = str(row_data.get(field_name, "")).strip()

            # Normalize values for case-insensitive comparison if applicable (like 'Y'/'y')
            # The rule should define the canonical values (e.g., ['Y', 'N', ''])
            # We compare the input value (e.g., 'y') against the list.
            allowed_values_case_insensitive = [v.lower() for v in rules["values"]]

            if value.lower() not in allowed_values_case_insensitive:
                errors.append(
                    ValidationError(
                        category="Format",
                        error_type="InvalidValue",
                        message=f"Row {row_number}: {rules['description']}",
                        severity=rules["severity"],
                        field=field_name,
                        error_value=value,
                        expected_value=f"One of: {', '.join(rules['values'])}",
                        row_number=row_number,
                    )
                )
        return errors


class ChannelTypeValidator:
    """
    Educational: Validates channel type business rules.
    This validator handles the complex logic around device requirements.
    """

    @staticmethod
    def validate_row(row_data: Dict[str, str], row_number: int) -> List[ValidationError]:
        """
        Educational: Validates channel type business rules for one row.

        Business Rule: If channel_type = "device", then device must be callable
        and device fields must be populated.
        """
        errors = []
        channel_type = str(row_data.get("channel_type", "")).strip().lower()

        # Rule 1: Channel type cannot be empty
        if not channel_type:
            errors.append(
                ValidationError(
                    category="ChannelType",
                    error_type="EmptyChannelType",
                    message=f"Row {row_number}: Channel type is empty - must be 'device' or 'phone'",
                    severity=ValidationSeverity.ERROR,
                    field="channel_type",
                    error_value="",
                    expected_value="device or phone",
                    row_number=row_number,
                )
            )
            return errors

        # Rule 2: If device channel, validate device requirements
        if channel_type == "device":
            # Check if device is callable
            is_callable = str(row_data.get("is_device_callable", "")).strip().upper()
            if is_callable != "Y":
                errors.append(
                    ValidationError(
                        category="ChannelType",
                        error_type="DeviceNotCallable",
                        message=f"Row {row_number}: When channel_type is 'device', is_device_callable must be 'Y'",
                        severity=ValidationSeverity.ERROR,
                        field="is_device_callable",
                        error_value=is_callable,
                        expected_value="Y",
                        row_number=row_number,
                    )
                )

            # Check required device fields
            required_device_fields = ["device_phone_number", "device_udi", "device_name"]
            for field in required_device_fields:
                value = str(row_data.get(field, "")).strip()
                if not value:
                    errors.append(
                        ValidationError(
                            category="ChannelType",
                            error_type="MissingDeviceField",
                            message=f"Row {row_number}: {field} is required when channel_type is 'device'",
                            severity=ValidationSeverity.ERROR,
                            field=field,
                            error_value="",
                            expected_value="Non-empty value",
                            row_number=row_number,
                        )
                    )

        return errors


class CareGapsValidator:
    """
    Educational: Validates care gaps against reference database.
    This validator handles the most complex business logic - care gaps consistency.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._care_gaps_cache = None

    def _get_active_care_gaps(self) -> Dict[str, bool]:
        if self._care_gaps_cache is not None:
            # LOGGING: Log when using cache
            logging.info("Using cached care gaps reference data.")
            return self._care_gaps_cache

        try:
            # LOGGING: Log DB query for care gaps
            logging.info("Fetching active care gaps from reference database...")
            # Get database logger from the parent processor
            db_logger = DatabaseLogger(self.connection_string)
            with db_logger.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT csv_import_flag_name, is_active 
                    FROM engage360.care_gaps
                """
                )

                self._care_gaps_cache = {}
                for row in cursor.fetchall():
                    care_gap_name = row[0]  # csv_import_flag_name
                    is_active = bool(row[1])  # is_active
                    self._care_gaps_cache[care_gap_name] = is_active

                # LOGGING: Log success
                logging.info(
                    f"Successfully fetched and cached {len(self._care_gaps_cache)} care gaps."
                )
                return self._care_gaps_cache

        except Exception as e:
            logging.error(f"Error retrieving care gaps from database: {str(e)}")
            return {}

    def validate_row(
        self, row_data: Dict[str, str], row_number: int
    ) -> Tuple[List[ValidationError], List[str], List[str]]:
        """
        Educational: Validates care gaps for a single row.

        This method:
        1. Parses the campaign_parameters JSON
        2. Extracts care gap flags ending with '_import_flag'
        3. Checks each active care gap against the reference table
        4. Returns errors and lists of active/inactive care gaps
        """
        errors = []
        active_care_gaps = []
        inactive_care_gaps_found = []

        # Parse campaign_parameters JSON
        campaign_params_str = str(row_data.get("campaign_parameters", "")).strip()
        if not campaign_params_str:
            errors.append(
                ValidationError(
                    category="CareGap",
                    error_type="MissingCampaignParameters",
                    message=f"Row {row_number}: campaign_parameters field is empty",
                    severity=ValidationSeverity.ERROR,
                    field="campaign_parameters",
                    error_value="",
                    expected_value="Valid JSON with care gap flags",
                    row_number=row_number,
                )
            )
            return errors, [], []

        try:
            # FIX: This logic to un-escape JSON from a CSV was in the wrong validator.
            # Moved here to correctly parse the campaign_parameters field.
            if campaign_params_str.startswith('"') and campaign_params_str.endswith('"'):
                unescaped_str = campaign_params_str[1:-1].replace('""', '"')
            else:
                unescaped_str = campaign_params_str

            campaign_params = json.loads(unescaped_str)

        except json.JSONDecodeError as e:
            errors.append(
                ValidationError(
                    category="CareGap",
                    error_type="InvalidJSON",
                    message=f"Row {row_number}: campaign_parameters is not valid JSON: {str(e)}",
                    severity=ValidationSeverity.ERROR,
                    field="campaign_parameters",
                    error_value=(
                        campaign_params_str[:100] + "..."
                        if len(campaign_params_str) > 100
                        else campaign_params_str
                    ),
                    expected_value="Valid JSON format",
                    row_number=row_number,
                )
            )
            return errors, [], []

        # Get reference care gaps
        reference_care_gaps = self._get_active_care_gaps()

        # Extract care gap flags ending with '_import_flag'
        for key, value in campaign_params.items():
            if key.endswith("_import_flag") and str(value).upper() == "Y":
                active_care_gaps.append(key)

                # Check if this care gap is active in the reference table
                if key in reference_care_gaps:
                    if not reference_care_gaps[key]:  # Care gap is inactive
                        inactive_care_gaps_found.append(key)
                        errors.append(
                            ValidationError(
                                category="CareGap",
                                error_type="InactiveCareGap",
                                message=f"Row {row_number}: Care gap '{key}' is active in file but inactive in reference table",
                                severity=ValidationSeverity.ERROR,
                                field="campaign_parameters",
                                error_value=f"{key}: Y",
                                expected_value="Only active care gaps should be marked as Y",
                                row_number=row_number,
                            )
                        )
                else:
                    # Care gap not found in reference table
                    errors.append(
                        ValidationError(
                            category="CareGap",
                            error_type="UnknownCareGap",
                            message=f"Row {row_number}: Care gap '{key}' not found in reference table",
                            severity=ValidationSeverity.WARNING,
                            field="campaign_parameters",
                            error_value=f"{key}: Y",
                            expected_value="Care gap should exist in reference table",
                            row_number=row_number,
                        )
                    )

        return errors, active_care_gaps, inactive_care_gaps_found


# ================================================================
# EDUCATIONAL SECTION 5: DATABASE OPERATIONS
# This class handles all database interactions for logging results
# ================================================================


class DatabaseLogger:
    """
    Educational: Manages all database operations for partner campaign validation.
    This class separates database concerns from validation logic.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

        # ... inside the DatabaseLogger class ...

    def log_care_gap_stats(
        self, file_processing_id: int, care_gap_summary: Dict[str, Dict[str, int]]
    ):
        """Logs the aggregated care gap statistics for the file."""
        if not care_gap_summary:
            logging.warning("No care gap data found to log.")
            return
        try:
            logging.info(
                f"Logging statistics for {len(care_gap_summary)} care gaps to the database for file_processing_id {file_processing_id}..."
            )
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for care_gap_name, stats in care_gap_summary.items():
                    # Note: We assume the reference table status (is_active_in_reference_table) would be joined in a view later.
                    cursor.execute(
                        """
                            INSERT INTO [engage360].[partner_file_care_gap_stats]
                            (file_processing_id, care_gap_name, active_member_count, total_member_count)
                            VALUES (%s, %s, %s, %s)
                        """,
                        (
                            file_processing_id,
                            care_gap_name,
                            stats["active_count"],
                            stats["total_count"],
                        ),
                    )
                conn.commit()
                logging.info(
                    f"Successfully logged {len(care_gap_summary)} care gap summary records."
                )
        except Exception as e:
            logging.error(f"Error logging care gap statistics: {e}")
            raise

    def _get_connection_params(self, conn_string: str) -> dict:
        """Educational: Parse connection string into pymssql parameters"""
        conn_params = {}
        for param in conn_string.split(";"):
            if "=" not in param:
                continue
            key, value = param.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "server":
                server_value = value
                if server_value.lower().startswith("tcp:"):
                    server_value = server_value[4:]
                if "," in server_value:
                    host, port = server_value.split(",", 1)
                    conn_params["server"] = host
                    conn_params["port"] = int(port)
                else:
                    conn_params["server"] = server_value
            elif key in ("initial catalog", "database"):
                conn_params["database"] = value
            elif key == "user id":
                conn_params["user"] = value
            elif key == "password":
                conn_params["password"] = value

        return conn_params

    def get_connection(self):
        """Educational: Create database connection using secure connection string"""
        try:
            # LOGGING: Added detailed logging for DB connection
            logging.info("Attempting to get database connection string from Key Vault...")
            key_vault_url = os.environ["KEY_VAULT_URL"]
            secret_name = os.environ.get("DB_SECRET_NAME", "SqlConnectionStringIOE")
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=key_vault_url, credential=credential)
            secure_conn = client.get_secret(secret_name).value
            logging.info("Successfully retrieved database connection string from Key Vault.")

            conn_kwargs = self._get_connection_params(secure_conn)
            logging.info(
                f"Connecting to database '{conn_kwargs.get('database')}' on server '{conn_kwargs.get('server')}'..."
            )
            conn = pymssql.connect(**conn_kwargs, login_timeout=30)
            conn.autocommit(False)  # Manage transactions manually
            logging.info("Database connection established successfully.")
            return conn
        except Exception as e:
            logging.error(f"Database connection failed: {str(e)}")
            raise

    def log_row_validation_results(self, file_processing_id: int, row_results: List[Dict]):
        """
        Educational: Logs the validation results for each row.
        """
        if not row_results:
            return

        try:
            # LOGGING: Log before inserting
            logging.info(
                f"Logging {len(row_results)} row validation results to the database for file_processing_id {file_processing_id}..."
            )
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for result in row_results:
                    # FIX: Added a missing column 'healthcare_member_id' from the original code that wasn't being passed. Assuming it should be extracted.
                    cursor.execute(
                        """
                        INSERT INTO [engage360].[partner_row_validation_results]
                        (file_processing_id, row_number, validation_status, total_errors_count, 
                         total_warnings_count, partner_name, campaign_name_source, salesforce_account_number,
                         active_care_gaps, healthcare_member_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            file_processing_id,
                            result["row_number"],
                            result["status"],
                            result["errors_count"],
                            result["warnings_count"],
                            result["partner_name"],
                            result["campaign_name_source"],
                            result["salesforce_account_number"],
                            json.dumps(result["active_care_gaps"]),
                            result.get("healthcare_member_id", ""),
                        ),
                    )  # Added get() for safety
                conn.commit()
                logging.info(f"Successfully logged {len(row_results)} row validation results.")
        except Exception as e:
            logging.error(f"Error logging row validation results: {e}")
            raise

    def log_row_level_errors(self, file_processing_id: int, errors: List[ValidationError]):
        """
        Educational: Logs row-level validation errors.
        """
        if not errors:
            return

        try:
            # LOGGING: Log before inserting
            logging.info(
                f"Logging {len(errors)} row-level errors to the database for file_processing_id {file_processing_id}..."
            )
            with self.get_connection() as conn:
                cursor = conn.cursor()

                for error in errors:
                    cursor.execute(
                        """
                        INSERT INTO [engage360].[partner_validation_error_details_row]
                        (file_processing_id, row_number, error_category, error_type, error_field,
                         error_message, error_value, expected_value, severity)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            file_processing_id,
                            error.row_number,
                            error.category,
                            error.error_type,
                            error.field,
                            error.message,
                            error.error_value,
                            error.expected_value,
                            error.severity,
                        ),
                    )

                conn.commit()
                logging.info(f"Successfully logged {len(errors)} row-level errors.")

        except Exception as e:
            logging.error(f"Error logging row-level errors: {str(e)}")
            raise

    def log_file_processing_start(
        self,
        file_name: str,
        original_path: str,
        final_path: str,
        file_size: int,
        partner_name: str,
        campaign_name: str,
    ) -> int:
        """
        Educational: Creates initial file processing log entry.
        """
        try:
            # LOGGING: Log before inserting
            logging.info("Creating initial file processing log entry in the database...")
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO [engage360].[partner_file_processing_log] 
                    (file_name, original_file_path, final_file_path, file_size_bytes, 
                     partner_name, campaign_name_source, processing_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        file_name,
                        original_path,
                        final_path,
                        file_size,
                        partner_name,
                        campaign_name,
                        ProcessingStatus.PROCESSING,
                    ),
                )

                cursor.execute("SELECT @@IDENTITY")
                file_processing_id = cursor.fetchone()[0]
                conn.commit()

                logging.info(
                    f"Successfully created file processing log entry with ID: {file_processing_id}"
                )
                return file_processing_id

        except Exception as e:
            logging.error(f"Error logging file processing start: {str(e)}")
            raise

    def refresh_summary_views(self):
        """
        Educational: Refreshes the partner campaign summary views.
        """
        try:
            # LOGGING: Log before refreshing
            logging.info("Refreshing summary materialized views...")
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Refresh views by running a simple select to ensure they're updated
                cursor.execute("SELECT COUNT(*) FROM [engage360].[vw_partner_file_summary]")
                cursor.fetchone()

                cursor.execute("SELECT COUNT(*) FROM [engage360].[vw_partner_error_summary]")
                cursor.fetchone()

                conn.commit()
                logging.info("Successfully refreshed partner campaign summary views.")

        except Exception as e:
            logging.error(f"Error refreshing summary views: {str(e)}")
            # Don't raise - view refresh failure shouldn't break processing

    def log_file_level_errors(self, file_processing_id: int, errors: List[ValidationError]):
        """
        Educational: Logs file-level validation errors.
        """
        if not errors:
            return

        try:
            # LOGGING: Log before inserting
            logging.info(
                f"Logging {len(errors)} file-level errors to the database for file_processing_id {file_processing_id}..."
            )
            with self.get_connection() as conn:
                cursor = conn.cursor()

                for error in errors:
                    cursor.execute(
                        """
                        INSERT INTO [engage360].[partner_validation_error_details_file]
                        (file_processing_id, error_category, error_type, error_field,
                         error_message, error_value, expected_value, severity)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                        (
                            file_processing_id,
                            error.category,
                            error.error_type,
                            error.field,
                            error.message,
                            error.error_value,
                            error.expected_value,
                            error.severity,
                        ),
                    )

                conn.commit()
                logging.info(f"Successfully logged {len(errors)} file-level errors.")

        except Exception as e:
            logging.error(f"Error logging file-level errors: {str(e)}")
            raise


# ================================================================
# EDUCATIONAL SECTION 6: MAIN ORCHESTRATOR
# This brings together all the validation components
# ================================================================


class PartnerCampaignProcessor:
    """
    Educational: Main orchestrator that coordinates all validation steps.
    """

    def __init__(self, config: PartnerCampaignConfig):
        self.config = config
        self.db_logger = DatabaseLogger(config.connection_string)
        self.care_gaps_validator = CareGapsValidator(config.connection_string)

    def process_file(self, file_name: str, container_name: str) -> ProcessingResult:
        start_time = time.time()
        logging.info(f"--- Starting Partner Campaign File Processing Workflow for: {file_name} ---")
        try:
            # STEP 1: Validate filename
            name_valid, name_error, name_components = FileNameValidator.validate(file_name)
            if not name_valid:
                return ProcessingResult(
                    success=False,
                    message=f"Filename validation failed: {name_error.message}",
                    validation_errors=[name_error],
                )

            partner_name, campaign_name = (
                name_components["partner_name"],
                name_components["campaign_name"],
            )
            original_path, validated_path = f"landing/{file_name}", f"validated/{file_name}"

            # STEP 2: Move file
            move_blob(file_name, "landing", "validated", container_name)

            # STEP 3: Download and parse file
            df = download_blob_as_dataframe(validated_path, container_name)
            df.columns = [col.lower().strip() for col in df.columns]

            file_processing_id = self.db_logger.log_file_processing_start(
                file_name,
                original_path,
                validated_path,
                len(df.to_csv(index=False).encode("utf-8")),
                partner_name,
                campaign_name,
            )

            # STEP 4: Validate column schema
            column_errors, missing_mandatory = ColumnValidator.validate(list(df.columns))
            if missing_mandatory:
                self.db_logger.log_file_level_errors(file_processing_id, column_errors)
                self._update_file_processing_completion(
                    file_processing_id, ProcessingStatus.REJECTED, len(df), 0, len(df), 0
                )
                return ProcessingResult(
                    success=False,
                    message=f"Missing mandatory columns: {', '.join(missing_mandatory)}",
                    validation_errors=column_errors,
                )

            # Add missing optional columns with null values
            for col in PartnerCampaignRules.EXPECTED_COLUMNS:
                if col not in df.columns:
                    df[col] = None

            # STEP 5: Clean data and perform row-level validation
            cleaner = DataCleanerAndValidator()
            cleaned_df, row_level_validation_errors = cleaner.clean_and_validate_dataframe(df)

            # STEP 6: Calculate final results
            total_rows = len(cleaned_df)
            error_rows_set = set(
                e.row_number
                for e in row_level_validation_errors
                if e.severity == ValidationSeverity.ERROR
            )
            invalid_rows = len(error_rows_set)
            valid_rows = total_rows - invalid_rows
            final_status = ProcessingStatus.COMPLETED
            final_message = (
                f"Processing completed with {invalid_rows} invalid rows out of {total_rows} total."
            )

            # STEP 7: Log all results
            self.db_logger.log_file_level_errors(file_processing_id, column_errors)
            self.db_logger.log_row_level_errors(file_processing_id, row_level_validation_errors)

            # FIX: Call the corrected helper function with the full dataframe
            row_results = self._create_row_results(cleaned_df, row_level_validation_errors)
            self.db_logger.log_row_validation_results(file_processing_id, row_results)

            # STEP 8: Log care gap stats
            care_gap_summary = self._calculate_care_gap_summary(cleaned_df)
            self.db_logger.log_care_gap_stats(file_processing_id, care_gap_summary)

            # STEP 9: Update final status
            warning_rows_count = len(
                set(
                    e.row_number
                    for e in row_level_validation_errors
                    if e.severity == ValidationSeverity.WARNING
                )
            )
            self._update_file_processing_completion(
                file_processing_id,
                final_status,
                total_rows,
                valid_rows,
                invalid_rows,
                warning_rows_count,
            )

            # STEP 10: Refresh views
            self.db_logger.refresh_summary_views()

            duration = time.time() - start_time
            logging.info(f"--- Partner campaign processing finished in {duration:.2f} seconds ---")
            return ProcessingResult(
                success=True,
                message=final_message,
                records_processed=total_rows,
                records_succeeded=valid_rows,
                records_failed=invalid_rows,
                duration_seconds=duration,
            )

        except Exception as e:
            logging.exception("A critical, unhandled exception occurred.")
            if "file_processing_id" in locals() and file_processing_id:
                self._update_file_processing_completion(
                    file_processing_id, ProcessingStatus.FAILED, 0, 0, 0, 0
                )
            return ProcessingResult(
                success=False, message=f"Critical error in processing: {e}", error_details=str(e)
            )

    def _calculate_care_gap_summary(self, df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
        """Calculates aggregate stats for all care gaps found in the file."""
        from collections import defaultdict

        care_gap_summary = defaultdict(lambda: {"active_count": 0, "total_count": len(df)})

        all_care_gap_flags = set()
        for params_str in df["campaign_parameters"].dropna():
            try:
                params = json.loads(params_str)
                for key in params:
                    if key.endswith("_import_flag"):
                        all_care_gap_flags.add(key)
            except (json.JSONDecodeError, TypeError):
                continue

        for _, row in df.iterrows():
            try:
                params = json.loads(row["campaign_parameters"])
                for flag in all_care_gap_flags:
                    if str(params.get(flag, "N")).upper() == "Y":
                        care_gap_summary[flag]["active_count"] += 1
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        return dict(care_gap_summary)

    def _create_row_results(
        self, df: pd.DataFrame, all_errors: List[ValidationError]
    ) -> List[Dict[str, Any]]:
        """
        FIX: This is the corrected helper function.
        It uses the dataframe to populate the log with real data.
        """
        results = []
        errors_by_row = {i: [] for i in range(2, len(df) + 2)}
        warnings_by_row = {i: [] for i in range(2, len(df) + 2)}

        for error in all_errors:
            if error.row_number:
                if error.severity == ValidationSeverity.ERROR:
                    errors_by_row[error.row_number].append(error)
                elif error.severity == ValidationSeverity.WARNING:
                    warnings_by_row[error.row_number].append(error)

        for idx, row in df.iterrows():
            row_number = idx + 2
            status = ValidationStatus.VALID
            if errors_by_row[row_number]:
                status = ValidationStatus.INVALID
            elif warnings_by_row[row_number]:
                status = ValidationStatus.WARNING

            active_care_gaps = []
            try:
                # Use .get() to avoid errors if the column is missing for some reason
                params_str = row.get("campaign_parameters", "{}")
                if pd.notna(params_str) and params_str:
                    params = json.loads(params_str)
                    active_care_gaps = [
                        k
                        for k, v in params.items()
                        if k.endswith("_import_flag") and str(v).upper() == "Y"
                    ]
            except (json.JSONDecodeError, TypeError):
                pass  # This error is already logged by the main validator

            results.append(
                {
                    "row_number": row_number,
                    "status": status,
                    "errors_count": len(errors_by_row[row_number]),
                    "warnings_count": len(warnings_by_row[row_number]),
                    "partner_name": row.get("partner_name", ""),
                    "campaign_name_source": row.get("campaign_name_source", ""),
                    "salesforce_account_number": row.get("salesforce_account_number", ""),
                    "active_care_gaps": active_care_gaps,
                    "healthcare_member_id": row.get("healthcare_member_id", ""),
                }
            )
        return results

    def _validate_single_row(
        self, row_data: Dict[str, str], row_number: int
    ) -> List[ValidationError]:
        """
        Educational: Validates a single row using all validation components.
        """
        all_errors = []

        # LOGGING: Added logging for each validator
        # logging.debug(f"Row {row_number}: Applying Format Validator...")
        format_errors = FormatValidator.validate_row(row_data, row_number)
        all_errors.extend(format_errors)

        # logging.debug(f"Row {row_number}: Applying Channel Type Validator...")
        channel_errors = ChannelTypeValidator.validate_row(row_data, row_number)
        all_errors.extend(channel_errors)

        # logging.debug(f"Row {row_number}: Applying Care Gaps Validator...")
        try:
            care_gap_errors, _, _ = self.care_gaps_validator.validate_row(row_data, row_number)
            all_errors.extend(care_gap_errors)
        except Exception as e:
            logging.warning(f"Care gaps validation failed unexpectedly for row {row_number}: {e}")
            all_errors.append(
                ValidationError(
                    category="CareGap",
                    error_type="ValidatorCrash",
                    message=f"Row {row_number}: Care gaps validation crashed: {str(e)}",
                    severity=ValidationSeverity.WARNING,
                    field="campaign_parameters",
                    row_number=row_number,
                )
            )

        return all_errors

    def _update_file_processing_completion(
        self,
        file_processing_id: int,
        status: str,
        total_rows: int,
        valid_rows: int,
        invalid_rows: int,
        warning_rows: int,
    ):
        """Educational: Updates the file processing log with final results"""
        try:
            # LOGGING: Log before update
            logging.info(
                f"Updating final status for file_processing_id {file_processing_id} to '{status}'."
            )
            with self.db_logger.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE [engage360].[partner_file_processing_log] 
                    SET processing_end_time = GETUTCDATE(),
                        processing_status = %s,
                        total_rows_in_file = %s,
                        valid_rows_count = %s,
                        invalid_rows_count = %s,
                        warning_rows_count = %s
                    WHERE file_processing_id = %s
                """,
                    (
                        status,
                        total_rows,
                        valid_rows,
                        invalid_rows,
                        warning_rows,
                        file_processing_id,
                    ),
                )

                conn.commit()
                logging.info(
                    f"Successfully updated final status for file_processing_id: {file_processing_id}."
                )

        except Exception as e:
            logging.error(f"Error updating file processing completion: {str(e)}")


# ================================================================
# EDUCATIONAL SECTION 7: PUBLIC API FUNCTION
# ================================================================


def process_partner_campaign_file_complete(
    file_path: str,
    connection_string: str = "",
    uploaded_by_user: Optional[str] = None,
    error_threshold_pct: float = 15.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Educational: Main entry point for partner campaign file processing.
    """
    # Use a named logger for better context
    logger = logging.getLogger("partner_campaign_processor")

    # Configure basic logging if not already configured
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    logger.info("=" * 70)
    logger.info("🚀 STARTING PARTNER CAMPAIGN FILE PROCESSING WORKFLOW")
    logger.info("=" * 70)
    logger.info(f"File to process: {file_path}")
    logger.info(f"Configured error threshold: {error_threshold_pct}%")
    logger.info(f"File uploaded by: {uploaded_by_user if uploaded_by_user else 'N/A'}")

    try:
        config = PartnerCampaignConfig(
            connection_string=connection_string, error_threshold_pct=error_threshold_pct
        )

        processor = PartnerCampaignProcessor(config)

        # Assume container name comes from environment variables
        container_name = os.environ["AZURE_CONTAINER_NAME_PARTNER"]
        result = processor.process_file(file_path, container_name)

        summary = {
            "file_name": file_path,
            "success": result.success,
            "message": result.message,
            "records_processed": result.records_processed,
            "records_succeeded": result.records_succeeded,
            "records_failed": result.records_failed,
            "duration_seconds": round(result.duration_seconds, 2),
            "error_rate_percent": (
                (result.records_failed / result.records_processed * 100)
                if result.records_processed > 0
                else 0
            ),
            "validation_errors_count": len(result.validation_errors),
        }

        if result.success:
            logger.info("✅ Workflow completed successfully.")
        else:
            logger.error(f"❌ Workflow failed: {result.message}")

        logger.info(f"📊 Final Summary: {json.dumps(summary, indent=2)}")
        logger.info("=" * 70)
        logger.info("🚀 WORKFLOW COMPLETE")
        logger.info("=" * 70)

        return result.success, result.message, summary

    except Exception as e:
        logger.exception("A critical, unhandled exception occurred in the main entry point.")
        error_msg = f"Critical error in partner campaign processing: {e}"

        return (
            False,
            error_msg,
            {
                "file_name": file_path,
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )


# ================================================================
# EDUCATIONAL SECTION 8: EXAMPLE USAGE
# ================================================================

if __name__ == "__main__":
    # This block is for local testing and won't run in Azure Functions.
    # You must set environment variables locally for this to work.
    # Example:
    # export KEY_VAULT_URL="https://your-keyvault.vault.azure.net/"
    # export AZURE_CONTAINER_NAME_PARTNER="your-container-name"

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # This is an example filename. The file must exist in the `landing` folder of your blob container.
    test_file = "FidelisCare_HearingMembers_20250101_Members.csv"

    print(f"--- Running local test for file: {test_file} ---")

    try:
        success, message, details = process_partner_campaign_file_complete(
            file_path=test_file, uploaded_by_user="local.test@system.com", error_threshold_pct=15.0
        )

        print("\n--- Local Test Result ---")
        if success:
            print(f"✅ Processing Succeeded: {message}")
        else:
            print(f"❌ Processing Failed: {message}")

        print("\n📊 Details:")
        print(json.dumps(details, indent=2))

    except KeyError as e:
        print(
            f"\n❌ ERROR: Missing environment variable: {e}. Please set it before running locally."
        )
    except Exception as e:
        print(f"\n❌ An unexpected error occurred during local test: {e}")
