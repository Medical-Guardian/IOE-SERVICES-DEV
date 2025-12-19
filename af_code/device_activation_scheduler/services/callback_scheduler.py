"""
Device Activation Callback Scheduler Service
BusinessCaseID: BC-TBD (Device Activation System)
Created: 2025-12-07

This service handles scheduled callbacks for Device Activation campaign.
When a member requests a callback during an AI call (e.g., "I'm busy, call me in 2 hours"),
this service:
1. Queries pending callbacks that are due for execution
2. Validates business hours (dual-timezone)
3. Creates callback batches for Bland AI
4. Tracks attempt count (max 3 attempts)
5. Handles timeout (24 hours or 3 attempts exceeded)
6. Returns timed-out members to main call sequence

EXAMPLE SCENARIO:
-----------------
1. Member John answers Call 1 at 10 AM
2. AI asks: "Are you ready to activate your device?"
3. John says: "I'm busy right now, can you call me back in 2 hours?"
4. AI creates callback entry: scheduled_callback_time = 12:00 PM
5. Callback scheduler picks up at 12:00 PM
6. Calls John again to help with device activation
7. If John doesn't answer, retry up to 3 times within 24 hours
8. If still no answer after 3 attempts or 24 hours, return to main sequence
"""

import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import pytz

from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.business_hours_utils import can_make_call

logger = logging.getLogger(__name__)


class CallbackScheduler:
    """
    Service to manage callback queue for Device Activation campaign

    This service runs as part of the main scheduler (every 30 minutes) to:
    - Process pending callbacks that are due
    - Validate business hours before calling
    - Track callback attempts (max 3)
    - Handle timeout scenarios (24 hours or 3 attempts)
    - Return timed-out members to main sequence
    """

    # SQL query to find pending callbacks due for execution
    PENDING_CALLBACKS_QUERY = """
    SELECT
        cq.callback_id,
        cq.enrollment_id,
        cq.member_id,
        cq.campaign_id,
        cq.scheduled_callback_time,
        cq.callback_reason,
        cq.preferred_contact_method,
        cq.attempt_count,
        cq.max_attempts,
        cq.last_attempt_ts,
        cq.created_ts,
        m.first_name,
        m.last_name,
        m.primary_phone,
        m.email,
        m.timezone,
        m.language_pref,
        md.device_id,
        md.device_udi,
        md.device_name,
        md.brand,
        md.device_phone_number,
        md.is_device_callable,
        md.delivery_date,
        md.fall_detection_status,
        md.battery_status,
        e.activation_start_date,
        e.campaign_end_date,
        e.customer_type

    FROM engage360.outreach_callback_queue cq
    JOIN engage360.members m ON cq.member_id = m.member_id
    JOIN engage360.member_devices md ON m.member_id = md.member_id
    JOIN engage360.member_campaign_enrollments_enhanced e ON cq.enrollment_id = e.enrollment_id

    WHERE
        -- Only pending callbacks
        cq.status = 'PENDING'

        -- Not exceeded max attempts
        AND cq.attempt_count < cq.max_attempts

        -- Callback time has arrived
        AND SYSDATETIMEOFFSET() >= cq.scheduled_callback_time

        -- Not timed out (24-hour window)
        AND DATEDIFF(HOUR, cq.created_ts, SYSDATETIMEOFFSET()) < 24

    ORDER BY cq.scheduled_callback_time
    """

    def __init__(self, db_service: DatabaseService):
        """
        Initialize CallbackScheduler

        Args:
            db_service: DatabaseService instance for database operations
        """
        self.db_service = db_service
        logger.info("📞 [CALLBACK-SCHEDULER] Initializing callback scheduler service")

    def get_pending_callbacks(self) -> List[Dict]:
        """
        Get pending callbacks that are due for execution

        Returns:
            List of callbacks ready to be processed

        Example:
        --------
        Callback created at 10:00 AM with scheduled_callback_time = 12:00 PM
        Current time: 12:05 PM
        Result: This callback will be returned in the list

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info("📞 [CALLBACK-SCHEDULER] Querying pending callbacks...")

        try:
            pending_callbacks = self.db_service.execute_query(
                self.PENDING_CALLBACKS_QUERY, fetch_results=True
            )

            if not pending_callbacks:
                logger.info("ℹ️ [CALLBACK-SCHEDULER] No pending callbacks found")
                return []

            logger.info(f"📊 [CALLBACK-SCHEDULER] Found {len(pending_callbacks)} pending callbacks")

            # Log callback summary
            for callback in pending_callbacks:
                logger.info(
                    f"📞 [CALLBACK-SCHEDULER] Callback {callback.get('callback_id')}: "
                    f"Member {callback.get('first_name')} {callback.get('last_name')}, "
                    f"Reason: {callback.get('callback_reason')}, "
                    f"Attempt {callback.get('attempt_count')}/{callback.get('max_attempts')}, "
                    f"Scheduled: {callback.get('scheduled_callback_time')}"
                )

            return pending_callbacks

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error querying pending callbacks: {str(e)}",
                exc_info=True,
            )
            raise

    def process_callbacks(self) -> Dict[str, Any]:
        """
        Process all pending callbacks

        This method:
        1. Gets pending callbacks from database
        2. Validates business hours for each callback
        3. Returns eligible callbacks for batch creation
        4. Reschedules callbacks outside business hours
        5. Marks timed-out callbacks

        Returns:
            Dict with:
                - eligible_callbacks (List[Dict]): Callbacks ready for calling
                - rescheduled_count (int): Callbacks rescheduled (outside business hours)
                - timed_out_count (int): Callbacks marked as timed out

        Example:
        --------
        Scenario 1: Callback ready, within business hours
        - Callback scheduled for 2:00 PM EST
        - Current time: 2:05 PM EST
        - Member timezone: America/New_York
        - Result: Returned in eligible_callbacks list

        Scenario 2: Callback ready, outside business hours
        - Callback scheduled for 6:00 PM EST (after 5 PM cutoff)
        - Result: Rescheduled to next business day at 9:00 AM

        Scenario 3: Callback timed out
        - Callback created 25 hours ago
        - Result: Marked as TIMED_OUT, member returns to main sequence

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info("🚀 [CALLBACK-SCHEDULER] Starting callback processing...")

        try:
            # Step 1: Get pending callbacks
            pending_callbacks = self.get_pending_callbacks()

            if not pending_callbacks:
                return {
                    "eligible_callbacks": [],
                    "rescheduled_count": 0,
                    "timed_out_count": 0,
                }

            # Step 2: Handle timeouts FIRST (before processing)
            timed_out_count = self._handle_callback_timeouts()

            # Step 3: Validate business hours for each callback
            eligible_callbacks = []
            rescheduled_count = 0

            for callback in pending_callbacks:
                callback_id = callback.get("callback_id")
                member_timezone = callback.get("timezone")
                member_id = callback.get("member_id")

                # Validate business hours
                can_call_now, reason = self._validate_callback_business_hours(
                    callback_id, member_timezone
                )

                if can_call_now:
                    # Add to eligible list
                    eligible_callbacks.append(callback)
                    logger.info(
                        f"✅ [CALLBACK-SCHEDULER] Callback {callback_id} eligible: {reason}"
                    )
                else:
                    # Reschedule to next valid time
                    rescheduled = self._reschedule_callback(callback_id, member_timezone)
                    if rescheduled:
                        rescheduled_count += 1
                        logger.info(
                            f"⏰ [CALLBACK-SCHEDULER] Callback {callback_id} rescheduled: {reason}"
                        )

            logger.info(
                f"✅ [CALLBACK-SCHEDULER] Callback processing complete: "
                f"{len(eligible_callbacks)} eligible, "
                f"{rescheduled_count} rescheduled, "
                f"{timed_out_count} timed out"
            )

            return {
                "eligible_callbacks": eligible_callbacks,
                "rescheduled_count": rescheduled_count,
                "timed_out_count": timed_out_count,
            }

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error processing callbacks: {str(e)}",
                exc_info=True,
            )
            raise

    def _validate_callback_business_hours(
        self, callback_id: str, member_timezone: str
    ) -> Tuple[bool, str]:
        """
        Validate if callback can be made right now (business hours check)

        Uses dual-timezone validation:
        - Medical Guardian operating hours (9 AM - 5 PM EST)
        - Member's local timezone (9 AM - 5 PM in their timezone)

        Args:
            callback_id: Callback UUID
            member_timezone: Member's IANA timezone (e.g., America/Chicago)

        Returns:
            Tuple of (can_call: bool, reason: str)

        Example:
        --------
        Scenario: Member in Pacific timezone (America/Los_Angeles)
        Current time UTC: 21:00 (9:00 PM UTC)
        Current time EST: 4:00 PM (within MG hours 9 AM - 5 PM)
        Current time PST: 1:00 PM (within member hours 9 AM - 5 PM)
        Result: (True, "Within business hours for both MG and member")

        Scenario: Member in Central timezone, after hours
        Current time UTC: 23:00 (11:00 PM UTC)
        Current time EST: 6:00 PM (OUTSIDE MG hours)
        Current time CST: 5:00 PM (OUTSIDE member hours)
        Result: (False, "Outside business hours - after 5 PM EST")
        """
        try:
            # Get current time in UTC
            now_utc = datetime.now(pytz.UTC)

            # Validate member timezone
            member_tz = pytz.timezone(member_timezone)

            # Use dual-timezone validation from business_hours_utils
            can_call, reason = can_make_call(now_utc, member_tz)

            logger.debug(
                f"⏰ [CALLBACK-SCHEDULER] Callback {callback_id} business hours check: "
                f"{can_call} - {reason}"
            )

            return can_call, reason

        except Exception as e:
            logger.warning(
                f"⚠️ [CALLBACK-SCHEDULER] Error validating business hours for callback {callback_id}: {str(e)}"
            )
            # On error, assume cannot call (safe default)
            return False, f"Error validating business hours: {str(e)}"

    def _reschedule_callback(self, callback_id: str, member_timezone: str) -> bool:
        """
        Reschedule callback to next valid business hours time

        Example:
        --------
        Scenario: Callback due at 6:00 PM EST (outside business hours)
        Next valid time: Tomorrow at 9:00 AM EST
        Result: Update scheduled_callback_time to tomorrow 9:00 AM

        Args:
            callback_id: Callback UUID
            member_timezone: Member's IANA timezone

        Returns:
            True if rescheduled successfully, False otherwise

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        try:
            # Get current time in UTC
            now_utc = datetime.now(pytz.UTC)

            # Calculate next valid business hours time (9 AM tomorrow)
            member_tz = pytz.timezone(member_timezone)
            now_member_tz = now_utc.astimezone(member_tz)

            # Add 1 day and set to 9:00 AM
            next_day = now_member_tz + timedelta(days=1)
            next_day_9am = next_day.replace(hour=9, minute=0, second=0, microsecond=0)

            # Convert back to UTC for database storage
            next_callback_time_utc = next_day_9am.astimezone(pytz.UTC)

            # Update database
            update_sql = """
            UPDATE engage360.outreach_callback_queue
            SET scheduled_callback_time = %s, updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = %s
            """

            self.db_service.execute_query(
                update_sql,
                (next_callback_time_utc.isoformat(), str(callback_id)),
                fetch_results=False,
            )

            logger.info(
                f"⏰ [CALLBACK-SCHEDULER] Rescheduled callback {callback_id} to {next_callback_time_utc.isoformat()}"
            )

            return True

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error rescheduling callback {callback_id}: {str(e)}",
                exc_info=True,
            )
            return False

    def _handle_callback_timeouts(self) -> int:
        """
        Mark callbacks as TIMED_OUT if they exceed 24 hours or max attempts

        Timeout conditions:
        1. 24 hours elapsed since callback creation
        2. 3 attempts exhausted (attempt_count >= max_attempts)

        When a callback times out, the member returns to the main call sequence.

        Returns:
            Number of callbacks marked as timed out

        Example:
        --------
        Scenario 1: 24-hour timeout
        - Callback created: 2025-12-07 10:00 AM
        - Current time: 2025-12-08 11:00 AM (25 hours later)
        - Result: Marked as TIMED_OUT

        Scenario 2: Max attempts exhausted
        - Callback attempt_count: 3
        - Callback max_attempts: 3
        - Result: Marked as TIMED_OUT

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        try:
            timeout_sql = """
            UPDATE engage360.outreach_callback_queue
            SET status = 'TIMED_OUT', updated_ts = SYSDATETIMEOFFSET()
            WHERE status = 'PENDING'
            AND (
                -- 24-hour timeout
                DATEDIFF(HOUR, created_ts, SYSDATETIMEOFFSET()) >= 24
                OR
                -- Max attempts exhausted
                attempt_count >= max_attempts
            )
            """

            # Execute update
            self.db_service.execute_query(timeout_sql, fetch_results=False)

            # Count how many were timed out
            count_sql = """
            SELECT COUNT(*) as timeout_count
            FROM engage360.outreach_callback_queue
            WHERE status = 'TIMED_OUT'
            AND updated_ts >= DATEADD(MINUTE, -5, SYSDATETIMEOFFSET())
            """

            result = self.db_service.execute_query(count_sql, fetch_results=True)
            timeout_count = result[0].get("timeout_count", 0) if result else 0

            if timeout_count > 0:
                logger.info(
                    f"⏰ [CALLBACK-SCHEDULER] Marked {timeout_count} callbacks as TIMED_OUT"
                )

            return timeout_count

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error handling callback timeouts: {str(e)}",
                exc_info=True,
            )
            return 0

    def increment_callback_attempt(self, callback_id: str) -> bool:
        """
        Increment callback attempt count after a call attempt

        This is called by the batch orchestrator AFTER submitting a callback batch to Bland AI.

        Args:
            callback_id: Callback UUID

        Returns:
            True if incremented successfully, False otherwise

        Example:
        --------
        Before: attempt_count = 0, status = 'PENDING'
        After calling: attempt_count = 1, status = 'IN_PROGRESS', last_attempt_ts = NOW

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        try:
            update_sql = """
            UPDATE engage360.outreach_callback_queue
            SET
                attempt_count = attempt_count + 1,
                status = 'IN_PROGRESS',
                last_attempt_ts = SYSDATETIMEOFFSET(),
                updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = %s
            """

            self.db_service.execute_query(update_sql, (str(callback_id),), fetch_results=False)

            logger.info(
                f"✅ [CALLBACK-SCHEDULER] Incremented attempt count for callback {callback_id}"
            )

            return True

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error incrementing callback attempt: {str(e)}",
                exc_info=True,
            )
            return False

    def mark_callback_completed(self, callback_id: str) -> bool:
        """
        Mark callback as COMPLETED (successful device activation)

        This is called by the webhook processor when device activation is confirmed.

        Args:
            callback_id: Callback UUID

        Returns:
            True if marked successfully, False otherwise

        Example:
        --------
        Webhook receives: disposition = 'COMPLETED', device_activated = 1
        Result: Callback marked as COMPLETED, member enrollment marked as COMPLETED

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        try:
            update_sql = """
            UPDATE engage360.outreach_callback_queue
            SET status = 'COMPLETED', updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = %s
            """

            self.db_service.execute_query(update_sql, (str(callback_id),), fetch_results=False)

            logger.info(f"✅ [CALLBACK-SCHEDULER] Marked callback {callback_id} as COMPLETED")

            return True

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error marking callback completed: {str(e)}",
                exc_info=True,
            )
            return False

    def mark_callback_failed(self, callback_id: str) -> bool:
        """
        Mark callback as FAILED (after all attempts exhausted with no success)

        Args:
            callback_id: Callback UUID

        Returns:
            True if marked successfully, False otherwise

        Example:
        --------
        Callback attempt 3: No answer
        Result: Callback marked as FAILED, member returns to main sequence

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        try:
            update_sql = """
            UPDATE engage360.outreach_callback_queue
            SET status = 'FAILED', updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = %s
            """

            self.db_service.execute_query(update_sql, (str(callback_id),), fetch_results=False)

            logger.info(f"❌ [CALLBACK-SCHEDULER] Marked callback {callback_id} as FAILED")

            return True

        except Exception as e:
            logger.error(
                f"💥 [CALLBACK-SCHEDULER] Error marking callback failed: {str(e)}",
                exc_info=True,
            )
            return False
