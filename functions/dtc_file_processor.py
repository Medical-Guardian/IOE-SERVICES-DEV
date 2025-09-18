import azure.functions as func
import logging
from af_code.af_dtc_logic import process_dtc_file_complete

# Create a "Blueprint" to organize this function
bp = func.Blueprint()

@bp.function_name(name="ProcessDTCCampaignBlob")
@bp.blob_trigger(
    arg_name="myblob",
    path="fs-dtc/landing/{name}",
    connection="AzureWebJobsStorage"
)
def process_blob(myblob: func.InputStream):
    """
    Triggered by a new file in the 'landing' folder.
    """
    filename = myblob.name.split('/')[-1]
    logging.info(f"🟡 New file detected: {filename}")

    # Validate naming pattern
    if not (filename.startswith("MedicalGuardian_DTCWellness_") and filename.endswith("_Delta.csv")):
        logging.warning(f"⚠️ File skipped due to invalid naming: {filename}")
        return

    # Call your shared logic to process the file
    success, msg, _ = process_dtc_file_complete(
        file_path=filename,
        connection_string="",
        uploaded_by_user="ai.admin@medicalguardian.com"
    )

    if success:
        logging.info("✅ File processing complete.")
    else:
        logging.error(f"❌ File processing failed: {msg}")