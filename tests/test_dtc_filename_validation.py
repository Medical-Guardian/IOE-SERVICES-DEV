"""
Unit tests for DTC Wellness filename validation.

Tests validate_dtc_wellness_filename() function with:
- Valid NEW pattern (snake_case)
- Valid LEGACY pattern (CamelCase)
- Invalid dates (Feb 30, Apr 31, month 13, etc.)
- Leap year edge cases
- Case sensitivity
- Pattern enforcement (Phase 1 vs Phase 2)

BusinessCaseID: BC-109 (DTC Wellness Campaign Processing)
"""

import pytest
from af_code.shared.filename_validators import validate_dtc_wellness_filename


class TestDTCWellnessFilenameValidation:
    """Test suite for DTC Wellness filename validation with calendar date validation."""

    # =========================================================================
    # Valid NEW Pattern Tests
    # =========================================================================

    def test_valid_new_pattern_basic(self):
        """Valid NEW pattern - basic case."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260202.csv"
        )
        assert is_valid is True
        assert error_msg == ""
        assert date_str == "20260202"
        assert pattern_type == "NEW"

    def test_valid_new_pattern_jan_1(self):
        """Valid NEW pattern - January 1st."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260101.csv"
        )
        assert is_valid is True
        assert date_str == "20260101"
        assert pattern_type == "NEW"

    def test_valid_new_pattern_dec_31(self):
        """Valid NEW pattern - December 31st."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20261231.csv"
        )
        assert is_valid is True
        assert date_str == "20261231"
        assert pattern_type == "NEW"

    def test_valid_new_pattern_leap_year_feb_29(self):
        """Valid NEW pattern - February 29 in leap year (2024)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20240229.csv"
        )
        assert is_valid is True
        assert date_str == "20240229"
        assert pattern_type == "NEW"

    # =========================================================================
    # Valid LEGACY Pattern Tests (Phase 1 Only)
    # =========================================================================

    def test_valid_legacy_pattern_basic(self):
        """Valid LEGACY pattern - basic case (Phase 1)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20260202_Delta.csv", allow_legacy=True
        )
        assert is_valid is True
        assert error_msg == ""
        assert date_str == "20260202"
        assert pattern_type == "LEGACY"

    def test_valid_legacy_pattern_jan_1(self):
        """Valid LEGACY pattern - January 1st (Phase 1)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20260101_Delta.csv", allow_legacy=True
        )
        assert is_valid is True
        assert date_str == "20260101"
        assert pattern_type == "LEGACY"

    def test_valid_legacy_pattern_leap_year(self):
        """Valid LEGACY pattern - leap year Feb 29 (Phase 1)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20240229_Delta.csv", allow_legacy=True
        )
        assert is_valid is True
        assert date_str == "20240229"
        assert pattern_type == "LEGACY"

    # =========================================================================
    # Invalid Date Tests - Calendar Validation
    # =========================================================================

    def test_invalid_date_feb_30(self):
        """Invalid date - February 30 (NEW pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260230.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg
        assert "20260230" in error_msg
        assert date_str is None
        assert pattern_type is None

    def test_invalid_date_feb_30_legacy(self):
        """Invalid date - February 30 (LEGACY pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20260230_Delta.csv", allow_legacy=True
        )
        assert is_valid is False
        assert "Invalid date" in error_msg
        assert "20260230" in error_msg

    def test_invalid_date_apr_31(self):
        """Invalid date - April 31 (NEW pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260431.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg
        assert "20260431" in error_msg
        assert date_str is None

    def test_invalid_date_month_13(self):
        """Invalid date - month 13 (NEW pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20261340.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg
        assert "20261340" in error_msg

    def test_invalid_date_leap_year_2026_feb_29(self):
        """Invalid date - Feb 29 in non-leap year (2026)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260229.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg
        assert "20260229" in error_msg

    def test_invalid_date_sep_31(self):
        """Invalid date - September 31 (NEW pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260931.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg

    def test_invalid_date_nov_31(self):
        """Invalid date - November 31 (NEW pattern)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20261131.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg

    # =========================================================================
    # Invalid Pattern Tests - Case Sensitivity & Format
    # =========================================================================

    def test_invalid_pattern_wrong_case_medical(self):
        """Invalid pattern - 'Medical' instead of 'medical'."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "Medical_Guardian_DTC_Wellness_20260202.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg
        assert "all lowercase" in error_msg
        assert date_str is None

    def test_invalid_pattern_wrong_case_guardian(self):
        """Invalid pattern - 'Guardian' instead of 'guardian'."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_Guardian_dtc_wellness_20260202.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_wrong_separator_hyphen(self):
        """Invalid pattern - hyphens instead of underscores."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical-guardian-dtc-wellness-20260202.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_wrong_separator_space(self):
        """Invalid pattern - spaces instead of underscores."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical guardian dtc wellness 20260202.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_missing_date(self):
        """Invalid pattern - missing date."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_incomplete_date(self):
        """Invalid pattern - incomplete date (6 digits instead of 8)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_202602.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_wrong_extension(self):
        """Invalid pattern - wrong file extension."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260202.txt"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_invalid_pattern_extra_suffix(self):
        """Invalid pattern - extra suffix before .csv."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260202_delta.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    # =========================================================================
    # Phase 2 Tests - Legacy Pattern Rejection
    # =========================================================================

    def test_legacy_pattern_rejected_phase_2(self):
        """Legacy pattern rejected when allow_legacy=False (Phase 2)."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20260202_Delta.csv", allow_legacy=False
        )
        assert is_valid is False
        assert "Legacy pattern no longer accepted" in error_msg
        assert "medical_guardian_dtc_wellness_YYYYMMDD.csv" in error_msg
        assert date_str is None
        assert pattern_type is None

    def test_new_pattern_still_valid_phase_2(self):
        """NEW pattern still valid in Phase 2."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260202.csv", allow_legacy=False
        )
        assert is_valid is True
        assert error_msg == ""
        assert date_str == "20260202"
        assert pattern_type == "NEW"

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_edge_case_empty_string(self):
        """Edge case - empty string."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename("")
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_edge_case_random_filename(self):
        """Edge case - completely random filename."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "random_file_123.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_edge_case_legacy_pattern_missing_delta(self):
        """Edge case - legacy pattern without _Delta suffix."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "MedicalGuardian_DTCWellness_20260202.csv", allow_legacy=True
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    def test_edge_case_new_pattern_with_delta(self):
        """Edge case - new pattern incorrectly includes _Delta."""
        is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260202_Delta.csv"
        )
        assert is_valid is False
        assert "Expected pattern" in error_msg

    # =========================================================================
    # Leap Year Comprehensive Tests
    # =========================================================================

    def test_leap_year_2024_feb_29(self):
        """Leap year - 2024 Feb 29 is valid."""
        is_valid, _, date_str, _ = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20240229.csv"
        )
        assert is_valid is True
        assert date_str == "20240229"

    def test_leap_year_2028_feb_29(self):
        """Leap year - 2028 Feb 29 is valid."""
        is_valid, _, date_str, _ = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20280229.csv"
        )
        assert is_valid is True
        assert date_str == "20280229"

    def test_non_leap_year_2025_feb_29(self):
        """Non-leap year - 2025 Feb 29 is invalid."""
        is_valid, error_msg, _, _ = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20250229.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg

    def test_non_leap_year_2026_feb_29(self):
        """Non-leap year - 2026 Feb 29 is invalid."""
        is_valid, error_msg, _, _ = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20260229.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg

    def test_non_leap_year_2027_feb_29(self):
        """Non-leap year - 2027 Feb 29 is invalid."""
        is_valid, error_msg, _, _ = validate_dtc_wellness_filename(
            "medical_guardian_dtc_wellness_20270229.csv"
        )
        assert is_valid is False
        assert "Invalid date" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
