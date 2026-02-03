#!/usr/bin/env python3
"""
Quick verification script for DTC Wellness filename validation.

Usage:
    python verify_dtc_filename_validation.py

This script tests the validator with various filenames and displays results.
Useful for quick verification after deployment or code changes.

BusinessCaseID: BC-109 (DTC Wellness Campaign Processing)
"""

from af_code.shared.filename_validators import validate_dtc_wellness_filename


def test_filename(filename, allow_legacy=True, description=""):
    """Test a single filename and print results."""
    is_valid, error_msg, date_str, pattern_type = validate_dtc_wellness_filename(
        filename, allow_legacy=allow_legacy
    )

    status_icon = "✅" if is_valid else "❌"
    pattern_info = f" [{pattern_type}]" if pattern_type else ""
    date_info = f" (date: {date_str})" if date_str else ""

    print(f"{status_icon} {filename}{pattern_info}{date_info}")
    if description:
        print(f"   Description: {description}")
    if not is_valid:
        print(f"   Error: {error_msg}")
    print()


def main():
    """Run comprehensive filename validation tests."""
    print("=" * 80)
    print("DTC WELLNESS FILENAME VALIDATION - VERIFICATION SCRIPT")
    print("=" * 80)
    print()

    print("📋 PHASE 1: DUAL SUPPORT (allow_legacy=True)")
    print("-" * 80)
    print()

    print("✅ VALID NEW PATTERN (Preferred):")
    test_filename(
        "medical_guardian_dtc_wellness_20260202.csv",
        description="Standard new pattern",
    )
    test_filename(
        "medical_guardian_dtc_wellness_20240229.csv",
        description="Leap year Feb 29 (2024)",
    )

    print("⚠️ VALID LEGACY PATTERN (Deprecated):")
    test_filename(
        "MedicalGuardian_DTCWellness_20260202_Delta.csv",
        description="Legacy CamelCase pattern - will be deprecated",
    )

    print("❌ INVALID DATES (Calendar Validation):")
    test_filename(
        "medical_guardian_dtc_wellness_20260230.csv", description="February 30 (invalid)"
    )
    test_filename(
        "medical_guardian_dtc_wellness_20260431.csv", description="April 31 (invalid)"
    )
    test_filename(
        "medical_guardian_dtc_wellness_20261340.csv", description="Month 13 (invalid)"
    )
    test_filename(
        "medical_guardian_dtc_wellness_20260229.csv",
        description="Feb 29 in non-leap year (2026)",
    )

    print("❌ INVALID PATTERNS (Format/Case Issues):")
    test_filename(
        "Medical_Guardian_DTC_Wellness_20260202.csv",
        description="Wrong case (should be lowercase)",
    )
    test_filename(
        "medical-guardian-dtc-wellness-20260202.csv",
        description="Wrong separator (hyphens)",
    )
    test_filename(
        "medical_guardian_dtc_wellness.csv", description="Missing date"
    )

    print()
    print("=" * 80)
    print("📋 PHASE 2: NEW PATTERN ONLY (allow_legacy=False)")
    print("-" * 80)
    print()

    print("✅ VALID NEW PATTERN (Still Accepted):")
    test_filename(
        "medical_guardian_dtc_wellness_20260202.csv",
        allow_legacy=False,
        description="New pattern continues to work",
    )

    print("❌ LEGACY PATTERN REJECTED (Expected Behavior):")
    test_filename(
        "MedicalGuardian_DTCWellness_20260202_Delta.csv",
        allow_legacy=False,
        description="Legacy pattern no longer accepted in Phase 2",
    )

    print("=" * 80)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 80)
    print()
    print("Next Steps:")
    print("1. Review results above - all should match expectations")
    print("2. Run full test suite: pytest tests/test_dtc_filename_validation.py -v")
    print("3. Check code quality: black --check . && ruff check .")
    print("4. Deploy to development environment for integration testing")
    print()


if __name__ == "__main__":
    main()
