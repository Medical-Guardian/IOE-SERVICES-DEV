import azure.functions as func
import logging
import pandas as pd
from io import BytesIO
from af_code.af_device_activation_logic import process_device_activation_file_complete
from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.schema_config import IOE_SCHEMA

# Create a "Blueprint" to organize this function
bp = func.Blueprint()


def get_campaign_id_from_csv(blob_content: bytes) -> tuple:
    """
    Extract campaign_name_source from CSV and query database for campaign_id

    Args:
        blob_content: Raw CSV bytes from blob

    Returns:
        Tuple of (campaign_id, campaign_name) or (None, None) if not found

    BusinessCaseID: BC-DA-002 (File Processing & ETL Pipeline)
    """
    try:
        # Read first row of CSV to get campaign_name_source
        df = pd.read_csv(BytesIO(blob_content), nrows=1, dtype=str)

        if "campaign_name_source" not in df.columns:
            logging.warning("⚠️ [DEVICE-ACTIVATION] CSV missing 'campaign_name_source' column")
            return None, None

        campaign_name = df["campaign_name_source"].iloc[0]
        logging.info(f"📋 [DEVICE-ACTIVATION] CSV campaign_name_source: {campaign_name}")

        # Query database for campaign_id
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)

        query = f"""
        SELECT campaign_id, name, status
        FROM {IOE_SCHEMA}.campaigns_enhanced
        WHERE name = ?
        """

        results = db_service.execute_query(query, (campaign_name,), fetch_results=True)

        if not results:
            logging.warning(
                f"⚠️ [DEVICE-ACTIVATION] Campaign '{campaign_name}' not found in database"
            )
            return None, None

        # DatabaseService returns list of dictionaries, not tuples
        campaign_id = str(results[0]["campaign_id"])
        db_name = results[0]["name"]
        status = results[0]["status"]

        if status != "Active":
            logging.warning(
                f"⚠️ [DEVICE-ACTIVATION] Campaign '{campaign_name}' is not Active (status: {status})"
            )
            return None, None

        logging.info(f"🎯 [DEVICE-ACTIVATION] Found campaign_id: {campaign_id}")
        return campaign_id, db_name

    except Exception as e:
        logging.error(
            f"❌ [DEVICE-ACTIVATION] Error reading campaign from CSV: {str(e)}",
            exc_info=True,
        )
        return None, None


@bp.function_name(name="ProcessDeviceActivationBlob")
@bp.blob_trigger(arg_name="myblob", path="fs-ops/landing/{name}", connection="BLOB_STORAGE_CONNECTION")
def process_blob(myblob: func.InputStream):
    """
    Azure Function blob trigger for Device Activation CSV files.

    Triggered by a new file in the 'fs-ops/landing' folder.
    Expected filename pattern: MedicalGuardian_DeviceActivation[suffix]_YYYYMMDD_DELTA.csv

    BusinessCaseID: BC-DA-002 (File Processing & ETL Pipeline)

    Args:
        myblob: InputStream from Azure Blob Storage containing the CSV file

    Processing Flow:
        1. Validate filename pattern
        2. Call process_device_activation_file_complete() for 5-phase ETL:
           - Extract: Download CSV from blob storage
           - Load to Staging: Validate and INSERT into stg_device_activation_delta
           - Validate: SQL-based cleansing
           - Transform & Load Core: MERGE into members/devices, INSERT enrollments
           - Audit & Log: File processing log, move to processed folder

    Container Structure:
        - fs-ops/landing/    → Incoming files (trigger location)
        - fs-ops/staging/    → Files being processed
        - fs-ops/processed/  → Successfully processed files
        - fs-ops/error/      → Failed files

    Filename Pattern:
        MedicalGuardian_DeviceActivation[suffix]_YYYYMMDD_DELTA.csv
        Examples:
            - MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv
            - MedicalGuardian_DeviceActivationDTCMA_20251216_DELTA.csv
            - MedicalGuardian_DeviceActivation<any alphanumeric suffix>_YYYYMMDD_DELTA.csv
    """
    filename = myblob.name.split("/")[-1]
    logging.info(f"📄 [DEVICE-ACTIVATION] New file detected: {filename}")

    # Validate naming pattern
    # Expected: MedicalGuardian_DeviceActivation[suffix]_YYYYMMDD_DELTA.csv
    # Accepts: DeviceActivationMedicaid, DeviceActivationDTCMA, DeviceActivation<any suffix>
    import re

    pattern = r"^MedicalGuardian_DeviceActivation[A-Za-z]+_\d{8}_DELTA\.csv$"
    if not re.match(pattern, filename):
        logging.warning(f"⚠️ [DEVICE-ACTIVATION] File skipped due to invalid naming: {filename}")
        logging.warning(
            "⚠️ [DEVICE-ACTIVATION] Expected pattern: MedicalGuardian_DeviceActivation[suffix]_YYYYMMDD_DELTA.csv"
        )
        logging.warning(
            "⚠️ [DEVICE-ACTIVATION] Examples: MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv, MedicalGuardian_DeviceActivationDTCMA_20251216_DELTA.csv"
        )
        return

    logging.info(f"✅ [DEVICE-ACTIVATION] Filename validation passed: {filename}")

    # Skip Operations Device Activation files (Medicaid/DTCMA)
    # These should be processed by operations_device_activation_file_processor
    if "Medicaid" in filename or "DTCMA" in filename:
        logging.info(
            "⏭️ [DEVICE-ACTIVATION] Skipping file - handled by operations_device_activation_file_processor"
        )
        logging.info(f"   File: {filename}")
        logging.info("   Reason: Matches Operations campaign pattern (Medicaid or DTCMA)")
        logging.info(
            "   This file will be processed by operations_device_activation_file_processor instead"
        )
        return

    # Read blob content to extract campaign from CSV (NEW)
    blob_content = myblob.read()
    logging.info(f"📥 [PROCESSOR] blob_content read: {len(blob_content)} bytes")
    campaign_id, campaign_name = get_campaign_id_from_csv(blob_content)

    if campaign_id:
        logging.info(f"🎯 [DEVICE-ACTIVATION] Using campaign: {campaign_name} ({campaign_id})")
    else:
        logging.warning(
            "⚠️ [DEVICE-ACTIVATION] Could not determine campaign from CSV, will use auto-discovery"
        )

    logging.info("🔄 [DEVICE-ACTIVATION] Starting 5-phase ETL pipeline...")

    # Call shared logic to process the file
    # process_device_activation_file_complete() implements:
    # Phase 1: Extract (CSV download and validation)
    # Phase 2: Load to Staging (row-by-row validation, bulk INSERT)
    # Phase 3: Validate (SQL cleansing, org_id lookup)
    # Phase 4: Transform & Load Core (MERGE members/devices, INSERT enrollments)
    # Phase 5: Audit & Log (file processing log, move to processed folder)
    success, msg, details = process_device_activation_file_complete(
        file_path=filename,
        blob_content=blob_content,  # Pass blob content for extract phase
        campaign_id=campaign_id,  # NEW: Pass explicit campaign_id
        connection_string=None,  # Retrieved from Key Vault via ConfigManager
        uploaded_by_user="AzureFunction",
        error_threshold_pct=10.0,  # 10% error threshold (reject file if >10% rows fail)
        log_level="INFO",
    )

    if success:
        logging.info(f"✅ [DEVICE-ACTIVATION] File processing complete: {msg}")
        logging.info(
            f"📊 [DEVICE-ACTIVATION] Processing details: "
            f"Rows processed: {details.get('rows_processed', 0)}, "
            f"Rows validated: {details.get('rows_validated', 0)}, "
            f"Rows failed: {details.get('rows_failed', 0)}"
        )
    else:
        logging.error(f"❌ [DEVICE-ACTIVATION] File processing failed: {msg}")
        logging.error(f"📊 [DEVICE-ACTIVATION] Error details: {details}")
