"""
Test suite for Call 5+ business day validation in Device Activation

Tests verify that Call 5+ members are only called on business days (not weekends or holidays)
while maintaining 7 CALENDAR days frequency window.

BusinessCaseID: BC-DA-006 (Call Frequency & Sequencing Logic)
"""

import pytest
import pytz
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService
from af_code.shared.business_hours_utils import is_business_day


class TestCall5BusinessDayValidation:
    """Test Call 5+ business day validation"""

    @pytest.fixture
    def mock_db_service(self):
        """Mock database service"""
        return Mock()

    @pytest.fixture
    def eligibility_service(self, mock_db_service):
        """Create EligibilityService instance with mocked database"""
        return EligibilityService(mock_db_service)

    def create_call_5_member(self, member_id="test-member-001", call_attempt=5):
        """Helper to create a mock Call 5+ member"""
        return {
            "member_id": member_id,
            "enrollment_id": f"enrollment-{member_id}",
            "call_attempt_number": call_attempt,
            "first_name": "John",
            "last_name": "Doe",
            "primary_phone": "+15551234567",
            "timezone": "America/New_York",
            "last_attempt_date": datetime.now(pytz.UTC) - timedelta(days=8),
        }

    # ========================================================================
    # Test Case 1: Call 5+ Member - Business Day (Monday-Friday)
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_business_day_monday(self, mock_datetime, eligibility_service, mock_db_service):
        """
        Test Case 1: Call 5+ member on Monday (business day)
        Expected: Member included in eligible list
        """
        # Setup: Monday January 6, 2025, 10:00 AM EST
        monday_time = datetime(2025, 1, 6, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = monday_time

        # Mock SQL query returns Call 5+ member
        call_5_member = self.create_call_5_member(call_attempt=5)
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = True  # Monday is a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) > 0, "Call 5+ member should be included on Monday"
        assert eligible_members[0]["member_id"] == "test-member-001"
        mock_is_bday.assert_called_once()  # Should check business day

    # ========================================================================
    # Test Case 2: Call 5+ Member - Weekend (Saturday)
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_weekend_saturday(self, mock_datetime, eligibility_service, mock_db_service):
        """
        Test Case 2: Call 5+ member on Saturday (weekend)
        Expected: Member filtered out (not in eligible list)
        """
        # Setup: Saturday January 11, 2025, 10:00 AM EST
        saturday_time = datetime(2025, 1, 11, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = saturday_time

        # Mock SQL query returns Call 5+ member
        call_5_member = self.create_call_5_member(call_attempt=5)
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = False  # Saturday is NOT a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, "Call 5+ member should be filtered out on Saturday"
        mock_is_bday.assert_called_once()  # Should check business day

    # ========================================================================
    # Test Case 3: Call 5+ Member - Weekend (Sunday)
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_weekend_sunday(self, mock_datetime, eligibility_service, mock_db_service):
        """
        Test Case 3: Call 5+ member on Sunday (weekend)
        Expected: Member filtered out (not in eligible list)
        """
        # Setup: Sunday January 12, 2025, 10:00 AM EST
        sunday_time = datetime(2025, 1, 12, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = sunday_time

        # Mock SQL query returns Call 5+ member
        call_5_member = self.create_call_5_member(call_attempt=6)
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = False  # Sunday is NOT a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, "Call 5+ member should be filtered out on Sunday"
        mock_is_bday.assert_called_once()

    # ========================================================================
    # Test Case 4: Call 5+ Member - Federal Holiday (Christmas)
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_federal_holiday_christmas(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test Case 4: Call 5+ member on Christmas Day (federal holiday)
        Expected: Member filtered out (not in eligible list)
        """
        # Setup: Thursday December 25, 2025, 10:00 AM EST (Christmas)
        christmas_time = datetime(2025, 12, 25, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = christmas_time

        # Mock SQL query returns Call 5+ member
        call_5_member = self.create_call_5_member(call_attempt=7)
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            # Real is_business_day() would return False for Christmas
            mock_is_bday.return_value = False

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, "Call 5+ member should be filtered out on Christmas"
        mock_is_bday.assert_called_once()

    # ========================================================================
    # Test Case 5: Call 5+ Member - Federal Holiday (New Year's Day)
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_federal_holiday_new_years(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test Case 5: Call 5+ member on New Year's Day (federal holiday)
        Expected: Member filtered out (not in eligible list)
        """
        # Setup: Wednesday January 1, 2025, 10:00 AM EST (New Year's Day)
        new_years_time = datetime(2025, 1, 1, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = new_years_time

        # Mock SQL query returns Call 5+ member
        call_5_member = self.create_call_5_member(call_attempt=8)
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = False  # New Year's Day is NOT a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 0, "Call 5+ member should be filtered out on New Year's Day"

    # ========================================================================
    # Test Case 6: Call 5+ Member - Next Business Day After Weekend
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_next_business_day_after_weekend(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test Case 6: Call 5+ member on Monday after being filtered out on Saturday/Sunday
        Expected: Member included on Monday (next business day)
        """
        # Setup: Monday January 13, 2025, 10:00 AM EST (after weekend Jan 11-12)
        monday_time = datetime(2025, 1, 13, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = monday_time

        # Mock SQL query returns Call 5+ member (now 9+ calendar days since last attempt)
        call_5_member = self.create_call_5_member(call_attempt=5)
        call_5_member["last_attempt_date"] = datetime(
            2025, 1, 3, 15, 0, tzinfo=pytz.UTC
        )  # 10 days ago
        mock_db_service.execute_query.return_value = [call_5_member]

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = True  # Monday is a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert (
            len(eligible_members) > 0
        ), "Call 5+ member should be included on Monday after weekend"
        assert eligible_members[0]["member_id"] == "test-member-001"

    # ========================================================================
    # Test Case 7: Multiple Call 5+ Members - Mixed Business/Non-Business Days
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_5_multiple_members_tuesday(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test Case 7: Multiple Call 5+ members on a business day (Tuesday)
        Expected: All members included
        """
        # Setup: Tuesday January 7, 2025, 10:00 AM EST
        tuesday_time = datetime(2025, 1, 7, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = tuesday_time

        # Mock SQL query returns 3 Call 5+ members
        members = [
            self.create_call_5_member("member-001", call_attempt=5),
            self.create_call_5_member("member-002", call_attempt=6),
            self.create_call_5_member("member-003", call_attempt=10),
        ]
        mock_db_service.execute_query.return_value = members

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday:
            mock_is_bday.return_value = True  # Tuesday is a business day

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        assert len(eligible_members) == 3, "All 3 Call 5+ members should be included on Tuesday"
        assert mock_is_bday.call_count == 3  # Should check business day for each member

    # ========================================================================
    # Test Case 8: Call 1-4 Members - No Impact from Call 5+ Changes
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_call_1_to_4_no_impact(self, mock_datetime, eligibility_service, mock_db_service):
        """
        Test Case 8: Verify Call 1-4 members are NOT affected by Call 5+ business day changes
        Expected: Call 1-4 still use get_business_days_between() logic (unchanged)
        """
        # Setup: Friday January 10, 2025, 10:00 AM EST
        friday_time = datetime(2025, 1, 10, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = friday_time

        # Mock SQL query returns Call 2 and Call 4 members
        members = [
            self.create_call_5_member("member-call2", call_attempt=2),
            self.create_call_5_member("member-call4", call_attempt=4),
        ]
        mock_db_service.execute_query.return_value = members

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday_calc:
            # Mock business day calculation to return sufficient days
            mock_bday_calc.return_value = 3  # 3 business days

            eligibility_service.get_eligible_members()

        # Assertions
        # Verify get_business_days_between was called for Call 2 and Call 4
        assert (
            mock_bday_calc.call_count == 2
        ), "Should call get_business_days_between for Call 2 and Call 4"
        # Call 5+ logic should NOT affect Call 1-4

    # ========================================================================
    # Test Case 9: Call 5+ with Call 1-4 Mixed - Separate Logic Paths
    # ========================================================================
    @patch("af_code.device_activation_scheduler.services.eligibility_service.datetime")
    def test_mixed_call_attempts_separate_logic(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test Case 9: Mix of Call 1-4 and Call 5+ members
        Expected: Call 1-4 use business day calculation, Call 5+ use current day check
        """
        # Setup: Wednesday January 8, 2025, 10:00 AM EST
        wednesday_time = datetime(2025, 1, 8, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
        mock_datetime.now.return_value = wednesday_time

        # Mock SQL query returns mixed call attempts
        members = [
            self.create_call_5_member("member-call1", call_attempt=1),
            self.create_call_5_member("member-call3", call_attempt=3),
            self.create_call_5_member("member-call5", call_attempt=5),
            self.create_call_5_member("member-call7", call_attempt=7),
        ]
        mock_db_service.execute_query.return_value = members

        # Execute
        with patch(
            "af_code.device_activation_scheduler.services.eligibility_service.is_business_day"
        ) as mock_is_bday, patch(
            "af_code.device_activation_scheduler.services.eligibility_service.get_business_days_between"
        ) as mock_bday_calc:

            mock_is_bday.return_value = True  # Wednesday is a business day
            mock_bday_calc.return_value = 3  # Sufficient business days for Call 3

            eligible_members = eligibility_service.get_eligible_members()

        # Assertions
        # Call 1: No previous attempts, always included (no business day check)
        # Call 3: Uses get_business_days_between
        # Call 5 & 7: Use is_business_day for current day
        assert len(eligible_members) == 4, "All members should be eligible on Wednesday"
        assert mock_is_bday.call_count == 2, "Should check business day for Call 5 and Call 7"
        assert mock_bday_calc.call_count == 1, "Should calculate business days for Call 3"

    # ========================================================================
    # Test Case 10: Real is_business_day Function Integration
    # ========================================================================
    def test_is_business_day_function_integration(self):
        """
        Test Case 10: Integration test with REAL is_business_day function
        Expected: Verify actual weekend/holiday detection works correctly
        """

        # Test weekday (Monday)
        monday = datetime(2025, 1, 6, 15, 0, tzinfo=pytz.UTC)
        assert is_business_day(monday), "Monday should be a business day"

        # Test weekend (Saturday)
        saturday = datetime(2025, 1, 11, 15, 0, tzinfo=pytz.UTC)
        assert not is_business_day(saturday), "Saturday should NOT be a business day"

        # Test weekend (Sunday)
        sunday = datetime(2025, 1, 12, 15, 0, tzinfo=pytz.UTC)
        assert not is_business_day(sunday), "Sunday should NOT be a business day"

        # Test federal holiday (Christmas 2025 - Thursday)
        christmas = datetime(2025, 12, 25, 15, 0, tzinfo=pytz.UTC)
        assert not is_business_day(christmas), "Christmas should NOT be a business day"

        # Test federal holiday (New Year's Day 2025 - Wednesday)
        new_years = datetime(2025, 1, 1, 15, 0, tzinfo=pytz.UTC)
        assert not is_business_day(new_years), "New Year's Day should NOT be a business day"

        # Test regular weekday (Tuesday)
        tuesday = datetime(2025, 1, 7, 15, 0, tzinfo=pytz.UTC)
        assert is_business_day(tuesday), "Tuesday should be a business day"
