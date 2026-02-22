import azure.functions as func
import logging
from af_code.af_dtc_logic import process_dtc_file_complete
from af_code.shared.filename_validators import validate_dtc_wellness_filename

# Create a "Blueprint" to organize this function
bp = func.Blueprint()


@bp.function_name(name="ProcessDTCCampaignBlob")
@bp.blob_trigger(arg_name="myblob", path="fs-dtc/landing/{name}", connection="AzureWebJobsStorage")
def process_blob(myblob: func.InputStream):
    """
    Triggered by a new file in the 'landing' folder.

    BusinessCaseID: BC-109 (DTC Wellness Campaign Processing)
    """
    filename = myblob.name.split("/")[-1]
    logging.info(f"🟡 New file detected: {filename}")

    # Validate naming pattern using shared validator
    is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
        filename, allow_legacy=True  # Phase 1: Accept both patterns (set to False for Phase 2)
    )

    if not is_valid:
        logging.warning(f"⚠️ File skipped due to invalid naming: {filename}")
        logging.warning(f"   Error: {error_msg}")
        logging.info("   Expected: medical_guardian_dtc_wellness_YYYYMMDD.csv")
        logging.info("   Example: medical_guardian_dtc_wellness_20260202.csv")
        return

    # Log pattern type for monitoring
    if pattern_type == "LEGACY":
        logging.warning(f"⚠️ LEGACY pattern detected: {filename}")
        logging.warning("   This pattern will be deprecated in 2 weeks")
        logging.warning("   Please update to: medical_guardian_dtc_wellness_YYYYMMDD.csv")
    else:
        logging.info(f"✅ NEW pattern validated: {filename} (date: {date_str})")

    # Call your shared logic to process the file
    success, msg, _ = process_dtc_file_complete(
        file_path=filename, connection_string="", uploaded_by_user="ai.admin@medicalguardian.com"
    )

    if success:
        logging.info("✅ File processing complete.")
    else:
        logging.error(f"❌ File processing failed: {msg}")
