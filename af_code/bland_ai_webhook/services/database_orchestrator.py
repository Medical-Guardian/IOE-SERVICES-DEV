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
        self._constraint_verified = False

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
        enr_qp = self._build_update_enrollment(webhook_data, enrollment_update, mapped_data)
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

    def verify_database_constraint(self) -> None:
        """
        Verify the actual CHECK constraint definition in the database.
        This helps identify discrepancies between code expectations and database reality.
        """
        if self._constraint_verified:
            return
        
        try:
            constraint_query = """
                SELECT 
                    cc.CONSTRAINT_NAME,
                    cc.CHECK_CLAUSE,
                    tc.TABLE_NAME,
                    tc.TABLE_SCHEMA
                FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS cc
                JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc 
                    ON cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                WHERE cc.CONSTRAINT_NAME = 'CK_mcee_current_status'
                    AND tc.TABLE_NAME = 'member_campaign_enrollments_enhanced'
                    AND tc.TABLE_SCHEMA = 'engage360'
            """
            
            results = self.db_service.execute_query(constraint_query, (), fetch_results=True)
            
            if results:
                constraint_info = results[0]
                logger.info(f"🔍 [DB-ORCH] Database constraint verification:")
                logger.info(f"🔍 [DB-ORCH]   - Constraint name: {constraint_info.get('CONSTRAINT_NAME')}")
                logger.info(f"🔍 [DB-ORCH]   - Table: {constraint_info.get('TABLE_SCHEMA')}.{constraint_info.get('TABLE_NAME')}")
                logger.info(f"🔍 [DB-ORCH]   - Check clause: {constraint_info.get('CHECK_CLAUSE')}")
                
                # Extract allowed values from CHECK clause
                check_clause = constraint_info.get('CHECK_CLAUSE', '')
                logger.info(f"🔍 [DB-ORCH]   - Raw check clause bytes: {check_clause.encode('utf-8').hex()}")
                
                # Parse allowed values (basic extraction)
                import re
                status_pattern = r"current_status\s*=\s*'([^']+)'"
                allowed_values = re.findall(status_pattern, check_clause)
                if allowed_values:
                    logger.info(f"🔍 [DB-ORCH]   - Extracted allowed values: {allowed_values}")
                    for value in allowed_values:
                        logger.info(f"🔍 [DB-ORCH]     * '{value}' (bytes: {value.encode('utf-8').hex()}, length: {len(value)})")
                else:
                    logger.warning(f"⚠️ [DB-ORCH] Could not extract allowed values from check clause")
                
            else:
                logger.error(f"❌ [DB-ORCH] Could not find constraint CK_mcee_current_status in database")
                
            self._constraint_verified = True
            
        except Exception as e:
            logger.error(f"❌ [DB-ORCH] Failed to verify database constraint: {e}")
            # Continue execution even if verification fails

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
            webhook_data.get("corrected_duration"),  # Use raw webhook value same as bland_call_logs
            mapped_data.response_summary,
            mapped_data.next_action,
            attempt_id,
        )
        return q, params

    def _build_update_enrollment(
        self, webhook_data: Dict[str, Any], enrollment_update: EnrollmentUpdate, mapped_data: MappedCallData
    ) -> Optional[Tuple[str, Tuple]]:
        """
        Prepare UPDATE for engage360.member_campaign_enrollments_enhanced
        using your schema (no update_reason; uses current_status, last_attempt_ts).
        Idempotent: only updates if the target status is different.
        
        NEW: Auto-transitions from intro campaign to wellness campaign when ENROLLED.
        """
        if not enrollment_update or not enrollment_update.should_update:
            return None

        md = webhook_data.get("metadata", {}) or {}
        member_id = md.get("member_id")
        campaign_id = md.get("campaign_id")
        new_status = enrollment_update.new_status

        logger.info(f"🔍 [DB-ORCH] Processing enrollment update:")
        logger.info(f"🔍 [DB-ORCH]   - Member ID: {member_id}")
        logger.info(f"🔍 [DB-ORCH]   - Campaign ID: {campaign_id}")
        logger.info(f"🔍 [DB-ORCH]   - New Status: {new_status}")

        if not member_id or not campaign_id or not new_status:
            logger.warning(f"⚠️ [DB-ORCH] Enrollment update skipped - Missing required fields:")
            logger.warning(f"⚠️ [DB-ORCH]   - member_id: {'✓' if member_id else '✗'}")
            logger.warning(f"⚠️ [DB-ORCH]   - campaign_id: {'✓' if campaign_id else '✗'}")
            logger.warning(f"⚠️ [DB-ORCH]   - new_status: {'✓' if new_status else '✗'}")
            return None
        
        # Campaign IDs for auto-transition logic
        INTRO_CAMPAIGN_ID = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
        WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
        
        # CAMPAIGN IDENTIFICATION
        is_intro_campaign = campaign_id.upper() == INTRO_CAMPAIGN_ID.upper()
        is_wellness_campaign = campaign_id.upper() == WELLNESS_CAMPAIGN_ID.upper()
        
        logger.info(f"🎯 [DB-ORCH] Campaign identification:")
        logger.info(f"🎯 [DB-ORCH]   - Is Intro Campaign: {'✅' if is_intro_campaign else '❌'}")
        logger.info(f"🎯 [DB-ORCH]   - Is Wellness Campaign: {'✅' if is_wellness_campaign else '❌'}")
        logger.info(f"🎯 [DB-ORCH]   - Campaign Type: {'INTRO' if is_intro_campaign else 'WELLNESS' if is_wellness_campaign else 'UNKNOWN'}")
        
        # WELLNESS CAMPAIGN LOGIC: Only update status for opt-out
        if is_wellness_campaign:
            if new_status.upper() == 'OPTED_OUT':
                logger.info(f"🩺 [DB-ORCH] ✅ Wellness campaign opt-out detected - proceeding with status update to OPTED_OUT")
                # Continue with normal processing to update status to OPTED_OUT
            else:
                logger.info(f"🩺 [DB-ORCH] ℹ️ Wellness campaign call completed successfully")
                logger.info(f"🩺 [DB-ORCH] ℹ️ No enrollment status change needed - member remains ENROLLED")
                logger.info(f"🩺 [DB-ORCH] ℹ️ Received status '{new_status}' will be logged in outreach_attempts only")
                # Log the call but don't change enrollment status for wellness campaigns
                return None

        # Campaign IDs for auto-transition logic
        INTRO_CAMPAIGN_ID = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
        WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"

        # Verify database constraint on first run
        self.verify_database_constraint()

        # Debug logging to help identify constraint violation
        logger.info(f"🔍 [DB-ORCH] Attempting to set current_status = '{new_status}' for member_id = {member_id}, campaign_id = {campaign_id}")
        logger.info(f"🔍 [DB-ORCH] Valid constraint values: OPTED_OUT, PENDING, ENROLLED, UNENROLLED")
        
        # Validate status value against constraint (updated to match database constraint)
        valid_statuses = ['OPTED_OUT', 'PENDING', 'ENROLLED', 'UNENROLLED']
        
        # Enhanced validation with exact byte comparison
        is_valid = False
        for valid_status in valid_statuses:
            if new_status == valid_status:
                is_valid = True
                logger.info(f"✅ [DB-ORCH] Status '{new_status}' matches valid status '{valid_status}' (exact match)")
                break
            elif new_status.upper() == valid_status.upper():
                logger.warning(f"⚠️ [DB-ORCH] Status '{new_status}' matches '{valid_status}' case-insensitively but not exactly")
            else:
                # Byte-level comparison for debugging
                status_bytes = new_status.encode('utf-8')
                valid_bytes = valid_status.encode('utf-8')
                if len(status_bytes) != len(valid_bytes):
                    logger.debug(f"🔬 [DB-ORCH] Length mismatch: '{new_status}' ({len(status_bytes)} bytes) vs '{valid_status}' ({len(valid_bytes)} bytes)")
                else:
                    for i, (b1, b2) in enumerate(zip(status_bytes, valid_bytes)):
                        if b1 != b2:
                            logger.debug(f"🔬 [DB-ORCH] Byte difference at position {i}: {b1} vs {b2} ('{chr(b1)}' vs '{chr(b2)}')")
                            break
        
        if not is_valid:
            logger.error(f"❌ [DB-ORCH] INVALID STATUS: '{new_status}' is not in allowed values: {valid_statuses}")
            logger.error(f"❌ [DB-ORCH] This will cause CHECK constraint violation CK_mcee_current_status")
            
            # Log each valid status with byte representation for comparison
            logger.error(f"❌ [DB-ORCH] Valid statuses with byte representations:")
            for vs in valid_statuses:
                logger.error(f"❌ [DB-ORCH]   - '{vs}': {vs.encode('utf-8').hex()} (length: {len(vs)})")
            
            # Skip the update to prevent constraint violation
            return None

        # AUTO-TRANSITION LOGIC: Check if intro campaign completion requires wellness transition
        should_transition_to_wellness = (
            is_intro_campaign and 
            new_status == "ENROLLED"
        )

        logger.info(f"🔄 [DB-ORCH] Auto-transition evaluation:")
        logger.info(f"🔄 [DB-ORCH]   - Is intro campaign: {'✅' if is_intro_campaign else '❌'}")
        logger.info(f"🔄 [DB-ORCH]   - Status is ENROLLED: {'✅' if new_status == 'ENROLLED' else '❌'}")
        logger.info(f"🔄 [DB-ORCH]   - Should auto-transition: {'✅ YES' if should_transition_to_wellness else '❌ NO'}")

        if should_transition_to_wellness:
            logger.info(f"🚀 [DB-ORCH] STARTING AUTO-TRANSITION PROCESS")
            logger.info(f"🚀 [DB-ORCH] Member: {member_id}")
            logger.info(f"🚀 [DB-ORCH] From: Intro Campaign ({campaign_id}) → UNENROLLED")
            logger.info(f"🚀 [DB-ORCH] To: Wellness Campaign ({WELLNESS_CAMPAIGN_ID}) → ENROLLED")
            
            # Step 0: Get current intro campaign data BEFORE making changes
            logger.info(f"🔍 [DB-ORCH] Step 0: Fetching intro campaign data before auto-transition")
            get_intro_data_q = """
                SELECT current_status, preferred_window 
                FROM engage360.member_campaign_enrollments_enhanced 
                WHERE member_id = %s AND campaign_id = %s
            """
            intro_data = self.db_service.execute_query(get_intro_data_q, (member_id, campaign_id))
            
            if intro_data:
                current_intro_status = intro_data[0].get('current_status')
                preferred_window = intro_data[0].get('preferred_window')
                logger.info(f"📊 [DB-ORCH] Intro campaign current data:")
                logger.info(f"📊 [DB-ORCH]   - Current status: {current_intro_status}")
                logger.info(f"📊 [DB-ORCH]   - Preferred window: {preferred_window}")
            else:
                logger.error(f"❌ [DB-ORCH] No intro campaign record found for member {member_id}, campaign {campaign_id}")
                return None
            
            # Step 1: Set intro campaign to UNENROLLED
            intro_update_q = """
                UPDATE engage360.member_campaign_enrollments_enhanced
                   SET current_status = 'UNENROLLED',
                       last_attempt_ts = SYSDATETIMEOFFSET()
                 WHERE member_id = %s
                   AND campaign_id = %s
            """
            
            # Step 2: Create/Update wellness campaign to ENROLLED (use preferred_window from intro)
            wellness_upsert_q = """
                MERGE engage360.member_campaign_enrollments_enhanced AS tgt
                USING (SELECT %s as member_id, %s as campaign_id, %s as new_status, %s as preferred_window) AS src
                ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id
                WHEN MATCHED THEN
                    UPDATE SET current_status = src.new_status, last_attempt_ts = SYSDATETIMEOFFSET()
                WHEN NOT MATCHED THEN
                    INSERT (enrollment_id, member_id, campaign_id, enrollment_ts, current_status, last_attempt_ts, preferred_window)
                    VALUES (NEWID(), src.member_id, src.campaign_id, SYSDATETIMEOFFSET(), src.new_status, SYSDATETIMEOFFSET(), src.preferred_window);
            """
            
            # Execute both queries
            from pymssql import connect, Error as PyMSSQLError
            
            try:
                # STEP 1: Update intro campaign to UNENROLLED
                logger.info(f"🔧 [DB-ORCH] Step 1/2: Updating intro campaign status to UNENROLLED")
                intro_rows = self.db_service.execute_query(intro_update_q, (member_id, campaign_id), fetch_results=False)
                logger.info(f"✅ [DB-ORCH] Step 1/2 completed: {intro_rows} intro campaign rows updated")
                
                # Log intro campaign status change: ENROLLED -> UNENROLLED
                if intro_rows > 0:
                    logger.info(f"📋 [DB-ORCH] Logging intro campaign status change to audit history")
                    self.log_status_change(
                        member_id=member_id,
                        campaign_id=campaign_id,
                        previous_status="ENROLLED",
                        new_status="UNENROLLED",
                        change_source="WEBHOOK",
                        change_details=f"Intro call successful - auto-transition to wellness campaign"
                    )
                    logger.info(f"✅ [DB-ORCH] Intro campaign audit log completed")
                
                # STEP 2: Create/Update wellness campaign to ENROLLED
                logger.info(f"🔧 [DB-ORCH] Step 2/2: Creating/updating wellness campaign enrollment")
                logger.info(f"🔧 [DB-ORCH] Using preferred_window '{preferred_window}' from intro campaign {campaign_id}")
                wellness_rows = self.db_service.execute_query(wellness_upsert_q, (member_id, WELLNESS_CAMPAIGN_ID, "ENROLLED", preferred_window), fetch_results=False)
                logger.info(f"✅ [DB-ORCH] Step 2/2 completed: {wellness_rows} wellness campaign rows affected")
                
                # Log wellness campaign status change
                if wellness_rows > 0:
                    logger.info(f"📋 [DB-ORCH] Logging wellness campaign status change to audit history")
                    # Check if wellness record existed before
                    check_wellness_q = """
                        SELECT current_status FROM engage360.member_campaign_enrollments_enhanced 
                        WHERE member_id = %s AND campaign_id = %s
                    """
                    existing_wellness_records = self.db_service.execute_query(check_wellness_q, (member_id, WELLNESS_CAMPAIGN_ID))
                    previous_wellness_status = existing_wellness_records[0].get('current_status') if existing_wellness_records else None
                    
                    logger.info(f"📊 [DB-ORCH] Wellness campaign previous status: {previous_wellness_status if previous_wellness_status else 'NEW_RECORD'}")
                    
                    self.log_status_change(
                        member_id=member_id,
                        campaign_id=WELLNESS_CAMPAIGN_ID,
                        previous_status=previous_wellness_status,
                        new_status="ENROLLED",
                        change_source="WEBHOOK",
                        change_details=f"Auto-transitioned from intro campaign after successful call"
                    )
                    logger.info(f"✅ [DB-ORCH] Wellness campaign audit log completed")
                
                logger.info(f"🎉 [DB-ORCH] AUTO-TRANSITION COMPLETED SUCCESSFULLY!")
                logger.info(f"🎉 [DB-ORCH] Summary:")
                logger.info(f"🎉 [DB-ORCH]   - Intro campaign rows updated: {intro_rows}")
                logger.info(f"🎉 [DB-ORCH]   - Wellness campaign rows affected: {wellness_rows}")
                logger.info(f"🎉 [DB-ORCH]   - Final transition: {campaign_id} (UNENROLLED) → {WELLNESS_CAMPAIGN_ID} (ENROLLED)")
                
                return None
            except Exception as e:
                logger.error(f"❌ [DB-ORCH] Auto-transition failed: {e}")
                return None
        else:
            # STANDARD STATUS UPDATE: No auto-transition needed
            logger.info(f"📝 [DB-ORCH] Processing standard enrollment status update")
            logger.info(f"📝 [DB-ORCH]   - Campaign: {campaign_id}")
            logger.info(f"📝 [DB-ORCH]   - Target status: {new_status}")
            
            try:
                # First get the current status for audit logging
                logger.info(f"🔍 [DB-ORCH] Fetching current enrollment status for audit trail")
                current_status_q = """
                    SELECT current_status FROM engage360.member_campaign_enrollments_enhanced 
                    WHERE member_id = %s AND campaign_id = %s
                """
                current_records = self.db_service.execute_query(current_status_q, (member_id, campaign_id))
                current_status = current_records[0].get('current_status') if current_records else None
                
                logger.info(f"📊 [DB-ORCH] Current enrollment status: {current_status if current_status else 'NOT_FOUND'}")
                logger.info(f"📊 [DB-ORCH] Status change: {current_status} → {new_status}")
                
                # Execute the update
                logger.info(f"🔄 [DB-ORCH] Executing enrollment status update")
                q = """
                    UPDATE engage360.member_campaign_enrollments_enhanced
                       SET current_status = %s,
                           last_attempt_ts = SYSDATETIMEOFFSET()
                     WHERE member_id = %s
                       AND campaign_id = %s
                       AND (current_status IS NULL OR current_status <> %s)
                """
                params = (new_status, member_id, campaign_id, new_status)
                
                rows_affected = self.db_service.execute_query(q, params, fetch_results=False)
                
                logger.info(f"✅ [DB-ORCH] Enrollment update completed - {rows_affected} rows affected")
                
                # Log status change if update actually happened
                if rows_affected > 0 and current_status != new_status:
                    logger.info(f"📋 [DB-ORCH] Logging status change to audit history")
                    self.log_status_change(
                        member_id=member_id,
                        campaign_id=campaign_id,
                        previous_status=current_status,
                        new_status=new_status,
                        change_source="WEBHOOK",
                        change_details=f"Webhook status update: {mapped_data.disposition}"
                    )
                    logger.info(f"✅ [DB-ORCH] Status change audit logged successfully")
                else:
                    logger.info(f"ℹ️ [DB-ORCH] No status change audit needed (no rows updated or status unchanged)")
                
                # Final validation before sending to database
                logger.info(f"🔍 [DB-ORCH] Final status value being sent to database: {repr(new_status)}")
                logger.info(f"🔍 [DB-ORCH] SQL parameter bytes: {new_status.encode('utf-8').hex()}")
                
                # Return None since this method executed the update directly
                return None
                
            except Exception as e:
                logger.error(f"❌ [DB-ORCH] Standard status update failed: {e}")
                return None

        # This should not be reached, but keeping for safety
        return None

    def _handle_campaign_auto_transition(
        self, webhook_data: Dict[str, Any], mapped_data: MappedCallData, 
        member_id: str, campaign_id: str, new_status: str
    ) -> bool:
        """
        Handle complex auto-transition logic (intro -> wellness).
        Returns True if auto-transition was handled, False if standard processing should continue.
        """
        INTRO_CAMPAIGN_ID = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
        WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
        
        # Check if this is intro campaign completion requiring auto-transition to wellness
        should_transition_to_wellness = (
            campaign_id.upper() == INTRO_CAMPAIGN_ID.upper() and 
            new_status == "ENROLLED"
        )

        if not should_transition_to_wellness:
            logger.info(f"ℹ️ [DB-ORCH] No auto-transition needed - not intro campaign or status not ENROLLED")
            return False
            
        logger.info(f"🚀 [DB-ORCH] STARTING AUTO-TRANSITION PROCESS")
        logger.info(f"🚀 [DB-ORCH] Member: {member_id}")
        logger.info(f"🚀 [DB-ORCH] From: Intro Campaign ({campaign_id}) → UNENROLLED")
        logger.info(f"🚀 [DB-ORCH] To: Wellness Campaign ({WELLNESS_CAMPAIGN_ID}) → ENROLLED")
        
        # Step 1: Set intro campaign to UNENROLLED
        intro_update_q = """
            UPDATE engage360.member_campaign_enrollments_enhanced
               SET current_status = 'UNENROLLED',
                   last_attempt_ts = SYSDATETIMEOFFSET()
             WHERE member_id = %s
               AND campaign_id = %s
        """
        
        # Step 2: Create/Update wellness campaign to ENROLLED (use preferred_window from intro)
        wellness_upsert_q = """
            MERGE engage360.member_campaign_enrollments_enhanced AS tgt
            USING (SELECT %s as member_id, %s as campaign_id, %s as new_status, %s as preferred_window) AS src
            ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id
            WHEN MATCHED THEN
                UPDATE SET current_status = src.new_status, last_attempt_ts = SYSDATETIMEOFFSET()
            WHEN NOT MATCHED THEN
                INSERT (enrollment_id, member_id, campaign_id, enrollment_ts, current_status, last_attempt_ts, preferred_window)
                VALUES (NEWID(), src.member_id, src.campaign_id, SYSDATETIMEOFFSET(), src.new_status, SYSDATETIMEOFFSET(), src.preferred_window);
        """
        
        try:
            # STEP 0: Get current intro campaign data BEFORE making changes
            logger.info(f"🔍 [DB-ORCH] Step 0: Fetching intro campaign data before auto-transition")
            get_intro_data_q = """
                SELECT current_status, preferred_window 
                FROM engage360.member_campaign_enrollments_enhanced 
                WHERE member_id = %s AND campaign_id = %s
            """
            intro_data = self.db_service.execute_query(get_intro_data_q, (member_id, campaign_id))
            
            if intro_data:
                current_intro_status = intro_data[0].get('current_status')
                preferred_window = intro_data[0].get('preferred_window')
                logger.info(f"📊 [DB-ORCH] Intro campaign current data:")
                logger.info(f"📊 [DB-ORCH]   - Current status: {current_intro_status}")
                logger.info(f"📊 [DB-ORCH]   - Preferred window: {preferred_window}")
            else:
                logger.error(f"❌ [DB-ORCH] No intro campaign record found for member {member_id}, campaign {campaign_id}")
                return False
            
            # STEP 1: Update intro campaign to UNENROLLED
            logger.info(f"🔧 [DB-ORCH] Step 1/2: Updating intro campaign status to UNENROLLED")
            intro_rows = self.db_service.execute_query(intro_update_q, (member_id, campaign_id), fetch_results=False)
            logger.info(f"✅ [DB-ORCH] Step 1/2 completed: {intro_rows} intro campaign rows updated")
            
            # Log intro campaign status change: ENROLLED -> UNENROLLED
            if intro_rows > 0:
                logger.info(f"📋 [DB-ORCH] Logging intro campaign status change to audit history")
                self.log_status_change(
                    member_id=member_id,
                    campaign_id=campaign_id,
                    previous_status="ENROLLED",
                    new_status="UNENROLLED",
                    change_source="WEBHOOK",
                    change_details=f"Intro call successful - auto-transition to wellness campaign"
                )
                logger.info(f"✅ [DB-ORCH] Intro campaign audit log completed")
            
            # STEP 2: Create/Update wellness campaign to ENROLLED
            logger.info(f"🔧 [DB-ORCH] Step 2/2: Creating/updating wellness campaign enrollment")
            logger.info(f"🔧 [DB-ORCH] Using preferred_window '{preferred_window}' from intro campaign {campaign_id}")
            wellness_rows = self.db_service.execute_query(wellness_upsert_q, (member_id, WELLNESS_CAMPAIGN_ID, "ENROLLED", preferred_window), fetch_results=False)
            logger.info(f"✅ [DB-ORCH] Step 2/2 completed: {wellness_rows} wellness campaign rows affected")
            
            # Log wellness campaign status change
            if wellness_rows > 0:
                logger.info(f"📋 [DB-ORCH] Logging wellness campaign status change to audit history")
                # Check if wellness record existed before
                check_wellness_q = """
                    SELECT current_status FROM engage360.member_campaign_enrollments_enhanced 
                    WHERE member_id = %s AND campaign_id = %s
                """
                existing_wellness_records = self.db_service.execute_query(check_wellness_q, (member_id, WELLNESS_CAMPAIGN_ID))
                previous_wellness_status = existing_wellness_records[0].get('current_status') if existing_wellness_records else None
                
                logger.info(f"📊 [DB-ORCH] Wellness campaign previous status: {previous_wellness_status if previous_wellness_status else 'NEW_RECORD'}")
                
                self.log_status_change(
                    member_id=member_id,
                    campaign_id=WELLNESS_CAMPAIGN_ID,
                    previous_status=previous_wellness_status,
                    new_status="ENROLLED",
                    change_source="WEBHOOK",
                    change_details=f"Auto-transitioned from intro campaign after successful call"
                )
                logger.info(f"✅ [DB-ORCH] Wellness campaign audit log completed")
            
            logger.info(f"🎉 [DB-ORCH] AUTO-TRANSITION COMPLETED SUCCESSFULLY!")
            logger.info(f"🎉 [DB-ORCH] Summary:")
            logger.info(f"🎉 [DB-ORCH]   - Intro campaign rows updated: {intro_rows}")
            logger.info(f"🎉 [DB-ORCH]   - Wellness campaign rows affected: {wellness_rows}")
            logger.info(f"🎉 [DB-ORCH]   - Final transition: {campaign_id} (UNENROLLED) → {WELLNESS_CAMPAIGN_ID} (ENROLLED)")
            return True
            
        except Exception as e:
            logger.error(f"❌ [DB-ORCH] Auto-transition failed: {e}")
            return False

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

    def log_status_change(self, member_id: str, campaign_id: str, previous_status: Optional[str], 
                         new_status: str, change_source: str, change_details: Optional[str] = None):
        """
        Log status changes to member_enrollment_status_history table.
        
        Args:
            member_id: Member UUID
            campaign_id: Campaign UUID
            previous_status: Previous status (None for new enrollments)
            new_status: New status
            change_source: Source of change ('CSV_PROCESSING', 'WEBHOOK', 'MANUAL')
            change_details: Additional context about the change
        """
        try:
            # Calculate duration since last change
            duration_hours = None
            if previous_status:
                last_change_query = """
                    SELECT TOP 1 change_timestamp 
                    FROM engage360.member_enrollment_status_history 
                    WHERE member_id = %s AND campaign_id = %s 
                    ORDER BY change_timestamp DESC
                """
                last_change_records = self.db_service.execute_query(last_change_query, (member_id, campaign_id))
                last_change = last_change_records[0] if last_change_records else None
                
                if last_change:
                    # Calculate duration in hours
                    import pytz
                    from datetime import datetime
                    
                    current_time = datetime.now(pytz.UTC)
                    last_time = last_change.get('change_timestamp')
                    if last_time.tzinfo is None:
                        last_time = pytz.UTC.localize(last_time)
                    
                    duration_delta = current_time - last_time
                    duration_hours = round(duration_delta.total_seconds() / 3600, 2)
            
            # Insert audit record
            audit_query = """
                INSERT INTO engage360.member_enrollment_status_history 
                (member_id, campaign_id, previous_status, new_status, duration_since_last_change_hours, 
                 change_source, change_details)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db_service.execute_query(audit_query, (
                member_id, campaign_id, previous_status, new_status, 
                duration_hours, change_source, change_details
            ), fetch_results=False)
            
            logger.info(f"📋 [DB-ORCH] Status change logged: {member_id} {previous_status}→{new_status} ({change_source})")
            
        except Exception as e:
            logger.error(f"❌ [DB-ORCH] Failed to log status change: {e}")
            # Don't let audit logging failure break the main operation
