"""
Device Activation Campaign Closure Scheduler - Azure Function
BusinessCaseID: BC-DA-007
Created: 2026-01-20

Automatically unenrolls Device Activation campaign members when their
90-day campaign window (campaign_end_date) is reached.

Timer Trigger: Runs hourly at the top of every hour (0 0 * * * *)
HTTP Trigger: Manual endpoint for testing (/api/device_activation_campaign_closure)

Pattern: Follows device_activation_scheduler.py structure with distributed locking
"""

import azure.functions as func
import logging
from datetime import datetime
import json
import traceback

# Import services
from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.device_activation_scheduler.services.campaign_closure_service import (
    CampaignClosureService,
)

# Create Blueprint to group these functions
device_activation_closure_bp = func.Blueprint()


@device_activation_closure_bp.function_name(name="timer_device_activation_campaign_closure")
@device_activation_closure_bp.timer_trigger(
    schedule="0 0 * * * *",  # Every hour at :00 minutes
    arg_name="timer",
    run_on_startup=False,
)
def timer_device_activation_campaign_closure(timer: func.TimerRequest) -> None:
    """
    Hourly timer trigger for Device Activation campaign closure

    Runs at the top of every hour to automatically unenroll members
    who have reached their campaign_end_date (90-day window completion).

    Features:
    - Distributed locking prevents concurrent executions
    - Updates enrollment status to UNENROLLED
    - Logs all status changes to audit history
    - Comprehensive logging for monitoring

    BusinessCaseID: BC-DA-007
    """
    start_time = datetime.utcnow()
    request_id = f"da-closure-timer-{start_time.strftime('%Y%m%d-%H%M%S')}"

    logging.info("=" * 80)
    logging.info("⏰ [DA-CLOSURE] Device Activation Campaign Closure Scheduler TRIGGERED")
    logging.info(f"🆔 [DA-CLOSURE] Request ID: {request_id}")
    logging.info(f"🕐 [DA-CLOSURE] Current time (UTC): {start_time.isoformat()}")
    logging.info("=" * 80)

    _execute_campaign_closure(request_id, start_time, trigger_type="timer")


@device_activation_closure_bp.route(
    route="device_activation_campaign_closure", methods=["GET", "POST"]
)
def http_device_activation_campaign_closure(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP endpoint for manual Device Activation campaign closure

    Allows manual triggering of campaign closure for testing or on-demand execution.

    GET/POST /api/device_activation_campaign_closure

    Response:
    {
        "success": true,
        "request_id": "da-closure-http-20260120-143022",
        "timestamp": "2026-01-20T14:30:22.123456",
        "result": {
            "enrollments_closed": 15,
            "campaigns_affected": ["Medicaid DeviceActivation", "DTCMA DeviceActivation"],
            "members_unenrolled": 15,
            "execution_duration_seconds": 2.45
        }
    }

    BusinessCaseID: BC-DA-007
    """
    start_time = datetime.utcnow()
    request_id = f"da-closure-http-{start_time.strftime('%Y%m%d-%H%M%S')}"

    logging.info("=" * 80)
    logging.info("🌐 [DA-CLOSURE] HTTP endpoint called for Device Activation campaign closure")
    logging.info(f"🆔 [DA-CLOSURE] Request ID: {request_id}")
    logging.info(f"🕐 [DA-CLOSURE] Current time (UTC): {start_time.isoformat()}")
    logging.info("=" * 80)

    try:
        result = _execute_campaign_closure(request_id, start_time, trigger_type="http")

        response_data = {
            "success": True,
            "request_id": request_id,
            "timestamp": start_time.isoformat(),
            "result": result,
        }

        logging.info("✅ [DA-CLOSURE] HTTP request completed successfully")
        logging.info(f"📊 [DA-CLOSURE] Response: {json.dumps(response_data, default=str)}")

        return func.HttpResponse(
            json.dumps(response_data, indent=2, default=str),
            status_code=200,
            mimetype="application/json",
        )

    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"🚨 [DA-CLOSURE] HTTP endpoint error: {str(e)}")
        logging.error(f"🚨 [DA-CLOSURE] Traceback: {error_details}")

        error_response = {
            "success": False,
            "request_id": request_id,
            "timestamp": start_time.isoformat(),
            "error": str(e),
            "details": "An internal server error occurred during campaign closure",
        }

        return func.HttpResponse(
            json.dumps(error_response, indent=2),
            status_code=500,
            mimetype="application/json",
        )


def _execute_campaign_closure(
    request_id: str, start_time: datetime, trigger_type: str = "timer"
) -> dict:
    """
    Core campaign closure logic shared between timer and HTTP triggers

    Args:
        request_id: Unique request identifier
        start_time: Execution start timestamp
        trigger_type: 'timer' or 'http'

    Returns:
        dict: Execution summary with counts and metrics
            - enrollments_closed (int): Number of enrollments updated
            - campaigns_affected (List[str]): Campaign names affected
            - members_unenrolled (int): Unique members unenrolled
            - execution_duration_seconds (float): Total execution time
    """
    try:
        # Step 1: Initialize services
        logging.info("🔧 [DA-CLOSURE] Step 1: Initializing services...")
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        closure_service = CampaignClosureService(db_service, config_manager)
        logging.info("✅ [DA-CLOSURE] Step 1: Services initialized successfully")

        # Step 2: Execute campaign closure (with distributed locking)
        logging.info("🔧 [DA-CLOSURE] Step 2: Executing campaign closure...")
        result = closure_service.close_expired_campaigns()
        logging.info("✅ [DA-CLOSURE] Step 2: Campaign closure completed")

        # Step 3: Log comprehensive summary
        duration = (datetime.utcnow() - start_time).total_seconds()

        logging.info("=" * 80)
        logging.info("🎉 [DA-CLOSURE] EXECUTION COMPLETED SUCCESSFULLY")
        logging.info(f"⏱️  [DA-CLOSURE] Total Duration: {duration:.2f} seconds")
        logging.info(f"📊 [DA-CLOSURE] Enrollments Closed: {result['enrollments_closed']}")
        logging.info(f"👥 [DA-CLOSURE] Members Unenrolled: {result['members_unenrolled']}")
        logging.info(f"📋 [DA-CLOSURE] Campaigns Affected: {len(result['campaigns_affected'])}")

        if result["campaigns_affected"]:
            logging.info("📋 [DA-CLOSURE] Campaign Names:")
            for campaign_name in result["campaigns_affected"]:
                logging.info(f"   - {campaign_name}")

        # Check if execution was skipped due to lock
        if "skipped_reason" in result:
            logging.info(f"ℹ️  [DA-CLOSURE] Execution skipped: {result['skipped_reason']}")

        logging.info("=" * 80)

        return result

    except Exception as e:
        error_details = traceback.format_exc()
        logging.error("=" * 80)
        logging.error("🚨 [DA-CLOSURE] CRITICAL ERROR during execution")
        logging.error(f"🚨 [DA-CLOSURE] Error: {str(e)}")
        logging.error(f"🚨 [DA-CLOSURE] Traceback: {error_details}")
        logging.error("=" * 80)

        # Timer: don't re-raise (let timer continue next hour)
        if trigger_type == "timer":
            logging.error("⚠️  [DA-CLOSURE] Timer execution failed but will retry next hour...")
            return {
                "enrollments_closed": 0,
                "campaigns_affected": [],
                "members_unenrolled": 0,
                "execution_duration_seconds": 0,
                "error": str(e),
            }
        else:
            # HTTP: re-raise for error response
            raise
