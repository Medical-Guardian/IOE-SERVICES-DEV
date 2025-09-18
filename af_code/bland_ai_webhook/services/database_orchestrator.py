import logging
import json
import time
from typing import Dict, Any, Optional

from .database_service import DatabaseService
from ..models.update_result import UpdateResult
from ..models.mapped_call_data import MappedCallData
from ..models.enrollment_update import EnrollmentUpdate

logger = logging.getLogger(__name__)


class DatabaseOrchestrator:
    """
    Manages atomic database operations using a dedicated DatabaseService.
    Ensures that updates to multiple tables are performed in a single transaction.
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self.max_retries = 3
        self.retry_delay = 2
        logger.info("💾 [DB-ORCHESTRATOR] Initialized to use DatabaseService")


    # ADD this new function to log the initial attempt
    def log_queue_submission_intent(self, call_id: str, submission_time: any) -> None:
        """Logs the intent to submit a message to the analysis queue."""
        logger.info(f"✍️ [DB-ORCHESTRATOR] Logging queue submission intent for call_id '{call_id}'...")
        query = """
            INSERT INTO engage360.analysis_queue_status
            (call_id, webhook_received_dttm, queue_submitted_dttm, 
             service_bus_message_id, processing_status, retry_count)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        # Insert with a status of 'SUBMITTING' and NULL for the message_id
        params = (call_id, submission_time, submission_time, None, "SUBMITTING", 0)
        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info("✅ [DB-ORCHESTRATOR] Queue submission intent logged successfully.")
        except Exception as e:
            logger.error(f"🚨 [DB-ORCHESTRATOR] Failed to log queue submission intent: {str(e)}")
            raise

    # ADD this new function to update the status after sending
    def update_queue_submission_status(self, call_id: str, message_id: Optional[str], success: bool) -> None:
        """Updates the queue status record with the result of the submission attempt."""
        logger.info(f"🔄 [DB-ORCHESTRATOR] Updating queue submission status for call_id '{call_id}'...")
        status = "PENDING" if success else "FAILED"
        query = """
            UPDATE engage360.analysis_queue_status
            SET service_bus_message_id = %s, processing_status = %s, queue_submitted_dttm = SYSDATETIMEOFFSET()
            WHERE call_id = %s
        """
        params = (message_id, status, call_id)
        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info(f"✅ [DB-ORCHESTRATOR] Queue submission status updated to '{status}'.")
        except Exception as e:
            logger.error(f"🚨 [DB-ORCHESTRATOR] Failed to update queue submission status: {str(e)}")
            # This is a critical error to log, as the message may have been sent but the DB update failed.
            raise

    def execute_atomic_updates(
            self,
            webhook_data: Dict[str, Any],
            mapped_data: MappedCallData,
            enrollment_update: EnrollmentUpdate,
            request_id: str
    ) -> UpdateResult:
        """
        Executes all database updates in a single atomic transaction.
        This includes inserting to bland_call_logs and updating outreach_attempts and enrollment.
        """
        logger.info(f"💾 [DB-ORCHESTRATOR] Starting atomic updates for request_id: {request_id}")
        start_time = time.time()
        queries_to_run = []
        tables_updated = []
        metadata = webhook_data.get('metadata', {})

        # --- 1. Build Query for bland_call_logs (Raw Webhook Data) ---
        bland_log_query = """
            INSERT INTO engage360.bland_call_logs (
                from_number, price, end_at, status, call_id, summary, analysis, batch_id, 
                first_name, last_name, member_id, attempt_id, language_pref, call_type_code, 
                salesforce_account_number, campaign_id, completed, created_at, pathway_id, 
                answered_by, transcripts, max_duration, pathway_logs, pathway_tags, 
                call_ended_by, error_message, recording_url, analysis_schema, 
                disposition_tag, corrected_duration, concatenated_transcript, raw_bland_response
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        def to_json_string(data):
            return json.dumps(data) if data is not None else None

        bland_log_params = (
            webhook_data.get('from'), webhook_data.get('price'), webhook_data.get('end_at'), webhook_data.get('status'),
            webhook_data.get('call_id'), webhook_data.get('summary'), to_json_string(webhook_data.get('analysis')),
            webhook_data.get('batch_id'), metadata.get('first_name'), metadata.get('last_name'),
            metadata.get('member_id'),
            metadata.get('attempt_id'), metadata.get('language_pref'), metadata.get('call_type_code'),
            metadata.get('salesforce_account_number'), metadata.get('campaign_id'), webhook_data.get('completed'),
            webhook_data.get('created_at'), webhook_data.get('pathway_id'), webhook_data.get('answered_by'),
            to_json_string(webhook_data.get('transcripts')), webhook_data.get('max_duration'),
            to_json_string(webhook_data.get('pathway_logs')), to_json_string(webhook_data.get('pathway_tags')),
            webhook_data.get('call_ended_by'), webhook_data.get('error_message'), webhook_data.get('recording_url'),
            webhook_data.get('analysis_schema'), webhook_data.get('disposition_tag'),
            webhook_data.get('corrected_duration'), webhook_data.get('concatenated_transcript'),
            to_json_string(webhook_data)  # Add the full webhook response
        )
        queries_to_run.append((bland_log_query, bland_log_params))
        tables_updated.append("bland_call_logs")

        # --- 2. Build Query for outreach_attempts (Processed Outcome) ---
        attempt_id = metadata.get('attempt_id')
        if attempt_id:
            outreach_attempt_query = """
                UPDATE engage360.outreach_attempts
                SET 
                    vendor_session_id = %s,
                    disposition = %s,
                    duration_sec = %s,
                    response_summary = %s,
                    next_action = %s,
                    status_updated_ts = SYSDATETIMEOFFSET()
                WHERE 
                    attempt_id = %s
            """
            outreach_attempt_params = (
                webhook_data.get('call_id'),
                mapped_data.disposition,
                mapped_data.duration_sec,
                mapped_data.response_summary,
                mapped_data.next_action,
                attempt_id
            )
            queries_to_run.append((outreach_attempt_query, outreach_attempt_params))
            tables_updated.append("outreach_attempts")
        else:
            logger.warning(
                f"⚠️ [DB-ORCHESTRATOR] No attempt_id in metadata for request_id: {request_id}. Skipping outreach_attempts update.")

        # --- 3. Build Query for enrollment (Conditional Status Change) ---
        if enrollment_update.should_update:
            enrollment_query = """
                UPDATE engage360.member_campaign_enrollments_enhanced
                SET status = %s, last_updated = GETDATE(), update_reason = %s
                WHERE phone_number = %s
            """
            enrollment_params = (enrollment_update.new_status, enrollment_update.reason, webhook_data.get('to'))
            queries_to_run.append((enrollment_query, enrollment_params))
            tables_updated.append("member_campaign_enrollments_enhanced")

        # --- 4. Execute the entire transaction ---
        for attempt in range(self.max_retries):
            try:
                records_affected = self.db_service.execute_transaction(queries_to_run)
                logger.info(
                    f"✅ [DB-ORCHESTRATOR] Transaction committed successfully for request_id: {request_id}. Tables updated: {tables_updated}")
                return UpdateResult(
                    success=True, tables_updated=tables_updated, error_message=None,
                    records_affected=records_affected, operation_duration_ms=int((time.time() - start_time) * 1000)
                )
            except Exception as e:
                logger.error(
                    f"🚨 [DB-ORCHESTRATOR] Transaction failed on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    return UpdateResult(
                        success=False, tables_updated=[], error_message=str(e),
                        records_affected=0, operation_duration_ms=int((time.time() - start_time) * 1000)
                    )

        return UpdateResult(
            success=False, tables_updated=[], error_message="Fell through retry loop",
            records_affected=0, operation_duration_ms=int((time.time() - start_time) * 1000)
        )

