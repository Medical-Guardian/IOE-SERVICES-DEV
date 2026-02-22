#!/usr/bin/env python
"""
DST Transition Verification Test for AZT and HAST/HADT Timezone Support

This script verifies that:
1. America/Adak correctly transitions between HAST (UTC-10) and HADT (UTC-9)
2. America/Phoenix stays UTC-7 year-round (no DST)
3. Both HAST and HADT abbreviations map to America/Adak
4. Call scheduling works correctly with DST-aware timezones
"""

import pytz
from datetime import datetime
import sys

# Add project to path
sys.path.insert(0, '/home/zubair-ashfaque/MG-IOE/Azure Function/Azure_function_Deployment/IOE-functions')

from af_code.af_device_activation_logic import map_timezone_to_iana, validate_timezone


def test_section(title):
    """Print test section header"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_passed(message):
    """Print success message"""
    print(f"   ✅ PASS: {message}")


def test_failed(message):
    """Print failure message and exit"""
    print(f"   ❌ FAIL: {message}")
    sys.exit(1)


def main():
    print("=" * 60)
    print("DST TRANSITION VERIFICATION TEST")
    print("=" * 60)

    # Test 1: America/Adak (Hawaii-Aleutian) - Observes DST
    test_section("1. AMERICA/ADAK (Hawaii-Aleutian Time Zone)")
    print("-" * 60)

    adak_tz = pytz.timezone("America/Adak")

    # Winter time (January - Standard Time / HAST)
    winter = adak_tz.localize(datetime(2026, 1, 15, 12, 0, 0))
    print(f"   Winter (Jan 15): {winter}")
    print(f"   UTC Offset: {winter.strftime('%z')} ({winter.tzname()})")
    print(f"   Expected: -1000 (UTC-10, HAST)")

    if winter.strftime('%z') == '-1000':
        test_passed("Winter offset is UTC-10 (HAST)")
    else:
        test_failed(f"Winter offset should be -1000, got {winter.strftime('%z')}")

    # Summer time (July - Daylight Time / HADT)
    summer = adak_tz.localize(datetime(2026, 7, 15, 12, 0, 0))
    print(f"   Summer (Jul 15): {summer}")
    print(f"   UTC Offset: {summer.strftime('%z')} ({summer.tzname()})")
    print(f"   Expected: -0900 (UTC-9, HADT)")

    if summer.strftime('%z') == '-0900':
        test_passed("Summer offset is UTC-9 (HADT)")
    else:
        test_failed(f"Summer offset should be -0900, got {summer.strftime('%z')}")

    test_passed("America/Adak correctly transitions between HAST and HADT")

    # Test 2: America/Phoenix (Arizona) - Does NOT observe DST
    test_section("2. AMERICA/PHOENIX (Arizona Time Zone - No DST)")
    print("-" * 60)

    phoenix_tz = pytz.timezone("America/Phoenix")

    # Winter time (January)
    winter = phoenix_tz.localize(datetime(2026, 1, 15, 12, 0, 0))
    print(f"   Winter (Jan 15): {winter}")
    print(f"   UTC Offset: {winter.strftime('%z')} ({winter.tzname()})")
    print(f"   Expected: -0700 (UTC-7, no DST)")

    if winter.strftime('%z') == '-0700':
        test_passed("Winter offset is UTC-7")
    else:
        test_failed(f"Winter offset should be -0700, got {winter.strftime('%z')}")

    # Summer time (July) - Should stay UTC-7 (no DST change)
    summer = phoenix_tz.localize(datetime(2026, 7, 15, 12, 0, 0))
    print(f"   Summer (Jul 15): {summer}")
    print(f"   UTC Offset: {summer.strftime('%z')} ({summer.tzname()})")
    print(f"   Expected: -0700 (UTC-7, no DST)")

    if summer.strftime('%z') == '-0700':
        test_passed("Summer offset is still UTC-7 (no DST change)")
    else:
        test_failed(f"Summer offset should be -0700, got {summer.strftime('%z')}")

    test_passed("America/Phoenix stays UTC-7 year-round (no DST)")

    # Test 3: Verify HAST and HADT both map to America/Adak
    test_section("3. ABBREVIATION MAPPING (HAST/HADT → America/Adak)")
    print("-" * 60)

    hast_mapped = map_timezone_to_iana("HAST")
    hadt_mapped = map_timezone_to_iana("HADT")

    print(f"   HAST maps to: {hast_mapped}")
    print(f"   HADT maps to: {hadt_mapped}")
    print(f"   Expected: Both → America/Adak")

    if hast_mapped == "America/Adak":
        test_passed("HAST correctly maps to America/Adak")
    else:
        test_failed(f"HAST should map to America/Adak, got {hast_mapped}")

    if hadt_mapped == "America/Adak":
        test_passed("HADT correctly maps to America/Adak")
    else:
        test_failed(f"HADT should map to America/Adak, got {hadt_mapped}")

    if hast_mapped == hadt_mapped:
        test_passed("Both HAST and HADT map to same timezone")
    else:
        test_failed("HAST and HADT should map to same timezone")

    # Test 4: Verify AZT maps to America/Phoenix
    test_section("4. ABBREVIATION MAPPING (AZT → America/Phoenix)")
    print("-" * 60)

    azt_mapped = map_timezone_to_iana("AZT")
    print(f"   AZT maps to: {azt_mapped}")
    print(f"   Expected: America/Phoenix")

    if azt_mapped == "America/Phoenix":
        test_passed("AZT correctly maps to America/Phoenix")
    else:
        test_failed(f"AZT should map to America/Phoenix, got {azt_mapped}")

    # Test 5: Validation of mapped timezones
    test_section("5. TIMEZONE VALIDATION")
    print("-" * 60)

    if validate_timezone("America/Adak"):
        test_passed("America/Adak passes validation")
    else:
        test_failed("America/Adak should be valid")

    if validate_timezone("America/Phoenix"):
        test_passed("America/Phoenix passes validation")
    else:
        test_failed("America/Phoenix should be valid")

    if validate_timezone("Pacific/Honolulu"):
        test_passed("Pacific/Honolulu passes validation")
    else:
        test_failed("Pacific/Honolulu should be valid")

    if validate_timezone("America/Honolulu"):
        test_passed("America/Honolulu still passes validation (backward compatibility)")
    else:
        test_failed("America/Honolulu should still be valid")

    # Test 6: Real-world scheduling scenario
    test_section("6. REAL-WORLD CALL SCHEDULING SCENARIO")
    print("-" * 60)
    print("   Scenario: Member in Adak enrolled with 'HAST' in winter CSV")
    print("   Question: Can we call them in summer at 11 PM UTC (2 PM local)?")
    print()

    # Member enrolled in winter with HAST, timezone stored as America/Adak
    member_tz_str = "America/Adak"
    member_tz = pytz.timezone(member_tz_str)

    # Simulate call scheduling in summer (July)
    utc_time = datetime(2026, 7, 15, 23, 0, 0, tzinfo=pytz.UTC)  # 11 PM UTC
    member_time = utc_time.astimezone(member_tz)

    print(f"   UTC Time: {utc_time}")
    print(f"   Member Local Time: {member_time}")
    print(f"   Member Hour: {member_time.hour}:00")
    print(f"   Business Hours: 9 AM - 5 PM (9-17)")

    # Check if within business hours
    if 9 <= member_time.hour < 17:
        print(f"   ✅ Within business hours - call can be scheduled")
        test_passed("Call scheduled correctly during business hours")
    else:
        print(f"   ❌ Outside business hours ({member_time.hour}:00) - call blocked")
        test_failed("Call should be within business hours")

    print()
    print("   Verification:")
    print(f"   - 11 PM UTC = {member_time.strftime('%I:%M %p')} {member_time.tzname()} (member local)")
    print(f"   - Member is in HADT zone (UTC-9) during summer")
    print(f"   - {member_time.hour}:00 is within 9 AM - 5 PM business hours")

    # Test 7: Cross-timezone comparison
    test_section("7. CROSS-TIMEZONE DST COMPARISON")
    print("-" * 60)

    # Test same UTC time in different timezones during DST
    test_time_utc = datetime(2026, 7, 15, 20, 0, 0, tzinfo=pytz.UTC)  # 8 PM UTC in summer

    timezones_to_test = {
        "America/New_York": ("EDT", -4),  # Eastern Daylight Time
        "America/Chicago": ("CDT", -5),   # Central Daylight Time
        "America/Denver": ("MDT", -6),    # Mountain Daylight Time
        "America/Los_Angeles": ("PDT", -7),  # Pacific Daylight Time
        "America/Phoenix": ("MST", -7),   # Mountain Standard Time (no DST)
        "America/Anchorage": ("AKDT", -8),  # Alaska Daylight Time
        "America/Adak": ("HDT", -9),      # Hawaii-Aleutian Daylight Time
        "Pacific/Honolulu": ("HST", -10), # Hawaii Standard Time (no DST)
    }

    print(f"   Test Time (UTC): {test_time_utc}")
    print()

    for tz_name, (expected_abbrev, expected_offset) in timezones_to_test.items():
        tz = pytz.timezone(tz_name)
        local_time = test_time_utc.astimezone(tz)
        actual_offset = local_time.utcoffset().total_seconds() / 3600

        print(f"   {tz_name:30} → {local_time.strftime('%I:%M %p')} {local_time.tzname()} (UTC{actual_offset:+.0f})")

        if actual_offset == expected_offset:
            test_passed(f"{tz_name} has correct offset (UTC{expected_offset:+.0f})")
        else:
            test_failed(f"{tz_name} offset should be UTC{expected_offset:+.0f}, got UTC{actual_offset:+.0f}")

    # Summary
    print("\n" + "=" * 60)
    print("DST VERIFICATION SUMMARY")
    print("=" * 60)
    print("✅ America/Adak: Transitions between HAST (UTC-10) and HADT (UTC-9)")
    print("✅ America/Phoenix: No DST, stays UTC-7 year-round")
    print("✅ HAST/HADT abbreviations: Both correctly map to America/Adak")
    print("✅ AZT abbreviation: Correctly maps to America/Phoenix")
    print("✅ Validation: All new timezones pass validation checks")
    print("✅ Call scheduling: DST-aware, uses correct offset based on date")
    print("✅ Cross-timezone: All US timezones show correct DST behavior")
    print()
    print("🎉 ALL DST TESTS PASSED - Implementation is fully DST-aware!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
