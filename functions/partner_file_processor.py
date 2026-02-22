import azure.functions as func
import logging
from af_code.af_partner_logic import process_partner_campaign_file_complete

# Create a "Blueprint" to organize this function
bp = func.Blueprint()


@bp.function_name(name="ProcessPartnerCampaignBlobValidationUI")
@bp.blob_trigger(
    arg_name="myblob",
    path="fs-partner/landing/{name}",
    connection="AzureWebJobsStorage",
)
def process_partner_campaign_blob(myblob: func.InputStream):
    """
    Educational: Triggered by a new Partner Campaign file in the 'landing' folder.

    This function demonstrates the Azure Functions blob trigger pattern.
    When a file is uploaded to fs-partner/landing/, this function automatically runs.
    """

    # Extract filename from the blob path
    filename = myblob.name.split("/")[-1]
    logging.info(f"🟡 New Partner Campaign file detected: {filename}")
    logging.info(f"📁 Full blob path: {myblob.name}")

    # Educational: Pre-validation check
    # Before doing expensive processing, we do a quick filename check
    if not filename.endswith(".csv"):
        logging.warning(f"⚠️ File skipped - not a CSV file: {filename}")
        return

    # Educational: Filename pattern validation
    # Partner Campaign files should follow: PartnerName_CampaignName_YYYYMMDD[_Suffix].csv
    import re

    pattern = r"^([A-Za-z0-9]+)_([A-Za-z0-9\/\s]+)_(\d{8})(_[A-Za-z0-9]+)?\.csv$"
    if not re.match(pattern, filename):
        logging.warning(f"⚠️ File skipped due to invalid naming pattern: {filename}")
        logging.info("Expected pattern: PartnerName_CampaignName_YYYYMMDD[_Suffix].csv")
        return

    try:
        # Educational: Call the main processing logic
        # We pass minimal parameters here - the heavy lifting happens in af_partner_logic.py
        success, message, details = process_partner_campaign_file_complete(
            file_path=filename,  # Just the filename - logic will handle blob operations
            connection_string="",  # Empty - logic gets secure connection from Key Vault
            uploaded_by_user="ai.admin@medicalguardian.com",  # Default system user
            error_threshold_pct=15.0,  # Allow up to 15% row errors
        )

        if success:
            logging.info("✅ Partner Campaign file processing completed successfully")
            logging.info(f"📊 Summary: {message}")

            # Educational: Log key metrics for monitoring
            if "records_processed" in details:
                logging.info(f"📈 Records processed: {details['records_processed']}")
                logging.info(f"✅ Records succeeded: {details['records_succeeded']}")
                logging.info(f"❌ Records failed: {details['records_failed']}")
                logging.info(f"⏱️ Processing time: {details.get('duration_seconds', 0):.2f}s")
        else:
            logging.error("❌ Partner Campaign file processing failed")
            logging.error(f"💥 Error: {message}")

            # Educational: Log additional error context for debugging
            if "error" in details:
                logging.error(f"🔍 Error details: {details['error']}")
            if "validation_errors_count" in details:
                logging.error(f"🚫 Validation errors: {details['validation_errors_count']}")

    except Exception as e:
        # Educational: Catch-all error handling
        # If something goes wrong in our logic, we want to log it clearly
        logging.error(f"💥 Critical error processing Partner Campaign file: {str(e)}")
        logging.error(f"📁 Failed file: {filename}")

        # Educational: This ensures the Azure Function doesn't crash
        # but we still log the problem for investigation
        import traceback

        logging.error(f"🔍 Stack trace: {traceback.format_exc()}")
