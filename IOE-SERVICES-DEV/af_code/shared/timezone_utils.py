"""
Timezone utility for converting between different timezone naming conventions

Supports conversion between:
1. SQL Server abbreviations (EST, CST, MST, PST)
2. IANA timezone names (America/New_York, America/Chicago, etc.) - Used in members.timezone
3. SQL Server Windows timezone names (Eastern Standard Time, etc.) - Used in AT TIME ZONE clause
4. pytz timezone objects
"""

import pytz
import logging

logger = logging.getLogger(__name__)


class TimezoneConverter:
    """
    Centralized timezone conversion for IOE system

    Database Fields:
    - members.timezone: IANA format (America/New_York)
    - campaigns_enhanced.operating_tz: Abbreviation (EST) or IANA format

    Usage:
    - Python (pytz): IANA format (America/New_York)
    - SQL Server AT TIME ZONE: Windows format (Eastern Standard Time)
    """

    # Map SQL Server abbreviations to IANA timezone names (for pytz)
    ABBREV_TO_IANA = {
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "MST": "America/Denver",
        "MDT": "America/Denver",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        # Additional US timezones
        "AKST": "America/Anchorage",
        "AKDT": "America/Anchorage",
        "HST": "Pacific/Honolulu",
        "HAST": "America/Adak",  # Hawaii-Aleutian Standard Time (Aleutian Islands)
        "HADT": "America/Adak",  # Hawaii-Aleutian Daylight Time (Aleutian Islands)
        "AZT": "America/Phoenix",  # Arizona Time (no DST)
    }

    # Map IANA timezone names to SQL Server Windows timezone names
    IANA_TO_WINDOWS = {
        "America/New_York": "Eastern Standard Time",
        "America/Chicago": "Central Standard Time",
        "America/Denver": "Mountain Standard Time",
        "America/Los_Angeles": "Pacific Standard Time",
        "America/Phoenix": "US Mountain Standard Time",  # Arizona (no DST)
        "America/Anchorage": "Alaskan Standard Time",
        "America/Adak": "Alaskan Standard Time",  # Hawaii-Aleutian (same Windows zone as Anchorage)
        "Pacific/Honolulu": "Hawaiian Standard Time",
        # Additional US zones
        "America/Detroit": "Eastern Standard Time",
        "America/Indiana/Indianapolis": "US Eastern Standard Time",
        "America/Kentucky/Louisville": "Eastern Standard Time",
        "America/New_Orleans": "Central Standard Time",
        "America/Dallas": "Central Standard Time",
        "America/Houston": "Central Standard Time",
        "America/Boise": "Mountain Standard Time",
        "America/Salt_Lake_City": "Mountain Standard Time",
        "America/Seattle": "Pacific Standard Time",
        "America/San_Francisco": "Pacific Standard Time",
    }

    # Map abbreviations directly to Windows timezone names (for SQL Server)
    ABBREV_TO_WINDOWS = {
        "EST": "Eastern Standard Time",
        "EDT": "Eastern Standard Time",
        "CST": "Central Standard Time",
        "CDT": "Central Standard Time",
        "MST": "Mountain Standard Time",
        "MDT": "Mountain Standard Time",
        "PST": "Pacific Standard Time",
        "PDT": "Pacific Standard Time",
        "AKST": "Alaskan Standard Time",
        "AKDT": "Alaskan Standard Time",
        "HST": "Hawaiian Standard Time",
    }

    # US timezones for member_tz qualification checks
    US_TIMEZONES_IANA = {
        "Eastern": "America/New_York",
        "Central": "America/Chicago",
        "Mountain": "America/Denver",
        "Pacific": "America/Los_Angeles",
    }

    @classmethod
    def to_iana(cls, tz_input: str) -> str:
        """
        Convert any timezone input to IANA format for use with pytz

        Args:
            tz_input: Timezone string (could be EST, America/New_York, Eastern Standard Time, etc.)

        Returns:
            IANA timezone name (e.g., America/New_York)

        Examples:
            to_iana('EST') → 'America/New_York'
            to_iana('America/Chicago') → 'America/Chicago'
            to_iana('Eastern Standard Time') → 'America/New_York'
        """
        if not tz_input:
            logger.warning("⚠️ [TIMEZONE] Empty timezone input, defaulting to America/New_York")
            return "America/New_York"

        # Already IANA format (contains /)
        if "/" in tz_input:
            if tz_input in pytz.all_timezones:
                return tz_input
            else:
                logger.warning(
                    f"⚠️ [TIMEZONE] Unknown IANA timezone '{tz_input}', defaulting to America/New_York"
                )
                return "America/New_York"

        # Check if it's an abbreviation
        if tz_input in cls.ABBREV_TO_IANA:
            iana_tz = cls.ABBREV_TO_IANA[tz_input]
            logger.debug(f"🔄 [TIMEZONE] Converted abbreviation '{tz_input}' → '{iana_tz}'")
            return iana_tz

        # Check if it's a Windows timezone name, reverse lookup
        for iana, windows in cls.IANA_TO_WINDOWS.items():
            if windows == tz_input:
                logger.debug(f"🔄 [TIMEZONE] Converted Windows timezone '{tz_input}' → '{iana}'")
                return iana

        # Unknown format, default to Eastern
        logger.warning(
            f"⚠️ [TIMEZONE] Unknown timezone format '{tz_input}', defaulting to America/New_York"
        )
        return "America/New_York"

    @classmethod
    def to_windows(cls, tz_input: str) -> str:
        """
        Convert any timezone input to Windows timezone name for SQL Server AT TIME ZONE

        Args:
            tz_input: Timezone string (could be EST, America/New_York, etc.)

        Returns:
            Windows timezone name (e.g., Eastern Standard Time)

        Examples:
            to_windows('EST') → 'Eastern Standard Time'
            to_windows('America/New_York') → 'Eastern Standard Time'
        """
        if not tz_input:
            logger.warning("⚠️ [TIMEZONE] Empty timezone input, defaulting to Eastern Standard Time")
            return "Eastern Standard Time"

        # Check if it's already a Windows timezone name
        if tz_input in cls.IANA_TO_WINDOWS.values():
            return tz_input

        # Check if it's an abbreviation
        if tz_input in cls.ABBREV_TO_WINDOWS:
            windows_tz = cls.ABBREV_TO_WINDOWS[tz_input]
            logger.debug(f"🔄 [TIMEZONE] Converted abbreviation '{tz_input}' → '{windows_tz}'")
            return windows_tz

        # Check if it's IANA format
        if "/" in tz_input:
            if tz_input in cls.IANA_TO_WINDOWS:
                windows_tz = cls.IANA_TO_WINDOWS[tz_input]
                logger.debug(f"🔄 [TIMEZONE] Converted IANA '{tz_input}' → '{windows_tz}'")
                return windows_tz

        # Unknown format, default to Eastern
        logger.warning(
            f"⚠️ [TIMEZONE] Unknown timezone format '{tz_input}', defaulting to Eastern Standard Time"
        )
        return "Eastern Standard Time"

    @classmethod
    def to_pytz(cls, tz_input: str) -> pytz.tzinfo.BaseTzInfo:
        """
        Convert any timezone input to pytz timezone object

        Args:
            tz_input: Timezone string

        Returns:
            pytz timezone object

        Examples:
            to_pytz('EST') → <DstTzInfo 'America/New_York' ...>
            to_pytz('America/Chicago') → <DstTzInfo 'America/Chicago' ...>
        """
        iana_tz = cls.to_iana(tz_input)
        try:
            return pytz.timezone(iana_tz)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.error(f"🚨 [TIMEZONE] pytz failed to load '{iana_tz}', using UTC")
            return pytz.UTC

    @classmethod
    def get_us_timezones_pytz(cls) -> dict:
        """
        Get pytz timezone objects for all US timezones

        Returns:
            dict: {'Eastern': <pytz timezone>, 'Central': <pytz timezone>, ...}
        """
        return {name: pytz.timezone(iana) for name, iana in cls.US_TIMEZONES_IANA.items()}

    @classmethod
    def validate_timezone(cls, tz_input: str) -> bool:
        """
        Check if timezone string is valid in any format

        Args:
            tz_input: Timezone string

        Returns:
            bool: True if valid, False otherwise
        """
        if not tz_input:
            return False

        # Check abbreviation
        if tz_input in cls.ABBREV_TO_IANA:
            return True

        # Check IANA
        if tz_input in pytz.all_timezones:
            return True

        # Check Windows timezone name
        if tz_input in cls.IANA_TO_WINDOWS.values():
            return True

        return False


# Convenience functions for direct use
def convert_to_iana(tz_input: str) -> str:
    """Convert any timezone format to IANA (for pytz)"""
    return TimezoneConverter.to_iana(tz_input)


def convert_to_windows(tz_input: str) -> str:
    """Convert any timezone format to Windows (for SQL Server)"""
    return TimezoneConverter.to_windows(tz_input)


def convert_to_pytz(tz_input: str) -> pytz.tzinfo.BaseTzInfo:
    """Convert any timezone format to pytz object"""
    return TimezoneConverter.to_pytz(tz_input)
