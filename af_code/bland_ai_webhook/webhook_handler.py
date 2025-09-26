import logging
import json
import traceback
from datetime import datetime, timezone
import azure.functions as func
from typing import Dict, Any, Optional

from .services.config_manager import ConfigManager
from .services.data_validator import DataValidator
from .services.duplicate_detector import DuplicateDetector
from .services.status_mapper import StatusMapper
from .services.database_orchestrator import DatabaseOrchestrator
from .services.business_rules_engine import BusinessRulesEngine
from .services.error_handler import ErrorHandler
from .services.service_bus_handler import ServiceBusHandler

# REMOVED: Unused imports from this specific file. The ServiceBusHandler now manages these.
# from azure.servicebus.aio import ServiceBusClient as AsyncServiceBusClient
# from azure.servicebus import ServiceBusMessage

logger = logging.getLogger(__name__)


class WebhookHandler:
    """
    Handles the processing of Bland AI webhook requests, orchestrating validation,
    duplicate detection, data mapping, database updates, and error handling.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        data_validator: DataValidator,
        duplicate_detector: DuplicateDetector,
        status_mapper: StatusMapper,
        db_orchestrator: DatabaseOrchestrator,
        business_rules: BusinessRulesEngine,
        error_handler: ErrorHandler,
        service_bus_handler: ServiceBusHandler,
    ):
        """
        Initialize the webhook handler with injected dependencies.
        """
        self.config_manager = config_manager
        self.data_validator = data_validator
        self.duplicate_detector = duplicate_detector
        self.status_mapper = status_mapper
        self.db_orchestrator = db_orchestrator
        self.business_rules = business_rules
        self.error_handler = error_handler
        self.service_bus_handler = service_bus_handler

    # REMOVED: This function was unused and its logic has been superseded by the ServiceBusHandler
    # and the main handle_webhook flow.
    # async def _trigger_post_call_analysis(self, call_id: str) -> None:
    #     ...

    async def handle_webhook(self, req: func.HttpRequest) -> func.HttpResponse:
        """
        Process the incoming webhook request through all pipeline stages.
        """
        request_id = f"webhook_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{id(req)}"
        logger.info(f"🚀 [WEBHOOK-START] {request_id} - Bland AI webhook received")
        webhook_data = {}

        try:
            # Phase 1: Initial Data Reception and Validation
            webhook_data = self._parse_request(req, request_id)
            if not webhook_data:
                return self._error_response(request_id, "Empty or invalid webhook payload", 400)

            validation_result = self.data_validator.validate_webhook_payload(webhook_data)
            if not validation_result.is_valid:
                self.error_handler.log_validation_error(
                    request_id, webhook_data, validation_result.errors
                )
                return self._error_response(
                    request_id, "Webhook validation failed", 400, errors=validation_result.errors
                )

            call_id = webhook_data["call_id"]

            # Phase 2: Duplicate Detection
            if self.duplicate_detector.check_duplicate(call_id):
                logger.warning(
                    f"⚠️ [DUPLICATE-DETECTED] {request_id} - Webhook already processed for call_id: {call_id}"
                )
                return self._success_response(request_id, "Webhook already processed", call_id)

            # Phase 3: Status Mapping and Business Logic
            mapped_data = self.status_mapper.map_webhook_to_internal_format(webhook_data)
            enrollment_update = self.business_rules.determine_enrollment_update(
                webhook_data, mapped_data
            )

            # Phase 4: Atomic Database Updates
            update_result = self.db_orchestrator.execute_atomic_updates(
                webhook_data=webhook_data,
                mapped_data=mapped_data,
                enrollment_update=enrollment_update,
                request_id=request_id,
            )

            if not update_result.success:
                self.error_handler.log_database_error(
                    request_id,
                    "Atomic database updates",
                    update_result.error_message,
                    update_result.tables_updated,
                )
                return self._error_response(request_id, "Internal processing error", 500)

            # --- Phase 5: Log intent, send message, and update status ---
            submission_time = datetime.now(timezone.utc)
            # This re-assignment is redundant as call_id is already defined, but keeping for clarity.
            call_id = webhook_data["call_id"]

            try:
                # 1. Log the intent to submit to the database FIRST
                self.db_orchestrator.log_queue_submission_intent(
                    call_id=call_id, submission_time=submission_time
                )

                # 2. Attempt to send the message to Service Bus
                success, message_id_or_error = await self.service_bus_handler.send_analysis_message(
                    webhook_data=webhook_data, mapped_data=mapped_data, request_id=request_id
                )

                # 3. Update the database record with the outcome
                if success:
                    logger.info(f"✅ Service Bus message sent. ID: {message_id_or_error}")
                    self.db_orchestrator.update_queue_submission_status(
                        call_id=call_id, message_id=message_id_or_error, success=True
                    )
                else:
                    logger.error(f"🚨 Failed to send Service Bus message: {message_id_or_error}")
                    self.db_orchestrator.update_queue_submission_status(
                        call_id=call_id, message_id=None, success=False
                    )
            # CORRECTED: Added the required 'except' block to handle potential errors
            # during the submission process and re-raise them to the main error handler.
            except Exception as e:
                logger.error(
                    f"🚨 A critical error occurred during the queue submission process: {str(e)}"
                )
                raise

            # REMOVED: The entire block of old, duplicated, and unreachable code that followed was deleted.
            # This includes the incorrect second "Phase 5", "Phase 6", and "Phase 7" comments and logic.

            # --- Phase 6: Success Response --- (This is the new final step)
            logger.info(
                f"🎉 [WEBHOOK-SUCCESS] {request_id} - Webhook processing completed successfully"
            )
            return self._success_response(
                request_id,
                "Webhook processed successfully",
                call_id,
                disposition=mapped_data.disposition,
                tables_updated=update_result.tables_updated,
            )

        except Exception as e:
            error_message = str(e)
            stack_trace = traceback.format_exc()
            self.error_handler.log_critical_error(
                request_id, webhook_data, error_message, stack_trace
            )
            return self._error_response(request_id, "An unexpected error occurred", 500)

    def _parse_request(self, req: func.HttpRequest, request_id: str) -> Optional[Dict[str, Any]]:
        """Parse the incoming HTTP request and extract the JSON payload."""
        try:
            return req.get_json()
        except Exception as e:
            logger.error(f"❌ [PAYLOAD-ERROR] {request_id} - Failed to parse JSON: {str(e)}")
            return None

    def _error_response(
        self, request_id: str, message: str, status_code: int, errors: Optional[list] = None
    ) -> func.HttpResponse:
        """Create a standardized error HTTP response."""
        response_body = {"status": "error", "message": message, "request_id": request_id}
        if errors:
            response_body["errors"] = errors
        return func.HttpResponse(
            json.dumps(response_body), status_code=status_code, mimetype="application/json"
        )

    def _success_response(
        self,
        request_id: str,
        message: str,
        call_id: str,
        disposition: Optional[str] = None,
        tables_updated: Optional[list] = None,
    ) -> func.HttpResponse:
        """Create a standardized success HTTP response."""
        response_body = {
            "status": "success",
            "message": message,
            "call_id": call_id,
            "request_id": request_id,
        }
        if disposition:
            response_body["disposition"] = disposition
        if tables_updated:
            response_body["tables_updated"] = tables_updated
        return func.HttpResponse(
            json.dumps(response_body), status_code=200, mimetype="application/json"
        )
