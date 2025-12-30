"""
Unit tests for business_hours_utils.py

Tests holiday detection, business day calculations, and dual-timezone business hours validation.

BusinessCaseID: BC-TBD (Device Activation System)
"""

import pytest
from datetime import datetime, timedelta
import pytz
from af_code.shared.business_hours_utils import (
    BusinessHoursValidator,
    is_business_day,
    add_business_days,
    can_make_call,
    get_next_valid_call_time,
    get_business_days_between
)


class TestHolidayDetection:
    """Test US federal holiday detection"""

    def test_christmas_is_holiday(self):
        """Test that Christmas Day is detected as a holiday"""
        christmas = datetime(2025, 12, 25, 10, 0, tzinfo=pytz.UTC)
        assert not BusinessHoursValidator.is_business_day(christmas)

    def test_thanksgiving_is_holiday(self):
        """Test that Thanksgiving is detected as a holiday"""
        # Thanksgiving 2025: Thursday, November 27
        thanksgiving = datetime(2025, 11, 27, 10, 0, tzinfo=pytz.UTC)
        assert not BusinessHoursValidator.is_business_day(thanksgiving)

    def test_new_years_is_holiday(self):
        """Test that New Year's Day is detected as a holiday"""
        new_years = datetime(2025, 1, 1, 10, 0, tzinfo=pytz.UTC)
        assert not BusinessHoursValidator.is_business_day(new_years)

    def test_independence_day_is_holiday(self):
        """Test that Independence Day is detected as a holiday"""
        july_4th = datetime(2025, 7, 4, 10, 0, tzinfo=pytz.UTC)
        assert not BusinessHoursValidator.is_business_day(july_4th)

    def test_regular_tuesday_not_holiday(self):
        """Test that a regular Tuesday is NOT a holiday"""
        regular_tuesday = datetime(2025, 6, 10, 10, 0, tzinfo=pytz.UTC)
        assert BusinessHoursValidator.is_business_day(regular_tuesday)


class TestWeekendDetection:
    """Test weekend detection"""

    def test_saturday_not_business_day(self):
        """Test that Saturday is not a business day"""
        saturday = datetime(2025, 1, 11, 10, 0, tzinfo=pytz.UTC)  # Saturday
        assert not BusinessHoursValidator.is_business_day(saturday)

    def test_sunday_not_business_day(self):
        """Test that Sunday is not a business day"""
        sunday = datetime(2025, 1, 12, 10, 0, tzinfo=pytz.UTC)  # Sunday
        assert not BusinessHoursValidator.is_business_day(sunday)

    def test_monday_is_business_day(self):
        """Test that Monday is a business day (when not a holiday)"""
        monday = datetime(2025, 1, 6, 10, 0, tzinfo=pytz.UTC)  # Monday, not a holiday
        assert BusinessHoursValidator.is_business_day(monday)

    def test_friday_is_business_day(self):
        """Test that Friday is a business day (when not a holiday)"""
        friday = datetime(2025, 1, 10, 10, 0, tzinfo=pytz.UTC)  # Friday, not a holiday
        assert BusinessHoursValidator.is_business_day(friday)


class TestBusinessDayAddition:
    """Test adding business days with weekend and holiday skipping"""

    def test_add_2_business_days_from_friday(self):
        """Test adding 2 business days from Friday skips weekend"""
        # Friday, January 3, 2025
        friday = datetime(2025, 1, 3, 10, 0, tzinfo=pytz.UTC)
        result = BusinessHoursValidator.add_business_days(friday, 2)

        # Should be Tuesday, January 7 (skip weekend)
        expected = datetime(2025, 1, 7, 10, 0, tzinfo=pytz.UTC)
        assert result.date() == expected.date()

    def test_add_1_business_day_before_christmas(self):
        """Test adding 1 business day from Dec 24 skips Christmas"""
        # Wednesday, December 24, 2025 (day before Christmas)
        dec_24 = datetime(2025, 12, 24, 10, 0, tzinfo=pytz.UTC)
        result = BusinessHoursValidator.add_business_days(dec_24, 1)

        # Should be Friday, December 26 (skip Christmas Dec 25)
        expected = datetime(2025, 12, 26, 10, 0, tzinfo=pytz.UTC)
        assert result.date() == expected.date()

    def test_add_5_business_days_with_holiday(self):
        """Test adding 5 business days with holiday in between"""
        # Monday, November 24, 2025 (before Thanksgiving)
        nov_24 = datetime(2025, 11, 24, 10, 0, tzinfo=pytz.UTC)
        result = BusinessHoursValidator.add_business_days(nov_24, 5)

        # Should skip:
        # - Weekend (Nov 29-30)
        # - Thanksgiving (Nov 27)
        # Expected: Monday, December 1, 2025
        expected = datetime(2025, 12, 1, 10, 0, tzinfo=pytz.UTC)
        assert result.date() == expected.date()

    def test_add_0_business_days(self):
        """Test adding 0 business days returns same date"""
        start = datetime(2025, 1, 6, 10, 0, tzinfo=pytz.UTC)
        result = BusinessHoursValidator.add_business_days(start, 0)
        assert result.date() == start.date()


class TestBusinessDaysBetween:
    """Test calculating business days between two dates (Device Activation Call 2-4 frequency)"""

    def test_friday_to_monday_weekend(self):
        """Test Friday to Monday (weekend): 1 business day (Friday)"""
        # Friday 5 PM to Monday 9 AM - skip weekend, count Friday
        friday = datetime(2025, 1, 3, 22, 0, tzinfo=pytz.UTC)  # Friday 5 PM EST
        monday = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)  # Monday 9 AM EST

        result = get_business_days_between(friday, monday)
        assert result == 1  # Friday counts, weekend doesn't

    def test_monday_to_wednesday(self):
        """Test Monday to Wednesday: 2 business days (Mon, Tue)"""
        monday = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)
        wednesday = datetime(2025, 1, 8, 14, 0, tzinfo=pytz.UTC)

        result = get_business_days_between(monday, wednesday)
        assert result == 2  # Monday and Tuesday

    def test_monday_to_next_monday(self):
        """Test Monday to next Monday: 5 business days"""
        monday1 = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)
        monday2 = datetime(2025, 1, 13, 14, 0, tzinfo=pytz.UTC)

        result = get_business_days_between(monday1, monday2)
        assert result == 5  # Mon, Tue, Wed, Thu, Fri

    def test_same_day(self):
        """Test same day: 0 business days"""
        same_day_morning = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)
        same_day_evening = datetime(2025, 1, 6, 22, 0, tzinfo=pytz.UTC)

        result = get_business_days_between(same_day_morning, same_day_evening)
        assert result == 0

    def test_skip_christmas_holiday(self):
        """Test skipping Christmas holiday"""
        dec_24 = datetime(2025, 12, 24, 14, 0, tzinfo=pytz.UTC)
        dec_26 = datetime(2025, 12, 26, 14, 0, tzinfo=pytz.UTC)

        result = get_business_days_between(dec_24, dec_26)
        assert result == 1  # Only Dec 24 (skip Christmas Dec 25)

    def test_skip_thanksgiving_and_weekend(self):
        """Test skipping Thanksgiving and weekend"""
        # Monday Nov 24 to Monday Dec 1
        nov_24 = datetime(2025, 11, 24, 14, 0, tzinfo=pytz.UTC)
        dec_1 = datetime(2025, 12, 1, 14, 0, tzinfo=pytz.UTC)

        result = get_business_days_between(nov_24, dec_1)
        # Mon 24, Tue 25, Wed 26, skip Thu 27 (Thanksgiving), Fri 28, skip weekend
        assert result == 4  # 24, 25, 26, 28

    def test_call_2_frequency_2_business_days(self):
        """Test Call 2 frequency: 2 business days requirement"""
        # Simulate: Last call Friday 2 PM, check Tuesday 9 AM
        last_call = datetime(2025, 1, 3, 19, 0, tzinfo=pytz.UTC)  # Friday 2 PM EST
        now = datetime(2025, 1, 7, 14, 0, tzinfo=pytz.UTC)  # Tuesday 9 AM EST

        result = get_business_days_between(last_call, now)
        assert result >= 2  # At least 2 business days (Fri, Mon)

    def test_call_4_frequency_5_business_days(self):
        """Test Call 4 frequency: 5 business days requirement"""
        last_call = datetime(2025, 1, 6, 19, 0, tzinfo=pytz.UTC)  # Monday 2 PM EST
        now = datetime(2025, 1, 13, 14, 0, tzinfo=pytz.UTC)  # Next Monday 9 AM EST

        result = get_business_days_between(last_call, now)
        assert result >= 5  # At least 5 business days

    def test_new_years_holiday_skip(self):
        """Test skipping New Year's Day (Jan 1)"""
        dec_31 = datetime(2024, 12, 31, 14, 0, tzinfo=pytz.UTC)  # Tuesday
        jan_2 = datetime(2025, 1, 2, 14, 0, tzinfo=pytz.UTC)  # Thursday

        result = get_business_days_between(dec_31, jan_2)
        assert result == 1  # Only Dec 31 (skip Jan 1 holiday)


class TestBusinessHoursValidation:
    """Test business hours validation for single timezone"""

    def test_10am_est_within_business_hours(self):
        """Test 10 AM EST is within business hours"""
        est_tz = pytz.timezone('America/New_York')
        time_10am = datetime(2025, 1, 6, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST

        assert BusinessHoursValidator.is_within_business_hours(time_10am, est_tz)

    def test_6pm_est_outside_business_hours(self):
        """Test 6 PM EST is outside business hours"""
        est_tz = pytz.timezone('America/New_York')
        time_6pm = datetime(2025, 1, 6, 23, 0, tzinfo=pytz.UTC)  # 6 PM EST

        assert not BusinessHoursValidator.is_within_business_hours(time_6pm, est_tz)

    def test_8am_est_outside_business_hours(self):
        """Test 8 AM EST is outside business hours (before 9 AM)"""
        est_tz = pytz.timezone('America/New_York')
        time_8am = datetime(2025, 1, 6, 13, 0, tzinfo=pytz.UTC)  # 8 AM EST

        assert not BusinessHoursValidator.is_within_business_hours(time_8am, est_tz)

    def test_9am_est_within_business_hours(self):
        """Test 9 AM EST is within business hours (start of day)"""
        est_tz = pytz.timezone('America/New_York')
        time_9am = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)  # 9 AM EST

        assert BusinessHoursValidator.is_within_business_hours(time_9am, est_tz)

    def test_4_59pm_est_within_business_hours(self):
        """Test 4:59 PM EST is within business hours (before 5 PM cutoff)"""
        est_tz = pytz.timezone('America/New_York')
        time_4_59pm = datetime(2025, 1, 6, 21, 59, tzinfo=pytz.UTC)  # 4:59 PM EST

        assert BusinessHoursValidator.is_within_business_hours(time_4_59pm, est_tz)


class TestDualTimezoneValidation:
    """Test dual-timezone business hours validation (MG EST + Member TZ)"""

    def test_valid_call_member_in_est(self):
        """Test valid call: 2 PM EST, member in EST"""
        call_time = datetime(2025, 1, 6, 19, 0, tzinfo=pytz.UTC)  # 2 PM EST, Monday
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call
        assert "Call allowed" in reason

    def test_invalid_call_outside_mg_hours(self):
        """Test invalid call: 6 PM EST (outside MG hours), member in EST"""
        call_time = datetime(2025, 1, 6, 23, 0, tzinfo=pytz.UTC)  # 6 PM EST, Monday
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call
        assert "Medical Guardian business hours" in reason

    def test_invalid_call_too_early_for_member_pst(self):
        """Test invalid: 9 AM EST (6 AM PST - too early for member)"""
        call_time = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)  # 9 AM EST = 6 AM PST, Monday
        member_tz = pytz.timezone('America/Los_Angeles')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call
        assert "member business hours" in reason

    def test_valid_call_member_in_pst(self):
        """Test valid call: 12 PM EST (9 AM PST), member in PST"""
        call_time = datetime(2025, 1, 6, 17, 0, tzinfo=pytz.UTC)  # 12 PM EST = 9 AM PST, Monday
        member_tz = pytz.timezone('America/Los_Angeles')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call
        assert "Call allowed" in reason

    def test_valid_call_member_in_cst(self):
        """Test valid call: 2 PM EST (1 PM CST), member in CST"""
        call_time = datetime(2025, 1, 6, 19, 0, tzinfo=pytz.UTC)  # 2 PM EST = 1 PM CST, Monday
        member_tz = pytz.timezone('America/Chicago')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call
        assert "Call allowed" in reason

    def test_invalid_call_weekend(self):
        """Test invalid call: Saturday (weekend)"""
        call_time = datetime(2025, 1, 11, 17, 0, tzinfo=pytz.UTC)  # Saturday
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call
        assert "not a business day" in reason

    def test_invalid_call_holiday(self):
        """Test invalid call: Christmas Day (federal holiday)"""
        call_time = datetime(2025, 12, 25, 17, 0, tzinfo=pytz.UTC)  # Christmas
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call
        assert "not a business day" in reason


class TestNextValidCallTime:
    """Test finding next valid call time"""

    def test_friday_evening_to_monday_morning(self):
        """Test Friday 6 PM → next valid is Monday 10 AM"""
        # Friday 6 PM EST
        current = datetime(2025, 1, 3, 23, 0, tzinfo=pytz.UTC)
        member_tz = pytz.timezone('America/New_York')

        next_time = BusinessHoursValidator.get_next_valid_call_time(current, member_tz, preferred_hour=10)

        # Should be Monday 10 AM EST
        assert next_time.astimezone(member_tz).weekday() == 0  # Monday
        assert next_time.astimezone(member_tz).hour == 10

    def test_before_holiday_to_after_holiday(self):
        """Test day before Christmas → next valid is day after Christmas"""
        # Wednesday Dec 24, 6 PM EST (after hours)
        current = datetime(2025, 12, 24, 23, 0, tzinfo=pytz.UTC)
        member_tz = pytz.timezone('America/New_York')

        next_time = BusinessHoursValidator.get_next_valid_call_time(current, member_tz, preferred_hour=10)

        # Should skip Christmas Dec 25 and go to Friday Dec 26 at 10 AM
        expected_date = datetime(2025, 12, 26).date()
        assert next_time.astimezone(member_tz).date() == expected_date
        assert next_time.astimezone(member_tz).hour == 10

    def test_early_morning_to_business_hours_same_day(self):
        """Test 7 AM Tuesday → next valid is 10 AM same day"""
        # Tuesday 7 AM EST (before business hours)
        current = datetime(2025, 1, 7, 12, 0, tzinfo=pytz.UTC)
        member_tz = pytz.timezone('America/New_York')

        next_time = BusinessHoursValidator.get_next_valid_call_time(current, member_tz, preferred_hour=10)

        # Should be same day at 10 AM
        assert next_time.astimezone(member_tz).date() == datetime(2025, 1, 7).date()
        assert next_time.astimezone(member_tz).hour == 10

    def test_member_pst_timezone_overlap(self):
        """Test finding valid time for PST member respecting timezone overlap"""
        # Current: Monday 8 AM EST = 5 AM PST (too early for PST member)
        current = datetime(2025, 1, 6, 13, 0, tzinfo=pytz.UTC)
        member_tz = pytz.timezone('America/Los_Angeles')

        next_time = BusinessHoursValidator.get_next_valid_call_time(current, member_tz, preferred_hour=9)

        # Should be Monday 9 AM PST = 12 PM EST
        local_time = next_time.astimezone(member_tz)
        assert local_time.hour >= 9  # At least 9 AM PST
        assert local_time.hour < 17  # Before 5 PM PST


class TestFederalHolidaysList:
    """Test federal holidays list retrieval"""

    def test_get_2025_federal_holidays(self):
        """Test retrieving 2025 federal holidays"""
        holidays_2025 = BusinessHoursValidator.get_federal_holidays(2025)

        # Check we have holidays
        assert len(holidays_2025) > 0

        # Check specific holidays exist
        assert datetime(2025, 1, 1).date() in holidays_2025  # New Year's
        assert datetime(2025, 7, 4).date() in holidays_2025  # Independence Day
        assert datetime(2025, 12, 25).date() in holidays_2025  # Christmas

    def test_holiday_has_name(self):
        """Test that holidays have names"""
        holidays_2025 = BusinessHoursValidator.get_federal_holidays(2025)

        christmas = datetime(2025, 12, 25).date()
        assert "Christmas" in holidays_2025[christmas]


class TestConvenienceFunctions:
    """Test convenience wrapper functions"""

    def test_convenience_is_business_day(self):
        """Test convenience function is_business_day()"""
        monday = datetime(2025, 1, 6, 10, 0, tzinfo=pytz.UTC)
        assert is_business_day(monday)

    def test_convenience_add_business_days(self):
        """Test convenience function add_business_days()"""
        start = datetime(2025, 1, 3, 10, 0, tzinfo=pytz.UTC)  # Friday
        result = add_business_days(start, 2)

        # Should be Tuesday
        assert result.date() == datetime(2025, 1, 7).date()

    def test_convenience_can_make_call(self):
        """Test convenience function can_make_call()"""
        call_time = datetime(2025, 1, 6, 19, 0, tzinfo=pytz.UTC)  # 2 PM EST
        member_tz = pytz.timezone('America/New_York')

        can_call_result, reason = can_make_call(call_time, member_tz)
        assert can_call_result

    def test_convenience_get_next_valid_call_time(self):
        """Test convenience function get_next_valid_call_time()"""
        current = datetime(2025, 1, 3, 23, 0, tzinfo=pytz.UTC)  # Friday evening
        member_tz = pytz.timezone('America/New_York')

        next_time = get_next_valid_call_time(current, member_tz)

        # Should be Monday
        assert next_time.astimezone(member_tz).weekday() == 0


class TestBusinessHoursDualTimezone:
    """Test dual-timezone validation: MG 9AM-4PM EST, Member 9AM-4PM local"""

    def test_3_30pm_est_member_in_est_valid(self):
        """Test 3:30 PM EST for EST member - valid for both (within 9-4 EST)"""
        call_time = datetime(2025, 1, 6, 20, 30, tzinfo=pytz.UTC)  # 3:30 PM EST, Monday
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call
        assert "Call allowed" in reason

    def test_4pm_est_member_in_est_invalid(self):
        """Test 4:00 PM EST for EST member - invalid (at cutoff, hour=16)"""
        call_time = datetime(2025, 1, 6, 21, 0, tzinfo=pytz.UTC)  # 4:00 PM EST, Monday
        member_tz = pytz.timezone('America/New_York')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call  # hour=16 fails (< 16 check)
        assert "business hours" in reason

    def test_12pm_est_member_in_pst_valid(self):
        """Test 12 PM EST (9 AM PST) for PST member - valid start of window"""
        call_time = datetime(2025, 1, 6, 17, 0, tzinfo=pytz.UTC)  # 12 PM EST = 9 AM PST
        member_tz = pytz.timezone('America/Los_Angeles')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call  # MG: 12 PM EST valid, Member: 9 AM PST valid
        assert "Call allowed" in reason

    def test_4pm_est_member_in_pst_invalid(self):
        """Test 4 PM EST (1 PM PST) for PST member - invalid (MG cutoff, member OK)"""
        call_time = datetime(2025, 1, 6, 21, 0, tzinfo=pytz.UTC)  # 4 PM EST = 1 PM PST
        member_tz = pytz.timezone('America/Los_Angeles')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call  # MG cutoff at 4 PM EST (member local 1 PM PST is OK)
        assert "Medical Guardian business hours" in reason

    def test_10am_est_member_in_cst_valid(self):
        """Test 10 AM EST (9 AM CST) for CST member - valid start of window"""
        call_time = datetime(2025, 1, 6, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST = 9 AM CST
        member_tz = pytz.timezone('America/Chicago')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert can_call  # MG: 10 AM EST valid, Member: 9 AM CST valid
        assert "Call allowed" in reason

    def test_9am_est_member_in_cst_invalid_member_early(self):
        """Test 9 AM EST (8 AM CST) for CST member - invalid (member too early)"""
        call_time = datetime(2025, 1, 6, 14, 0, tzinfo=pytz.UTC)  # 9 AM EST = 8 AM CST
        member_tz = pytz.timezone('America/Chicago')

        can_call, reason = BusinessHoursValidator.can_make_call(call_time, member_tz)
        assert not can_call  # Member local 8 AM CST is before 9 AM
        assert "member business hours" in reason


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
