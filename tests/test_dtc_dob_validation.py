"""
Unit tests for DTC date of birth (DOB) validation.

Tests validate that the DTC file processing accepts any valid date format
without age range restrictions (previously rejected ages <18 or >120).

Key test scenarios:
- Infant/child ages (< 18 years) - should be ACCEPTED
- Super-centenarian ages (> 120 years) - should be ACCEPTED
- Standard adult ages (18-120 years) - should be ACCEPTED
- Invalid date formats - should be REJECTED
- Empty/null values - should be ACCEPTED (DOB is optional)
- Multiple date format support (YYYY-MM-DD, MM/DD/YYYY, etc.)

BusinessCaseID: BC-109 (DTC Wellness Campaign Processing)

Change History:
- 2026-02-11: Created test suite after removing age range validation
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from af_code.af_dtc_logic import validate_and_cleanse_data_before_insert


class TestDTCDOBValidation:
    """Test suite for DTC date of birth validation without age restrictions."""

    @pytest.fixture
    def minimal_row_data(self):
        """Minimal valid row data for testing DOB validation."""
        return {
            "member_id": "test-member-123",
            "member_first_name": "John",
            "member_last_name": "Doe",
            "member_phone_number": "18125551234",
            "address_line_1": "123 Main St",
            "address_city": "Indianapolis",
            "address_state": "IN",
            "address_zip": "46220",
            "language_pref": "EN",
            "gender": "M",
            "member_dob": None,  # Will be set in individual tests
            "partner_name": "Medical Guardian",
            "salesforce_account_number": "12345",
            "enrollment_status": "enroll",
            "checkin_time": "AM",
        }

    @pytest.fixture
    def minimal_context(self):
        """Minimal context dictionary for validation function."""
        return {
            "file_id": "test-file-123",
            "filename": "medical_guardian_dtc_wellness_20260211.csv",
        }

    # =========================================================================
    # Tests for Ages < 18 Years (Previously Rejected, Now Accepted)
    # =========================================================================

    def test_valid_dob_infant_age_5(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 5 is now accepted (previously rejected)."""
        # Calculate DOB for 5 year old
        dob_5_years = (datetime.now() - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_5_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        # Should be valid - no age-related errors
        assert len(df_clean) == 1, "Row should not be rejected"
        assert df_clean.iloc[0]["dob_clean"] is not None, "DOB should be parsed"
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED", "Row should be VALIDATED"

        # Check for no age-related errors in validation_errors list
        age_errors = [
            err for err in validation_errors
            if any("unrealistic age" in e for e in err.get("errors", []))
        ]
        assert len(age_errors) == 0, "Should not have age-related errors"

    def test_valid_dob_child_age_10(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 10 is now accepted (previously rejected)."""
        dob_10_years = (datetime.now() - timedelta(days=10 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_10_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_teenager_age_16(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 16 is now accepted (previously rejected)."""
        dob_16_years = (datetime.now() - timedelta(days=16 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_16_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_infant_age_1(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 1 is now accepted (edge case)."""
        dob_1_year = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_1_year

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    # =========================================================================
    # Tests for Ages > 120 Years (Previously Rejected, Now Accepted)
    # =========================================================================

    def test_valid_dob_super_centenarian_age_125(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 125 is now accepted (previously rejected)."""
        dob_125_years = (datetime.now() - timedelta(days=125 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_125_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

        # Check for no age-related errors in validation_errors list
        age_errors = [
            err for err in validation_errors
            if any("unrealistic age" in e for e in err.get("errors", []))
        ]
        assert len(age_errors) == 0, "Should not have age-related errors"

    def test_valid_dob_age_135(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 135 is now accepted (data quality edge case)."""
        dob_135_years = (datetime.now() - timedelta(days=135 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_135_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_age_150(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 150 is now accepted (extreme edge case)."""
        dob_150_years = (datetime.now() - timedelta(days=150 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_150_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    # =========================================================================
    # Tests for Standard Ages (18-120 Years) - Always Accepted
    # =========================================================================

    def test_valid_dob_age_30(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 30 is accepted (always valid)."""
        dob_30_years = (datetime.now() - timedelta(days=30 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_30_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_age_75(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 75 is accepted (senior)."""
        dob_75_years = (datetime.now() - timedelta(days=75 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_75_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_age_105(self, minimal_context, minimal_row_data):
        """Test that DOB indicating age 105 is accepted (centenarian)."""
        dob_105_years = (datetime.now() - timedelta(days=105 * 365)).strftime("%Y-%m-%d")
        minimal_row_data["member_dob"] = dob_105_years

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    # =========================================================================
    # Tests for Multiple Date Formats (All Should Work)
    # =========================================================================

    def test_valid_dob_format_yyyy_mm_dd(self, minimal_context, minimal_row_data):
        """Test DOB in YYYY-MM-DD format (standard ISO format)."""
        minimal_row_data["member_dob"] = "2015-06-15"  # Age ~10

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["member_dob"] == "2015-06-15"
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_format_mm_dd_yyyy(self, minimal_context, minimal_row_data):
        """Test DOB in MM/DD/YYYY format (US standard)."""
        minimal_row_data["member_dob"] = "06/15/2015"  # Age ~10

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_format_mm_dash_dd_dash_yyyy(self, minimal_context, minimal_row_data):
        """Test DOB in MM-DD-YYYY format (US with dashes)."""
        minimal_row_data["member_dob"] = "06-15-2015"  # Age ~10

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_format_yyyy_slash_mm_slash_dd(self, minimal_context, minimal_row_data):
        """Test DOB in YYYY/MM/DD format (ISO with slashes)."""
        minimal_row_data["member_dob"] = "2015/06/15"  # Age ~10

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert df_clean.iloc[0]["dob_clean"] is not None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    # =========================================================================
    # Tests for Invalid Date Formats (Should Be Rejected)
    # =========================================================================

    def test_invalid_dob_format_text(self, minimal_context, minimal_row_data):
        """Test that invalid DOB format (text) is rejected."""
        minimal_row_data["member_dob"] = "not-a-date"

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        # Should have format error
        assert df_clean.iloc[0]["processing_status"] == "VALIDATION_ERROR"
        assert len(validation_errors) > 0, "Should have validation errors"
        # Check for format error
        has_format_error = any(
            any("Invalid date format" in e for e in err.get("errors", []))
            for err in validation_errors
        )
        assert has_format_error, "Should have format error"

    def test_invalid_dob_format_invalid_date(self, minimal_context, minimal_row_data):
        """Test that invalid date (13/45/2020) is rejected."""
        minimal_row_data["member_dob"] = "13/45/2020"

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        # Should have format error
        assert df_clean.iloc[0]["processing_status"] == "VALIDATION_ERROR"
        assert len(validation_errors) > 0, "Should have validation errors"
        # Check for format error
        has_format_error = any(
            any("Invalid date format" in e for e in err.get("errors", []))
            for err in validation_errors
        )
        assert has_format_error, "Should have format error"

    def test_invalid_dob_format_month_13(self, minimal_context, minimal_row_data):
        """Test that invalid month (13) is rejected."""
        minimal_row_data["member_dob"] = "2020-13-01"

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        # Should have format error
        assert df_clean.iloc[0]["processing_status"] == "VALIDATION_ERROR"

    # =========================================================================
    # Tests for Empty/Null Values (Should Be Accepted - DOB is Optional)
    # =========================================================================

    def test_valid_dob_empty_string(self, minimal_context, minimal_row_data):
        """Test that empty DOB is accepted (DOB is optional)."""
        minimal_row_data["member_dob"] = ""

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert pd.isna(df_clean.iloc[0]["dob_clean"]) or df_clean.iloc[0]["dob_clean"] is None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    def test_valid_dob_null(self, minimal_context, minimal_row_data):
        """Test that null DOB is accepted (DOB is optional)."""
        minimal_row_data["member_dob"] = None

        df = pd.DataFrame([minimal_row_data])
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        assert len(df_clean) == 1
        assert pd.isna(df_clean.iloc[0]["dob_clean"]) or df_clean.iloc[0]["dob_clean"] is None
        assert df_clean.iloc[0]["processing_status"] == "VALIDATED"

    # =========================================================================
    # Integration Test: Multiple Rows with Different Ages
    # =========================================================================

    def test_multiple_rows_different_ages(self, minimal_context, minimal_row_data):
        """Test processing multiple rows with different ages (all should be accepted)."""
        rows = []

        # Age 5 (infant)
        row1 = minimal_row_data.copy()
        row1["member_id"] = "member-001"
        row1["member_dob"] = (datetime.now() - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
        rows.append(row1)

        # Age 30 (adult)
        row2 = minimal_row_data.copy()
        row2["member_id"] = "member-002"
        row2["member_dob"] = (datetime.now() - timedelta(days=30 * 365)).strftime("%Y-%m-%d")
        rows.append(row2)

        # Age 125 (super-centenarian)
        row3 = minimal_row_data.copy()
        row3["member_id"] = "member-003"
        row3["member_dob"] = (datetime.now() - timedelta(days=125 * 365)).strftime("%Y-%m-%d")
        rows.append(row3)

        # Empty DOB
        row4 = minimal_row_data.copy()
        row4["member_id"] = "member-004"
        row4["member_dob"] = None
        rows.append(row4)

        df = pd.DataFrame(rows)
        df_clean, validation_errors = validate_and_cleanse_data_before_insert(df, minimal_context)

        # All 4 rows should be valid
        assert len(df_clean) == 4, "All rows should be processed"
        assert (df_clean["processing_status"] == "VALIDATED").all(), "All rows should be VALIDATED"

        # No age-related errors
        age_errors = [
            err for err in validation_errors
            if any("unrealistic age" in e for e in err.get("errors", []))
        ]
        assert len(age_errors) == 0, "Should have no age-related errors"
