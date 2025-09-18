import azure.functions as func
import logging
# Create the main app instance
app = func.FunctionApp()

# Import the blueprints from your function files
from functions import dtc_file_processor #DTC wellness file processor
from functions import partner_file_processor  #Partner Campaign file processor
from functions.dtc_intro_call_scheduler import dtc_intro_call_bp #DTC INTRO CALL
from functions import bland_ai_webhook

# Register each blueprint with the main app
logging.info("Registering DTC File Processor blueprint...")
app.register_functions(dtc_file_processor.bp)

# Register the Partner Campaign file processor
logging.info("Registering Partner Campaign file processor...")
app.register_functions(partner_file_processor.bp)


# Register the blueprint containing our timer and HTTP triggers
logging.info("Registering DTC Intro Call ...")
app.register_functions(dtc_intro_call_bp)

#bland ai webhook
logging.info("Registering Bland AI Webhook...")
app.register_functions(bland_ai_webhook.bp)


logging.info("All function blueprints have been registered successfully.")