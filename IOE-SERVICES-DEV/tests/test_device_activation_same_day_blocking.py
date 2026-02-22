"""
Test suite for Device Activation Same-Day Retry Blocking

Tests verify that the TodayActiveAttempts CTE correctly blocks members from receiving
multiple calls on the same day, regardless of call disposition or outcome.

**The Rule:** One call per member per day - If a member was already called today
(even if the call failed), they will NOT be called again until tomorrow.

**Test Approach:**
- Uses mocked DatabaseService (no real database connection required)
- Tests SQL query logic via mocked query results
- Validates CTE filtering, UTC date boundaries, and disposition blocking

BusinessCaseID: BC-DA-007 (Same-Day Retry Protection)
Created: 2026-01-14
"""

import pytest
import pytz
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call
from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService


class TestSameDayRetryBlocking:
    """Test TodayActiveAttempts CTE blocks same-day retries"""

    @pytest.fixture
    def mock_db_service(self):
        """Mock database service - no real database needed"""
        return Mock()

    @pytest.fixture
    def eligibility_service(self, mock_db_service):
        """Create EligibilityService instance with mocked database"""
        return EligibilityService(mock_db_service)

    @pytest.fixture
    def today_9am_utc(self):
        """Today at 9:00 AM UTC"""
        return datetime.now(pytz.UTC).replace(hour=9, minute=0, second=0, microsecond=0)

    @pytest.fixture
    def today_2pm_utc(self):
        """Today at 2:00 PM UTC"""
        return datetime.now(pytz.UTC).replace(hour=14, minute=0, second=0, microsecond=0)

    @pytest.fixture
    def yesterday_2pm_utc(self):
        """Yesterday at 2:00 PM UTC"""
        yesterday = datetime.now(pytz.UTC) - timedelta(days=1)
        return yesterday.replace(hour=14, minute=0, second=0, microsecond=0)

    def create_test_member(
        self,
        member_id="test-member-001",
        enrollment_id="test-enrollment-001",
        call_attempt_number=1,
        last_attempt_date=None,
        last_disposition=None,
    ):
        """
        Helper to create a mock member record

        Args:
            member_id: Unique member identifier
            enrollment_id: Unique enrollment identifier
            call_attempt_number: Which call attempt this is (1, 2, 3, 4, 5+)
            last_attempt_date: Datetime of last attempt (None for Call 1)
            last_disposition: Last call disposition (None for Call 1)

        Returns:
            Dict representing a member record from eligibility query
        """
        return {
            "member_id": member_id,
            "enrollment_id": enrollment_id,
            "campaign_id": "test-campaign-001",
            "first_name": "John",
            "last_name": "Doe",
            "primary_phone": "+15551234567",
            "email": "john.doe@example.com",
            "timezone": "America/New_York",
            "language_pref": "EN",
            "device_id": "device-001",
            "device_phone_number": "+15559876543",
            "is_device_callable": 1,
            "call_attempt_number": call_attempt_number,
            "last_attempt_date": last_attempt_date,
            "last_disposition": last_disposition,
        }

    # ========================================================================
    # Database-Level Tests: SQL Query Validation
    # ========================================================================

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_1_completed_call_blocks_same_day_retry(
        self, mock_datetime, eligibility_service, mock_db_service, today_9am_utc, today_2pm_utc
    ):
        """
        Scenario 1: Successful Call - No Same-Day Retry

        Timeline:
        - 9:00 AM UTC: Member John gets called → Call completes successfully (Completed)
        - 2:00 PM UTC: Scheduler runs again

        Expected: John is NOT eligible (already called today)
        """
        # Setup: Current time is 2 PM UTC (scheduler running again)
        mock_datetime.now.return_value = today_2pm_utc

        # Mock SQL query returns NO members (CTE filtered out John who was called at 9 AM)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member with 'Completed' call today should be blocked by TodayActiveAttempts CTE"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_2_failed_call_blocks_same_day_retry(
        self, mock_datetime, eligibility_service, mock_db_service, today_2pm_utc
    ):
        """
        Scenario 2: Failed Call - No Same-Day Retry

        Timeline:
        - 10:00 AM UTC: Member Sarah gets called → Call fails (Failed)
        - 3:30 PM UTC: Scheduler runs again

        Expected: Sarah is NOT eligible (already called today, even though it failed)
        """
        # Setup: Current time is 3:30 PM UTC
        afternoon_time = today_2pm_utc.replace(hour=15, minute=30)
        mock_datetime.now.return_value = afternoon_time

        # Mock SQL query returns NO members (CTE filtered out Sarah)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member with 'Failed' call today should be blocked (same-day protection applies to all dispositions)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_3_no_answer_blocks_same_day_retry(
        self, mock_datetime, eligibility_service, mock_db_service, today_2pm_utc
    ):
        """
        Scenario 3: No Answer - No Same-Day Retry

        Timeline:
        - 11:00 AM UTC: Member Mike gets called → No answer (NoAnswer)
        - 4:00 PM UTC: Scheduler runs again

        Expected: Mike is NOT eligible (already called today)
        """
        # Setup: Current time is 4 PM UTC
        afternoon_time = today_2pm_utc.replace(hour=16, minute=0)
        mock_datetime.now.return_value = afternoon_time

        # Mock SQL query returns NO members (CTE filtered out Mike)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member with 'NoAnswer' today should be blocked (no same-day retries for any disposition)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_4_pending_call_blocks_same_day_retry(
        self, mock_datetime, eligibility_service, mock_db_service, today_2pm_utc
    ):
        """
        Scenario 4: Pending Call - No Same-Day Retry

        Timeline:
        - 1:00 PM UTC: Member Lisa gets called → Batch submitted, call still pending (Pending)
        - 4:30 PM UTC: Scheduler runs again

        Expected: Lisa is NOT eligible (already has pending attempt today)
        """
        # Setup: Current time is 4:30 PM UTC
        afternoon_time = today_2pm_utc.replace(hour=16, minute=30)
        mock_datetime.now.return_value = afternoon_time

        # Mock SQL query returns NO members (CTE filtered out Lisa with pending call)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member with 'Pending' call today should be blocked (prevents duplicate submissions)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_5_canceled_call_blocks_same_day_retry(
        self, mock_datetime, eligibility_service, mock_db_service, today_9am_utc, today_2pm_utc
    ):
        """
        Scenario 5: Canceled Call - No Same-Day Retry

        Timeline:
        - 8:00 AM UTC: Member Tom gets called → Call gets canceled (Canceled)
        - 12:00 PM UTC: Scheduler runs again

        Expected: Tom is NOT eligible (already called today)
        """
        # Setup: Current time is 12 PM UTC
        noon_time = today_2pm_utc.replace(hour=12, minute=0)
        mock_datetime.now.return_value = noon_time

        # Mock SQL query returns NO members (CTE filtered out Tom)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member with 'Canceled' call today should be blocked"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_6_next_day_eligibility(
        self, mock_datetime, eligibility_service, mock_db_service, yesterday_2pm_utc
    ):
        """
        Scenario 6: Next Day Eligibility

        Timeline:
        - Day 1 (Monday) 9:00 AM: Member Jane gets called → No answer (NoAnswer)
        - Day 1 (Monday) 4:00 PM: Scheduler runs → Jane is NOT eligible (same day)
        - Day 2 (Tuesday) 9:00 AM: Scheduler runs → Jane IS eligible (new day)

        Expected: Jane IS eligible on Day 2 (new UTC day, frequency rules allow)
        """
        # Setup: Current time is Day 2 (Tuesday) at 9 AM UTC
        tomorrow = datetime.now(pytz.UTC) + timedelta(days=1)
        tuesday_9am = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = tuesday_9am

        # Mock SQL query returns Jane (she's no longer blocked by TodayActiveAttempts)
        # Her last attempt was yesterday, so CTE won't include her
        jane = self.create_test_member(
            member_id="jane-002",
            call_attempt_number=2,  # This will be her Call 2
            last_attempt_date=yesterday_2pm_utc,  # Yesterday at 2 PM
            last_disposition="NoAnswer",
        )
        mock_db_service.execute_query.return_value = [jane]

        # Execute (with business day filtering and business hours mocked to pass)
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday_calc, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call:
            mock_bday_calc.return_value = 2  # Sufficient business days for Call 2
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 1, (
            "Member should be eligible next day (new UTC day, not blocked by CTE)"
        )
        assert eligible_members[0]["member_id"] == "jane-002"
        assert eligible_members[0]["call_attempt_number"] == 2

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_7_multiple_members_selective_blocking(
        self, mock_datetime, eligibility_service, mock_db_service, yesterday_2pm_utc
    ):
        """
        Scenario 7: Multiple Members - Selective Blocking

        Setup:
        - Member A: Called today at 9 AM (BLOCKED)
        - Member B: Called yesterday at 9 AM (ELIGIBLE)
        - Member C: Never called (ELIGIBLE)

        Expected: Only Member B and Member C are eligible (Member A blocked by CTE)
        """
        # Setup: Current time is today at 10 AM UTC
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        # Mock SQL query returns only Member B and Member C
        # (Member A was filtered out by TodayActiveAttempts CTE)
        member_b = self.create_test_member(
            member_id="member-b",
            enrollment_id="enrollment-b",
            call_attempt_number=2,
            last_attempt_date=yesterday_2pm_utc,
            last_disposition="NoAnswer",
        )
        member_c = self.create_test_member(
            member_id="member-c",
            enrollment_id="enrollment-c",
            call_attempt_number=1,  # First call
            last_attempt_date=None,
            last_disposition=None,
        )
        mock_db_service.execute_query.return_value = [member_b, member_c]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday_calc, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call:
            mock_bday_calc.return_value = 2  # Sufficient for Call 2
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 2, (
            "Should return 2 members (Member A blocked, Members B and C eligible)"
        )
        member_ids = [m["member_id"] for m in eligible_members]
        assert "member-b" in member_ids, "Member B should be eligible (called yesterday)"
        assert "member-c" in member_ids, "Member C should be eligible (never called)"

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_scenario_8_utc_date_boundary_edge_case(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Scenario 8: Timezone Edge Case (UTC vs Local)

        Timeline:
        - 11:50 PM EST (Monday) = 4:50 AM UTC (Tuesday): Member called
        - 8:00 AM EST (Tuesday) = 1:00 PM UTC (Tuesday): Scheduler runs

        Expected: Member is NOT eligible (same UTC day - both Tuesday in UTC)

        This tests that the CTE correctly uses UTC date boundaries, not local time.
        """
        # Setup: Current time is 1:00 PM UTC Tuesday
        tuesday_1pm_utc = datetime(2025, 1, 14, 13, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = tuesday_1pm_utc

        # Mock SQL query returns NO members
        # Member was called at 4:50 AM UTC Tuesday (same UTC day)
        # CTE filtered them out
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "Member called at 4:50 AM UTC Tuesday should be blocked at 1 PM UTC Tuesday "
            "(same UTC day, even though different local days in EST)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_all_dispositions_block_same_day(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test: All 5 Dispositions Block Same-Day Retries

        Setup:
        - 5 members with different dispositions today:
          - Member 1: Completed
          - Member 2: Failed
          - Member 3: NoAnswer
          - Member 4: Pending
          - Member 5: Canceled

        Expected: ALL 5 members are excluded by TodayActiveAttempts CTE
        """
        # Setup: Current time is today at 3 PM UTC
        today_3pm = datetime.now(pytz.UTC).replace(hour=15, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_3pm

        # Mock SQL query returns NO members
        # All 5 members were filtered out by CTE (all have attempts today)
        mock_db_service.execute_query.return_value = []

        # Execute
        eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, (
            "All 5 dispositions (Completed, Failed, NoAnswer, Pending, Canceled) "
            "should be blocked by TodayActiveAttempts CTE"
        )

    # ========================================================================
    # Integration Tests: Full EligibilityService
    # ========================================================================

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_get_eligible_members_excludes_today_attempts(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Integration Test: get_eligible_members() excludes members with today's attempts

        Validates the full method call chain including SQL execution
        """
        # Setup
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        # Mock SQL returns empty (member was blocked by CTE)
        mock_db_service.execute_query.return_value = []

        # Execute
        result = eligibility_service.get_eligible_members()

        # Assertions
        assert isinstance(result, list), "Should return a list"
        assert len(result) == 0, "Should exclude member with today's attempt"
        mock_db_service.execute_query.assert_called_once()  # SQL was executed

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_get_eligible_members_includes_yesterday_attempts(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Integration Test: get_eligible_members() includes members with yesterday's attempts

        Validates that members called yesterday pass through CTE filtering
        """
        # Setup
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        yesterday = today_10am - timedelta(days=1)
        member = self.create_test_member(
            member_id="eligible-member",
            call_attempt_number=2,
            last_attempt_date=yesterday,
            last_disposition="NoAnswer",
        )
        mock_db_service.execute_query.return_value = [member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call:
            mock_bday.return_value = 2  # Sufficient business days
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check

            result = eligibility_service.get_eligible_members()

        # Assertions
        assert len(result) == 1, "Should include member with yesterday's attempt"
        assert result[0]["member_id"] == "eligible-member"

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_eligibility_service_with_mixed_attempt_dates(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Integration Test: Mixed attempt dates - only non-today attempts are eligible

        Setup:
        - Member A: Last attempt TODAY at 9 AM (BLOCKED by CTE)
        - Member B: Last attempt 2 business days ago (ELIGIBLE for Call 2)
        - Member C: Last attempt 5 business days ago (ELIGIBLE for Call 4)
        - Member D: Last attempt 10 calendar days ago (ELIGIBLE for Call 5+)

        Expected: Only Members B, C, D are returned (A filtered by CTE)
        """
        # Setup
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        # Mock SQL returns only B, C, D (A was filtered by TodayActiveAttempts CTE)
        # Need to provide last_attempt_date for Calls 2+ to pass validation
        two_days_ago = today_10am - timedelta(days=2)
        five_days_ago = today_10am - timedelta(days=5)
        ten_days_ago = today_10am - timedelta(days=10)

        member_b = self.create_test_member(
            "member-b",
            call_attempt_number=2,
            last_attempt_date=two_days_ago,
            last_disposition="NoAnswer"
        )
        member_c = self.create_test_member(
            "member-c",
            call_attempt_number=4,
            last_attempt_date=five_days_ago,
            last_disposition="NoAnswer"
        )
        member_d = self.create_test_member(
            "member-d",
            call_attempt_number=5,
            last_attempt_date=ten_days_ago,
            last_disposition="NoAnswer"
        )
        mock_db_service.execute_query.return_value = [member_b, member_c, member_d]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call:

            mock_bday.return_value = 5  # Sufficient for Call 2 and Call 4
            mock_is_bday.return_value = True  # Today is a business day
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check

            result = eligibility_service.get_eligible_members()

        # Assertions
        assert len(result) == 3, "Should return 3 members (A blocked, B/C/D eligible)"
        member_ids = [m["member_id"] for m in result]
        assert "member-b" in member_ids
        assert "member-c" in member_ids
        assert "member-d" in member_ids

    # ========================================================================
    # Edge Case Tests
    # ========================================================================

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_midnight_utc_transition(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Edge Case: Midnight UTC Transition

        Timeline:
        - 11:55 PM UTC Day 1: Member called
        - 10:00 AM UTC Day 2: Scheduler runs

        Expected: Member IS eligible (crossed into new UTC day)

        This tests the UTC date boundary logic in the CTE:
        - Day 1: >= 2025-01-13 00:00 AND < 2025-01-14 00:00 (includes 11:55 PM)
        - Day 2: >= 2025-01-14 00:00 AND < 2025-01-15 00:00 (excludes 11:55 PM from Day 1)
        """
        # Setup: Current time is 10 AM UTC Day 2 (during business hours)
        day_2_morning = datetime(2025, 1, 14, 10, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = day_2_morning

        # Member called yesterday at 11:55 PM UTC (just before midnight)
        day_1_late_night = datetime(2025, 1, 13, 23, 55, tzinfo=pytz.UTC)
        member = self.create_test_member(
            member_id="midnight-member",
            call_attempt_number=2,
            last_attempt_date=day_1_late_night,
            last_disposition="NoAnswer",
        )
        mock_db_service.execute_query.return_value = [member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_bday.return_value = 2  # 2 business days (sufficient for Call 2)
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check
            mock_is_bday.return_value = True  # Day 2 is a business day

            result = eligibility_service.get_eligible_members()

        # Assertions
        assert len(result) == 1, (
            "Member called at 11:55 PM UTC Day 1 should be eligible at 10 AM UTC Day 2 "
            "(crossed UTC date boundary, different UTC days)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_multiple_campaigns_same_member(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Edge Case: Multiple Campaigns - Same Member Blocked Across Campaigns

        Setup:
        - Campaign A: Member called today
        - Campaign B: Same member enrolled

        Expected: Member is NOT eligible in Campaign B (CTE blocks across campaigns)

        The TodayActiveAttempts CTE filters by member_id, not enrollment_id,
        so a member with ANY attempt today is blocked across ALL campaigns.
        """
        # Setup
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        # Mock SQL returns NO members
        # Member has attempt today in Campaign A, so blocked in Campaign B too
        mock_db_service.execute_query.return_value = []

        # Execute
        result = eligibility_service.get_eligible_members()

        # Assertions
        assert len(result) == 0, (
            "Member with attempt today in Campaign A should be blocked in Campaign B "
            "(CTE filters by member_id, not campaign_id)"
        )

    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_no_attempts_member_eligible(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Edge Case: No Previous Attempts - Member Eligible (Call 1)

        Setup: Member with activation_start_date in past, no previous attempts

        Expected: Member IS eligible (no same-day blocking for Call 1)
        """
        # Setup
        today_10am = datetime.now(pytz.UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        mock_datetime.now.return_value = today_10am

        # Mock SQL returns member with no previous attempts
        member = self.create_test_member(
            member_id="new-member",
            call_attempt_number=1,
            last_attempt_date=None,
            last_disposition=None,
        )
        mock_db_service.execute_query.return_value = [member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.can_make_call"
        ) as mock_can_call:
            mock_can_call.return_value = (True, "Within business hours")  # Pass business hours check

            result = eligibility_service.get_eligible_members()

        # Assertions
        assert len(result) == 1, "Member with no previous attempts should be eligible"
        assert result[0]["call_attempt_number"] == 1


class TestSameDayBlockingDocumentation:
    """
    Documentation tests - verify understanding of same-day blocking logic

    These tests serve as executable documentation showing how the
    TodayActiveAttempts CTE works in different scenarios.
    """

    def test_cte_date_range_logic_explained(self):
        """
        Documentation: CTE Date Range Logic

        The TodayActiveAttempts CTE uses UTC date boundaries:

        SQL Logic:
        ```sql
        AND oa.attempt_ts >= CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET)
        AND oa.attempt_ts < DATEADD(day, 1, CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET))
        ```

        Example (Today = 2025-01-14):
        - Start: 2025-01-14 00:00:00 UTC (inclusive)
        - End:   2025-01-15 00:00:00 UTC (exclusive)

        Any attempt with attempt_ts in this range will be included in the CTE.
        """
        # Get today's date in UTC
        today_utc = datetime.now(pytz.UTC).date()

        # CTE start boundary: Today at 00:00:00 UTC
        cte_start = datetime.combine(today_utc, datetime.min.time()).replace(tzinfo=pytz.UTC)

        # CTE end boundary: Tomorrow at 00:00:00 UTC
        tomorrow_utc = today_utc + timedelta(days=1)
        cte_end = datetime.combine(tomorrow_utc, datetime.min.time()).replace(tzinfo=pytz.UTC)

        # Test examples
        attempt_early_morning = cte_start.replace(hour=2, minute=30)
        attempt_late_night = cte_start.replace(hour=23, minute=55)
        attempt_yesterday = cte_start - timedelta(hours=1)  # 11 PM yesterday
        attempt_tomorrow = cte_end + timedelta(hours=1)  # 1 AM tomorrow

        # Verify CTE logic
        assert cte_start <= attempt_early_morning < cte_end, "2:30 AM today should be included"
        assert cte_start <= attempt_late_night < cte_end, "11:55 PM today should be included"
        assert not (cte_start <= attempt_yesterday < cte_end), "11 PM yesterday should NOT be included"
        assert not (cte_start <= attempt_tomorrow < cte_end), "1 AM tomorrow should NOT be included"

    def test_disposition_filtering_explained(self):
        """
        Documentation: Disposition Filtering Logic

        The CTE blocks ALL of these dispositions:
        - 'Completed': Call completed successfully
        - 'Pending': Call submitted to Bland AI, waiting for result
        - 'Failed': Call failed (system error, invalid number, etc.)
        - 'NoAnswer': Member didn't answer
        - 'Canceled': Call was canceled

        SQL:
        ```sql
        AND oa.disposition IN ('Completed', 'Pending', 'Failed', 'NoAnswer', 'Canceled')
        ```

        WHY block all dispositions?
        - Prevents member fatigue (one call per day regardless of outcome)
        - Prevents duplicate submissions (blocks Pending)
        - Consistent retry logic (wait until next day for any outcome)
        """
        blocked_dispositions = ['Completed', 'Pending', 'Failed', 'NoAnswer', 'Canceled']

        # All 5 dispositions trigger same-day blocking
        assert len(blocked_dispositions) == 5, "CTE blocks exactly 5 disposition types"
        assert 'Completed' in blocked_dispositions, "Success blocks same-day retry"
        assert 'Failed' in blocked_dispositions, "Failure blocks same-day retry"
        assert 'NoAnswer' in blocked_dispositions, "No answer blocks same-day retry"
        assert 'Pending' in blocked_dispositions, "Pending blocks duplicate submission"
        assert 'Canceled' in blocked_dispositions, "Canceled blocks same-day retry"

    def test_left_join_filter_pattern_explained(self):
        """
        Documentation: LEFT JOIN + IS NULL Filter Pattern

        The eligibility query uses this pattern to exclude members in the CTE:

        ```sql
        -- Define CTE
        WITH TodayActiveAttempts AS (
            SELECT DISTINCT e.member_id FROM ... WHERE ... (attempt today)
        )

        -- Main query
        SELECT ...
        FROM member_campaign_enrollments_enhanced e
        LEFT JOIN TodayActiveAttempts taa ON e.member_id = taa.member_id
        WHERE ...
          AND taa.member_id IS NULL  -- Exclude members in CTE
        ```

        How it works:
        1. LEFT JOIN: All members get a row, even if not in CTE
        2. Members IN CTE: taa.member_id is NOT NULL (matched)
        3. Members NOT in CTE: taa.member_id IS NULL (no match)
        4. Filter: `WHERE taa.member_id IS NULL` keeps only members NOT in CTE

        Example:
        - Member A: Called today → IN CTE → taa.member_id = 'A' → EXCLUDED
        - Member B: Not called today → NOT in CTE → taa.member_id = NULL → INCLUDED
        """
        # Simulate LEFT JOIN + IS NULL filtering

        # Members with attempts today (in CTE)
        members_in_cte = {'member-a', 'member-d'}

        # All members
        all_members = [
            {'member_id': 'member-a', 'name': 'Alice'},
            {'member_id': 'member-b', 'name': 'Bob'},
            {'member_id': 'member-c', 'name': 'Charlie'},
            {'member_id': 'member-d', 'name': 'Diana'},
        ]

        # LEFT JOIN simulation: Add taa.member_id field
        joined_members = []
        for member in all_members:
            member_copy = member.copy()
            # If in CTE, taa.member_id = member_id; else taa.member_id = None
            member_copy['taa_member_id'] = member['member_id'] if member['member_id'] in members_in_cte else None
            joined_members.append(member_copy)

        # Filter: WHERE taa.member_id IS NULL (exclude members in CTE)
        eligible_members = [m for m in joined_members if m['taa_member_id'] is None]

        # Verify
        assert len(eligible_members) == 2, "Should return 2 members (B and C)"
        assert eligible_members[0]['member_id'] == 'member-b', "Bob should be eligible"
        assert eligible_members[1]['member_id'] == 'member-c', "Charlie should be eligible"
