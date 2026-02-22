"""
Device Activation Callback Scheduler Service

BusinessCaseID: BC-DA-005 (Callback Scheduling & Queue Management)
Created: 2025-12-07
Updated: 2025-12-24 - Added comprehensive documentation and BusinessCaseID mapping

This service manages scheduled callback requests for Device Activation campaigns. When a member
requests a callback during an AI call (e.g., "I'm busy, call me in 2 hours"), this service
orchestrates the callback lifecycle from creation through completion or timeout.

PURPOSE:
--------
Device Activation calls sometimes occur at inconvenient times for members. Instead of losing
the opportunity for engagement, the AI agent can schedule a callback at the member's preferred
time. This service ensures callbacks are processed promptly while respecting business hours
and attempt limits.

CALLBACK LIFECYCLE:
-------------------
1. **Creation (via Webhook)**:
   - Member requests callback during AI call
   - Webhook processor creates entry in outreach_callback_queue
   - Fields: scheduled_callback_time, callback_reason, status='PENDING'

2. **Processing (via CallbackScheduler)**:
   - Scheduler checks every 15 minutes for due callbacks
   - Validates business hours (dual-timezone)
   - Creates callback batch for Bland AI
   - Increments attempt_count

3. **Completion (via Webhook)**:
   - Webhook receives call result
   - If device activated: mark_callback_completed()
   - If no answer: retry (up to max_attempts)
   - If max attempts reached: mark_callback_failed()

4. **Timeout Handling**:
   - 24-hour timeout: Mark TIMED_OUT, return member to main sequence
   - 3 attempts exhausted: Mark TIMED_OUT or FAILED
   - Member re-enters normal call sequence (Call 2, 3, 4, etc.)

TIMEOUT LOGIC:
--------------
Callbacks have two timeout conditions (OR logic - either triggers timeout):

1. **Time-Based Timeout**: 24 hours since callback creation
   - Created: 2025-12-07 10:00 AM
   - Timeout: 2025-12-08 10:00 AM (24 hours later)
   - Reason: Prevents callbacks from sitting in queue indefinitely

2. **Attempt-Based Timeout**: 3 attempts exhausted
   - Attempt 1: No answer (reschedule for later)
   - Attempt 2: No answer (reschedule for later)
   - Attempt 3: No answer (mark TIMED_OUT)
   - Reason: Prevents infinite retry loops

When timeout occurs:
- Status changed to 'TIMED_OUT'
- Member remains ENROLLED in campaign
- Member re-enters main call sequence (next frequency window)
- Callback history preserved in outreach_callback_queue for audit

BUSINESS HOURS VALIDATION:
---------------------------
All callbacks are validated by dual-timezone business hours:

1. **Medical Guardian Operating Hours**: 9 AM - 5 PM EST [CONFIRMED]
2. **Member's Local Timezone**: 9 AM - 5 PM in member.timezone

If callback is due outside business hours:
- Automatically rescheduled to next business day at 9:00 AM (member's timezone)
- Attempt count NOT incremented for reschedule
- Only actual call attempts increment attempt_count

EXAMPLE SCENARIO 1 (Successful Callback):
------------------------------------------
1. **10:00 AM**: Member John answers Call 1
2. **10:01 AM**: AI asks: "Are you ready to activate your device?"
3. **10:02 AM**: John says: "I'm busy right now, can you call me back in 2 hours"
4. **10:02 AM**: Webhook creates callback entry:
   - scheduled_callback_time = 12:00 PM
   - callback_reason = "Member requested callback in 2 hours"
   - status = 'PENDING'
   - attempt_count = 0
   - max_attempts = 3
5. **12:00 PM**: CallbackScheduler picks up callback (scheduled time reached)
6. **12:01 PM**: Business hours validated (both timezones within 9 AM - 5 PM)
7. **12:02 PM**: Callback submitted to Bland AI
8. **12:05 PM**: John answers, activates device
9. **12:06 PM**: Webhook marks callback as COMPLETED
10. **Result**: Device activation successful via callback

EXAMPLE SCENARIO 2 (Timeout - 24 Hours):
-----------------------------------------
1. **10:00 AM Day 1**: Callback created (scheduled_callback_time = 12:00 PM Day 1)
2. **12:00 PM Day 1**: Callback attempt 1 - No answer (rescheduled to Day 2)
3. **9:00 AM Day 2**: Callback attempt 2 - No answer (rescheduled later)
4. **2:00 PM Day 2**: Callback attempt 3 - No answer
5. **10:01 AM Day 3**: 24 hours elapsed since creation
6. **10:01 AM Day 3**: _handle_callback_timeouts() marks status = 'TIMED_OUT'
7. **Result**: Member re-enters main call sequence (Call 2, 3, 4...)

EXAMPLE SCENARIO 3 (Rescheduled - Outside Business Hours):
-----------------------------------------------------------
1. **5:30 PM EST**: Callback due (outside MG operating hours)
2. **5:31 PM EST**: Business hours validation fails
3. **5:31 PM EST**: _reschedule_callback() calculates next valid time
4. **5:31 PM EST**: Updated scheduled_callback_time = Tomorrow 9:00 AM EST
5. **Next Day 9:00 AM**: Callback processed during business hours
6. **Result**: Callback delayed but not penalized (attempt_count unchanged)

INTEGRATION WITH MAIN SCHEDULER:
---------------------------------
The CallbackScheduler is called by main_logic.py as part of the scheduler flow:

```python
# In main_logic.py (simplified)
def create_device_activation_batch():
    # Step 1: Process callbacks FIRST (higher priority)
    callback_result = callback_scheduler.process_callbacks()
    eligible_callbacks = callback_result['eligible_callbacks']

    # Step 2: Get regular eligible members
    eligible_members = eligibility_service.get_eligible_members()

    # Step 3: Combine callbacks + regular members, submit to Bland AI
    all_eligible = eligible_callbacks + eligible_members
    batch_orchestrator.create_and_submit_batches(all_eligible)
```

**Callback Priority**: Callbacks are processed BEFORE regular call sequence members to ensure
promised callback times are honored.

DATABASE TABLES ACCESSED:
--------------------------
- **outreach_callback_queue** (read/write):
  - Fields: callback_id, enrollment_id, member_id, campaign_id
  - Fields: scheduled_callback_time, callback_reason, preferred_contact_method
  - Fields: status, attempt_count, max_attempts, last_attempt_ts, created_ts
  - Operations: SELECT (pending callbacks), UPDATE (reschedule, timeout, complete)

- **members** (read): Contact information, timezone
- **member_devices** (read): Device information for metadata
- **member_campaign_enrollments_enhanced** (read): Enrollment status, activation dates

RELATED COMPONENTS:
-------------------
- **EligibilityService** (BC-DA-003): Gets regular eligible members
- **BatchOrchestrator** (BC-DA-004): Submits callbacks + regular members to Bland AI
- **Webhook Processor** (BC-DA-007): Creates callbacks, updates status after calls
- **business_hours_utils.py**: Shared dual-timezone validation

RELATED DOCUMENTATION:
----------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Call Sequence Diagrams: documentation/device_activation/FLOWS/DEVICE_ACTIVATION_CALL_SEQUENCE.md
- State Machines: documentation/device_activation/FLOWS/DEVICE_ACTIVATION_STATE_MACHINES.md

EXAMPLES:
---------
Basic usage in scheduler:
    >>> from af_code.device_activation_scheduler.services.callback_scheduler import CallbackScheduler
    >>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
    >>>
    >>> db_service = DatabaseService(config_manager)
    >>> callback_scheduler = CallbackScheduler(db_service)
    >>>
    >>> # Process all pending callbacks
    >>> result = callback_scheduler.process_callbacks()
    >>> print(f"Eligible: {len(result['eligible_callbacks'])}, "
    ...       f"Rescheduled: {result['rescheduled_count']}, "
    ...       f"Timed out: {result['timed_out_count']}")
    Eligible: 3, Rescheduled: 2, Timed out: 1
    >>>
    >>> # Process eligible callbacks with BatchOrchestrator
    >>> for callback in result['eligible_callbacks']:
    ...     print(f"Callback for {callback['first_name']} {callback['last_name']}, "
    ...           f"Attempt {callback['attempt_count']}/{callback['max_attempts']}")
"""

from af_code.shared.schema_config import IOE_SCHEMA

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

    BusinessCaseID: BC-DA-005

    This service orchestrates the callback lifecycle for Device Activation campaigns. It runs
    as part of the main scheduler (every 15 minutes) to process callback requests created when
    members ask to be called back at a more convenient time.

    The service handles the complete callback workflow:
    - Query pending callbacks from outreach_callback_queue
    - Validate dual-timezone business hours (MG EST + member timezone)
    - Return eligible callbacks for Bland AI batch submission
    - Reschedule callbacks outside business hours (next business day 9 AM)
    - Track callback attempts (increment after each call)
    - Handle timeouts (24 hours OR 3 attempts)
    - Mark callbacks completed/failed based on webhook results

    Attributes:
        db_service (DatabaseService): Database service for query execution and connection management
        PENDING_CALLBACKS_QUERY (str): Class-level SQL query to fetch pending callbacks (200+ lines)

    Methods:
        **Public Methods** (called by main_logic.py):
            get_pending_callbacks() -> List[Dict]:
                Query database for callbacks due for execution

            process_callbacks() -> Dict[str, Any]:
                Main entry point - process all pending callbacks (business hours validation, timeout handling)

            increment_callback_attempt(callback_id: str) -> bool:
                Increment attempt count after Bland AI submission

            mark_callback_completed(callback_id: str) -> bool:
                Mark callback as COMPLETED (webhook: device activated)

            mark_callback_failed(callback_id: str) -> bool:
                Mark callback as FAILED (webhook: all attempts exhausted)

        **Private Methods** (internal use only):
            _validate_callback_business_hours(callback_id: str, member_timezone: str) -> Tuple[bool, str]:
                Validate if callback can be made right now (dual-timezone check)

            _reschedule_callback(callback_id: str, member_timezone: str) -> bool:
                Reschedule callback to next business day 9 AM

            _handle_callback_timeouts() -> int:
                Mark callbacks as TIMED_OUT (24 hours OR 3 attempts)

    Callback Queue Processing Flow:
        1. **Query Stage**: Execute PENDING_CALLBACKS_QUERY to get callbacks
           - Filter: status = 'PENDING'
           - Filter: scheduled_callback_time <= NOW
           - Filter: attempt_count < max_attempts
           - Filter: created_ts + 24 hours > NOW (not timed out)

        2. **Timeout Stage**: Mark timed-out callbacks BEFORE processing
           - Condition 1: created_ts + 24 hours <= NOW
           - Condition 2: attempt_count >= max_attempts
           - Action: UPDATE status = 'TIMED_OUT'

        3. **Business Hours Stage**: For each callback:
           - Validate dual-timezone business hours
           - If eligible: Add to eligible_callbacks list
           - If outside hours: Reschedule to next business day 9 AM

        4. **Return Stage**: Return eligible_callbacks to BatchOrchestrator
           - Callbacks submitted to Bland AI in same batch as regular members
           - Callbacks have HIGHER priority (processed first)

    Timeout Logic (OR Condition):
        **24-Hour Timeout** (Time-Based):
        - Threshold: created_ts + 24 hours
        - SQL: `DATEDIFF(HOUR, created_ts, SYSDATETIMEOFFSET()) >= 24`
        - Rationale: Prevents callbacks from sitting in queue indefinitely
        - Example: Callback created Monday 10 AM, times out Tuesday 10 AM

        **3-Attempt Timeout** (Attempt-Based):
        - Threshold: attempt_count >= max_attempts (default 3)
        - SQL: `attempt_count >= max_attempts`
        - Rationale: Prevents infinite retry loops for unresponsive members
        - Example: Attempt 1 (no answer), Attempt 2 (no answer), Attempt 3 (timeout)

        **Either condition triggers timeout** (OR logic, not AND)

    Rescheduling Logic:
        When callback is due outside business hours:
        1. Calculate member's current local time
        2. Add 1 day (tomorrow)
        3. Set time to 9:00 AM (member's timezone)
        4. Convert back to UTC for database storage
        5. UPDATE scheduled_callback_time
        6. **Attempt count NOT incremented** (only actual calls count)

        Example:
        - Callback due: Today 6:00 PM EST (outside MG hours)
        - Member timezone: America/New_York
        - Reschedule to: Tomorrow 9:00 AM EST
        - Attempt count: Unchanged (0 → 0)

    Integration with Scheduler:
        CallbackScheduler is called by main_logic.py BEFORE EligibilityService:

        ```python
        # In device_activation_scheduler/main_logic.py
        def create_device_activation_batch():
            # Step 1: Process callbacks (higher priority)
            callback_result = callback_scheduler.process_callbacks()
            callbacks = callback_result['eligible_callbacks']

            # Step 2: Get regular eligible members
            members = eligibility_service.get_eligible_members()

            # Step 3: Combine and submit to Bland AI
            all_eligible = callbacks + members
            batch_orchestrator.create_and_submit_batches(all_eligible)
        ```

        **Why callbacks first?**: To honor promised callback times and ensure member
        expectations are met before processing general outreach.

    Example:
        >>> # Initialize service
        >>> from af_code.device_activation_scheduler.services.callback_scheduler import CallbackScheduler
        >>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
        >>>
        >>> db_service = DatabaseService(config_manager)
        >>> callback_scheduler = CallbackScheduler(db_service)
        >>>
        >>> # Process all pending callbacks
        >>> result = callback_scheduler.process_callbacks()
        >>> print(f"Eligible: {len(result['eligible_callbacks'])}")
        >>> print(f"Rescheduled: {result['rescheduled_count']}")
        >>> print(f"Timed out: {result['timed_out_count']}")
        Eligible: 5
        Rescheduled: 2
        Timed out: 1
        >>>
        >>> # Check eligible callbacks
        >>> for callback in result['eligible_callbacks']:
        ...     print(f"{callback['first_name']} - Attempt {callback['attempt_count']}/3")
        John - Attempt 0/3
        Jane - Attempt 1/3
        Bob - Attempt 2/3

    Notes:
        - This service is called every 15 minutes by device_activation_scheduler timer trigger
        - Callbacks have HIGHER priority than regular call sequence members
        - Timeout is OR condition: 24 hours elapsed OR 3 attempts exhausted
        - Rescheduling does NOT count as an attempt (only actual Bland AI calls count)
        - Timed-out members return to main call sequence (Call 2, 3, 4, etc.)
        - Business hours validation uses shared utility: business_hours_utils.can_make_call()
        - All datetime operations use timezone-aware datetime objects (pytz)

    Related Components:
        - EligibilityService (BC-DA-003): Gets regular eligible members (after callbacks)
        - BatchOrchestrator (BC-DA-004): Submits callbacks + members to Bland AI
        - Webhook Processor (BC-DA-007): Creates callbacks, updates status
        - DatabaseService: Executes SQL queries and manages connections
        - business_hours_utils.can_make_call(): Dual-timezone validation

    Related Code:
        - af_code/device_activation_scheduler/main_logic.py:48-75 - Calls this service
        - af_code/device_activation_scheduler/services/batch_orchestrator.py:177-239 - Consumes callbacks
        - af_code/shared/business_hours_utils.py:15-45 - Business hours validation
        - af_code/bland_ai_webhook/services/database_orchestrator.py:400-450 - Creates callbacks
    """

    # SQL query to find pending callbacks due for execution
    PENDING_CALLBACKS_QUERY = f"""
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
        md.fall_detection,
        md.powersaver_mode,
        e.activation_start_date,
        e.campaign_end_date,
        e.customer_type

    FROM {IOE_SCHEMA}.outreach_callback_queue cq
    JOIN {IOE_SCHEMA}.members m ON cq.member_id = m.member_id
    JOIN {IOE_SCHEMA}.member_devices md ON m.member_id = md.member_id
    JOIN {IOE_SCHEMA}.member_campaign_enrollments_enhanced e ON cq.enrollment_id = e.enrollment_id

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

        BusinessCaseID: BC-DA-005
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

        BusinessCaseID: BC-DA-005
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
                _member_id = callback.get("member_id")

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

        BusinessCaseID: BC-DA-005
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
            update_sql = f"""
            UPDATE {IOE_SCHEMA}.outreach_callback_queue
            SET scheduled_callback_time = ?, updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = ?
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

        Timeout conditions (OR logic - either condition triggers timeout):
        1. 24 hours elapsed since callback creation (CALENDAR hours, not business days)
        2. 3 attempts exhausted (attempt_count >= max_attempts)

        When a callback times out, the member returns to the main call sequence.

        NOTE: Callback timeout uses 24 CALENDAR hours, which is DIFFERENT from:
        - Main sequence Calls 1-4: Use BUSINESS days (2-5 days, excluding weekends/holidays)
        - Main sequence Call 5+: Use 7 CALENDAR days (weekly frequency)

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

        BusinessCaseID: BC-DA-005
        """
        try:
            timeout_sql = f"""
            UPDATE {IOE_SCHEMA}.outreach_callback_queue
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
            count_sql = f"""
            SELECT COUNT(*) as timeout_count
            FROM {IOE_SCHEMA}.outreach_callback_queue
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

        BusinessCaseID: BC-DA-005
        """
        try:
            update_sql = f"""
            UPDATE {IOE_SCHEMA}.outreach_callback_queue
            SET
                attempt_count = attempt_count + 1,
                status = 'IN_PROGRESS',
                last_attempt_ts = SYSDATETIMEOFFSET(),
                updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = ?
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

        BusinessCaseID: BC-DA-005
        """
        try:
            update_sql = f"""
            UPDATE {IOE_SCHEMA}.outreach_callback_queue
            SET status = 'COMPLETED', updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = ?
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

        BusinessCaseID: BC-DA-005
        """
        try:
            update_sql = f"""
            UPDATE {IOE_SCHEMA}.outreach_callback_queue
            SET status = 'FAILED', updated_ts = SYSDATETIMEOFFSET()
            WHERE callback_id = ?
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
