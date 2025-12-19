import azure.functions as func
import logging
from af_code.af_device_activation_logic import process_device_activation_file_complete

# Create a "Blueprint" to organize this function
bp = func.Blueprint()


@bp.function_name(name="ProcessDeviceActivationBlob")
@bp.blob_trigger(
    arg_name="myblob", path="fs-ops/landing/{name}", connection="AzureWebJobsStorage"
)
def process_blob(myblob: func.InputStream):
    """
    Azure Function blob trigger for Device Activation CSV files.

    Triggered by a new file in the 'fs-ops/landing' folder.
    Expected filename pattern: MedicalGuardian_DeviceActivation[suffix]_YYYYMMDD_DELTA.csv

    BusinessCaseID: BC-TBD (Device Activation System)

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
