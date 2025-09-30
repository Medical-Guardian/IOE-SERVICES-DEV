"""
Engage360 DTC File Processing Workflow
=====================================

Industry-standard implementation for processing DTC wellness CSV files.
Follows modular architecture with staging → core table flow and comprehensive validation.
"""

import os
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
import logging
import time
import uuid
import pandas as pd
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field
import pymssql  # Replaced pyodbc
from pathlib import Path
import pandera as pa
from pandera import Column, DataFrameSchema, Check
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import date  # For date handling
from azure.storage.blob import BlobServiceClient
from io import BytesIO
import re  # For special character cleaning


def get_blob_service_client():

    # Securely fetch connection string from Key Vault
    key_vault_url = os.environ.get("KEY_VAULT_URL")
    secret_name_storage = "AzureStorageConnectionString"  # nosec B105 - This is a Key Vault secret name, not a password

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=key_vault_url, credential=credential)
    secret_storage = client.get_secret(secret_name_storage)
    secure_connection_string_storage = secret_storage.value
    # conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    return BlobServiceClient.from_connection_string(secure_connection_string_storage)


def download_blob_as_dataframe(blob_name: str, container_name: str) -> pd.DataFrame:
    blob_service = get_blob_service_client()
    blob_client = blob_service.get_container_client(container_name).get_blob_client(blob_name)
    stream = BytesIO()
    blob_data = blob_client.download_blob()
    blob_data.readinto(stream)
    stream.seek(0)
    return pd.read_csv(stream, dtype=str, keep_default_na=False)


def move_blob(blob_name: str, source_folder: str, target_folder: str, container_name: str):
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
    """
    Safely move blob with proper error handling and fallback logic
    """
    try:
        # Check if source blob exists first
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(container_name)
        source_blob_path = f"{source_folder}/{source_filename}"

        # Check if source blob exists
        try:
            source_blob_client = container_client.get_blob_client(source_blob_path)
            source_blob_client.get_blob_properties()  # This will raise if blob doesn't exist

            # If we get here, blob exists, so move it
            move_blob(source_filename, source_folder, target_folder, container_name)
            logger.info(
                f"✅ Successfully moved {source_filename} from {source_folder} to {target_folder}"
            )

        except Exception as blob_check_error:
            if "BlobNotFound" in str(blob_check_error) or "does not exist" in str(blob_check_error):
                logger.warning(
                    f"⚠️ Source blob {source_blob_path} not found, checking other locations..."
                )

                # Try to find the blob in other common locations
                for check_folder in ["landing", "staging", "processed"]:
                    if check_folder == source_folder:
                        continue  # Skip the folder we already checked

                    try:
                        check_blob_path = f"{check_folder}/{source_filename}"
                        check_blob_client = container_client.get_blob_client(check_blob_path)
                        check_blob_client.get_blob_properties()

                        # Found it! Move from this location
                        move_blob(source_filename, check_folder, target_folder, container_name)
                        logger.info(
                            f"✅ Found and moved {source_filename} from {check_folder} to {target_folder}"
                        )
                        return

                    except Exception as e:  # nosec B112 - Continue searching other folders on error
                        logger.debug(f"Could not check {check_folder} for {source_filename}: {e}")
                        continue  # Keep looking

                logger.error(
                    f"❌ Could not find {source_filename} in any folder (landing, staging, processed)"
                )
            else:
                logger.error(f"❌ Unexpected error checking blob: {blob_check_error}")
                raise blob_check_error

    except Exception as move_error:
        logger.error(f"❌ Failed to move blob {source_filename}: {move_error}")


# Configuration and Data Classes
# ===============================


@dataclass
class ValidationResult:
    """Result of data validation operations."""

    is_valid: bool
    total_records: int
    valid_records: int
    invalid_records: int
    error_details: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ProcessingConfig:
    """Configuration for DTC file processing operations."""

    connection_string: str
    staging_table: str = "engage360_stg.stg_dtc_wellness_delta"
    rejection_table: str = "engage360_stg.dtc_rejection_log"
    error_threshold_pct: float = 10.0
    max_retries: int = 3
    retry_delay_seconds: int = 5
    auto_notify: bool = True
    timeout_seconds: int = 300
    expected_filename_pattern: str = "MedicalGuardian_DTCWellness_*_Delta.csv"


@dataclass
class ProcessingResult:
    """Result of a processing operation."""

    success: bool
    message: str
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    duration_seconds: float = 0.0
    error_details: Optional[str] = None
    validation_result: Optional[ValidationResult] = None


@dataclass
class DTCProcessingContext:
    """Context object for DTC processing workflow."""

    file_batch_id: uuid.UUID
    source_filename: str
    file_path: str
    # campaign_id: Optional[uuid.UUID]
    uploaded_by_user: Optional[str]
    file_size_bytes: Optional[int]
    config: ProcessingConfig
    connection: pymssql.Connection


# Custom Exceptions
# =================


class DTCProcessingError(Exception):
    """Base exception for DTC processing errors."""

    pass


class TransientError(DTCProcessingError):
    """Exception for transient errors that can be retried."""

    pass


class PermanentError(DTCProcessingError):
    """Exception for permanent errors that should not be retried."""

    pass


class ValidationError(DTCProcessingError):
    """Exception for data validation failures."""

    pass


# Logging Setup
# =============


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Set up structured logging for the DTC file processor."""

    logger = logging.getLogger("dtc_file_processor")
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# DTC Data Validation Schema
# ==========================


def get_dtc_schema() -> DataFrameSchema:
    """Define the expected schema for DTC wellness CSV files."""

    return DataFrameSchema(
        {
            "partner_name": Column(str, nullable=True),
            "campaign_name_source": Column(str, nullable=True),
            "language_pref": Column(
                str, nullable=True, checks=Check.isin(["EN", "ES", "Other", None])
            ),
            "salesforce_account_number": Column(
                str, nullable=False, checks=Check.str_length(min_value=1)
            ),
            "healthcare_member_id": Column(str, nullable=True),
            "member_first_name": Column(str, nullable=True),
            "member_last_name": Column(str, nullable=True),
            "member_phone_number": Column(str, nullable=True),
            "customer_timezone": Column(str, nullable=True),
            "member_dob": Column(str, nullable=True),
            "member_email": Column(str, nullable=True),
            "member_address_street": Column(str, nullable=True),
            "member_address_city": Column(str, nullable=True),
            "member_address_state": Column(str, nullable=True),
            "member_address_zip": Column(str, nullable=True),
            "member_address_country": Column(str, nullable=True),
            "caregiver_first_name": Column(
                str, nullable=True, checks=Check.str_matches(r"^[A-Za-z ]+$", ignore_na=True)
            ),
            "caregiver_last_name": Column(
                str, nullable=True, checks=Check.str_matches(r"^[A-Za-z ]+$", ignore_na=True)
            ),
            "caregiver_phone_number": Column(str, nullable=True),
            "caregiver_email": Column(str, nullable=True),  # ADDED
            "device_udi": Column(str, nullable=True),
            "device_name": Column(str, nullable=True),
            "is_device_callable": Column(
                str,
                nullable=True,
                checks=Check.isin(["Y", "N", "Yes", "No", "True", "False", "1", "0", None]),
            ),
            "device_phone_number": Column(str, nullable=True),
            "checkin_time": Column(str, nullable=True, checks=Check.isin(["AM", "PM", "EV", None])),
            "enrollment_status": Column(
                str, nullable=False, checks=Check.isin(["enroll", "update", "unenroll"])
            ),
            "unenrollment_reason": Column(str, nullable=True),
        },
        strict=False,
    )  # Allow additional columns


# DTC Validation Functions
# ========================


def standardize_phone(phone: str) -> Optional[str]:
    """
    Standardize phone number to E.164 format.

    Args:
        phone: Raw phone number string

    Returns:
        Standardized phone number in E.164 format or None if invalid
    """
    if not phone or pd.isna(phone):
        return None

    # Convert to string and strip whitespace
    phone_str = str(phone).strip()

    # If already in E.164 format (starts with +), validate and return
    if phone_str.startswith("+"):
        # Remove + and any non-numeric characters after it
        digits_only = "".join(c for c in phone_str[1:] if c.isdigit())
        # E.164 format allows 7-15 digits after the +
        if 7 <= len(digits_only) <= 15:
            return f"+{digits_only}"
        else:
            return None

    # Remove all non-numeric characters
    digits_only = "".join(c for c in phone_str if c.isdigit())

    # Handle different phone number formats
    if len(digits_only) == 10 and digits_only[0] in "23456789":
        # Standard 10-digit US number
        return f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only[0] == "1" and digits_only[1] in "23456789":
        # 11-digit number starting with 1
        return f"+{digits_only}"
    elif 7 <= len(digits_only) <= 15:
        # International number without + prefix
        # For numbers that don't fit US patterns but are valid international lengths
        return f"+{digits_only}"

    return None


def validate_timezone(timezone_str: str) -> Optional[str]:
    """
    Validate and convert timezone to standardized Olson format.
    NOW EXPANDED to cover all 11 US time zones, including territories.

    Args:
        timezone_str: Raw timezone string

    Returns:
        Standardized Olson timezone identifier or None if invalid
    """
    if not timezone_str or pd.isna(timezone_str):
        return None

    clean_tz = str(timezone_str).strip()

    # Direct Olson matches
    # Direct Olson matches - EXPANDED LIST
    valid_olson = [
        "America/New_York",  # Eastern
        "America/Chicago",  # Central
        "America/Denver",  # Mountain
        "America/Los_Angeles",  # Pacific
        "America/Anchorage",  # Alaska
        "Pacific/Honolulu",  # Hawaii
        "America/Phoenix",  # Mountain (no DST)
        # --- NEW ADDITIONS TO COVER ALL ZONES ---
        "America/Puerto_Rico",  # Atlantic Time (AST)
        "Pacific/Samoa",  # Samoa Standard Time (SST)
        "Pacific/Guam",  # Chamorro Standard Time (ChST)
        "Pacific/Wake",  # Wake Island Time (WAKT)
        "America/Adak",  # Hawaii-Aleutian Time (for Aleutian Islands)
        "Etc/GMT+12",  # Baker/Howland Island Time (UTC-12)
    ]

    if clean_tz in valid_olson:
        return clean_tz

    # Friendly name mappings - EXPANDED MAPPINGS
    timezone_mappings = {
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "EASTERN": "America/New_York",
        "ET": "America/New_York",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "CENTRAL": "America/Chicago",
        "CT": "America/Chicago",
        "MST": "America/Denver",
        "MDT": "America/Denver",
        "MOUNTAIN": "America/Denver",
        "MT": "America/Denver",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        "PACIFIC": "America/Los_Angeles",
        "PT": "America/Los_Angeles",
        "AKST": "America/Anchorage",
        "AKDT": "America/Anchorage",
        "ALASKA": "America/Anchorage",
        "HST": "Pacific/Honolulu",
        "HAWAII": "Pacific/Honolulu",
        "AZT": "America/Phoenix",
        # --- NEW ADDITIONS TO COVER ALL ZONES ---
        "AST": "America/Puerto_Rico",
        "ATLANTIC": "America/Puerto_Rico",
        "SST": "Pacific/Samoa",
        "SAMOA": "Pacific/Samoa",
        "CHST": "Pacific/Guam",
        "CHAMORRO": "Pacific/Guam",
        # Daylight Saving Time abbreviations (map to same IANA zones as standard time)
        "ADT": "America/Puerto_Rico",  # Atlantic Daylight Time
        "HADT": "America/Adak",  # Hawaii-Aleutian Daylight Time
        "HAST": "America/Adak",  # Hawaii-Aleutian Standard Time (different from HST)
        # Additional standard time zones that might be received
        "EASTERN DAYLIGHT": "America/New_York",
        "CENTRAL DAYLIGHT": "America/Chicago",
        "MOUNTAIN DAYLIGHT": "America/Denver",
        "PACIFIC DAYLIGHT": "America/Los_Angeles",
        "ATLANTIC DAYLIGHT": "America/Puerto_Rico",
        "ALASKA DAYLIGHT": "America/Anchorage",
    }

    return timezone_mappings.get(clean_tz.upper())


def proper_case(name: str) -> Optional[str]:
    """Convert name to proper case with special handling for common patterns."""
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


# Database Connection Management
# ==============================
class DatabaseManager:
    """Manages database connections using pymssql, either fetching from Key Vault or using a raw conn string,
    and applies retry logic for transient failures."""

    def __init__(self, secret_or_conn: str, key_vault_url_env: str = "KEY_VAULT_URL"):
        self.logger = logging.getLogger("dtc_file_processor")
        self.raw_conn_string = None
        self.secret_name = None

        # detect if what was passed is a full conn string or a vault secret name
        if ";" in secret_or_conn and "=" in secret_or_conn:
            # treat as a raw connection string
            self.raw_conn_string = secret_or_conn
            self.logger.debug("Initialized with raw connection string (no Key Vault).")
        else:
            # treat as a Key Vault secret name
            self.secret_name = secret_or_conn
            key_vault_url = os.environ.get(key_vault_url_env)
            if not key_vault_url:
                raise ValueError(f"{key_vault_url_env} environment variable is not set")
            self.key_vault_url = key_vault_url
            self.logger.debug(
                f"Initialized with Key Vault secret '{self.secret_name}' at {self.key_vault_url}"
            )

    def _fetch_connection_string(self) -> str:
        """Pulled only when using Key Vault mode."""
        try:
            self.logger.info(
                f"🔐 Fetching secret '{self.secret_name}' from Key Vault: {self.key_vault_url}"
            )
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=self.key_vault_url, credential=credential)
            secret = client.get_secret(self.secret_name)

            if not secret or not secret.value:
                raise ValueError(f"Secret '{self.secret_name}' was retrieved but is empty.")
            self.logger.info("✅ Secret retrieved successfully.")
            return secret.value

        except Exception as e:
            self.logger.error(f"❌ Failed to fetch secret from Key Vault: {e}", exc_info=True)
            raise

    def _get_pymssql_kwargs(self, conn_string: str) -> dict:
        """Parse an Azure-style conn string into a kwargs dict for pymssql."""
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
                # Check for port
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

        self.logger.info(f"Connecting to server:   {conn_params.get('server')}")
        self.logger.info(f"Database:              {conn_params.get('database')}")
        self.logger.info(f"User:                  {conn_params.get('user')}")

        return conn_params

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TransientError),
    )
    def get_connection(self) -> pymssql.Connection:
        """Establish and return a DB connection using pymssql."""
        try:
            # choose source
            if self.raw_conn_string:
                raw = self.raw_conn_string
                self.logger.debug("Using provided raw connection string.")
            else:
                raw = self._fetch_connection_string()

            conn_kwargs = self._get_pymssql_kwargs(raw)
            self.logger.info("Attempting database connection with pymssql...")
            conn = pymssql.connect(**conn_kwargs, login_timeout=30)
            conn.autocommit(False)  # Set autocommit to False to manage transactions
            self.logger.info("Database connection established successfully")
            return conn

        except pymssql.Error as e:
            self.logger.error(f"Failed to connect to DB with pymssql: {e}", exc_info=True)
            raise TransientError(f"Database connection failed: {e}")

        except Exception as e:
            self.logger.error(f"Unexpected error during DB connection: {e}", exc_info=True)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TransientError),
    )
    def execute_with_retry(
        self, connection: pymssql.Connection, sql: str, params: Optional[tuple] = None
    ) -> Any:  # pymssql cursor is not easily typed
        """Run SQL with retry logic for transient errors."""
        try:
            cursor = connection.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return cursor

        except pymssql.Error as e:
            msg = str(e).lower()
            if any(term in msg for term in ("timeout", "connection", "network", "lost connection")):
                self.logger.warning(f"Retryable DB error: {e}")
                raise TransientError(f"Retryable DB error: {e}")
            else:
                self.logger.error(f"Permanent DB error: {e}", exc_info=True)
                raise PermanentError(f"Permanent DB error: {e}")


# Core Processing Functions Following Industry Standards
# ======================================================


def extract(file_path: str, context: DTCProcessingContext) -> Tuple[pd.DataFrame, ProcessingResult]:
    """
    Step 1: Extract and parse the DTC CSV file with schema validation.

    Args:
        file_path: Path to the CSV file
        context: Processing context

    Returns:
        Tuple of (DataFrame, ProcessingResult)
    """
    logger = logging.getLogger("dtc_file_processor")
    start_time = time.time()

    logger.info("STEP 1: EXTRACT - Reading and parsing DTC CSV file")
    logger.info(f"File path: {file_path}")

    try:
        # Validate file exists and is readable
        # if not Path(file_path).exists():
        #    raise PermanentError(f"File not found: {file_path}")

        # Read CSV file
        # df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        # df = download_blob_as_dataframe(f"{source_filename}", container_name=os.environ["AZURE_CONTAINER_NAME"])
        df = download_blob_as_dataframe(
            f"landing/{context.source_filename}", os.environ["AZURE_CONTAINER_NAME"]
        )

        # Replace empty strings with None for proper NULL handling
        df = df.replace("", None)

        # Add processing metadata
        df["file_batch_id"] = str(context.file_batch_id)
        df["source_filename"] = context.source_filename
        df["row_number_in_file"] = range(1, len(df) + 1)
        df["load_timestamp"] = datetime.now(timezone.utc)
        df["file_size_bytes"] = context.file_size_bytes
        df["total_rows_in_file"] = len(df)
        df["uploaded_by_user"] = context.uploaded_by_user

        # Schema validation
        schema = get_dtc_schema()
        try:
            schema.validate(df, lazy=True)
            logger.info("✅ Schema validation passed")
        except pa.errors.SchemaErrors as e:
            logger.warning(f"Schema validation issues found: {len(e.failure_cases)} failures")
            # Log but don't fail - let staging handle validation

        duration = time.time() - start_time
        logger.info(f"✅ File extracted successfully: {len(df)} records in {duration:.2f}s")

        return df, ProcessingResult(
            success=True,
            message=f"File extracted successfully: {len(df)} records",
            records_processed=len(df),
            records_succeeded=len(df),
            duration_seconds=duration,
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ File extraction failed: {e}")

        return pd.DataFrame(), ProcessingResult(
            success=False,
            message=f"File extraction failed: {e}",
            duration_seconds=duration,
            error_details=str(e),
        )


def load_to_staging(df: pd.DataFrame, context: DTCProcessingContext) -> ProcessingResult:
    """
    Step 2: Load raw data into staging table with light validation.

    Args:
        df: DataFrame to load
        context: Processing context

    Returns:
        ProcessingResult
    """
    logger = logging.getLogger("dtc_file_processor")
    start_time = time.time()

    logger.info("STEP 2: LOAD_TO_STAGING - Loading data with comprehensive DTC validation")
    logger.info(f"Records to load: {len(df)}")

    try:
        db_manager = DatabaseManager(context.config.connection_string)

        # Clear existing staging data for this batch
        cleanup_sql = f"""DELETE FROM {context.config.staging_table} WHERE file_batch_id = %s"""
        cursor = db_manager.execute_with_retry(
            context.connection, cleanup_sql, (str(context.file_batch_id),)
        )

        # 🔥 NEW: COMPREHENSIVE VALIDATION INTEGRATION
        # ============================================
        logger.info("Performing comprehensive data validation and cleansing...")
        # Set cleansing timestamps
        cleansing_start_time = datetime.now(timezone.utc)
        df_validated, validation_errors = validate_and_cleanse_data_before_insert(df, context)

        # Check error threshold
        total_records = len(df)
        error_records = len(validation_errors)
        error_rate = (error_records / total_records * 100) if total_records > 0 else 0

        if error_rate > context.config.error_threshold_pct:
            raise ValidationError(
                f"Error rate {error_rate:.2f}% exceeds threshold {context.config.error_threshold_pct}%"
            )

        # 🔥 NEW: FINAL PRE-INSERT VALIDATION
        # ==================================
        is_valid, final_errors = pre_insert_final_validation(df_validated)
        if not is_valid:
            raise ValidationError(f"Final validation failed: {'; '.join(final_errors)}")

        # Filter to only process valid records
        df_for_insert = df_validated[df_validated["processing_status"] == "VALIDATED"].copy()

        # Set completion timestamp
        cleansing_end_time = datetime.now(timezone.utc)
        df_for_insert["cleansing_started_ts"] = cleansing_start_time
        df_for_insert["cleansing_completed_ts"] = cleansing_end_time

        if len(df_for_insert) == 0:
            raise ValidationError("No valid records to insert after validation")

        # 🔄 EXISTING: Data preparation for insert (MODIFIED to use df_for_insert)
        # ========================================================================

        # Define the exact columns that exist in the staging table
        # Based on the SQL schema in your document
        staging_columns = [
            "file_batch_id",
            "source_filename",
            "row_number_in_file",
            "load_timestamp",
            "file_load_date",
            "processing_status",
            "error_message",
            "campaign_id",
            # 🔥 ADD METADATA COLUMNS:
            "file_size_bytes",
            "total_rows_in_file",
            "uploaded_by_user",
            "cleansing_started_ts",
            "cleansing_completed_ts",
            "enrollment_started_ts",
            # Raw CSV columns
            "partner_name",
            "campaign_name_source",
            "language_pref",
            "salesforce_account_number",
            "healthcare_member_id",
            "member_first_name",
            "member_last_name",
            "member_phone_number",
            "customer_timezone",
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
            "device_udi",
            "device_name",
            "is_device_callable",
            "device_phone_number",
            "checkin_time",
            "enrollment_status",
            "unenrollment_reason",
            # Clean columns
            "first_name_clean",
            "last_name_clean",
            "primary_phone_clean",
            "caregiver_first_clean",
            "caregiver_last_clean",
            "caregiver_phone_clean",
            "caregiver_email_clean",
            "device_phone_clean",
            "dob_clean",
            "timezone_clean",
            "is_device_callable_clean",
        ]
        # Prepare data for insertion - ensure all columns exist and are in the right order
        insert_data = []
        for _, row in df_for_insert.iterrows():
            row_data = []
            for col in staging_columns:
                if col == "file_batch_id":
                    row_data.append(str(context.file_batch_id))
                elif col == "source_filename":
                    row_data.append(context.source_filename)
                elif col == "row_number_in_file":
                    row_data.append(row.get("row_number_in_file", 1))
                elif col == "load_timestamp":
                    row_data.append(datetime.now(timezone.utc))
                elif col == "file_load_date":
                    row_data.append(datetime.now(timezone.utc).date())
                elif col == "processing_status":
                    row_data.append(row.get("processing_status", "PENDING"))
                elif col == "error_message":
                    row_data.append(row.get("error_message", None))
                elif col == "campaign_id":
                    row_data.append(getattr(context, "campaign_id", None))
                # 🔥 ADD MISSING FIELD HANDLERS:
                elif col == "file_size_bytes":
                    row_data.append(context.file_size_bytes)
                elif col == "total_rows_in_file":
                    row_data.append(row.get("total_rows_in_file", len(df_for_insert)))
                elif col == "uploaded_by_user":
                    row_data.append(context.uploaded_by_user)
                elif col == "cleansing_started_ts":
                    row_data.append(row.get("cleansing_started_ts", None))
                elif col == "cleansing_completed_ts":
                    row_data.append(row.get("cleansing_completed_ts", None))
                elif col == "enrollment_started_ts":
                    row_data.append(row.get("enrollment_started_ts", None))
                else:
                    # Get the value from the row, defaulting to None if not present
                    value = row.get(col, None)
                    # 🔥 CRITICAL: All values are now guaranteed clean from validation
                    row_data.append(value)

            insert_data.append(tuple(row_data))

        # Build the INSERT SQL with proper parameter placeholders
        placeholders = ",".join(["%s" for _ in staging_columns])
        insert_sql = f"""
        INSERT INTO {context.config.staging_table} 
        ({','.join(staging_columns)}) 
        VALUES ({placeholders})
        """

        # Use executemany for bulk insert (don't use execute_with_retry for bulk operations)
        cursor = context.connection.cursor()

        logger.info(f"Executing bulk insert of {len(insert_data)} records...")
        logger.debug(f"Insert SQL: {insert_sql}")
        logger.debug(f"Sample data (first row): {insert_data[0] if insert_data else 'No data'}")

        cursor.executemany(insert_sql, insert_data)
        context.connection.commit()

        # 🔄 EXISTING: Results reporting (ENHANCED)
        # =========================================
        valid_records = len(df_for_insert)
        invalid_records = len(validation_errors)

        duration = time.time() - start_time
        logger.info(f"✅ Staging load completed in {duration:.2f}s")
        logger.info(f"   Total records: {total_records}")
        logger.info(f"   Valid records: {valid_records}")
        logger.info(f"   Invalid records: {invalid_records}")
        logger.info(f"   Error rate: {error_rate:.2f}%")

        # Return enhanced validation result
        validation_result = ValidationResult(
            is_valid=error_rate <= context.config.error_threshold_pct,
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            error_details=validation_errors,
        )

        return ProcessingResult(
            success=True,
            message=f"Staging load completed: {valid_records}/{total_records} valid records",
            records_processed=total_records,
            records_succeeded=valid_records,
            records_failed=invalid_records,
            duration_seconds=duration,
            validation_result=validation_result,
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Staging load failed: {e}")
        logger.error(f"Error details: {str(e)}")

        # Log additional debugging information
        if "insert_sql" in locals():
            logger.error(f"Failed SQL: {insert_sql}")
        if "insert_data" in locals() and insert_data:
            logger.error(f"Sample data: {insert_data[0]}")

        return ProcessingResult(
            success=False,
            message=f"Staging load failed: {e}",
            duration_seconds=duration,
            error_details=str(e),
        )


def validate_and_cleanse_data_before_insert(
    df: pd.DataFrame, context: DTCProcessingContext
) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    Comprehensive data validation and cleansing before database insertion.
    Returns cleansed DataFrame and list of validation errors.
    """
    logger = logging.getLogger("dtc_file_processor")
    validation_errors = []
    df_clean = df.copy()

    # Initialize all the *_clean columns that the SQL expects
    logger.info("Initializing clean columns for validation...")

    # Initialize all clean columns with None
    df_clean["first_name_clean"] = None
    df_clean["last_name_clean"] = None
    df_clean["primary_phone_clean"] = None
    df_clean["caregiver_first_clean"] = None
    df_clean["caregiver_last_clean"] = None
    df_clean["caregiver_phone_clean"] = None
    df_clean["caregiver_email_clean"] = None  # ADDED
    df_clean["device_phone_clean"] = None
    df_clean["processing_status"] = "PENDING"
    df_clean["error_message"] = None
    df_clean["dob_clean"] = None
    df_clean["timezone_clean"] = None
    df_clean["is_device_callable_clean"] = None
    # 🔥 ADD MISSING TIMESTAMP COLUMNS:
    cleansing_start_time = datetime.now(timezone.utc)
    df_clean["cleansing_started_ts"] = cleansing_start_time
    df_clean["cleansing_completed_ts"] = None  # Will be set at end
    df_clean["enrollment_started_ts"] = None  # Will be set during enrollment
    logger.info(f"Initialized clean columns. DataFrame now has {len(df_clean.columns)} columns")

    logger.info("Starting comprehensive data validation and cleansing...")

    # Audit logging function for status changes
    def log_enrollment_status_change(connection, member_id: str, campaign_id: str, 
                                     previous_status: Optional[str], new_status: str, 
                                     change_source: str, change_details: Optional[str] = None):
        """Log status changes to member_enrollment_status_history table for CSV processing."""
        try:
            # Calculate duration since last change
            duration_hours = None
            if previous_status:
                last_change_query = """
                    SELECT TOP 1 change_timestamp 
                    FROM engage360.member_enrollment_status_history 
                    WHERE member_id = %s AND campaign_id = %s 
                    ORDER BY change_timestamp DESC
                """
                cursor = connection.cursor()
                cursor.execute(last_change_query, (member_id, campaign_id))
                last_change = cursor.fetchone()
                
                if last_change:
                    from datetime import datetime, timezone
                    current_time = datetime.now(timezone.utc)
                    last_time = last_change[0]
                    
                    if last_time.tzinfo is None:
                        import pytz
                        last_time = pytz.UTC.localize(last_time)
                    
                    duration_delta = current_time - last_time
                    duration_hours = round(duration_delta.total_seconds() / 3600, 2)
            
            # Insert audit record
            audit_query = """
                INSERT INTO engage360.member_enrollment_status_history 
                (member_id, campaign_id, previous_status, new_status, duration_since_last_change_hours, 
                 change_source, change_details)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor = connection.cursor()
            cursor.execute(audit_query, (
                member_id, campaign_id, previous_status, new_status, 
                duration_hours, change_source, change_details
            ))
            
            logger.info(f"📋 [DTC-AUDIT] Status change logged: {member_id} {previous_status}→{new_status} ({change_source})")
            
        except Exception as e:
            logger.error(f"❌ [DTC-AUDIT] Failed to log status change: {e}")

    # Step 1: Handle Empty Values and NULL Conversion
    def clean_empty_values(value, target_type="string"):
        """Convert various empty representations to proper NULL values"""
        if pd.isna(value) or value is None:
            return None

        str_val = str(value).strip().upper()

        # Common empty value representations
        empty_indicators = ["", "NULL", "N/A", "NA", "NONE", "EMPTY", "BLANK", "-"]

        if str_val in empty_indicators:
            return None

        # Return original value if not empty
        return str(value).strip() if target_type == "string" else value

    # Step 2: Column-by-Column Validation and Cleansing
    for idx, row in df_clean.iterrows():
        row_errors = []
        row_id = f"Row {idx + 1} (Account: {row.get('salesforce_account_number', 'Unknown')})"

        # REQUIRED FIELD VALIDATION
        # ========================

        # Partner Name
        partner_name = clean_empty_values(row.get("partner_name"))
        if not partner_name:
            row_errors.append(f"{row_id}: Missing required partner_name")
        elif len(partner_name) > 100:
            row_errors.append(f"Invalid partner_name: '{partner_name}' (exceeds the 100 character limit)")
        elif partner_name != "Medical Guardian":
            row_errors.append(
                f"Invalid partner_name: '{partner_name}' (expected 'Medical Guardian')"
            )
        df_clean.loc[idx, "partner_name"] = partner_name

        # Salesforce Account Number
        sf_account = clean_empty_values(row.get("salesforce_account_number"))
        if not sf_account:
            row_errors.append("Missing required salesforce_account_number")
        else:
            # Validate numeric and length
            try:
                sf_number = str(sf_account).strip()
                if not sf_number.isdigit():
                    row_errors.append(f"salesforce_account_number must be numeric: '{sf_account}'")
                elif len(sf_number) < 4 or len(sf_number) > 15:
                    row_errors.append(
                        f"salesforce_account_number invalid length: '{sf_account}' (4-15 digits expected)"
                    )
            except Exception:
                row_errors.append(f"salesforce_account_number conversion error: '{sf_account}'")
        df_clean.loc[idx, "salesforce_account_number"] = sf_account

        # Enrollment Status
        enrollment_status = clean_empty_values(row.get("enrollment_status"))
        valid_statuses = ["enroll", "update", "unenroll"]
        if not enrollment_status:
            row_errors.append("Missing required enrollment_status")
        elif enrollment_status.lower() not in valid_statuses:
            row_errors.append(
                f"Invalid enrollment_status: '{enrollment_status}' (must be: {valid_statuses})"
            )
        df_clean.loc[idx, "enrollment_status"] = (
            enrollment_status.lower() if enrollment_status else None
        )

        # Language Preference
        language_pref = clean_empty_values(row.get("language_pref"))
        valid_languages = ["EN", "ES", "Other"]
        if language_pref and language_pref.upper() not in valid_languages:
            row_errors.append(
                f"Invalid language_pref: '{language_pref}' (must be: {valid_languages})"
            )
        df_clean.loc[idx, "language_pref"] = (
            language_pref.upper() if language_pref else "EN"
        )  # Default to EN

        # PHONE NUMBER VALIDATION
        # ======================

        # Member Phone Number
        member_phone = clean_empty_values(row.get("member_phone_number"))
        if member_phone:
            standardized_phone = standardize_phone(member_phone)
            if not standardized_phone:
                row_errors.append(f"Invalid member_phone_number format: '{member_phone}'")
            df_clean.loc[idx, "member_phone_number"] = standardized_phone
            df_clean.loc[idx, "primary_phone_clean"] = standardized_phone
        else:
            df_clean.loc[idx, "member_phone_number"] = None
            df_clean.loc[idx, "primary_phone_clean"] = None

        # Caregiver Phone Number
        # 🔥 FIXED: Caregiver Phone Number Processing
        caregiver_phone = clean_empty_values(row.get("caregiver_phone_number"))
        if caregiver_phone:
            standardized_caregiver_phone = standardize_phone(caregiver_phone)
            if not standardized_caregiver_phone:
                row_errors.append(f"Invalid caregiver_phone_number format: '{caregiver_phone}'")
            df_clean.loc[idx, "caregiver_phone_number"] = standardized_caregiver_phone
            df_clean.loc[idx, "caregiver_phone_clean"] = standardized_caregiver_phone
        else:
            df_clean.loc[idx, "caregiver_phone_number"] = None
            df_clean.loc[idx, "caregiver_phone_clean"] = None

        # NAME VALIDATION AND PROPER CASE
        # ===============================

        # Member First Name
        first_name = clean_empty_values(row.get("member_first_name"))
        if first_name:
            # Remove special characters but allow letters, spaces, and apostrophes
            cleaned_first = re.sub(r"[^a-zA-Z\s']", "", first_name)
            if len(cleaned_first) > 50:
                row_errors.append("member_first_name exceeds maximum length of 50 characters")
                cleaned_first = None

            if cleaned_first:
                proper_first = proper_case(cleaned_first)
                df_clean.loc[idx, "member_first_name"] = proper_first
                df_clean.loc[idx, "first_name_clean"] = proper_first
            else:
                df_clean.loc[idx, "member_first_name"] = None
                df_clean.loc[idx, "first_name_clean"] = None
        else:
            df_clean.loc[idx, "member_first_name"] = None
            df_clean.loc[idx, "first_name_clean"] = None
            if enrollment_status and enrollment_status.lower() == "enroll":
                row_errors.append("member_first_name required for new enrollments")

        # Device Phone Number
        device_phone = clean_empty_values(row.get("device_phone_number"))
        if device_phone:
            standardized_device_phone = standardize_phone(device_phone)
            if not standardized_device_phone:
                row_errors.append(f"Invalid device_phone_number format: '{device_phone}'")
            df_clean.loc[idx, "device_phone_number"] = standardized_device_phone
            df_clean.loc[idx, "device_phone_clean"] = standardized_device_phone
        else:
            df_clean.loc[idx, "device_phone_number"] = None
            df_clean.loc[idx, "device_phone_clean"] = None

        # Member Last Name
        last_name = clean_empty_values(row.get("member_last_name"))
        if last_name:
            # Remove special characters but allow letters, spaces, and apostrophes
            cleaned_last = re.sub(r"[^a-zA-Z\s']", "", last_name)
            if len(cleaned_last) > 50:
                row_errors.append("member_last_name exceeds maximum length of 50 characters")
                cleaned_last = None

            if cleaned_last:
                proper_last = proper_case(cleaned_last)
                df_clean.loc[idx, "member_last_name"] = proper_last
                df_clean.loc[idx, "last_name_clean"] = proper_last
            else:
                df_clean.loc[idx, "member_last_name"] = None
                df_clean.loc[idx, "last_name_clean"] = None
        else:
            df_clean.loc[idx, "member_last_name"] = None
            df_clean.loc[idx, "last_name_clean"] = None
            if enrollment_status and enrollment_status.lower() == "enroll":
                row_errors.append("member_last_name required for new enrollments")

        # Caregiver Names
        # 🔥 FIXED: Caregiver Names Processing
        caregiver_first = clean_empty_values(row.get("caregiver_first_name"))
        if caregiver_first:
            # Remove special characters but allow letters, spaces, and apostrophes
            cleaned_caregiver_first = re.sub(r"[^a-zA-Z\s']", "", caregiver_first)
            if len(cleaned_caregiver_first) > 50:
                row_errors.append("caregiver_first_name exceeds maximum length of 50 characters")
                cleaned_caregiver_first = None

            if cleaned_caregiver_first:
                proper_caregiver_first = proper_case(cleaned_caregiver_first)
                df_clean.loc[idx, "caregiver_first_name"] = proper_caregiver_first
                df_clean.loc[idx, "caregiver_first_clean"] = proper_caregiver_first
            else:
                df_clean.loc[idx, "caregiver_first_name"] = None
                df_clean.loc[idx, "caregiver_first_clean"] = None
        else:
            df_clean.loc[idx, "caregiver_first_name"] = None
            df_clean.loc[idx, "caregiver_first_clean"] = None

        caregiver_last = clean_empty_values(row.get("caregiver_last_name"))
        if caregiver_last:
            # Remove special characters but allow letters, spaces, and apostrophes
            cleaned_caregiver_last = re.sub(r"[^a-zA-Z\s']", "", caregiver_last)
            if len(cleaned_caregiver_last) > 50:
                row_errors.append("caregiver_last_name exceeds maximum length of 50 characters")
                cleaned_caregiver_last = None

            if cleaned_caregiver_last:
                proper_caregiver_last = proper_case(cleaned_caregiver_last)
                df_clean.loc[idx, "caregiver_last_name"] = proper_caregiver_last
                df_clean.loc[idx, "caregiver_last_clean"] = proper_caregiver_last
            else:
                df_clean.loc[idx, "caregiver_last_name"] = None
                df_clean.loc[idx, "caregiver_last_clean"] = None
        else:
            df_clean.loc[idx, "caregiver_last_name"] = None
            df_clean.loc[idx, "caregiver_last_clean"] = None

        # DATE VALIDATION
        # ==============

        # Date of Birth
        dob = clean_empty_values(row.get("member_dob"))
        if dob:
            try:
                # Try multiple date formats
                parsed_date = None
                date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"]

                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(str(dob), fmt).date()
                        break
                    except ValueError:
                        continue

                if not parsed_date:
                    row_errors.append(
                        f"Invalid date format for member_dob: '{dob}' (expected YYYY-MM-DD)"
                    )
                    df_clean.loc[idx, "member_dob"] = None
                    df_clean.loc[idx, "dob_clean"] = None
                else:
                    # Validate reasonable age range (18-120 years old)
                    today = datetime.now().date()
                    age = (today - parsed_date).days / 365.25
                    if age < 18 or age > 120:
                        row_errors.append(f"member_dob indicates unrealistic age: {age:.1f} years")

                    df_clean.loc[idx, "member_dob"] = parsed_date.strftime("%Y-%m-%d")
                    df_clean.loc[idx, "dob_clean"] = parsed_date
            except Exception as e:
                row_errors.append(f"member_dob parsing error: '{dob}' - {str(e)}")
                df_clean.loc[idx, "member_dob"] = None
                df_clean.loc[idx, "dob_clean"] = None
        else:
            df_clean.loc[idx, "member_dob"] = None
            df_clean.loc[idx, "dob_clean"] = None

        # TIMEZONE VALIDATION
        # ==================

        timezone_val = clean_empty_values(row.get("customer_timezone"))
        if timezone_val:
            validated_tz = validate_timezone(timezone_val)
            if not validated_tz:
                row_errors.append(f"Invalid timezone: '{timezone_val}'")
            df_clean.loc[idx, "customer_timezone"] = validated_tz
            df_clean.loc[idx, "timezone_clean"] = validated_tz
        else:
            df_clean.loc[idx, "customer_timezone"] = None
            df_clean.loc[idx, "timezone_clean"] = None

        # EMAIL VALIDATION
        # ===============

        # Member Email
        email = clean_empty_values(row.get("member_email"))
        if email:
            # Basic email format validation
            import re

            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, email):
                row_errors.append(f"Invalid email format: '{email}'")
            df_clean.loc[idx, "member_email"] = email.lower()
        else:
            df_clean.loc[idx, "member_email"] = None

        # Caregiver Email (ADDED)
        caregiver_email = clean_empty_values(row.get("caregiver_email"))
        if caregiver_email:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, caregiver_email):
                row_errors.append(f"Invalid caregiver_email format: '{caregiver_email}'")
            df_clean.loc[idx, "caregiver_email_clean"] = caregiver_email.lower()
        else:
            df_clean.loc[idx, "caregiver_email_clean"] = None

        # DEVICE VALIDATION
        # ================

        device_udi = clean_empty_values(row.get("device_udi"))
        device_name = clean_empty_values(row.get("device_name"))
        is_callable = clean_empty_values(row.get("is_device_callable"))

        # Device UDI validation
        if device_udi:
            df_clean.loc[idx, "device_udi"] = device_udi

            # If device exists, device_name should be provided
            if not device_name:
                row_errors.append("device_name required when device_udi provided")
            else:
                df_clean.loc[idx, "device_name"] = device_name

            # Validate is_device_callable
            if is_callable:
                callable_val = is_callable.upper()
                if callable_val in ["Y", "YES", "TRUE", "1"]:
                    df_clean.loc[idx, "is_device_callable"] = "Y"
                    df_clean.loc[idx, "is_device_callable_clean"] = 1
                    # If callable, device phone should be provided
                    if not device_phone:
                        row_errors.append("device_phone_number required when device is callable")
                elif callable_val in ["N", "NO", "FALSE", "0"]:
                    df_clean.loc[idx, "is_device_callable"] = "N"
                    df_clean.loc[idx, "is_device_callable_clean"] = 0
                else:
                    row_errors.append(f"Invalid is_device_callable: '{is_callable}' (must be Y/N)")
                    df_clean.loc[idx, "is_device_callable_clean"] = None
            else:
                df_clean.loc[idx, "is_device_callable"] = "N"  # Default to not callable
                df_clean.loc[idx, "is_device_callable_clean"] = 0
        else:
            # No device
            df_clean.loc[idx, "device_udi"] = None
            df_clean.loc[idx, "device_name"] = None
            df_clean.loc[idx, "is_device_callable"] = None
            df_clean.loc[idx, "device_phone_number"] = None
            df_clean.loc[idx, "is_device_callable_clean"] = None

        # CHECK-IN TIME VALIDATION
        # =======================

        checkin_time = clean_empty_values(row.get("checkin_time"))
        valid_checkin_times = ["AM", "PM", "EV"]
        if checkin_time:
            if checkin_time.upper() not in valid_checkin_times:
                row_errors.append(
                    f"Invalid checkin_time: '{checkin_time}' (must be: {valid_checkin_times})"
                )
            df_clean.loc[idx, "checkin_time"] = checkin_time.upper()
        else:
            df_clean.loc[idx, "checkin_time"] = None

        # UNENROLLMENT REASON VALIDATION
        # =============================

        unenroll_reason = clean_empty_values(row.get("unenrollment_reason"))
        if enrollment_status and enrollment_status.lower() == "unenroll":
            if not unenroll_reason:
                row_errors.append(
                    "unenrollment_reason required when enrollment_status = 'unenroll'"
                )
        df_clean.loc[idx, "unenrollment_reason"] = unenroll_reason

        # ADDRESS VALIDATION
        # =================

        # Clean address fields
        for addr_field in [
            "member_address_street",
            "member_address_city",
            "member_address_state",
            "member_address_zip",
            "member_address_country",
        ]:
            addr_val = clean_empty_values(row.get(addr_field))
            df_clean.loc[idx, addr_field] = addr_val

        # Default country to US if not specified
        if not df_clean.loc[idx, "member_address_country"]:
            df_clean.loc[idx, "member_address_country"] = "US"

        # BUSINESS LOGIC VALIDATION
        # ========================

        # Contact method validation - must have at least one way to contact
        if not member_phone and not email and not device_phone:
            row_errors.append(
                "At least one contact method required (member_phone, email, or device_phone)"
            )

        # RECORD ERROR STATUS
        # ==================

        if row_errors:
            validation_errors.append(
                {
                    "row_number": idx + 1,
                    "salesforce_account_number": sf_account,
                    "errors": row_errors,
                    "severity": "ERROR",
                }
            )
            df_clean.loc[idx, "processing_status"] = "VALIDATION_ERROR"
            df_clean.loc[idx, "error_message"] = "; ".join(row_errors)
        else:
            df_clean.loc[idx, "processing_status"] = "VALIDATED"
            df_clean.loc[idx, "error_message"] = None

    # SUMMARY LOGGING
    # ==============

    total_rows = len(df_clean)
    valid_rows = len(df_clean[df_clean["processing_status"] == "VALIDATED"])
    error_rows = len(validation_errors)

    # 🔥 SET COMPLETION TIMESTAMP:
    cleansing_end_time = datetime.now(timezone.utc)
    df_clean["cleansing_completed_ts"] = cleansing_end_time

    logger.info("Data validation completed:")
    logger.info(f"  Total rows: {total_rows}")
    logger.info(f"  Valid rows: {valid_rows}")
    logger.info(f"  Error rows: {error_rows}")
    logger.info(f"  Success rate: {(valid_rows/total_rows*100):.1f}%")

    if validation_errors:
        logger.warning(f"Found {len(validation_errors)} rows with validation errors:")
        for error in validation_errors[:5]:  # Show first 5 errors
            logger.warning(f"  Row {error['row_number']}: {'; '.join(error['errors'][:2])}...")

    return df_clean, validation_errors


def pre_insert_final_validation(df_clean: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Final validation before database insertion to catch any remaining issues.
    """
    final_errors = []

    # Check for any remaining empty strings in critical fields
    critical_fields = ["salesforce_account_number", "enrollment_status"]

    for field_name in critical_fields:
        empty_count = len(df_clean[df_clean[field_name].isin(["", None])])
        if empty_count > 0:
            final_errors.append(f"Found {empty_count} empty values in critical field: {field_name}")

    # Check data types that will be sent to database
    for idx, row in df_clean.iterrows():
        # Ensure all values are either None or properly formatted strings
        for col in df_clean.columns:
            value = row[col]
            if value is not None and not isinstance(value, (str, int, float, datetime, date)):
                final_errors.append(f"Row {idx+1}, Column {col}: Invalid data type {type(value)}")

    return len(final_errors) == 0, final_errors


def validate_data(context: DTCProcessingContext) -> ProcessingResult:
    """
    Step 3: Perform comprehensive business rule validation.

    Args:
        context: Processing context

    Returns:
        ProcessingResult
    """
    logger = logging.getLogger("dtc_file_processor")
    start_time = time.time()

    logger.info("STEP 3: VALIDATE_DATA - Performing comprehensive business validation")

    try:
        db_manager = DatabaseManager(context.config.connection_string)

        # Update processing status to validation
        update_sql = f"""
        UPDATE {context.config.staging_table}
        SET processing_status = 'VALIDATING', processing_step = 'BUSINESS_VALIDATION'
        WHERE file_batch_id = %s AND processing_status = 'PENDING'
        """

        cursor = db_manager.execute_with_retry(
            context.connection, update_sql, (str(context.file_batch_id),)
        )

        # Apply comprehensive cleansing with DTC validation functions
        cleansing_sql = f"""
        UPDATE stg
        SET 
            -- Org lookup (partner_name → org_id)
            org_id = o.org_id,
            
            -- Phone number cleansing using built-in functions
            primary_phone_clean = engage360_stg.fn_standardize_phone(member_phone_number),
            caregiver_phone_clean = engage360_stg.fn_standardize_phone(caregiver_phone_number),
            device_phone_clean = engage360_stg.fn_standardize_phone(device_phone_number),
            
            -- Name cleansing with proper case
            first_name_clean = engage360_stg.fn_proper_case(member_first_name),
            last_name_clean = engage360_stg.fn_proper_case(member_last_name),
            caregiver_first_clean = engage360_stg.fn_proper_case(caregiver_first_name),
            caregiver_last_clean = engage360_stg.fn_proper_case(caregiver_last_name),
            
            -- Date cleansing
            dob_clean = TRY_CONVERT(DATE, member_dob),
            
            -- Timezone validation
            timezone_clean = engage360_stg.fn_validate_timezone(customer_timezone),
            
            -- Boolean conversion
            is_device_callable_clean = CASE 
                WHEN UPPER(LTRIM(RTRIM(is_device_callable))) IN ('Y','YES','TRUE','1') THEN 1
                WHEN UPPER(LTRIM(RTRIM(is_device_callable))) IN ('N','NO','FALSE','0') THEN 0
                ELSE NULL
            END,
            
            processing_step = 'VALIDATED',
            updated_ts = SYSDATETIMEOFFSET()
            
        FROM {context.config.staging_table} stg
        LEFT JOIN engage360.orgs o ON LTRIM(RTRIM(stg.partner_name)) = o.org_name
        WHERE stg.file_batch_id = %s AND stg.processing_status = 'VALIDATING'
        """

        cursor = db_manager.execute_with_retry(
            context.connection, cleansing_sql, (str(context.file_batch_id),)
        )

        # Mark successfully validated records
        mark_validated_sql = f"""
        UPDATE {context.config.staging_table}
        SET processing_status = 'VALIDATED'
        WHERE file_batch_id = %s AND processing_status = 'VALIDATING'
        """

        cursor = db_manager.execute_with_retry(
            context.connection, mark_validated_sql, (str(context.file_batch_id),)
        )

        # Get validation results
        result_sql = f"""
        SELECT 
            COUNT(*) as total_processed,
            SUM(CASE WHEN processing_status = 'VALIDATED' THEN 1 ELSE 0 END) as valid_count,
            SUM(CASE WHEN processing_status = 'VALIDATION_ERROR' THEN 1 ELSE 0 END) as invalid_count
        FROM {context.config.staging_table}
        WHERE file_batch_id = %s
        """

        cursor = db_manager.execute_with_retry(
            context.connection, result_sql, (str(context.file_batch_id),)
        )
        result = cursor.fetchone()

        total_processed = result[0]
        valid_count = result[1]
        invalid_count = result[2]

        error_rate = (invalid_count / total_processed * 100) if total_processed > 0 else 0

        context.connection.commit()

        duration = time.time() - start_time
        logger.info(f"✅ Data validation completed in {duration:.2f}s")
        logger.info(f"   Total records: {total_processed}")
        logger.info(f"   Valid records: {valid_count}")
        logger.info(f"   Invalid records: {invalid_count}")
        logger.info(f"   Error rate: {error_rate:.2f}%")

        if error_rate > context.config.error_threshold_pct:
            raise ValidationError(
                f"Error rate {error_rate:.2f}% exceeds threshold {context.config.error_threshold_pct}%"
            )

        validation_result = ValidationResult(
            is_valid=error_rate <= context.config.error_threshold_pct,
            total_records=total_processed,
            valid_records=valid_count,
            invalid_records=invalid_count,
        )

        return ProcessingResult(
            success=True,
            message=f"Data validation completed: {valid_count}/{total_processed} records validated",
            records_processed=total_processed,
            records_succeeded=valid_count,
            records_failed=invalid_count,
            duration_seconds=duration,
            validation_result=validation_result,
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Data validation failed: {e}")

        return ProcessingResult(
            success=False,
            message=f"Data validation failed: {e}",
            duration_seconds=duration,
            error_details=str(e),
        )


def transform_and_load_core(context: DTCProcessingContext) -> ProcessingResult:
    """
    Step 4: Apply DTC business logic and load into core tables.
    FIXED VERSION - Better error handling and corrected SQL
    """
    logger = logging.getLogger("dtc_file_processor")
    start_time = time.time()
    logger.info("STEP 4: TRANSFORM_AND_LOAD_CORE - Applying DTC business logic")

    try:
        db_manager = DatabaseManager(context.config.connection_string)

        # 🔍 FIRST: Ensure staging data has org_id populated
        logger.info("Ensuring staging data has org_id populated...")
        populate_org_sql = f"""
        UPDATE stg 
        SET org_id = o.org_id
        FROM {context.config.staging_table} stg
        JOIN engage360.orgs o ON LTRIM(RTRIM(LOWER(stg.partner_name))) = LTRIM(RTRIM(LOWER(o.org_name)))
        WHERE stg.file_batch_id = %s 
        AND stg.org_id IS NULL
        AND stg.partner_name IS NOT NULL
        """
        cursor = db_manager.execute_with_retry(
            context.connection, populate_org_sql, (str(context.file_batch_id),)
        )
        org_updated = cursor.rowcount
        logger.info(f"Updated org_id for {org_updated} records")

        # 🔍 Get campaign IDs with better error handling
        logger.info("Fetching campaign IDs for 'dtc_intro_onboarding' and 'dtc_wellness_check'")
        fetch_campaign_ids_sql = """
        SELECT campaign_id, name, status
        FROM engage360.campaigns_enhanced
        WHERE name IN ('dtc_intro_onboarding', 'dtc_wellness_check')
        AND status = 'Active'
        """
        cursor = db_manager.execute_with_retry(context.connection, fetch_campaign_ids_sql)
        rows = cursor.fetchall()

        if not rows:
            raise PermanentError(
                "❌ No active campaigns found for dtc_intro_onboarding or dtc_wellness_check"
            )

        campaign_map = {}
        for row in rows:
            campaign_map[row[1]] = row[0]  # name = index 1, campaign_id = index 0
            logger.info(f"Found campaign: {row[1]} = {row[0]} (Status: {row[2]})")

        intro_campaign_id = campaign_map.get("dtc_intro_onboarding")
        wellness_campaign_id = campaign_map.get("dtc_wellness_check")

        if not intro_campaign_id:
            raise PermanentError("❌ Missing dtc_intro_onboarding campaign")
        if not wellness_campaign_id:
            raise PermanentError("❌ Missing dtc_wellness_check campaign")

        logger.info(f"Using campaigns: intro={intro_campaign_id}, wellness={wellness_campaign_id}")

        # 🟡 Set records to TRANSFORMING
        update_status_sql = f"""
        UPDATE {context.config.staging_table}
        SET processing_status = 'TRANSFORMING', 
            processing_step = 'DTC_BUSINESS_LOGIC',
            updated_ts = SYSDATETIMEOFFSET()
        WHERE file_batch_id = %s 
        AND processing_status IN ('PENDING', 'VALIDATED', 'PROCESSED')
        """
        cursor = db_manager.execute_with_retry(
            context.connection, update_status_sql, (str(context.file_batch_id),)
        )
        transforming_count = cursor.rowcount
        logger.info(f"Set {transforming_count} records to TRANSFORMING status")

        if transforming_count == 0:
            raise PermanentError("❌ No records available for transformation")

        # 🔍 Check staging data before processing
        check_staging_sql = f"""
        SELECT 
            COUNT(*) as total_records,
            COUNT(CASE WHEN org_id IS NOT NULL THEN 1 END) as records_with_org,
            COUNT(CASE WHEN salesforce_account_number IS NOT NULL AND LTRIM(RTRIM(salesforce_account_number)) != '' THEN 1 END) as records_with_sf_account,
            COUNT(CASE WHEN enrollment_status IS NOT NULL THEN 1 END) as records_with_enrollment_status
        FROM {context.config.staging_table}
        WHERE file_batch_id = %s AND processing_status = 'TRANSFORMING'
        """
        cursor = db_manager.execute_with_retry(
            context.connection, check_staging_sql, (str(context.file_batch_id),)
        )
        staging_check = cursor.fetchone()

        logger.info("Staging data check:")
        logger.info(f"  Total records: {staging_check[0]}")
        logger.info(f"  Records with org_id: {staging_check[1]}")
        logger.info(f"  Records with SF account: {staging_check[2]}")
        logger.info(f"  Records with enrollment status: {staging_check[3]}")

        # 🔍 Check for duplicate members first
        logger.info("Checking for duplicate members...")

        duplicate_check_sql = f"""
        SELECT 
            stg.org_id,
            LTRIM(RTRIM(stg.salesforce_account_number)) AS salesforce_account_number,
            COUNT(*) as duplicate_count
        FROM {context.config.staging_table} stg
        WHERE stg.file_batch_id = %s
          AND stg.processing_status = 'TRANSFORMING'
          AND stg.org_id IS NOT NULL
          AND stg.salesforce_account_number IS NOT NULL
          AND LTRIM(RTRIM(stg.salesforce_account_number)) != ''
        GROUP BY stg.org_id, LTRIM(RTRIM(stg.salesforce_account_number))
        HAVING COUNT(*) > 1
        """

        cursor = db_manager.execute_with_retry(
            context.connection, duplicate_check_sql, (str(context.file_batch_id),)
        )
        duplicates = cursor.fetchall()

        if duplicates:
            duplicate_details = []
            for dup in duplicates:
                duplicate_details.append(
                    f"org_id: {dup[0]}, salesforce_account_number: {dup[1]}, count: {dup[2]}"
                )

            error_message = "Duplicate members found in staging data:\n" + "\n".join(
                duplicate_details
            )
            logger.error(f"❌ {error_message}")
            raise ValueError(error_message)

        logger.info("✅ No duplicate members found")

        # 👤 Upsert members with improved SQL
        logger.info("Upserting members...")

        member_upsert_sql = f"""
        WITH source_members AS (
            SELECT DISTINCT
                stg.org_id,
                LTRIM(RTRIM(stg.salesforce_account_number)) AS salesforce_account_number,
                LTRIM(RTRIM(stg.first_name_clean)) AS first_name,
                LTRIM(RTRIM(stg.last_name_clean)) AS last_name,
                LTRIM(RTRIM(stg.caregiver_first_clean)) AS caregiver_first_name,
                LTRIM(RTRIM(stg.caregiver_last_clean)) AS caregiver_last_name,
                stg.caregiver_email_clean AS caregiver_email,
                stg.primary_phone_clean AS primary_phone,
                stg.caregiver_phone_clean AS caregiver_phone,
                stg.member_email AS email,
                stg.dob_clean AS dob,
                ISNULL(stg.language_pref, 'EN') AS language_pref,
                stg.timezone_clean AS timezone,
                stg.member_address_street AS address_street,
                stg.member_address_city AS address_city,
                stg.member_address_state AS address_state,
                stg.member_address_zip AS address_zip,
                ISNULL(stg.member_address_country, 'US') AS address_country
            FROM {context.config.staging_table} stg
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND stg.org_id IS NOT NULL
              AND stg.salesforce_account_number IS NOT NULL
              AND LTRIM(RTRIM(stg.salesforce_account_number)) != ''
        )
        MERGE engage360.members AS tgt
        USING source_members AS src
        ON (tgt.org_id = src.org_id AND tgt.salesforce_account_number = src.salesforce_account_number)
        WHEN MATCHED THEN
            UPDATE SET
                first_name = ISNULL(src.first_name, tgt.first_name),
                last_name = ISNULL(src.last_name, tgt.last_name),
                caregiver_first_name = ISNULL(src.caregiver_first_name, tgt.caregiver_first_name),
                caregiver_last_name = ISNULL(src.caregiver_last_name, tgt.caregiver_last_name),
                caregiver_email = ISNULL(src.caregiver_email, tgt.caregiver_email),
                primary_phone = ISNULL(src.primary_phone, tgt.primary_phone),
                caregiver_phone = ISNULL(src.caregiver_phone, tgt.caregiver_phone),
                email = ISNULL(src.email, tgt.email),
                dob = ISNULL(src.dob, tgt.dob),
                language_pref = ISNULL(src.language_pref, tgt.language_pref),
                timezone = ISNULL(src.timezone, tgt.timezone),
                address_street = ISNULL(src.address_street, tgt.address_street),
                address_city = ISNULL(src.address_city, tgt.address_city),
                address_state = ISNULL(src.address_state, tgt.address_state),
                address_zip = ISNULL(src.address_zip, tgt.address_zip),
                address_country = ISNULL(src.address_country, tgt.address_country)
        WHEN NOT MATCHED THEN
            INSERT (member_id, org_id, salesforce_account_number, first_name, last_name,
                   caregiver_first_name, caregiver_last_name, caregiver_email, primary_phone, caregiver_phone,
                   email, dob, language_pref, timezone, address_street, address_city,
                   address_state, address_zip, address_country, created_ts)
            VALUES (NEWID(), src.org_id, src.salesforce_account_number, src.first_name, src.last_name,
                   src.caregiver_first_name, src.caregiver_last_name, src.caregiver_email, src.primary_phone, src.caregiver_phone,
                   src.email, src.dob, src.language_pref, src.timezone, src.address_street, src.address_city,
                   src.address_state, src.address_zip, src.address_country, SYSDATETIMEOFFSET());
        """

        cursor = db_manager.execute_with_retry(
            context.connection, member_upsert_sql, (str(context.file_batch_id),)
        )
        members_affected = cursor.rowcount
        logger.info(f"Members merge affected {members_affected} rows")

        # 🔍 Verify members were created/updated
        verify_members_sql = """
        SELECT COUNT(*) FROM engage360.members m
        JOIN engage360_stg.stg_dtc_wellness_delta stg 
            ON m.org_id = stg.org_id 
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
        """
        cursor = db_manager.execute_with_retry(
            context.connection, verify_members_sql, (str(context.file_batch_id),)
        )
        members_count = cursor.fetchone()[0]
        logger.info(f"Verified {members_count} members exist after upsert")

        # 🔁 Handle enrollments by status
        new_enrollments = 0
        updated_enrollments = 0
        unenrolled_count = 0

        # 🔥 SET ENROLLMENT START TIMESTAMP:
        enrollment_start_time = datetime.now(timezone.utc)
        update_enrollment_start_sql = f"""
        UPDATE {context.config.staging_table}
        SET enrollment_started_ts = %s
        WHERE file_batch_id = %s AND processing_status = 'TRANSFORMING'
        """
        cursor = db_manager.execute_with_retry(
            context.connection,
            update_enrollment_start_sql,
            (enrollment_start_time, str(context.file_batch_id)),
        )

        # Handle "enroll" - use intro campaign, but first handle UNENROLLED wellness transitions
        logger.info("Processing 'enroll' records...")
        
        # First, transition UNENROLLED wellness members back to intro campaign
        logger.info("Handling UNENROLLED wellness members transition to intro campaign...")
        wellness_to_intro_sql = f"""
        UPDATE wellness_enroll
        SET campaign_id = %s,
            current_status = 'ENROLLED',
            enrollment_ts = SYSDATETIMEOFFSET(),
            unenrollment_reason = NULL
        FROM engage360.member_campaign_enrollments_enhanced wellness_enroll
        JOIN engage360.members m ON wellness_enroll.member_id = m.member_id
        JOIN {context.config.staging_table} stg 
            ON m.org_id = stg.org_id 
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.processing_status = 'TRANSFORMING'
          AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'ENROLL'
          AND wellness_enroll.campaign_id = %s
          AND wellness_enroll.current_status = 'UNENROLLED'
        """
        cursor = db_manager.execute_with_retry(
            context.connection, 
            wellness_to_intro_sql, 
            (str(intro_campaign_id), str(context.file_batch_id), str(wellness_campaign_id))
        )
        transitioned_wellness = cursor.rowcount
        logger.info(f"Transitioned {transitioned_wellness} UNENROLLED wellness members back to intro campaign")
        
        # Log status changes for transitioned members
        if transitioned_wellness > 0:
            # Get the member IDs that were transitioned for audit logging
            transitioned_members_sql = f"""
                SELECT DISTINCT m.member_id
                FROM engage360.members m
                JOIN {context.config.staging_table} stg 
                    ON m.org_id = stg.org_id 
                    AND m.salesforce_account_number = stg.salesforce_account_number
                JOIN engage360.member_campaign_enrollments_enhanced e ON e.member_id = m.member_id
                WHERE stg.file_batch_id = %s
                  AND stg.processing_status = 'TRANSFORMING'
                  AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'ENROLL'
                  AND e.campaign_id = %s
            """
            cursor = db_manager.execute_with_retry(
                context.connection, 
                transitioned_members_sql, 
                (str(context.file_batch_id), str(intro_campaign_id))
            )
            transitioned_member_ids = cursor.fetchall()
            
            for member_record in transitioned_member_ids:
                member_id = str(member_record[0])
                log_enrollment_status_change(
                    context.connection, member_id, str(intro_campaign_id),
                    "UNENROLLED", "ENROLLED", "CSV_PROCESSING",
                    "Re-enrollment: Transitioned from UNENROLLED wellness back to intro ENROLLED"
                )
        
        # Then handle normal intro campaign enrollments (new enrollments and re-enrollments)
        enroll_sql = f"""
        MERGE engage360.member_campaign_enrollments_enhanced AS tgt
        USING (
            SELECT m.member_id,
                   %s AS campaign_id,
                   CASE LTRIM(RTRIM(UPPER(stg.checkin_time)))
                       WHEN 'AM' THEN 'AM9-10'
                       WHEN 'PM' THEN 'PM1-3'
                       WHEN 'EV' THEN 'EV4-6'
                       ELSE NULL
                   END AS preferred_window
            FROM {context.config.staging_table} stg
            JOIN engage360.members m 
                ON m.org_id = stg.org_id 
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'ENROLL'
              -- Exclude members who already have wellness enrollments (handled above)
              AND NOT EXISTS (
                  SELECT 1 FROM engage360.member_campaign_enrollments_enhanced existing
                  WHERE existing.member_id = m.member_id 
                    AND existing.campaign_id = %s
              )
        ) AS src ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id
        WHEN MATCHED THEN
            UPDATE SET 
                current_status = CASE WHEN tgt.current_status = 'UNENROLLED' THEN 'ENROLLED' ELSE tgt.current_status END,
                enrollment_ts = CASE WHEN tgt.current_status = 'UNENROLLED' THEN SYSDATETIMEOFFSET() ELSE tgt.enrollment_ts END,
                preferred_window = ISNULL(src.preferred_window, tgt.preferred_window),
                unenrollment_reason = CASE WHEN tgt.current_status = 'UNENROLLED' THEN NULL ELSE tgt.unenrollment_reason END
        WHEN NOT MATCHED THEN
            INSERT (enrollment_id, member_id, campaign_id, enrollment_ts, current_status, preferred_window)
            VALUES (NEWID(), src.member_id, src.campaign_id, SYSDATETIMEOFFSET(), 'ENROLLED', src.preferred_window);
        """
        cursor = db_manager.execute_with_retry(
            context.connection, 
            enroll_sql, 
            (str(intro_campaign_id), str(context.file_batch_id), str(wellness_campaign_id))
        )
        new_enrollments = cursor.rowcount
        logger.info(f"Processed {new_enrollments} intro campaign enrollment records (new + re-enrolled)")
        
        total_enrollments = transitioned_wellness + new_enrollments
        logger.info(f"Total enrollment processing: {total_enrollments} records (transitions + new/re-enrolled)")

        # Handle "update" - use wellness campaign
        logger.info("Processing 'update' records...")

        # 🔍 Check for duplicate update enrollments first
        update_duplicates_sql = f"""
        SELECT m.member_id, COUNT(*) as duplicate_count
        FROM {context.config.staging_table} stg
        JOIN engage360.members m 
            ON m.org_id = stg.org_id 
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.processing_status = 'TRANSFORMING'
          AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'UPDATE'
        GROUP BY m.member_id
        HAVING COUNT(*) > 1
        """

        cursor = db_manager.execute_with_retry(
            context.connection, update_duplicates_sql, (str(context.file_batch_id),)
        )
        update_duplicates = cursor.fetchall()

        if update_duplicates:
            duplicate_details = []
            for dup in update_duplicates:
                duplicate_details.append(f"member_id: {dup[0]}, count: {dup[1]}")

            error_message = "Duplicate update enrollments found:\n" + "\n".join(duplicate_details)
            logger.error(f"❌ {error_message}")
            raise ValueError(error_message)

        logger.info("✅ No duplicate update enrollments found")

        update_enrollments_sql = f"""
        MERGE engage360.member_campaign_enrollments_enhanced AS tgt
        USING (
            SELECT m.member_id, 
                   CASE LTRIM(RTRIM(UPPER(stg.checkin_time)))
                       WHEN 'AM' THEN 'AM9-10'
                       WHEN 'PM' THEN 'PM1-3'
                       WHEN 'EV' THEN 'EV4-6'
                       ELSE NULL
                   END AS preferred_window
            FROM {context.config.staging_table} stg
            JOIN engage360.members m 
                ON m.org_id = stg.org_id 
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'UPDATE'
        ) AS src ON tgt.member_id = src.member_id AND tgt.campaign_id = %s
        WHEN MATCHED THEN
            UPDATE SET 
                preferred_window = ISNULL(src.preferred_window, tgt.preferred_window)
                -- Remove: current_status = 'PENDING' - preserve existing status
        """
        cursor = db_manager.execute_with_retry(
            context.connection,
            update_enrollments_sql,
            (str(context.file_batch_id), str(wellness_campaign_id)),
        )
        updated_enrollments = cursor.rowcount
        logger.info(f"Updated {updated_enrollments} existing wellness enrollments")

        # Handle "unenroll"
        logger.info("Processing 'unenroll' records...")
        unenroll_sql = f"""
        UPDATE e
        SET current_status = 'UNENROLLED',
            unenrollment_reason = COALESCE(stg.unenrollment_reason, 'Updated via file processing')
        FROM engage360.member_campaign_enrollments_enhanced e
        JOIN engage360.members m ON e.member_id = m.member_id
        JOIN {context.config.staging_table} stg 
            ON m.org_id = stg.org_id 
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.processing_status = 'TRANSFORMING'
          AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'UNENROLL'
          AND e.campaign_id IN (%s, %s)
        """
        cursor = db_manager.execute_with_retry(
            context.connection,
            unenroll_sql,
            (str(context.file_batch_id), str(intro_campaign_id), str(wellness_campaign_id)),
        )
        unenrolled_count = cursor.rowcount
        logger.info(f"Unenrolled {unenrolled_count} members")
        
        # Log status changes for unenrolled members
        if unenrolled_count > 0:
            # Get the member IDs and campaign IDs that were unenrolled for audit logging
            unenrolled_members_sql = f"""
                SELECT DISTINCT m.member_id, e.campaign_id, e.current_status
                FROM engage360.members m
                JOIN {context.config.staging_table} stg 
                    ON m.org_id = stg.org_id 
                    AND m.salesforce_account_number = stg.salesforce_account_number
                JOIN engage360.member_campaign_enrollments_enhanced e ON e.member_id = m.member_id
                WHERE stg.file_batch_id = %s
                  AND stg.processing_status = 'TRANSFORMING'
                  AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'UNENROLL'
                  AND e.campaign_id IN (%s, %s)
                  AND e.current_status = 'UNENROLLED'
            """
            cursor = db_manager.execute_with_retry(
                context.connection,
                unenrolled_members_sql,
                (str(context.file_batch_id), str(intro_campaign_id), str(wellness_campaign_id)),
            )
            unenrolled_member_records = cursor.fetchall()
            
            for member_record in unenrolled_member_records:
                member_id = str(member_record[0])
                campaign_id = str(member_record[1])
                # Assume previous status was ENROLLED (since we only unenroll active members)
                log_enrollment_status_change(
                    context.connection, member_id, campaign_id,
                    "ENROLLED", "UNENROLLED", "CSV_PROCESSING",
                    "CSV unenroll processing"
                )

        # 📦 Handle device processing (if any devices in data)
        logger.info("Checking for duplicate devices...")

        # 🔍 Check for duplicate devices first
        device_duplicates_sql = f"""
        SELECT stg.device_udi, COUNT(*) as duplicate_count
        FROM {context.config.staging_table} stg
        JOIN engage360.members m 
            ON m.org_id = stg.org_id 
            AND m.salesforce_account_number = stg.salesforce_account_number
        WHERE stg.file_batch_id = %s
          AND stg.processing_status = 'TRANSFORMING'
          AND stg.device_udi IS NOT NULL
          AND LTRIM(RTRIM(stg.device_udi)) != ''
        GROUP BY stg.device_udi
        HAVING COUNT(*) > 1
        """

        cursor = db_manager.execute_with_retry(
            context.connection, device_duplicates_sql, (str(context.file_batch_id),)
        )
        device_duplicates = cursor.fetchall()

        if device_duplicates:
            duplicate_details = []
            for dup in device_duplicates:
                duplicate_details.append(f"device_udi: {dup[0]}, count: {dup[1]}")

            error_message = "Duplicate devices found:\n" + "\n".join(duplicate_details)
            logger.error(f"❌ {error_message}")
            raise ValueError(error_message)

        logger.info("✅ No duplicate devices found")

        device_sql = f"""
        MERGE engage360.member_devices AS tgt
        USING (
            SELECT DISTINCT
                stg.device_udi,
                m.member_id,
                stg.device_phone_clean AS device_phone_number,
                stg.is_device_callable_clean AS is_device_callable,
                stg.device_name
            FROM {context.config.staging_table} stg
            JOIN engage360.members m 
                ON m.org_id = stg.org_id 
                AND m.salesforce_account_number = stg.salesforce_account_number
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND stg.device_udi IS NOT NULL
              AND LTRIM(RTRIM(stg.device_udi)) != ''
        ) AS src ON tgt.device_id = src.device_udi
        WHEN MATCHED THEN
            UPDATE SET
                device_phone_number = ISNULL(src.device_phone_number, tgt.device_phone_number),
                is_device_callable = ISNULL(src.is_device_callable, tgt.is_device_callable),
                device_name = ISNULL(src.device_name, tgt.device_name)
        WHEN NOT MATCHED THEN
            INSERT (device_id, member_id, device_phone_number, is_device_callable, device_name, created_ts)
            VALUES (src.device_udi, src.member_id, src.device_phone_number, src.is_device_callable, src.device_name, SYSDATETIMEOFFSET());
        """
        cursor = db_manager.execute_with_retry(
            context.connection, device_sql, (str(context.file_batch_id),)
        )
        devices_affected = cursor.rowcount
        logger.info(f"Devices merge affected {devices_affected} rows")

        # 🔥 UPDATE: Track member and enrollment IDs
        update_tracking_sql = f"""
        UPDATE stg
        SET member_id_processed = m.member_id,
            enrollment_id_processed = e.enrollment_id,
            enrollment_started_ts = SYSDATETIMEOFFSET(),
            enrollment_completed_ts = SYSDATETIMEOFFSET()
        FROM {context.config.staging_table} stg
        JOIN engage360.members m ON m.org_id = stg.org_id AND m.salesforce_account_number = stg.salesforce_account_number
        LEFT JOIN engage360.member_campaign_enrollments_enhanced e ON e.member_id = m.member_id
        WHERE stg.file_batch_id = %s AND stg.processing_status = 'TRANSFORMING'
        """
        cursor = db_manager.execute_with_retry(
            context.connection, update_tracking_sql, (str(context.file_batch_id),)
        )

        # ✅ Mark as processed
        complete_sql = f"""
        UPDATE {context.config.staging_table}
        SET processing_status = 'PROCESSED',
            updated_ts = SYSDATETIMEOFFSET()
        WHERE file_batch_id = %s AND processing_status = 'TRANSFORMING'
        """
        cursor = db_manager.execute_with_retry(
            context.connection, complete_sql, (str(context.file_batch_id),)
        )
        processed_count = cursor.rowcount

        # 🔍 Final verification
        final_check_sql = """
        SELECT 
            (SELECT COUNT(*) FROM engage360.members WHERE created_ts >= CONVERT(date, GETDATE())) as members_today,
            (SELECT COUNT(*) FROM engage360.member_campaign_enrollments_enhanced WHERE enrollment_ts >= CONVERT(date, GETDATE())) as enrollments_today
        """
        cursor = db_manager.execute_with_retry(context.connection, final_check_sql)
        final_counts = cursor.fetchone()

        context.connection.commit()
        duration = time.time() - start_time

        logger.info(f"✅ DTC business logic completed in {duration:.2f}s")
        logger.info(f"   Records processed: {processed_count}")
        logger.info(f"   Members affected: {members_affected}")
        logger.info(f"   New enrollments: {new_enrollments}")
        logger.info(f"   Updated enrollments: {updated_enrollments}")
        logger.info(f"   Unenrolled: {unenrolled_count}")
        logger.info(f"   Devices affected: {devices_affected}")
        logger.info(
            f"   Final counts - Members today: {final_counts[0]}, Enrollments today: {final_counts[1]}"
        )

        return ProcessingResult(
            success=True,
            message=f"DTC business logic completed: {processed_count} records processed, {members_affected} members, {new_enrollments + updated_enrollments} enrollments",
            records_processed=processed_count,
            records_succeeded=processed_count,
            duration_seconds=duration,
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ DTC business logic failed: {e}")
        logger.error(f"Exception details: {str(e)}", exc_info=True)

        # Try to get more details about the failure
        try:
            context.connection.rollback()
            logger.info("Transaction rolled back")
        except Exception:
            logger.warning("Could not rollback transaction")

        return ProcessingResult(
            success=False,
            message=f"DTC business logic failed: {e}",
            duration_seconds=duration,
            error_details=str(e),
        )


def log_audit(
    context: DTCProcessingContext, processing_results: List[ProcessingResult]
) -> ProcessingResult:
    """
    Step 5: Log comprehensive audit information.

    Args:
        context: Processing context
        processing_results: Results from all processing steps

    Returns:
        ProcessingResult
    """
    logger = logging.getLogger("dtc_file_processor")
    start_time = time.time()

    logger.info("STEP 5: LOG_AUDIT - Recording comprehensive audit trail")

    try:
        db_manager = DatabaseManager(context.config.connection_string)

        # Calculate totals
        total_duration = sum(result.duration_seconds for result in processing_results)
        total_processed = sum(result.records_processed for result in processing_results)
        total_succeeded = sum(result.records_succeeded for result in processing_results)
        total_failed = sum(result.records_failed for result in processing_results)

        # Update master file processing log
        audit_sql = """
        UPDATE engage360_stg.file_processing_log
        SET 
            current_status = 'COMPLETED',
            processing_step = 'COMPLETED',
            enrollment_completed_ts = SYSDATETIMEOFFSET(),
            completed_ts = SYSDATETIMEOFFSET(),
            total_records_processed = %s,
            successful_records = %s,
            failed_records = %s,
            error_percentage = CASE WHEN %s > 0 THEN (CAST(%s AS DECIMAL(10,2)) / CAST(%s AS DECIMAL(10,2))) * 100 ELSE 0 END
        WHERE file_batch_id = %s
        """

        db_manager.execute_with_retry(
            context.connection,
            audit_sql,
            (
                total_processed,
                total_succeeded,
                total_failed,
                total_processed,
                total_failed,
                total_processed,
                str(context.file_batch_id),
            ),
        )

        # Create detailed audit log entry
        audit_detail_sql = """
        INSERT INTO engage360_stg.processing_step_log 
        (file_batch_id, step_name, step_sequence, step_status, records_input, records_output, 
         records_failed, step_message, step_started_ts, step_completed_ts)
        VALUES (%s, 'DTC_COMPLETE_WORKFLOW', 99, 'COMPLETED', %s, %s, %s, %s, %s, SYSDATETIMEOFFSET())
        """

        audit_message = f"DTC workflow completed successfully. Duration: {total_duration:.2f}s"

        db_manager.execute_with_retry(
            context.connection,
            audit_detail_sql,
            (
                str(context.file_batch_id),
                total_processed,
                total_succeeded,
                total_failed,
                audit_message,
                datetime.now(timezone.utc),
            ),
        )

        context.connection.commit()

        duration = time.time() - start_time
        logger.info(f"✅ Audit logging completed in {duration:.2f}s")

        return ProcessingResult(
            success=True,
            message="Audit logging completed successfully",
            records_processed=1,
            records_succeeded=1,
            duration_seconds=duration,
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Audit logging failed: {e}")

        return ProcessingResult(
            success=False,
            message=f"Audit logging failed: {e}",
            duration_seconds=duration,
            error_details=str(e),
        )


def handle_errors(
    context: DTCProcessingContext, error: Exception, processing_results: List[ProcessingResult]
) -> None:
    """
    Step 6: Comprehensive error handling with retry logic and failure logging.

    Args:
        context: Processing context
        error: Exception that occurred
        processing_results: Results from completed steps
    """
    logger = logging.getLogger("dtc_file_processor")

    try:
        # Classify error type
        error_type = "PERMANENT"
        if isinstance(error, TransientError):
            error_type = "TRANSIENT"
        elif isinstance(error, ValidationError):
            error_type = "VALIDATION"

        # Calculate partial results
        total_processed = sum(result.records_processed for result in processing_results)
        total_succeeded = sum(result.records_succeeded for result in processing_results)
        total_failed = sum(result.records_failed for result in processing_results)

        # Update master log with failure status - use a simple cursor without retry logic
        failure_sql = """
        UPDATE engage360_stg.file_processing_log
        SET 
            current_status = 'FAILED',
            processing_step = 'FAILED',
            completed_ts = SYSDATETIMEOFFSET(),
            final_error_message = %s,
            total_records_processed = %s,
            successful_records = %s,
            failed_records = %s
        WHERE file_batch_id = %s
        """

        cursor = context.connection.cursor()
        cursor.execute(
            failure_sql,
            (
                str(error),
                total_processed,
                total_succeeded,
                total_failed,
                str(context.file_batch_id),
            ),
        )
        context.connection.commit()

        # Only try to log detailed error information if the master record exists
        # Check if master record exists first
        check_sql = (
            "SELECT COUNT(*) FROM engage360_stg.file_processing_log WHERE file_batch_id = %s"
        )
        cursor.execute(check_sql, (str(context.file_batch_id),))
        if cursor.fetchone()[0] > 0:
            # Master record exists, safe to insert step log
            try:
                error_detail_sql = """
                INSERT INTO engage360_stg.processing_step_log 
                (file_batch_id, step_name, step_sequence, step_status, step_message, error_details, step_started_ts, step_completed_ts)
                VALUES (%s, 'ERROR_HANDLING', 999, 'FAILED', %s, %s, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET())
                """

                error_message = f"DTC processing failed with {error_type} error"
                cursor.execute(
                    error_detail_sql, (str(context.file_batch_id), error_message, str(error))
                )
                context.connection.commit()

                logger.info("Error details logged successfully")
            except Exception as step_log_error:
                logger.warning(f"Failed to log error step details: {step_log_error}")
        else:
            logger.warning("Master log record not found, skipping detailed error logging")

        logger.error(f"Error handling completed for batch {context.file_batch_id}")

    except Exception as logging_error:
        logger.error(f"Failed to log error information: {logging_error}")
        # Don't re-raise this exception - we don't want error handling to fail the entire process


# Main Orchestrator Function
# ===========================


def process_dtc_file_complete(
    file_path: str,
    connection_string: str,
    uploaded_by_user: Optional[str] = None,
    error_threshold_pct: float = 10.0,
    auto_notify: bool = True,
    log_level: str = "INFO",
    log_file: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    # -------------------------------------------------------------------------
    # Setup logging and initial metadata
    # -------------------------------------------------------------------------
    logger = setup_logging(log_level, log_file)
    file_batch_id = uuid.uuid4()
    source_filename = Path(file_path).name

    logger.info("=" * 70)
    logger.info("🚀 DTC FILE PROCESSING WORKFLOW - INDUSTRY STANDARD")
    logger.info("=" * 70)
    logger.info(f"Batch ID:           {file_batch_id}")
    logger.info(f"Source file:        {source_filename}")
    logger.info(f"Error threshold:    {error_threshold_pct}%")
    logger.info("Expected pattern:   MedicalGuardian_DTCWellness_*_Delta.csv")

    # -------------------------------------------------------------------------
    # Validate filename
    # -------------------------------------------------------------------------
    if not source_filename.startswith(
        "MedicalGuardian_DTCWellness_"
    ) or not source_filename.endswith("_Delta.csv"):
        msg = f"Invalid filename pattern. Expected MedicalGuardian_DTCWellness_*_Delta.csv, got {source_filename}"
        logger.error(f"❌ {msg}")
        return False, msg, {"error": msg}

    # -------------------------------------------------------------------------
    # Fetch DB conn string from Key Vault
    # -------------------------------------------------------------------------
    key_vault_url = os.environ["KEY_VAULT_URL"]
    secret_name = os.environ.get("DB_SECRET_NAME", "SqlConnectionStringIOE")
    cred = DefaultAzureCredential()
    kv_client = SecretClient(vault_url=key_vault_url, credential=cred)
    secure_conn = kv_client.get_secret(secret_name).value

    # Build config & connect
    config = ProcessingConfig(
        connection_string=secure_conn,
        error_threshold_pct=error_threshold_pct,
        auto_notify=auto_notify,
    )
    try:
        dbm = DatabaseManager(config.connection_string)
        connection = dbm.get_connection()
        logger.info("✅ Database connection established")
    except Exception as e:
        msg = f"Failed to establish database connection: {e}"
        logger.error(f"❌ {msg}")
        return False, msg, {"error": str(e)}

    # Build context
    context = DTCProcessingContext(
        file_batch_id=file_batch_id,
        source_filename=source_filename,
        file_path=file_path,
        uploaded_by_user=uploaded_by_user,
        file_size_bytes=Path(file_path).stat().st_size if Path(file_path).exists() else None,
        config=config,
        connection=connection,
    )

    processing_results = []
    workflow_start = time.time()

    try:
        # ---------------------------------------------------------------------
        # Seed the parent log row FIRST - outside transaction
        # ---------------------------------------------------------------------
        # Determine file_type based on filename pattern
        file_type = "DTC_WELLNESS"  # Default for DTC wellness files
        if "Partner" in source_filename or "Roster" in source_filename:
            file_type = "PARTNER_ROSTER"
        elif "DTCWellness" in source_filename:
            file_type = "DTC_WELLNESS"

        # Initialize the master log entry FIRST (with autocommit)
        master_sql = """
        INSERT INTO engage360_stg.file_processing_log
          (file_batch_id, source_filename, file_type, created_ts, current_status, error_threshold_pct)
        VALUES (%s, %s, %s, SYSDATETIMEOFFSET(), 'STARTED', %s)
        """

        # Use a separate connection with autocommit for the master log
        master_cursor = connection.cursor()
        master_cursor.execute(
            master_sql, (str(file_batch_id), source_filename, file_type, error_threshold_pct)
        )
        connection.commit()  # Commit this immediately
        logger.info(f"Master log entry created for batch {file_batch_id}")

        # ---------------------------------------------------------------------
        # Now begin transaction for the main processing
        # ---------------------------------------------------------------------
        # pymssql transactions are managed by commit() and rollback() on the connection object

        # ---------------------------------------------------------------------
        # Step 1: Extract
        # ---------------------------------------------------------------------
        df, result = extract(file_path, context)
        processing_results.append(result)

        logger.info(f"Moving file from 'landing' → 'staging': {source_filename}")
        if result.success:
            try:
                handle_blob_movement_with_error_handling(
                    source_filename,
                    "landing",
                    "staging",
                    os.environ["AZURE_CONTAINER_NAME"],
                    logger,
                )
            except Exception as move_error:
                logger.error(f"Failed to move from landing to staging: {move_error}")
                # Continue processing anyway - file might have been moved already
        else:
            raise PermanentError(f"Extraction failed: {result.message}")

        # ---------------------------------------------------------------------
        # Step 2: Load to Staging
        # ---------------------------------------------------------------------
        result = load_to_staging(df, context)
        processing_results.append(result)
        if not result.success:
            raise PermanentError(f"Staging load failed: {result.message}")

        # ---------------------------------------------------------------------
        # Step 3: Validate Data
        # ---------------------------------------------------------------------
        result = validate_data(context)
        processing_results.append(result)
        if not result.success:
            raise ValidationError(f"Data validation failed: {result.message}")

        # ---------------------------------------------------------------------
        # Step 4: Transform & Load Core
        # ---------------------------------------------------------------------
        result = transform_and_load_core(context)
        processing_results.append(result)
        if not result.success:
            raise PermanentError(f"DTC business logic failed: {result.message}")

        # ---------------------------------------------------------------------
        # Step 5: Log Audit
        # ---------------------------------------------------------------------
        result = log_audit(context, processing_results)
        processing_results.append(result)

        logger.info(f"Moving file from 'staging' → 'processed': {source_filename}")
        if result.success:
            try:
                handle_blob_movement_with_error_handling(
                    source_filename,
                    "staging",
                    "processed",
                    os.environ["AZURE_CONTAINER_NAME"],
                    logger,
                )
            except Exception as move_error:
                logger.error(f"Failed to move to processed: {move_error}")
                # Don't fail the entire process for file movement issues
        else:
            raise PermanentError(f"Audit logging failed: {result.message}")

        # ---------------------------------------------------------------------
        # Commit
        # ---------------------------------------------------------------------
        connection.commit()

        total_time = time.time() - workflow_start
        logger.info("=" * 70)
        logger.info("🎉 DTC FILE PROCESSING COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info(f"Total workflow time: {total_time:.2f}s")
        logger.info(f"Batch ID: {file_batch_id}")

        # Build summary
        summary = {
            "batch_id": str(file_batch_id),
            "total_duration_seconds": total_time,
            "steps_completed": len([r for r in processing_results if r.success]),
            "workflow_steps": [
                {
                    "step": i + 1,
                    "name": name,
                    "success": r.success,
                    "message": r.message,
                    "duration_seconds": r.duration_seconds,
                    "records_processed": r.records_processed,
                }
                for i, (name, r) in enumerate(
                    zip(
                        [
                            "EXTRACT",
                            "LOAD_TO_STAGING",
                            "VALIDATE_DATA",
                            "TRANSFORM_AND_LOAD_CORE",
                            "LOG_AUDIT",
                        ],
                        processing_results,
                    )
                )
            ],
        }
        return True, "DTC file processing completed successfully", summary

    except Exception as e:
        # Rollback & error handling
        try:
            connection.rollback()
            logger.info("Transaction rolled back due to error")
        except Exception:
            logger.warning("Rollback failed")

        # Update the master log to show failure (this should work since it's already committed)
        try:
            failure_sql = """
            UPDATE engage360_stg.file_processing_log
            SET 
                current_status = 'FAILED',
                processing_step = 'FAILED',
                completed_ts = SYSDATETIMEOFFSET(),
                final_error_message = %s
            WHERE file_batch_id = %s
            """
            failure_cursor = connection.cursor()
            failure_cursor.execute(failure_sql, (str(e), str(file_batch_id)))
            connection.commit()
            logger.info("Master log updated with failure status")
        except Exception as log_error:
            logger.error(f"Failed to update master log: {log_error}")

        handle_errors(context, e, processing_results)

        logger.info(f"Moving file to 'error' folder: {source_filename}")
        try:
            handle_blob_movement_with_error_handling(
                source_filename, "staging", "error", os.environ["AZURE_CONTAINER_NAME"], logger
            )
        except Exception as mv:
            logger.error(f"Failed to move to error folder: {mv}")

        total_time = time.time() - workflow_start
        logger.error("=" * 70)
        logger.error("❌ DTC FILE PROCESSING FAILED")
        logger.error("=" * 70)
        logger.error(f"Error: {e}")
        logger.error(f"Total workflow time: {total_time:.2f}s")
        logger.error(f"Batch ID: {file_batch_id}")

        summary = {
            "batch_id": str(file_batch_id),
            "total_duration_seconds": total_time,
            "steps_completed": len([r for r in processing_results if r.success]),
            "error": str(e),
            "error_type": type(e).__name__,
            "workflow_steps": [
                {
                    "step": i + 1,
                    "name": name,
                    "success": r.success,
                    "message": r.message,
                    "duration_seconds": r.duration_seconds,
                    "records_processed": r.records_processed,
                }
                for i, (name, r) in enumerate(
                    zip(
                        [
                            "EXTRACT",
                            "LOAD_TO_STAGING",
                            "VALIDATE_DATA",
                            "TRANSFORM_AND_LOAD_CORE",
                            "LOG_AUDIT",
                        ],
                        processing_results,
                    )
                )
            ],
        }
        return False, f"DTC file processing failed: {e}", summary

    finally:
        # Always close
        try:
            connection.close()
            logger.info("Database connection closed")
        except Exception:
            logger.warning("Error closing DB connection")


# Example Usage
# =============

if __name__ == "__main__":
    # Example configuration
    CONNECTION_STRING = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=engage360;UID=user;PWD=password"

    # Example usage for DTC processing
    success, message, details = process_dtc_file_complete(
        file_path="/path/to/MedicalGuardian_DTCWellness_20250519_Delta.csv",
        connection_string=CONNECTION_STRING,
        uploaded_by_user="admin@medicalguardian.com",
        error_threshold_pct=10.0,
        log_level="INFO",
        log_file="dtc_processing.log",
    )

    if success:
        print(f"✅ DTC Processing completed: {message}")
        print(f"📊 Batch ID: {details['batch_id']}")
        print(f"⏱️  Duration: {details['total_duration_seconds']:.2f}s")
        print(f"📝 Records processed: {details['total_records_processed']}")

        # Print step details
        for step in details["workflow_steps"]:
            status = "✅" if step["success"] else "❌"
            print(
                f"{status} Step {step['step']} ({step['name']}): {step['message']} - {step['duration_seconds']:.2f}s"
            )
    else:
        print(f"❌ DTC Processing failed: {message}")
        print(f"📊 Batch ID: {details['batch_id']}")
        print(f"⚠️  Error: {details.get('error', 'Unknown error')}")
        print(f"🔍 Error Type: {details.get('error_type', 'Unknown')}")
