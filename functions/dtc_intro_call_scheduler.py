# NEW: This file contains the triggers for the DTC Intro Call function.
import azure.functions as func
import logging
import json
from datetime import datetime

# Import the main logic function and services from the af_code directory
from af_code.af_dtc_intro_call.main_logic import create_bland_ai_batch_call
from af_code.af_dtc_intro_call.services.database_service import DatabaseService
from af_code.af_dtc_intro_call.services.member_service import MemberQualificationService
from af_code.af_dtc_intro_call.services.blandai_service import BlandAIService
from af_code.af_dtc_intro_call.utils.config import KEY_VAULT_URL

# Create a Blueprint to group these functions
dtc_intro_call_bp = func.Blueprint()


@dtc_intro_call_bp.timer_trigger(schedule="0 */10 * * * *", arg_name="timer", run_on_startup=False)
def timer_dtc_intro_call(timer: func.TimerRequest) -> None:
    logging.info("⏰ [TIMER] DTC Intro Call Scheduler TRIGGERED")
    campaign_id = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
    logging.info(f"📋 [TIMER] Using campaign ID: {campaign_id}")

    try:
        # Initialize services
        db_service = DatabaseService()
        member_service = MemberQualificationService(db_service)
        bland_service = BlandAIService(db_service)

        # Execute the main logic
        create_bland_ai_batch_call(campaign_id, member_service, bland_service)

    except Exception as e:
        logging.error(
            f"💥 [TIMER] A critical error occurred in the trigger: {str(e)}", exc_info=True
        )

    logging.info("⏰ [TIMER] DTC Intro Call Scheduler COMPLETED")


@dtc_intro_call_bp.route(route="create_dtc_intro_batch", methods=["POST"])
def http_dtc_intro_call(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("🌐 [HTTP] Create DTC Intro Batch TRIGGERED")
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
        bland_service = BlandAIService(db_service)

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
        logging.error(f"💥 [HTTP] An internal server error occurred: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"success": False, "error": "An internal server error occurred."}),
            status_code=500,
            mimetype="application/json",
        )
