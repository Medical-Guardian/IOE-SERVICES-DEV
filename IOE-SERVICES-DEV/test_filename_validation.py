"""
Test script for Device Activation filename validation.

Tests the validate_device_activation_filename() function with various valid and invalid filenames.
"""

from af_code.shared.filename_validators import validate_device_activation_filename


def test_valid_filenames():
    """Test valid Medicaid and DTCMA filenames."""
    print("\n" + "="*80)
    print("TESTING VALID FILENAMES")
    print("="*80)

    valid_cases = [
        ("MedicalGuardian_DeviceActivationMedicaid_20260105_DELTA.csv", "20260105", "Medicaid"),
        ("MedicalGuardian_DeviceActivationDTCMA_20260105_DELTA.csv", "20260105", "DTCMA"),
        ("MedicalGuardian_DeviceActivationMedicaid_20240229_DELTA.csv", "20240229", "Medicaid"),  # Leap year
        ("MedicalGuardian_DeviceActivationDTCMA_20251231_DELTA.csv", "20251231", "DTCMA"),  # Dec 31
        ("MedicalGuardian_DeviceActivationMedicaid_20260101_DELTA.csv", "20260101", "Medicaid"),  # Jan 1
    ]

    passed = 0
    failed = 0

    for filename, expected_date, expected_campaign in valid_cases:
        is_valid, error_msg, date_str, campaign_type = validate_device_activation_filename(filename)

        if is_valid and date_str == expected_date and campaign_type == expected_campaign:
            print(f"✅ PASS: {filename}")
            print(f"   Date: {date_str}, Campaign: {campaign_type}")
            passed += 1
        else:
            print(f"❌ FAIL: {filename}")
            print(f"   Expected: valid=True, date={expected_date}, campaign={expected_campaign}")
            print(f"   Got: valid={is_valid}, date={date_str}, campaign={campaign_type}, error={error_msg}")
            failed += 1

    print(f"\nValid Filename Tests: {passed} passed, {failed} failed")
    return passed, failed


def test_invalid_dates():
    """Test filenames with invalid calendar dates."""
    print("\n" + "="*80)
    print("TESTING INVALID DATES")
    print("="*80)

    invalid_cases = [
        ("MedicalGuardian_DeviceActivationMedicaid_20251340_DELTA.csv", "Month 13"),
        ("MedicalGuardian_DeviceActivationDTCMA_20250230_DELTA.csv", "Feb 30"),
        ("MedicalGuardian_DeviceActivationMedicaid_20250431_DELTA.csv", "Apr 31"),
        ("MedicalGuardian_DeviceActivationDTCMA_20250631_DELTA.csv", "Jun 31"),
        ("MedicalGuardian_DeviceActivationMedicaid_20250931_DELTA.csv", "Sep 31"),
        ("MedicalGuardian_DeviceActivationDTCMA_20230229_DELTA.csv", "Feb 29 non-leap year"),
        ("MedicalGuardian_DeviceActivationMedicaid_20250100_DELTA.csv", "Day 00"),
        ("MedicalGuardian_DeviceActivationDTCMA_20250132_DELTA.csv", "Jan 32"),
        ("MedicalGuardian_DeviceActivationMedicaid_20250001_DELTA.csv", "Month 00"),
    ]

    passed = 0
    failed = 0

    for filename, reason in invalid_cases:
        is_valid, error_msg, date_str, campaign_type = validate_device_activation_filename(filename)

        if not is_valid and date_str is None:
            print(f"✅ PASS: {filename}")
            print(f"   Correctly rejected ({reason}): {error_msg}")
            passed += 1
        else:
            print(f"❌ FAIL: {filename}")
            print(f"   Expected: rejection for {reason}")
            print(f"   Got: valid={is_valid}, date={date_str}, campaign={campaign_type}")
            failed += 1

    print(f"\nInvalid Date Tests: {passed} passed, {failed} failed")
    return passed, failed


def test_invalid_patterns():
    """Test filenames with invalid patterns (wrong suffix, case mismatch, etc.)."""
    print("\n" + "="*80)
    print("TESTING INVALID PATTERNS")
    print("="*80)

    invalid_cases = [
        ("MedicalGuardian_DeviceActivation_20260105_DELTA.csv", "No suffix"),
        ("MedicalGuardian_DeviceActivationOther_20260105_DELTA.csv", "Unknown suffix"),
        ("MedicalGuardian_DeviceActivationXYZ_20260105_DELTA.csv", "Unknown suffix"),
        ("MedicalGuardian_DeviceActivationMedicaid_20260105_Delta.csv", "Lowercase delta"),
        ("MedicalGuardian_DeviceActivationMedicaid_20260105_delta.csv", "All lowercase"),
        ("MedicalGuardian_DeviceActivationMedicaid_2026105_DELTA.csv", "7 digits"),
        ("MedicalGuardian_DeviceActivationMedicaid_202601050_DELTA.csv", "9 digits"),
        ("medicalguardian_DeviceActivationMedicaid_20260105_DELTA.csv", "Lowercase first word"),
    ]

    passed = 0
    failed = 0

    for filename, reason in invalid_cases:
        is_valid, error_msg, date_str, campaign_type = validate_device_activation_filename(filename)

        if not is_valid and date_str is None and campaign_type is None:
            print(f"✅ PASS: {filename}")
            print(f"   Correctly rejected ({reason}): {error_msg}")
            passed += 1
        else:
            print(f"❌ FAIL: {filename}")
            print(f"   Expected: rejection for {reason}")
            print(f"   Got: valid={is_valid}, date={date_str}, campaign={campaign_type}")
            failed += 1

    print(f"\nInvalid Pattern Tests: {passed} passed, {failed} failed")
    return passed, failed


def main():
    """Run all tests and print summary."""
    print("\n" + "#"*80)
    print("# Device Activation Filename Validation Test Suite")
    print("#"*80)

    # Run all tests
    valid_passed, valid_failed = test_valid_filenames()
    invalid_date_passed, invalid_date_failed = test_invalid_dates()
    invalid_pattern_passed, invalid_pattern_failed = test_invalid_patterns()

    # Calculate totals
    total_passed = valid_passed + invalid_date_passed + invalid_pattern_passed
    total_failed = valid_failed + invalid_date_failed + invalid_pattern_failed
    total_tests = total_passed + total_failed

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_passed} ✅")
    print(f"Failed: {total_failed} ❌")
    print(f"Success Rate: {(total_passed/total_tests)*100:.1f}%")
    print("="*80 + "\n")

    if total_failed == 0:
        print("🎉 ALL TESTS PASSED! 🎉\n")
        return 0
    else:
        print(f"⚠️  {total_failed} test(s) failed. Please review failures above.\n")
        return 1


if __name__ == "__main__":
    exit(main())
