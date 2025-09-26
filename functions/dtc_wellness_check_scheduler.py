# NEW FILE: This file contains the triggers for the DTC Wellness Check function.
# It is a modified copy of the intro call scheduler.

import azure.functions as func
import logging
import json
from datetime import datetime

# Import the shared main logic function and common services
from af_code.af_dtc_intro_call.main_logic import create_bland_ai_batch_call
from af_code.af_dtc_intro_call.services.database_service import DatabaseService
from af_code.af_dtc_intro_call.services.member_service import MemberQualificationService

# --- CHANGE: Import the new, specialized service for the wellness check ---
from af_code.af_dtc_wellness_check.services.blandai_service_wellness import BlandAIServiceWellness

# --- END CHANGE ---

# Create a new, unique Blueprint to group the wellness check functions
dtc_wellness_check_bp = func.Blueprint()


@dtc_wellness_check_bp.timer_trigger(
    schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False
)
def timer_dtc_wellness_check(timer: func.TimerRequest) -> None:
    """Timer-triggered function for the DTC Wellness Check campaign."""
    logging.info("🩺 [TIMER] DTC Wellness Check Scheduler TRIGGERED")
    # --- CHANGE: Use the new Campaign ID for the Wellness Check ---
    campaign_id = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
    # --- END CHANGE ---
    logging.info(f"🩺 [TIMER] Using campaign ID: {campaign_id}")

    try:
        # Initialize services
        db_service = DatabaseService()
        member_service = MemberQualificationService(db_service)
        # --- CHANGE: Instantiate the new BlandAIServiceWellness ---
        bland_service = BlandAIServiceWellness(db_service)
        # --- END CHANGE ---

        # Execute the main logic (which is generic and can be reused)
        create_bland_ai_batch_call(campaign_id, member_service, bland_service)

    except Exception as e:
        logging.error(
            f"💥 [TIMER] A critical error occurred in the wellness check trigger: {str(e)}",
            exc_info=True,
        )

    logging.info("🩺 [TIMER] DTC Wellness Check Scheduler COMPLETED")


@dtc_wellness_check_bp.route(route="create_dtc_wellness_batch", methods=["POST"])
def http_dtc_wellness_check(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP-triggered function to manually create a DTC Wellness Check batch."""
    logging.info("🌐 [HTTP] Create DTC Wellness Batch TRIGGERED")
    try:
        req_body = req.get_json()
        campaign_id = req_body.get("campaign_id")

        if not campaign_id:
            return func.HttpResponse(
                json.dumps(
                    {"success": False, "error": "campaign_id is required in the request body."}
                ),
                status_code=400,
                mimetype="application/json",
            )

        # Initialize services
        db_service = DatabaseService()
        member_service = MemberQualificationService(db_service)
        # --- CHANGE: Instantiate the new BlandAIServiceWellness ---
        bland_service = BlandAIServiceWellness(db_service)
        # --- END CHANGE ---

        # Execute the main logic
        result = create_bland_ai_batch_call(campaign_id, member_service, bland_service)
        status_code = 200 if result.get("success") else 500

        return func.HttpResponse(
            json.dumps(result, default=str), status_code=status_code, mimetype="application/json"
        )

    except json.JSONDecodeError:
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid JSON in request body."}),
            status_code=400,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(
            f"💥 [HTTP] An internal server error occurred in wellness check: {str(e)}",
            exc_info=True,
        )
        return func.HttpResponse(
            json.dumps({"success": False, "error": "An internal server error occurred."}),
            status_code=500,
            mimetype="application/json",
        )
