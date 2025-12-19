# Device Activation Scheduler - Azure Function Triggers
# BusinessCaseID: BC-TBD (Device Activation System)
# Created: 2025-12-07
#
# This file contains the triggers for the Device Activation campaign scheduler.
# The scheduler runs every 15 minutes to:
# 1. Find eligible members (based on call sequence and business hours)
# 2. Create batches for Bland AI
# 3. Submit batches for calling
#
# Supports both Device Activation and Operations campaign types
#
# Call Sequence:
# - Call 1: Day 2 (delivery_date + 2 business days)
# - Call 2: Day 4 (Call 1 + 2 business days, if no success)
# - Call 3: Day 6 (Call 2 + 2 business days, if no success)
# - Call 4: Day 11 (Call 3 + 5 business days, if no success)
# - Call 5+: Weekly until 90-day limit
#
# Pattern: Follows dtc_intro_call_scheduler.py structure

import azure.functions as func
import logging
import json
from datetime import datetime

# Import the main logic function and services from the af_code directory
from af_code.device_activation_scheduler.main_logic import create_device_activation_batch
from af_code.device_activation_scheduler.services.eligibility_service import (
    EligibilityService,
)
from af_code.device_activation_scheduler.services.batch_orchestrator import (
    BatchOrchestrator,
)
from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService

# Create a Blueprint to group these functions
device_activation_bp = func.Blueprint()


@device_activation_bp.function_name(name="timer_device_activation")
@device_activation_bp.timer_trigger(
    schedule="0 */15 * * * *",  # Every 15 minutes (updated for Operations campaigns)
    arg_name="timer",
    run_on_startup=False,
)
def timer_device_activation(timer: func.TimerRequest) -> None:
    """
    Timer-triggered scheduler for Device Activation campaign calls

    Runs every 15 minutes to find eligible members and create call batches.
    Supports both Device Activation and Operations campaign types.

    BusinessCaseID: BC-TBD (Device Activation System)
    """
    logging.info("⏰ [TIMER] Device Activation Scheduler TRIGGERED")
    logging.info(f"🕐 [TIMER] Current time (UTC): {datetime.utcnow().isoformat()}")

    try:
        # Initialize services
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        eligibility_service = EligibilityService(db_service)
        batch_orchestrator = BatchOrchestrator(db_service, config_manager)

        # Execute the main logic
        result = create_device_activation_batch(eligibility_service, batch_orchestrator)

        # Log result summary
        if result.get("success"):
            logging.info("✅ [TIMER] Device Activation batch creation SUCCEEDED")
            logging.info(
                f"📊 [TIMER] Summary: {result.get('total_eligible', 0)} eligible, "
                f"{result.get('batches_created', 0)} batches created, "
                f"{result.get('calls_submitted', 0)} calls submitted"
            )
        else:
            logging.warning("⚠️ [TIMER] Device Activation batch creation completed with issues")
            logging.warning(f"ℹ️ [TIMER] Message: {result.get('message', 'No details available')}")

    except Exception as e:
        logging.error(
            f"💥 [TIMER] A critical error occurred in Device Activation scheduler: {str(e)}",
            exc_info=True,
        )

    logging.info("⏰ [TIMER] Device Activation Scheduler COMPLETED")


@device_activation_bp.function_name(name="http_device_activation")
@device_activation_bp.route(route="create_device_activation_batch", methods=["POST"])
def http_device_activation(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP-triggered endpoint for manual Device Activation batch creation

    Allows manual triggering of batch creation for testing or on-demand execution.

    POST /api/create_device_activation_batch
    Body (optional): {"force": true}  # Force batch creation even if no eligible members

    BusinessCaseID: BC-TBD (Device Activation System)
    """
    logging.info("🌐 [HTTP] Create Device Activation Batch TRIGGERED")

    try:
        # Parse request body (optional)
        req_body = {}
        try:
            req_body = req.get_json()
        except ValueError:
            # No JSON body provided, use defaults
            pass

        force = req_body.get("force", False)
        logging.info(f"ℹ️ [HTTP] Force mode: {force}")

        # Initialize services
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        eligibility_service = EligibilityService(db_service)
        batch_orchestrator = BatchOrchestrator(db_service, config_manager)

        # Execute the main logic
        result = create_device_activation_batch(
            eligibility_service, batch_orchestrator, force=force
        )

        # Determine status code
        status_code = 200 if result.get("success") else 500

        # Build response
        response_body = {
            "success": result.get("success"),
            "message": result.get("message"),
            "total_eligible": result.get("total_eligible", 0),
            "batches_created": result.get("batches_created", 0),
            "calls_submitted": result.get("calls_submitted", 0),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return func.HttpResponse(
            json.dumps(response_body, default=str),
            status_code=status_code,
            mimetype="application/json",
        )

    except json.JSONDecodeError:
        logging.error("❌ [HTTP] Invalid JSON in request body")
        return func.HttpResponse(
            json.dumps({"success": False, "error": "Invalid JSON in request body."}),
            status_code=400,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"💥 [HTTP] An internal server error occurred: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps(
                {
                    "success": False,
                    "error": "An internal server error occurred.",
                    "details": str(e),
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
