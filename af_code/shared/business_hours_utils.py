"""
Business Hours and Holiday Management Utility

This module handles:
1. US federal holiday detection
2. Business day calculations (excluding weekends and holidays)
3. Dual-timezone business hours validation (Member timezone + Medical Guardian EST)
4. Call scheduling within valid business hours

BusinessCaseID: BC-TBD (Device Activation System)

Dependencies:
- holidays: US federal holiday calendar
- pytz: Timezone handling
- datetime: Date/time operations
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Tuple
import pytz
import holidays

logger = logging.getLogger(__name__)


class BusinessHoursValidator:
    """
    Validates business hours and holidays for IOE call scheduling

    Medical Guardian operates in EST timezone with business hours 9 AM - 4 PM EST.
    Members can be in any US timezone.

    Calls can only be made when:
    1. It's a business day (Mon-Fri, not a federal holiday)
    2. It's within Medical Guardian business hours (9 AM - 4 PM EST)
    3. It's within member's local business hours (9 AM - 5 PM member timezone)
    4. Both timezones overlap in their business hours
    """

    # Medical Guardian operates in Eastern Time
    MG_TIMEZONE = pytz.timezone('America/New_York')

    # Business hours (9 AM - 4 PM for MG, 9 AM - 5 PM for members)
    BUSINESS_START_HOUR = 9  # 9:00 AM
    BUSINESS_END_HOUR = 16   # 4:00 PM (Medical Guardian end time)

    # US Federal Holidays (automatically includes all federal holidays)
    US_HOLIDAYS = holidays.US(observed=True)  # observed=True handles holidays that fall on weekends

    @classmethod
    def is_business_day(cls, check_date: datetime) -> bool:
        """
        Check if a date is a business day (Mon-Fri, not a federal holiday)

        Args:
            check_date: Datetime to check (timezone-aware)

        Returns:
            bool: True if business day, False if weekend or holiday

        Examples:
            >>> # Monday, not a holiday
            >>> is_business_day(datetime(2025, 1, 6, tzinfo=pytz.UTC))
            True

            >>> # Saturday
            >>> is_business_day(datetime(2025, 1, 11, tzinfo=pytz.UTC))
            False

            >>> # Christmas Day (federal holiday)
            >>> is_business_day(datetime(2025, 12, 25, tzinfo=pytz.UTC))
            False
        """
        # Check if weekend (Saturday=5, Sunday=6)
        if check_date.weekday() >= 5:
            logger.debug(f"📅 [BUSINESS-HOURS] {check_date.date()} is a weekend")
            return False

        # Check if federal holiday
        if check_date.date() in cls.US_HOLIDAYS:
            holiday_name = cls.US_HOLIDAYS.get(check_date.date())
            logger.debug(f"🎉 [BUSINESS-HOURS] {check_date.date()} is a federal holiday: {holiday_name}")
            return False

        logger.debug(f"✅ [BUSINESS-HOURS] {check_date.date()} is a business day")
        return True

    @classmethod
    def add_business_days(cls, start_date: datetime, num_days: int) -> datetime:
        """
        Add business days to a date, skipping weekends and federal holidays

        Args:
            start_date: Starting datetime (timezone-aware)
            num_days: Number of business days to add

        Returns:
            datetime: New date after adding business days

        Examples:
            >>> # Add 2 business days from Friday
            >>> start = datetime(2025, 1, 3, 10, 0, tzinfo=pytz.UTC)  # Friday
            >>> result = add_business_days(start, 2)
            >>> result.date()  # Should be Tuesday (skipping weekend)
            datetime.date(2025, 1, 7)

            >>> # Add 1 business day before a holiday
            >>> start = datetime(2025, 12, 24, 10, 0, tzinfo=pytz.UTC)  # Wednesday before Christmas
            >>> result = add_business_days(start, 1)
            >>> result.date()  # Should skip Christmas Day
            datetime.date(2025, 12, 26)
        """
        current_date = start_date
        days_added = 0

        while days_added < num_days:
            current_date += timedelta(days=1)

            if cls.is_business_day(current_date):
                days_added += 1
                logger.debug(f"➕ [BUSINESS-HOURS] Added business day {days_added}/{num_days}: {current_date.date()}")
            else:
                logger.debug(f"⏭️ [BUSINESS-HOURS] Skipped non-business day: {current_date.date()}")

        logger.info(f"📅 [BUSINESS-HOURS] Added {num_days} business days: {start_date.date()} → {current_date.date()}")
        return current_date

    @classmethod
    def is_within_business_hours(cls, check_time: datetime, timezone: pytz.tzinfo.BaseTzInfo) -> bool:
        """
        Check if a datetime is within business hours (9 AM - 5 PM) in a specific timezone

        Args:
            check_time: Datetime to check (timezone-aware)
            timezone: Timezone to check against

        Returns:
            bool: True if within business hours, False otherwise

        Examples:
            >>> # 10 AM EST
            >>> dt = datetime(2025, 1, 6, 10, 0, tzinfo=pytz.timezone('America/New_York'))
            >>> is_within_business_hours(dt, pytz.timezone('America/New_York'))
            True

            >>> # 6 PM EST (after hours)
            >>> dt = datetime(2025, 1, 6, 18, 0, tzinfo=pytz.timezone('America/New_York'))
            >>> is_within_business_hours(dt, pytz.timezone('America/New_York'))
            False
        """
        # Convert to target timezone
        local_time = check_time.astimezone(timezone)
        hour = local_time.hour

        is_valid = cls.BUSINESS_START_HOUR <= hour < cls.BUSINESS_END_HOUR

        logger.debug(
            f"🕐 [BUSINESS-HOURS] Time check: {local_time.strftime('%Y-%m-%d %H:%M %Z')} "
            f"({'✅' if is_valid else '❌'} valid for business hours {cls.BUSINESS_START_HOUR}:00-{cls.BUSINESS_END_HOUR}:00)"
        )

        return is_valid

    @classmethod
    def can_make_call(
        cls,
        call_time: datetime,
        member_timezone: pytz.tzinfo.BaseTzInfo
    ) -> Tuple[bool, str]:
        """
        Validate if a call can be made at a specific time considering:
        1. Must be a business day (not weekend or holiday)
        2. Must be within Medical Guardian business hours (9 AM - 4 PM EST)
        3. Must be within member's local business hours (9 AM - 5 PM member TZ)

        Args:
            call_time: Proposed call datetime (timezone-aware, typically UTC)
            member_timezone: Member's timezone (pytz object)

        Returns:
            Tuple[bool, str]: (can_call, reason)
                - can_call: True if call is allowed, False otherwise
                - reason: Explanation of validation result

        Examples:
            >>> # Valid call: Monday 10 AM EST, member in EST
            >>> call_time = datetime(2025, 1, 6, 15, 0, tzinfo=pytz.UTC)  # 10 AM EST
            >>> member_tz = pytz.timezone('America/New_York')
            >>> can_make_call(call_time, member_tz)
            (True, "Call allowed - within both MG and member business hours")

            >>> # Invalid: Weekend
            >>> call_time = datetime(2025, 1, 11, 15, 0, tzinfo=pytz.UTC)  # Saturday
            >>> can_make_call(call_time, member_tz)
            (False, "Call blocked - not a business day (weekend or holiday)")

            >>> # Invalid: Outside MG business hours
            >>> call_time = datetime(2025, 1, 6, 21, 0, tzinfo=pytz.UTC)  # 4 PM EST
            >>> can_make_call(call_time, member_tz)
            (False, "Call blocked - outside Medical Guardian business hours (9 AM - 4 PM EST)")
        """
        # Convert to UTC if not already
        if call_time.tzinfo is None:
            logger.warning("⚠️ [BUSINESS-HOURS] Naive datetime provided, assuming UTC")
            call_time = pytz.UTC.localize(call_time)

        # Check 1: Business day validation
        if not cls.is_business_day(call_time):
            return (False, "Call blocked - not a business day (weekend or holiday)")

        # Check 2: Medical Guardian business hours (EST)
        mg_time = call_time.astimezone(cls.MG_TIMEZONE)
        if not cls.is_within_business_hours(call_time, cls.MG_TIMEZONE):
            return (
                False,
                f"Call blocked - outside Medical Guardian business hours "
                f"(9 AM - 4 PM EST, current time: {mg_time.strftime('%I:%M %p %Z')})"
            )

        # Check 3: Member business hours (member's local timezone)
        member_time = call_time.astimezone(member_timezone)
        if not cls.is_within_business_hours(call_time, member_timezone):
            return (
                False,
                f"Call blocked - outside member business hours "
                f"(9 AM - 5 PM {member_timezone.zone}, member local time: {member_time.strftime('%I:%M %p %Z')})"
            )

        # All checks passed
        logger.info(
            f"✅ [BUSINESS-HOURS] Call allowed at {mg_time.strftime('%Y-%m-%d %I:%M %p %Z')} "
            f"(Member time: {member_time.strftime('%I:%M %p %Z')})"
        )

        return (
            True,
            f"Call allowed - within both MG and member business hours "
            f"(MG: {mg_time.strftime('%I:%M %p %Z')}, Member: {member_time.strftime('%I:%M %p %Z')})"
        )

    @classmethod
    def get_next_valid_call_time(
        cls,
        current_time: datetime,
        member_timezone: pytz.tzinfo.BaseTzInfo,
        preferred_hour: int = 10  # Default to 10 AM
    ) -> datetime:
        """
        Find the next valid call time considering business days, holidays, and business hours

        Args:
            current_time: Current datetime (timezone-aware)
            member_timezone: Member's timezone
            preferred_hour: Preferred hour to call (24-hour format, default 10 = 10 AM)

        Returns:
            datetime: Next valid call time (timezone-aware UTC)

        Examples:
            >>> # Current time: Friday 6 PM EST, should return Monday 10 AM EST
            >>> current = datetime(2025, 1, 3, 23, 0, tzinfo=pytz.UTC)  # Friday 6 PM EST
            >>> member_tz = pytz.timezone('America/New_York')
            >>> next_time = get_next_valid_call_time(current, member_tz, preferred_hour=10)
            >>> next_time.astimezone(member_tz).strftime('%A %I:%M %p')
            'Monday 10:00 AM'
        """
        # Ensure preferred_hour is within business hours
        if preferred_hour < cls.BUSINESS_START_HOUR or preferred_hour >= cls.BUSINESS_END_HOUR:
            logger.warning(
                f"⚠️ [BUSINESS-HOURS] Preferred hour {preferred_hour} outside business hours, "
                f"defaulting to {cls.BUSINESS_START_HOUR + 1}"
            )
            preferred_hour = cls.BUSINESS_START_HOUR + 1  # 10 AM

        # Start checking from current time
        check_time = current_time
        max_attempts = 30  # Prevent infinite loop (check up to 30 days ahead)
        attempts = 0

        while attempts < max_attempts:
            attempts += 1

            # Move to next day if we're past business hours today
            member_time = check_time.astimezone(member_timezone)
            if member_time.hour >= cls.BUSINESS_END_HOUR:
                # Move to next day at preferred hour
                check_time = member_timezone.localize(
                    datetime.combine(
                        member_time.date() + timedelta(days=1),
                        time(hour=preferred_hour, minute=0)
                    )
                ).astimezone(pytz.UTC)
            elif member_time.hour < cls.BUSINESS_START_HOUR:
                # Move to today at preferred hour
                check_time = member_timezone.localize(
                    datetime.combine(
                        member_time.date(),
                        time(hour=preferred_hour, minute=0)
                    )
                ).astimezone(pytz.UTC)

            # Check if this time is valid
            can_call, reason = cls.can_make_call(check_time, member_timezone)
            if can_call:
                logger.info(f"✅ [BUSINESS-HOURS] Found next valid call time: {check_time}")
                return check_time

            # Not valid, try next day
            logger.debug(f"⏭️ [BUSINESS-HOURS] {check_time.date()} not valid ({reason}), trying next day")
            check_time += timedelta(days=1)

        # Fallback: return time 1 business day from now at preferred hour
        logger.warning(f"⚠️ [BUSINESS-HOURS] Could not find valid time in {max_attempts} days, using fallback")
        fallback = cls.add_business_days(current_time, 1)
        return member_timezone.localize(
            datetime.combine(fallback.date(), time(hour=preferred_hour, minute=0))
        ).astimezone(pytz.UTC)

    @classmethod
    def get_federal_holidays(cls, year: int) -> dict:
        """
        Get all US federal holidays for a specific year

        Args:
            year: Year to get holidays for

        Returns:
            dict: {date: holiday_name}

        Examples:
            >>> holidays_2025 = get_federal_holidays(2025)
            >>> holidays_2025[datetime.date(2025, 7, 4)]
            'Independence Day'
        """
        return {date: name for date, name in holidays.US(years=year, observed=True).items()}

    @classmethod
    def log_holiday_info(cls, start_date: datetime, end_date: datetime) -> None:
        """
        Log all holidays between two dates for debugging/planning purposes

        Args:
            start_date: Start date
            end_date: End date
        """
        logger.info(f"🎉 [BUSINESS-HOURS] Federal holidays between {start_date.date()} and {end_date.date()}:")

        current = start_date
        while current <= end_date:
            if current.date() in cls.US_HOLIDAYS:
                holiday_name = cls.US_HOLIDAYS.get(current.date())
                logger.info(f"   📅 {current.date()} ({current.strftime('%A')}): {holiday_name}")
            current += timedelta(days=1)


# Convenience functions for backward compatibility
def is_business_day(check_date: datetime) -> bool:
    """Check if a date is a business day"""
    return BusinessHoursValidator.is_business_day(check_date)


def add_business_days(start_date: datetime, num_days: int) -> datetime:
    """Add business days to a date"""
    return BusinessHoursValidator.add_business_days(start_date, num_days)


def can_make_call(call_time: datetime, member_timezone: pytz.tzinfo.BaseTzInfo) -> Tuple[bool, str]:
    """Validate if a call can be made at a specific time"""
    return BusinessHoursValidator.can_make_call(call_time, member_timezone)


def get_next_valid_call_time(
    current_time: datetime,
    member_timezone: pytz.tzinfo.BaseTzInfo,
    preferred_hour: int = 10
) -> datetime:
    """Find the next valid call time"""
    return BusinessHoursValidator.get_next_valid_call_time(current_time, member_timezone, preferred_hour)
