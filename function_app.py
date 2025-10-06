import azure.functions as func
import logging

# Create the main app instance
app = func.FunctionApp()

# Import the blueprints from your function files
from functions import dtc_file_processor  # DTC wellness file processor
from functions import partner_file_processor  # Partner Campaign file processor
from functions.dtc_intro_call_scheduler import dtc_intro_call_bp  # DTC INTRO CALL
from functions import bland_ai_webhook
from functions.dtc_wellness_check_scheduler import dtc_wellness_check_bp
from functions.partner_campaign_scheduler import partner_campaign_bp  # Partner Campaign Scheduler
from functions.batch_completion_reconciler import batch_completion_bp  # Batch Completion Reconciler

# Register each blueprint with the main app
logging.info("Registering DTC File Processor blueprint...")
app.register_functions(dtc_file_processor.bp)

# Register the Partner Campaign file processor
logging.info("Registering Partner Campaign file processor...")
app.register_functions(partner_file_processor.bp)


# Register the blueprint containing our timer and HTTP triggers
logging.info("Registering DTC Intro Call ...")
app.register_functions(dtc_intro_call_bp)

# bland ai webhook
logging.info("Registering Bland AI Webhook...")
app.register_functions(bland_ai_webhook.bp)

# Registering DTC Wellness Check
logging.info("Registering DTC Wellness Check Call ...")
app.register_functions(dtc_wellness_check_bp)

# Register Partner Campaign Scheduler
logging.info("Registering Partner Campaign Scheduler...")
app.register_functions(partner_campaign_bp)

# Register Batch Completion Reconciler
logging.info("Registering Batch Completion Reconciler...")
app.register_functions(batch_completion_bp)

logging.info("All function blueprints have been registered successfully.")
