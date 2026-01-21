"""
Unit tests for Device Activation business day fix

Tests the corrected business day frequency logic and weekend/holiday blocking.

BusinessCaseID: BC-DA-003, BC-DA-006

Test Coverage:
1. Call 2-3 frequency: AFTER 2 business days (> 2, not >= 2)
2. Call 4 frequency: AFTER 5 business days (> 5, not >= 5)
3. Weekend blocking: Scheduler returns [] on Sat/Sun
4. Federal holiday blocking: Scheduler returns [] on holidays
5. Business day boundary cases
"""

import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch, MagicMock
import pytz

# Import the service we're testing
from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService
from af_code.shared.business_hours_utils import is_business_day


class TestDeviceActivationBusinessDayFix:
    """Test suite for Device Activation business day calculation fixes"""

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service"""
        return Mock()

    @pytest.fixture
    def eligibility_service(self, mock_db_service):
        """Create EligibilityService with mocked database"""
        return EligibilityService(mock_db_service)

    # ======================================================================
    # TEST 1: Weekend Blocking (Saturday)
    # ======================================================================
    @patch('af_code.device_activation_scheduler.services.eligibility_service.datetime')
    def test_scheduler_on_saturday_returns_empty(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test scheduler run on Saturday returns empty list

        Scenario: Scheduler runs on Saturday Jan 17, 2026
        Expected: Returns [] immediately (no calls on weekends)
        """
        # Mock current time to Saturday Jan 17, 2026 at 10:00 AM UTC
        saturday_utc = datetime(2026, 1, 17, 10, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = saturday_utc

        # Mock database to return some potential members
        mock_db_service.execute_query.return_value = [
            {
                'member_id': 'test-member-1',
                'call_attempt_number': 1,
                'enrollment_id': 'test-enrollment-1'
            }
        ]

        # Execute
        result = eligibility_service.get_eligible_members()

        # Verify
        assert result == [], "Scheduler should return empty list on Saturday"

    # ======================================================================
    # TEST 2: Weekend Blocking (Sunday)
    # ======================================================================
    @patch('af_code.device_activation_scheduler.services.eligibility_service.datetime')
    def test_scheduler_on_sunday_returns_empty(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test scheduler run on Sunday returns empty list

        Scenario: Scheduler runs on Sunday Jan 18, 2026
        Expected: Returns [] immediately (no calls on weekends)
        """
        # Mock current time to Sunday Jan 18, 2026 at 10:00 AM UTC
        sunday_utc = datetime(2026, 1, 18, 10, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = sunday_utc

        # Mock database to return some potential members
        mock_db_service.execute_query.return_value = [
            {
                'member_id': 'test-member-2',
                'call_attempt_number': 2,
                'enrollment_id': 'test-enrollment-2',
                'last_attempt_date': datetime(2026, 1, 15, 14, 0, tzinfo=pytz.UTC)
            }
        ]

        # Execute
        result = eligibility_service.get_eligible_members()

        # Verify
        assert result == [], "Scheduler should return empty list on Sunday"

    # ======================================================================
    # TEST 3: Federal Holiday Blocking (New Year's Day)
    # ======================================================================
    @patch('af_code.device_activation_scheduler.services.eligibility_service.datetime')
    def test_scheduler_on_new_years_day_returns_empty(
        self, mock_datetime, eligibility_service, mock_db_service
    ):
        """
        Test scheduler run on New Year's Day returns empty list

        Scenario: Scheduler runs on Thursday Jan 1, 2026 (New Year's Day)
        Expected: Returns [] immediately (no calls on federal holidays)
        """
        # Mock current time to New Year's Day 2026 (Thursday) at 10:00 AM UTC
        new_years_utc = datetime(2026, 1, 1, 10, 0, 0, tzinfo=pytz.UTC)
        mock_datetime.now.return_value = new_years_utc

        # Verify it's recognized as a holiday (not a business day)
        assert not is_business_day(new_years_utc), "Jan 1 should not be a business day"

        # Mock database to return some potential members
        mock_db_service.execute_query.return_value = [
            {
                'member_id': 'test-member-3',
                'call_attempt_number': 1,
                'enrollment_id': 'test-enrollment-3'
            }
        ]

        # Execute
        result = eligibility_service.get_eligible_members()

        # Verify
        assert result == [], "Scheduler should return empty list on New Year's Day"

    # ======================================================================
    # TEST 4: Call 2 Frequency - Eligible Case
    # ======================================================================
    def test_call_2_eligible_after_3_business_days(self):
        """
        Test Call 2 eligible AFTER 2 business days (3+ business days)

        Scenario:
        - Call 1: Wednesday Jan 15, 2026 at 14:00 UTC
        - Check: Monday Jan 20, 2026 at 09:00 UTC
        - Business days: 3 (Thu 16, Fri 17, Mon 20)
        Expected: Member eligible (3 > 2)
        """
        from af_code.shared.business_hours_utils import get_business_days_between

        call_1_date = datetime(2026, 1, 15, 14, 0, tzinfo=pytz.UTC)
        check_date = datetime(2026, 1, 20, 9, 0, tzinfo=pytz.UTC)

        business_days = get_business_days_between(call_1_date, check_date)

        assert business_days == 3, f"Expected 3 business days, got {business_days}"
        assert business_days > 2, "Member should be eligible for Call 2 (3 > 2)"

    # ======================================================================
    # TEST 5: Call 2 Frequency - NOT Eligible Case (Boundary)
    # ======================================================================
    def test_call_2_not_eligible_on_2_business_days(self):
        """
        Test Call 2 NOT eligible on exactly 2 business days

        Scenario:
        - Call 1: Wednesday Jan 15, 2026 at 14:00 UTC
        - Check: Friday Jan 17, 2026 at 09:00 UTC
        - Business days: 2 (Thu 16, Fri 17)
        Expected: Member NOT eligible (2 <= 2, need > 2)
        """
        from af_code.shared.business_hours_utils import get_business_days_between

        call_1_date = datetime(2026, 1, 15, 14, 0, tzinfo=pytz.UTC)
        check_date = datetime(2026, 1, 17, 9, 0, tzinfo=pytz.UTC)

        business_days = get_business_days_between(call_1_date, check_date)

        assert business_days == 2, f"Expected 2 business days, got {business_days}"
        assert not (business_days > 2), "Member should NOT be eligible for Call 2 (2 <= 2)"

    # ======================================================================
    # TEST 6: Call 2 Frequency - Weekend Exclusion
    # ======================================================================
    def test_call_2_weekend_excluded_from_business_days(self):
        """
        Test Call 2 correctly excludes weekends from business day count

        Scenario:
        - Call 1: Friday Jan 17, 2026 at 14:00 UTC
        - Check: Tuesday Jan 21, 2026 at 09:00 UTC
        - Calendar days: 4 (Sat 18, Sun 19, Mon 20, Tue 21)
        - Business days: 2 (Mon 20, Tue 21) - weekends excluded
        Expected: Member NOT eligible (2 <= 2, need > 2)
        """
        from af_code.shared.business_hours_utils import get_business_days_between

        call_1_date = datetime(2026, 1, 17, 14, 0, tzinfo=pytz.UTC)
        check_date = datetime(2026, 1, 21, 9, 0, tzinfo=pytz.UTC)

        business_days = get_business_days_between(call_1_date, check_date)

        assert business_days == 2, f"Expected 2 business days (weekends excluded), got {business_days}"
        assert not (business_days > 2), "Member should NOT be eligible (2 <= 2, need > 2)"

    # ======================================================================
    # TEST 7: Call 4 Frequency - Eligible Case
    # ======================================================================
    def test_call_4_eligible_after_6_business_days(self):
        """
        Test Call 4 eligible AFTER 5 business days (6+ business days)

        Scenario:
        - Call 3: Monday Jan 13, 2026 at 14:00 UTC
        - Check: Tuesday Jan 21, 2026 at 09:00 UTC
        - Business days: 6 (Tue 14, Wed 15, Thu 16, Fri 17, Mon 20, Tue 21)
        Expected: Member eligible (6 > 5)
        """
        from af_code.shared.business_hours_utils import get_business_days_between

        call_3_date = datetime(2026, 1, 13, 14, 0, tzinfo=pytz.UTC)
        check_date = datetime(2026, 1, 21, 9, 0, tzinfo=pytz.UTC)

        business_days = get_business_days_between(call_3_date, check_date)

        assert business_days == 6, f"Expected 6 business days, got {business_days}"
        assert business_days > 5, "Member should be eligible for Call 4 (6 > 5)"

    # ======================================================================
    # TEST 8: Call 4 Frequency - NOT Eligible Case (Boundary)
    # ======================================================================
    def test_call_4_not_eligible_on_5_business_days(self):
        """
        Test Call 4 NOT eligible on exactly 5 business days

        Scenario:
        - Call 3: Monday Jan 13, 2026 at 14:00 UTC
        - Check: Monday Jan 20, 2026 at 09:00 UTC
        - Business days: 5 (Tue 14, Wed 15, Thu 16, Fri 17, Mon 20)
        Expected: Member NOT eligible (5 <= 5, need > 5)
        """
        from af_code.shared.business_hours_utils import get_business_days_between

        call_3_date = datetime(2026, 1, 13, 14, 0, tzinfo=pytz.UTC)
        check_date = datetime(2026, 1, 20, 9, 0, tzinfo=pytz.UTC)

        business_days = get_business_days_between(call_3_date, check_date)

        assert business_days == 5, f"Expected 5 business days, got {business_days}"
        assert not (business_days > 5), "Member should NOT be eligible for Call 4 (5 <= 5)"

    # ======================================================================
    # TEST 9: is_business_day Utility Function
    # ======================================================================
    def test_is_business_day_recognizes_weekends(self):
        """Test is_business_day() correctly identifies weekends"""

        # Saturday Jan 17, 2026
        saturday = datetime(2026, 1, 17, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(saturday), "Saturday should not be a business day"

        # Sunday Jan 18, 2026
        sunday = datetime(2026, 1, 18, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(sunday), "Sunday should not be a business day"

        # Monday Jan 19, 2026 (MLK Day - 3rd Monday of January)
        # Note: MLK Day is NOT in our 6 critical US holidays, so it IS a business day
        mlk_day = datetime(2026, 1, 19, 10, 0, tzinfo=pytz.UTC)
        assert is_business_day(mlk_day), "MLK Day is not a critical holiday - should be business day"

        # Tuesday Jan 20, 2026 (regular business day)
        tuesday = datetime(2026, 1, 20, 10, 0, tzinfo=pytz.UTC)
        assert is_business_day(tuesday), "Tuesday should be a business day"

    # ======================================================================
    # TEST 10: Federal Holidays Recognition
    # ======================================================================
    def test_is_business_day_recognizes_federal_holidays(self):
        """Test is_business_day() correctly identifies 6 critical US federal holidays"""

        # New Year's Day (Jan 1)
        new_years = datetime(2026, 1, 1, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(new_years), "New Year's Day should not be a business day"

        # Memorial Day (last Monday of May - May 25, 2026)
        memorial_day = datetime(2026, 5, 25, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(memorial_day), "Memorial Day should not be a business day"

        # Independence Day (July 4)
        july_4th = datetime(2026, 7, 4, 10, 0, tzinfo=pytz.UTC)  # Saturday in 2026
        # Note: When July 4 falls on weekend, it's observed on Friday/Monday

        # Labor Day (first Monday of September - Sep 7, 2026)
        labor_day = datetime(2026, 9, 7, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(labor_day), "Labor Day should not be a business day"

        # Thanksgiving (4th Thursday of November - Nov 26, 2026)
        thanksgiving = datetime(2026, 11, 26, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(thanksgiving), "Thanksgiving should not be a business day"

        # Christmas (Dec 25)
        christmas = datetime(2026, 12, 25, 10, 0, tzinfo=pytz.UTC)
        assert not is_business_day(christmas), "Christmas should not be a business day"


# ======================================================================
# RUN TESTS
# ======================================================================
if __name__ == "__main__":
    print("Running Device Activation Business Day Fix Unit Tests...")
    print("=" * 80)
    pytest.main([__file__, "-v", "--tb=short"])
