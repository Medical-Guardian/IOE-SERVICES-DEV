# database_orchestrator.py
import logging
import time
from typing import Dict, Any, Optional, List, Tuple

from .database_service import DatabaseService
from ..models.update_result import UpdateResult
from ..models.mapped_call_data import MappedCallData
from ..models.enrollment_update import EnrollmentUpdate

logger = logging.getLogger(__name__)


class DatabaseOrchestrator:
    """
    Manages atomic database operations using a dedicated DatabaseService.
    Responsibilities:
      - Build SQL for call log insert, outreach attempt update, and enrollment update
      - Execute them atomically with retries.
      - Provide helpers for analysis queue status logging.
    """

    def __init__(self, db_service: DatabaseService, max_retries: int = 3, retry_delay: float = 1.0):
        self.db_service = db_service
        self.max_retries = max_retries
        self.retry_delay = retry_delay  # seconds (exponential backoff)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def execute_atomic_updates(
        self,
        webhook_data: Dict[str, Any],
        mapped_data: MappedCallData,
        enrollment_update: EnrollmentUpdate,
        request_id: Optional[str] = None,
    ) -> UpdateResult:
        if request_id:
            logger.info(f"[DB-ORCH] request_id={request_id} execute_atomic_updates starting")
        """
        Builds and executes the batched SQL statements as ONE transaction:
          1) INSERT engage360.bland_call_logs
          2) UPDATE engage360.outreach_attempts (if attempt_id present)
          3) UPDATE engage360.member_campaign_enrollments_enhanced (conditional/idempotent)

        Returns UpdateResult with tables updated and timings.
        """
        start_time = time.time()
        tables_updated: List[str] = []
        queries_to_run: List[Tuple[str, Tuple]] = []

        # 1) Call logs insert (always)
        log_query, log_params = self._build_insert_bland_call_logs(webhook_data)
        queries_to_run.append((log_query, log_params))
        tables_updated.append("bland_call_logs")

        # 2) Outreach attempts update (optional)
        att_qp = self._build_update_outreach_attempts(webhook_data, mapped_data)
        if att_qp:
            queries_to_run.append(att_qp)
            tables_updated.append("outreach_attempts")

        # 3) Enrollment update (conditional + idempotent)
        enr_qp = self._build_update_enrollment(webhook_data, enrollment_update)
        if enr_qp:
            queries_to_run.append(enr_qp)
            tables_updated.append("member_campaign_enrollments_enhanced")

        # Execute with retries
        for attempt in range(self.max_retries):
            try:
                self.db_service.execute_transaction(queries_to_run)
                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    f"✅ [DB-ORCH] Transaction committed in {duration_ms} ms "
                    f"(tables={tables_updated})"
                )
                return UpdateResult(
                    success=True,
                    tables_updated=tables_updated,
                    error_message=None,
                    records_affected=len(queries_to_run),
                    operation_duration_ms=duration_ms,
                )
            except Exception as e:
                logger.error(
                    f"🚨 [DB-ORCH] TX failed attempt {attempt + 1}/{self.max_retries}: {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))
                else:
                    duration_ms = int((time.time() - start_time) * 1000)
                    return UpdateResult(
                        success=False,
                        tables_updated=[],
                        error_message=str(e),
                        records_affected=0,
                        operation_duration_ms=duration_ms,
                    )

    # -------- Analysis queue helpers (optional, used by ServiceBus flow) ------
    def log_queue_submission_intent(self, call_id: str, submission_time) -> None:
        """
        Insert a SUBMITTING row into engage360.analysis_queue_status.
        """
        query = """
            INSERT INTO engage360.analysis_queue_status
                (call_id, webhook_received_dttm, queue_submitted_dttm,
                 service_bus_message_id, processing_status, retry_count)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (call_id, submission_time, submission_time, None, "SUBMITTING", 0)
        self.db_service.execute_query(query, params, fetch_results=False)
        logger.info("✅ [DB-ORCH] Queue submission intent logged.")

    def update_queue_submission_status(
        self, call_id: str, message_id: Optional[str], success: bool
    ) -> None:
        """
        Update engage360.analysis_queue_status to PENDING on success, FAILED otherwise.
        """
        if success:
            query = """
                UPDATE engage360.analysis_queue_status
                SET service_bus_message_id = %s,
                    processing_status = 'PENDING',
                    queue_submitted_dttm = SYSDATETIMEOFFSET()
                WHERE call_id = %s
            """
            params = (message_id, call_id)
        else:
            query = """
                UPDATE engage360.analysis_queue_status
                SET processing_status = 'FAILED',
                    queue_submitted_dttm = SYSDATETIMEOFFSET()
                WHERE call_id = %s
            """
            params = (call_id,)

        self.db_service.execute_query(query, params, fetch_results=False)
        logger.info(
            f"✅ [DB-ORCH] Queue submission status updated ({'PENDING' if success else 'FAILED'})."
        )

    # -------------------------------------------------------------------------
    # Builders
    # -------------------------------------------------------------------------
    def _build_insert_bland_call_logs(self, webhook_data: Dict[str, Any]) -> Tuple[str, Tuple]:
        """
        Prepare the INSERT for engage360.bland_call_logs with fields commonly
        captured from Bland's webhook (raw JSON is also stored for audit).
        """
        q = """
            INSERT INTO engage360.bland_call_logs (
                from_number, price, end_at, status, call_id, summary, analysis, batch_id,
                first_name, last_name, member_id, attempt_id, language_pref, call_type_code,
                salesforce_account_number, campaign_id, completed, created_at, pathway_id,
                answered_by, transcripts, max_duration, pathway_logs, pathway_tags,
                call_ended_by, error_message, recording_url, analysis_schema,
                disposition_tag, corrected_duration, concatenated_transcript, raw_bland_response
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
        """
        md = webhook_data.get("metadata", {}) or {}
        params = (
            webhook_data.get("from"),
            webhook_data.get("price"),
            webhook_data.get("end_at"),
            webhook_data.get("status"),
            webhook_data.get("call_id"),
            webhook_data.get("summary"),
            self._safe_json(webhook_data.get("analysis")),
            webhook_data.get("batch_id"),
            md.get("first_name"),
            md.get("last_name"),
            md.get("member_id"),
            md.get("attempt_id"),
            md.get("language_pref"),
            md.get("call_type_code"),
            md.get("salesforce_account_number"),
            md.get("campaign_id"),
            webhook_data.get("completed"),
            webhook_data.get("created_at"),
            webhook_data.get("pathway_id"),
            webhook_data.get("answered_by"),
            self._safe_json(webhook_data.get("transcripts")),
            webhook_data.get("max_duration"),
            self._safe_json(webhook_data.get("pathway_logs")),
            self._safe_json(webhook_data.get("pathway_tags")),
            webhook_data.get("call_ended_by"),
            webhook_data.get("error_message"),
            webhook_data.get("recording_url"),
            webhook_data.get("analysis_schema"),
            webhook_data.get("disposition_tag"),
            webhook_data.get("corrected_duration"),
            webhook_data.get("concatenated_transcript"),
            self._safe_json(webhook_data),  # full raw payload
        )
        return q, params

    def _build_update_outreach_attempts(
        self, webhook_data: Dict[str, Any], mapped_data: MappedCallData
    ) -> Optional[Tuple[str, Tuple]]:
        """
        Prepare UPDATE for engage360.outreach_attempts if attempt_id is present.
        """
        attempt_id = (webhook_data.get("metadata") or {}).get("attempt_id")
        if not attempt_id:
            return None

        q = """
            UPDATE engage360.outreach_attempts
               SET vendor_session_id = %s,
                   disposition      = %s,
                   duration_sec     = %s,
                   response_summary = %s,
                   next_action      = %s,
                   status_updated_ts= SYSDATETIMEOFFSET()
             WHERE attempt_id = %s
        """
        params = (
            webhook_data.get("call_id"),
            mapped_data.disposition,
            mapped_data.duration_sec,
            mapped_data.response_summary,
            mapped_data.next_action,
            attempt_id,
        )
        return q, params

    def _build_update_enrollment(
        self, webhook_data: Dict[str, Any], enrollment_update: EnrollmentUpdate
    ) -> Optional[Tuple[str, Tuple]]:
        """
        Prepare UPDATE for engage360.member_campaign_enrollments_enhanced
        using your schema (no update_reason; uses current_status, last_attempt_ts).
        Idempotent: only updates if the target status is different.
        """
        if not enrollment_update or not enrollment_update.should_update:
            return None

        md = webhook_data.get("metadata", {}) or {}
        member_id = md.get("member_id")
        campaign_id = md.get("campaign_id")
        new_status = enrollment_update.new_status

        if not member_id or not campaign_id or not new_status:
            # Missing keys -> skip enrollment update
            logger.info(
                "ℹ️ [DB-ORCH] Enrollment update skipped (missing member_id/campaign_id/new_status)."
            )
            return None

        # Debug logging to help identify constraint violation
        logger.info(f"🔍 [DB-ORCH] Attempting to set current_status = '{new_status}' for member_id = {member_id}, campaign_id = {campaign_id}")
        logger.info(f"🔍 [DB-ORCH] Valid constraint values: OPTED_OUT, PENDING, ENROLLED, Unenrolled")
        
        # Validate status value against constraint
        valid_statuses = ['OPTED_OUT', 'PENDING', 'ENROLLED', 'Unenrolled']
        if new_status not in valid_statuses:
            logger.error(f"❌ [DB-ORCH] INVALID STATUS: '{new_status}' is not in allowed values: {valid_statuses}")
            logger.error(f"❌ [DB-ORCH] This will cause CHECK constraint violation CK_mcee_current_status")
            # Skip the update to prevent constraint violation
            return None

        q = """
            UPDATE engage360.member_campaign_enrollments_enhanced
               SET current_status = %s,
                   last_attempt_ts = SYSDATETIMEOFFSET()
             WHERE member_id = %s
               AND campaign_id = %s
               AND (current_status IS NULL OR current_status <> %s)
        """
        params = (new_status, member_id, campaign_id, new_status)
        return q, params

    # -------------------------------------------------------------------------
    # Utils
    # -------------------------------------------------------------------------
    @staticmethod
    def _safe_json(obj: Any) -> Optional[str]:
        try:
            import json as _json

            return _json.dumps(obj) if obj is not None else None
        except Exception:
            return None
