import azure.functions as func
import logging
import os

# Force module reload version: 2025-10-16-v1
logging.info("🔄 [FUNCTION-APP] Loading function_app.py - FORCING MODULE RELOAD")

# Verify critical environment variables at startup
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")
DB_SECRET_NAME = os.environ.get("DB_SECRET_NAME", "SqlConnectionStringIOE")

logging.info(f"🔍 Environment check:")
logging.info(f"   KEY_VAULT_URL: {'✅ Set' if KEY_VAULT_URL else '❌ Missing'}")
logging.info(f"   DB_SECRET_NAME: {'✅ Set' if DB_SECRET_NAME else '❌ Missing'}")

if not KEY_VAULT_URL:
    logging.error("❌ CRITICAL: KEY_VAULT_URL environment variable is not set!")
    logging.error("   This will cause all database-dependent functions to fail during import.")

# Create the main app instance
app = func.FunctionApp()

# Import the blueprints from your function files with error handling
try:
    from functions import dtc_file_processor  # DTC wellness file processor
    logging.info("✅ Successfully imported dtc_file_processor")
    app.register_functions(dtc_file_processor.bp)
    logging.info("✅ Successfully registered DTC File Processor blueprint")
except Exception as e:
    logging.error(f"❌ Failed to import/register dtc_file_processor: {str(e)}")

try:
    from functions import partner_file_processor  # Partner Campaign file processor
    logging.info("✅ Successfully imported partner_file_processor")
    app.register_functions(partner_file_processor.bp)
    logging.info("✅ Successfully registered Partner Campaign file processor")
except Exception as e:
    logging.error(f"❌ Failed to import/register partner_file_processor: {str(e)}")

try:
    from functions.dtc_intro_call_scheduler import dtc_intro_call_bp  # DTC INTRO CALL
    logging.info("✅ Successfully imported dtc_intro_call_bp")
    app.register_functions(dtc_intro_call_bp)
    logging.info("✅ Successfully registered DTC Intro Call")
except Exception as e:
    logging.error(f"❌ Failed to import/register dtc_intro_call_bp: {str(e)}")

try:
    from functions import bland_ai_webhook
    logging.info("✅ Successfully imported bland_ai_webhook")
    app.register_functions(bland_ai_webhook.bp)
    logging.info("✅ Successfully registered Bland AI Webhook")
except Exception as e:
    logging.error(f"❌ Failed to import/register bland_ai_webhook: {str(e)}")

try:
    from functions.dtc_wellness_check_scheduler import dtc_wellness_check_bp
    logging.info("✅ Successfully imported dtc_wellness_check_bp")
    app.register_functions(dtc_wellness_check_bp)
    logging.info("✅ Successfully registered DTC Wellness Check Call")
except Exception as e:
    logging.error(f"❌ Failed to import/register dtc_wellness_check_bp: {str(e)}")

try:
    from functions.partner_campaign_scheduler import partner_campaign_bp  # Partner Campaign Scheduler
    logging.info("✅ Successfully imported partner_campaign_bp")
    app.register_functions(partner_campaign_bp)
    logging.info("✅ Successfully registered Partner Campaign Scheduler")
except Exception as e:
    logging.error(f"❌ Failed to import/register partner_campaign_bp: {str(e)}")

try:
    from functions.batch_completion_reconciler import batch_completion_bp  # Batch Completion Reconciler
    logging.info("✅ Successfully imported batch_completion_bp")
    app.register_functions(batch_completion_bp)
    logging.info("✅ Successfully registered Batch Completion Reconciler")
except Exception as e:
    logging.error(f"❌ Failed to import/register batch_completion_bp: {str(e)}")

logging.info("Function registration process completed.")