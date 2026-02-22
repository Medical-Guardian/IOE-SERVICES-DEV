"""
Custom US Holidays for Medical Guardian Business Operations

Filters the standard Python `holidays` package to use only 6 business-critical
US holidays instead of all 11 federal holidays.

BusinessCaseID: BC-DA-003 (Business Hours Utils)

Usage:
    from af_code.shared.custom_holidays import CustomUSHolidays

    holidays = CustomUSHolidays(observed=True)

    # Check if date is a holiday
    if datetime.date(2025, 1, 20) in holidays:
        print("Holiday!")  # Will be False (MLK Day excluded)

    if datetime.date(2025, 7, 4) in holidays:
        print("Holiday!")  # Will be True (Independence Day included)
"""

from holidays.countries import US as USHolidaysClass


class CustomUSHolidays(USHolidaysClass):
    """
    Filtered US holidays for Medical Guardian business operations.

    Only includes 6 business-critical holidays:
    - New Year's Day (January 1)
    - Memorial Day (last Monday in May)
    - Independence Day (July 4)
    - Labor Day (first Monday in September)
    - Thanksgiving (fourth Thursday in November)
    - Christmas (December 25)

    Automatically filters out other federal holidays:
    - MLK Jr. Day, Washington's Birthday, Juneteenth, Columbus Day, Veterans Day

    Inherits from holidays.US and uses all its edge case handling:
    - Observed holidays (when holiday falls on weekend, observed on Friday/Monday)
    - Multi-year support
    - Timezone-aware datetime compatibility

    Examples:
        >>> # Basic usage
        >>> mg_holidays = CustomUSHolidays(observed=True)
        >>> datetime.date(2025, 1, 1) in mg_holidays
        True  # New Year's Day included

        >>> datetime.date(2025, 1, 20) in mg_holidays
        False  # MLK Day excluded

        >>> # Multi-year support
        >>> mg_holidays = CustomUSHolidays(years=[2025, 2026], observed=True)
        >>> len(mg_holidays)
        12  # 6 holidays × 2 years
    """

    # Define wanted holiday names at class level
    _WANTED_HOLIDAYS = {
        "New Year's Day",  # January 1
        "Memorial Day",  # Last Monday in May
        "Independence Day",  # July 4
        "Labor Day",  # First Monday in September
        "Thanksgiving Day",  # Fourth Thursday in November
        "Christmas Day",  # December 25
    }

    def __init__(self, *args, **kwargs):
        """
        Initialize CustomUSHolidays with filtered holiday list

        Args:
            years: Int or list of ints (which years to generate)
            observed: Boolean (handle holidays that fall on weekends)
            **kwargs: Other parameters passed to parent class
        """
        # Initialize parent, which populates holidays
        super().__init__(*args, **kwargs)
        # Filter to only wanted holidays
        self._filter_holidays()

    def _populate(self, year):
        """
        Override parent's _populate to generate holidays then filter

        This method is called by the parent class to populate holidays for a year.
        We call the parent implementation first, then filter to only wanted holidays.

        Args:
            year: Year to populate holidays for
        """
        # Call parent to populate all US federal holidays
        super()._populate(year)
        # Filter to only wanted holidays
        self._filter_holidays()

    def _filter_holidays(self):
        """
        Filter holidays to keep only the 6 business-critical ones

        This method:
        1. Iterates through all current holidays
        2. Keeps only holidays matching wanted names
        3. Removes all other holidays
        """
        # Get current holidays before filtering
        holidays_to_remove = []
        for date, name in self.items():
            if name not in self._WANTED_HOLIDAYS:
                holidays_to_remove.append(date)

        # Remove unwanted holidays
        for date in holidays_to_remove:
            self.pop(date)
