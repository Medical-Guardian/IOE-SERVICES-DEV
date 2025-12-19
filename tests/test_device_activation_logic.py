"""
Unit tests for Device Activation CSV file processing logic.

Tests validation functions, ETL pipeline phases, and business day calculations.

BusinessCaseID: BC-TBD (Device Activation System)
Updated: 2025-12-15 - Updated for 27-column CSV format and new enrollment logic
"""

import pytest
from datetime import datetime, timedelta, date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import pytz

# Import functions to test
from af_code.af_device_activation_logic import (
    standardize_phone,
    validate_email,
    proper_case,
    validate_timezone,
    map_timezone_to_iana,
    validate_device_status,
    validate_and_cleanse_data_before_insert,
    ProcessingContext,
    ProcessingResult,
)


class TestPhoneNumberValidation:
    """Test phone number standardization to E.164 format"""

    def test_standardize_phone_valid_10_digit(self):
        """Test converting 10-digit US phone number to E.164"""
        result = standardize_phone("5551234567")
        assert result == "+15551234567"

    def test_standardize_phone_valid_11_digit(self):
        """Test converting 11-digit phone (1XXXXXXXXXX) to E.164"""
        result = standardize_phone("15551234567")
        assert result == "+15551234567"

    def test_standardize_phone_already_e164(self):
        """Test phone number already in E.164 format"""
        result = standardize_phone("+15551234567")
        assert result == "+15551234567"

    def test_standardize_phone_with_dashes(self):
        """Test phone number with dashes (555-123-4567)"""
        result = standardize_phone("555-123-4567")
        assert result == "+15551234567"

    def test_standardize_phone_with_spaces(self):
        """Test phone number with spaces"""
        result = standardize_phone("555 123 4567")
        assert result == "+15551234567"

    def test_standardize_phone_with_parentheses(self):
        """Test phone number with parentheses (555) 123-4567"""
        result = standardize_phone("(555) 123-4567")
        assert result == "+15551234567"

    def test_standardize_phone_invalid_too_short(self):
        """Test invalid phone number (too short)"""
        result = standardize_phone("555123")
        assert result is None

    def test_standardize_phone_invalid_too_long(self):
        """Test invalid phone number (too long)"""
        result = standardize_phone("555123456789012345")
        assert result is None

    def test_standardize_phone_empty(self):
        """Test empty phone number"""
        result = standardize_phone("")
        assert result is None

    def test_standardize_phone_none(self):
        """Test None phone number"""
        result = standardize_phone(None)
        assert result is None


class TestEmailValidation:
    """Test email validation"""

    def test_validate_email_valid(self):
        """Test valid email address"""
        assert validate_email("john.doe@example.com") is True

    def test_validate_email_valid_with_plus(self):
        """Test valid email with + sign"""
        assert validate_email("john+test@example.com") is True

    def test_validate_email_invalid_no_at(self):
        """Test invalid email (no @ sign)"""
        assert validate_email("johndoe.example.com") is False

    def test_validate_email_invalid_no_domain(self):
        """Test invalid email (no domain)"""
        assert validate_email("john@") is False

    def test_validate_email_empty(self):
        """Test empty email"""
        assert validate_email("") is False

    def test_validate_email_none(self):
        """Test None email"""
        assert validate_email(None) is False


class TestProperCase:
    """Test name proper casing"""

    def test_proper_case_lowercase(self):
        """Test converting lowercase to proper case"""
        assert proper_case("john doe") == "John Doe"

    def test_proper_case_uppercase(self):
        """Test converting uppercase to proper case"""
        assert proper_case("JOHN DOE") == "John Doe"

    def test_proper_case_mixed(self):
        """Test mixed case to proper case"""
        assert proper_case("jOhN DoE") == "John Doe"

    def test_proper_case_already_proper(self):
        """Test already proper case"""
        assert proper_case("John Doe") == "John Doe"

    def test_proper_case_with_apostrophe(self):
        """Test name with apostrophe (O'Brien)"""
        assert proper_case("o'brien") == "O'Brien"

    def test_proper_case_empty(self):
        """Test empty string"""
        assert proper_case("") == ""

    def test_proper_case_none(self):
        """Test None"""
        assert proper_case(None) == ""


class TestTimezoneValidation:
    """Test IANA timezone validation"""

    def test_validate_timezone_est(self):
        """Test valid timezone: America/New_York"""
        assert validate_timezone("America/New_York") is True

    def test_validate_timezone_pst(self):
        """Test valid timezone: America/Los_Angeles"""
        assert validate_timezone("America/Los_Angeles") is True

    def test_validate_timezone_cst(self):
        """Test valid timezone: America/Chicago"""
        assert validate_timezone("America/Chicago") is True

    def test_validate_timezone_mst(self):
        """Test valid timezone: America/Denver"""
        assert validate_timezone("America/Denver") is True

    def test_validate_timezone_invalid_abbreviation(self):
        """Test invalid timezone abbreviation (EST instead of America/New_York)"""
        assert validate_timezone("EST") is False

    def test_validate_timezone_invalid(self):
        """Test invalid timezone"""
        assert validate_timezone("Invalid/Timezone") is False

    def test_validate_timezone_empty(self):
        """Test empty timezone"""
        assert validate_timezone("") is False

    def test_validate_timezone_none(self):
        """Test None timezone"""
        assert validate_timezone(None) is False


class TestTimezoneMapping:
    """Test timezone abbreviation to IANA format mapping (NEW for 27-column CSV)"""

    def test_map_timezone_est_to_iana(self):
        """Test mapping EST → America/New_York"""
        result = map_timezone_to_iana("EST")
        assert result == "America/New_York"

    def test_map_timezone_edt_to_iana(self):
        """Test mapping EDT → America/New_York"""
        result = map_timezone_to_iana("EDT")
        assert result == "America/New_York"

    def test_map_timezone_cst_to_iana(self):
        """Test mapping CST → America/Chicago"""
        result = map_timezone_to_iana("CST")
        assert result == "America/Chicago"

    def test_map_timezone_cdt_to_iana(self):
        """Test mapping CDT → America/Chicago"""
        result = map_timezone_to_iana("CDT")
        assert result == "America/Chicago"

    def test_map_timezone_mst_to_iana(self):
        """Test mapping MST → America/Denver"""
        result = map_timezone_to_iana("MST")
        assert result == "America/Denver"

    def test_map_timezone_pst_to_iana(self):
        """Test mapping PST → America/Los_Angeles"""
        result = map_timezone_to_iana("PST")
        assert result == "America/Los_Angeles"

    def test_map_timezone_already_iana(self):
        """Test timezone already in IANA format (should remain unchanged)"""
        result = map_timezone_to_iana("America/New_York")
        assert result == "America/New_York"

    def test_map_timezone_empty(self):
        """Test empty timezone (should default to America/New_York)"""
        result = map_timezone_to_iana("")
        assert result == "America/New_York"

    def test_map_timezone_none(self):
        """Test None timezone (should default to America/New_York)"""
        result = map_timezone_to_iana(None)
        assert result == "America/New_York"

    def test_map_timezone_unknown_abbreviation(self):
        """Test unknown timezone abbreviation (should return as-is)"""
        result = map_timezone_to_iana("XYZ")
        assert result == "XYZ"


class TestDeviceStatusValidation:
    """Test device status field validation (fall_detection_status, battery_status)"""

    def test_validate_fall_detection_active(self):
        """Test valid fall_detection_status: Active"""
        is_valid, msg = validate_device_status("Active", "fall_detection_status")
        assert is_valid is True

    def test_validate_fall_detection_inactive(self):
        """Test valid fall_detection_status: Inactive"""
        is_valid, msg = validate_device_status("Inactive", "fall_detection_status")
        assert is_valid is True

    def test_validate_fall_detection_not_applicable(self):
        """Test valid fall_detection_status: Not Applicable"""
        is_valid, msg = validate_device_status("Not Applicable", "fall_detection_status")
        assert is_valid is True

    def test_validate_fall_detection_unknown(self):
        """Test valid fall_detection_status: Unknown"""
        is_valid, msg = validate_device_status("Unknown", "fall_detection_status")
        assert is_valid is True

    def test_validate_fall_detection_invalid(self):
        """Test invalid fall_detection_status"""
        is_valid, msg = validate_device_status("InvalidStatus", "fall_detection_status")
        assert is_valid is False
        assert "Invalid fall_detection_status" in msg

    def test_validate_battery_good(self):
        """Test valid battery_status: Good"""
        is_valid, msg = validate_device_status("Good", "battery_status")
        assert is_valid is True

    def test_validate_battery_low(self):
        """Test valid battery_status: Low"""
        is_valid, msg = validate_device_status("Low", "battery_status")
        assert is_valid is True

    def test_validate_battery_critical(self):
        """Test valid battery_status: Critical"""
        is_valid, msg = validate_device_status("Critical", "battery_status")
        assert is_valid is True

    def test_validate_battery_charging(self):
        """Test valid battery_status: Charging"""
        is_valid, msg = validate_device_status("Charging", "battery_status")
        assert is_valid is True

    def test_validate_battery_unknown(self):
        """Test valid battery_status: Unknown"""
        is_valid, msg = validate_device_status("Unknown", "battery_status")
        assert is_valid is True

    def test_validate_battery_invalid(self):
        """Test invalid battery_status"""
        is_valid, msg = validate_device_status("InvalidBattery", "battery_status")
        assert is_valid is False
        assert "Invalid battery_status" in msg

    def test_validate_device_status_empty(self):
        """Test empty device status (should be valid - nullable field)"""
        is_valid, msg = validate_device_status("", "fall_detection_status")
        assert is_valid is True

    def test_validate_device_status_none(self):
        """Test None device status (should be valid - nullable field)"""
        is_valid, msg = validate_device_status(None, "battery_status")
        assert is_valid is True


class TestActivationDateCalculation:
    """
    Test business day calculations for activation dates

    FINAL: 2025-12-16 - activation_start_date = first business day on or after enrollment_ts
    - Files can arrive ANY day (including weekends/holidays)
    - If Mon-Fri (business day) → Day 0 = same day
    - If Sat/Sun/Holiday → Day 0 = next business day
    """

    def test_calculate_activation_date_weekday(self):
        """Test activation_start_date when file uploaded on a weekday (business day)"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Wednesday (business day)
        enrollment_ts = datetime(2025, 12, 10, 10, 30, tzinfo=pytz.UTC)
        enrollment_date = enrollment_ts.date()  # 2025-12-10 (Wednesday)

        # Calculate activation_start_date
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date  # Same day
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Verify same day (Wednesday is a business day)
        assert activation_start_date == date(2025, 12, 10)
        assert activation_start_date == enrollment_date

    def test_calculate_activation_date_weekend_saturday(self):
        """Test activation_start_date when file uploaded on Saturday"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Saturday
        enrollment_ts = datetime(2025, 12, 13, 14, 0, tzinfo=pytz.UTC)  # Saturday
        enrollment_date = enrollment_ts.date()  # 2025-12-13 (Saturday)

        # Calculate activation_start_date
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Verify next Monday (skip Saturday and Sunday)
        assert activation_start_date == date(2025, 12, 15)  # Monday
        assert activation_start_date > enrollment_date

    def test_calculate_activation_date_weekend_sunday(self):
        """Test activation_start_date when file uploaded on Sunday"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Sunday
        enrollment_ts = datetime(2025, 12, 14, 10, 0, tzinfo=pytz.UTC)  # Sunday
        enrollment_date = enrollment_ts.date()  # 2025-12-14 (Sunday)

        # Calculate activation_start_date
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Verify next Monday
        assert activation_start_date == date(2025, 12, 15)  # Monday
        assert activation_start_date > enrollment_date

    def test_calculate_activation_date_christmas(self):
        """Test activation_start_date when file uploaded on Christmas (federal holiday)"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Christmas Day (Wednesday, Dec 25, 2025)
        enrollment_ts = datetime(2025, 12, 25, 11, 0, tzinfo=pytz.UTC)  # Thursday
        enrollment_date = enrollment_ts.date()  # 2025-12-25 (Christmas)

        # Calculate activation_start_date
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Verify next business day (Thursday, Dec 26)
        assert activation_start_date == date(2025, 12, 26)  # Thursday
        assert activation_start_date > enrollment_date

    def test_calculate_activation_date_friday_before_weekend(self):
        """Test activation_start_date when file uploaded on Friday (last business day of week)"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Friday
        enrollment_ts = datetime(2025, 12, 12, 15, 30, tzinfo=pytz.UTC)  # Friday
        enrollment_date = enrollment_ts.date()  # 2025-12-12 (Friday)

        # Calculate activation_start_date
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date  # Same day
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Verify same day (Friday is a business day)
        assert activation_start_date == date(2025, 12, 12)  # Friday
        assert activation_start_date == enrollment_date

    def test_campaign_end_date_calculation(self):
        """Test campaign_end_date = activation_start_date + 90 days"""
        activation_start = date(2025, 1, 7)
        campaign_end = activation_start + timedelta(days=90)

        # 90 days from Jan 7 = April 7
        assert campaign_end == date(2025, 4, 7)

    def test_enrollment_to_activation_timeline(self):
        """Test complete timeline: enrollment → activation (first business day) → end (90 days)"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Wednesday (business day)
        enrollment_ts = datetime(2025, 12, 10, 10, 30, tzinfo=pytz.UTC)
        enrollment_date = enrollment_ts.date()  # 2025-12-10 (Wednesday)

        # CORRECTED LOGIC: activation_start_date = first business day on or after enrollment
        # Wednesday is a business day, so Day 0 = same day
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date  # Same day
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Expected campaign end: activation + 90 days
        campaign_end_date = activation_start_date + timedelta(days=90)  # March 10, 2026

        # Verify the dates
        assert activation_start_date == date(2025, 12, 10)  # Same day (Wednesday is business day)
        assert campaign_end_date == date(2026, 3, 10)  # 90 days later

    def test_enrollment_to_activation_timeline_weekend(self):
        """Test complete timeline when file uploaded on weekend"""
        from af_code.shared.business_hours_utils import is_business_day, add_business_days

        # File uploaded on Saturday
        enrollment_ts = datetime(2025, 12, 13, 14, 0, tzinfo=pytz.UTC)
        enrollment_date = enrollment_ts.date()  # 2025-12-13 (Saturday)

        # Calculate activation_start_date (should be next Monday)
        if is_business_day(enrollment_ts):
            activation_start_date = enrollment_date
        else:
            activation_start_date = add_business_days(enrollment_ts, 1).date()

        # Expected campaign end: activation + 90 days
        campaign_end_date = activation_start_date + timedelta(days=90)

        # Verify the dates
        assert activation_start_date == date(2025, 12, 15)  # Monday (next business day)
        assert activation_start_date > enrollment_date  # Later than enrollment
        assert campaign_end_date == date(2026, 3, 15)  # 90 days from Monday


class TestRowLevelValidation:
    """
    Test row-level validation function

    UPDATED: 2025-12-15 - Changed to use actual 27-column CSV structure
    (removed delivery_date and customer_type fields)
    """

    def test_validate_and_cleanse_valid_row(self):
        """Test validation with all valid data (27-column CSV format)"""
        df = pd.DataFrame(
            [
                {
                    # Campaign metadata
                    "partner_name": "Medical Guardian",
                    "campaign_name_source": "Device Activation - Medicaid",
                    # Member identity
                    "salesforce_account_id": "001ABC123",
                    "salesforce_account_number": "ACC-123456",
                    "member_first_name": "john",
                    "member_last_name": "doe",
                    # Contact
                    "member_phone_number": "5551234567",  # Will be auto-formatted to +1
                    "member_email": "john.doe@example.com",
                    # Address (will be combined)
                    "member_address_street": "123 Main St",
                    "member_address_city": "New York",
                    "member_address_state": "NY",
                    "member_address_zip": "10001",
                    "member_address_country": "USA",
                    # Demographics
                    "member_dob": "1980-01-15",
                    "member_timezone": "EST",  # Will be mapped to America/New_York
                    "language_pref": "English",  # Will be mapped to EN
                    # Device info
                    "device_udi": "UDI-123456",
                    "device_name": "MGMini",
                    "member_brand": "MedScope",
                    "device_phone_number": "5559876543",
                    "is_device_callable": "1",
                    # Device status
                    "fall_detection": "1",  # Will be converted to Active
                    "battery_mode": "Standard",  # Will be converted to Good
                    # Campaign tracking
                    "campaign_parameters": "",
                    "monitoring_system_id": "a3lR30000012HU1IAM",
                    "enrollment_status": "enrolled",
                    "unenrollment_reason": "",
                }
            ]
        )

        context = ProcessingContext(
            file_batch_id="test-batch-123",
            source_filename="test_file.csv",
            uploaded_by_user="test_user",
        )

        result_df = validate_and_cleanse_data_before_insert(df, context)

        # Check validation status
        assert result_df.loc[0, "validation_status"] == "VALIDATED"
        assert pd.isna(result_df.loc[0, "error_message"]) or result_df.loc[0, "error_message"] == ""

        # Check clean columns
        assert result_df.loc[0, "first_name_clean"] == "John"
        assert result_df.loc[0, "last_name_clean"] == "Doe"
        assert result_df.loc[0, "primary_phone_clean"] == "+15551234567"  # Auto-formatted
        assert result_df.loc[0, "timezone_clean"] == "America/New_York"  # Mapped from EST
        assert result_df.loc[0, "language_pref_clean"] == "EN"  # Mapped from English

    def test_validate_and_cleanse_invalid_partner(self):
        """Test validation fails for invalid partner name"""
        df = pd.DataFrame(
            [
                {
                    "partner_name": "Invalid Partner",  # INVALID
                    "campaign_name_source": "Device Activation - Medicaid",
                    "salesforce_account_id": "001ABC123",
                    "salesforce_account_number": "ACC-123456",
                    "member_first_name": "john",
                    "member_last_name": "doe",
                    "member_phone_number": "5551234567",
                    "member_email": "john.doe@example.com",
                    "member_address_street": "123 Main St",
                    "member_address_city": "New York",
                    "member_address_state": "NY",
                    "member_address_zip": "10001",
                    "member_dob": "1980-01-15",
                    "member_timezone": "EST",
                    "language_pref": "EN",
                    "device_udi": "UDI-123456",
                    "device_name": "MGMini",
                    "member_brand": "MedScope",
                    "device_phone_number": "5559876543",
                    "is_device_callable": "1",
                    "fall_detection": "1",
                    "battery_mode": "Standard",
                    "enrollment_status": "enrolled",
                }
            ]
        )

        context = ProcessingContext(
            file_batch_id="test-batch-123",
            source_filename="test_file.csv",
            uploaded_by_user="test_user",
        )

        result_df = validate_and_cleanse_data_before_insert(df, context)

        # Check validation status
        assert result_df.loc[0, "validation_status"] == "VALIDATION_ERROR"
        assert "partner_name" in result_df.loc[0, "error_message"]


class TestProcessingContext:
    """Test ProcessingContext data model"""

    def test_processing_context_creation(self):
        """Test creating ProcessingContext"""
        context = ProcessingContext(
            file_batch_id="batch-123",
            source_filename="test.csv",
            container_name="fs-ops",
            uploaded_by_user="test_user",
            error_threshold_pct=15.0,
        )

        assert context.file_batch_id == "batch-123"
        assert context.source_filename == "test.csv"
        assert context.container_name == "fs-ops"
        assert context.uploaded_by_user == "test_user"
        assert context.error_threshold_pct == 15.0

    def test_processing_context_defaults(self):
        """Test ProcessingContext default values"""
        context = ProcessingContext(file_batch_id="batch-123", source_filename="test.csv")

        assert context.container_name == "fs-ops"
        assert context.uploaded_by_user == "AzureFunction"
        assert context.error_threshold_pct == 10.0


class TestProcessingResult:
    """Test ProcessingResult data model"""

    def test_processing_result_success(self):
        """Test creating successful ProcessingResult"""
        result = ProcessingResult(
            success=True, message="Processing complete", details={"rows_processed": 100}
        )

        assert result.success is True
        assert result.message == "Processing complete"
        assert result.details["rows_processed"] == 100
        assert result.error is None

    def test_processing_result_failure(self):
        """Test creating failed ProcessingResult"""
        error = ValueError("Test error")
        result = ProcessingResult(
            success=False, message="Processing failed", details={}, error=error
        )

        assert result.success is False
        assert result.message == "Processing failed"
        assert result.error == error


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
