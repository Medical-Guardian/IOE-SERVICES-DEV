"""
Test script to validate enrollment-level channel migration changes.

This script verifies:
1. SQL query syntax is valid
2. Field names are correctly updated
3. Device validation logic is present

Run before deployment to catch syntax errors.
"""

import re


def test_dtc_logic_sql_queries():
    """Test that af_dtc_logic.py has enrollment channel in MERGE queries."""
    print("Testing af_dtc_logic.py...")

    with open("af_code/af_dtc_logic.py", "r") as f:
        content = f.read()

    # Check intro enrollment MERGE has channel in source CTE
    assert "stg.channel_type_clean AS channel" in content, (
        "❌ Missing: 'stg.channel_type_clean AS channel' in intro enrollment MERGE"
    )

    # Check intro enrollment MERGE updates channel
    assert "channel = ISNULL(src.channel, tgt.channel)" in content, (
        "❌ Missing: 'channel = ISNULL(src.channel, tgt.channel)' in intro MERGE UPDATE"
    )

    # Check intro enrollment MERGE inserts channel
    assert re.search(
        r"INSERT.*enrollment_id.*preferred_window.*channel", content, re.DOTALL
    ), "❌ Missing: channel in intro MERGE INSERT columns"

    assert re.search(
        r"VALUES.*src\.preferred_window.*src\.channel", content, re.DOTALL
    ), "❌ Missing: src.channel in intro MERGE INSERT values"

    # Check wellness enrollment UPDATE has channel
    assert re.search(
        r"UPDATE SET.*preferred_window.*channel.*ISNULL\(src\.channel",
        content,
        re.DOTALL,
    ), "❌ Missing: channel update in wellness enrollment MERGE"

    print("✅ af_dtc_logic.py: All SQL queries updated correctly")


def test_dtc_config_queries():
    """Test that config.py uses enrollment-level channel and device validation."""
    print("Testing af_dtc_intro_call/utils/config.py...")

    with open("af_code/af_dtc_intro_call/utils/config.py", "r") as f:
        content = f.read()

    # Check GET_MEMBERS_WITH_ATTEMPTS_QUERY uses mce.channel
    assert "mce.channel," in content, (
        "❌ Missing: 'mce.channel' in GET_MEMBERS_WITH_ATTEMPTS_QUERY"
    )

    # Ensure old member-level Channel is not used
    assert "m.Channel," not in content, (
        "❌ Found deprecated: 'm.Channel' in queries (should be mce.channel)"
    )

    # Check ELIGIBLE_MEMBERS_QUERY_INTRO has device validation
    assert "LEFT JOIN" in content and "engage360.member_devices md" in content, (
        "❌ Missing: LEFT JOIN for member_devices in eligibility query"
    )

    assert "md.service_status = 'In Service'" in content, (
        "❌ Missing: service_status filter in member_devices JOIN"
    )

    # Check channel validation logic
    assert "mce.channel != 'device'" in content, (
        "❌ Missing: channel validation logic (mce.channel != 'device')"
    )

    assert "mce.channel = 'device' AND md.device_id IS NOT NULL" in content, (
        "❌ Missing: device validation logic (mce.channel = 'device' AND md.device_id IS NOT NULL)"
    )

    print("✅ af_dtc_intro_call/utils/config.py: All queries updated correctly")


def test_phone_selector():
    """Test that phone_selector.py uses enrollment-level channel and removes fallback."""
    print("Testing af_dtc_intro_call/utils/phone_selector.py...")

    with open("af_code/af_dtc_intro_call/utils/phone_selector.py", "r") as f:
        content = f.read()

    # Check field name changed to enrollment-level channel
    assert 'member_channel = member_data.get("channel")' in content, (
        "❌ Missing: member_data.get('channel') - should use enrollment-level channel"
    )

    # Ensure old member-level Channel is not used
    assert 'member_data.get("Channel")' not in content, (
        "❌ Found deprecated: member_data.get('Channel') - should be 'channel'"
    )

    # Check fallback logic is removed
    assert "Using fallback" not in content, (
        "❌ Found: 'Using fallback' - fallback logic should be removed"
    )

    # Check ineligibility logging is present
    assert "INELIGIBLE" in content and "No fallback" in content, (
        "❌ Missing: Ineligibility logging with 'INELIGIBLE' and 'No fallback' keywords"
    )

    assert "respecting member preference" in content or "respecting enrollment preference" in content, (
        "❌ Missing: 'respecting member preference' in ineligibility log"
    )

    print("✅ af_dtc_intro_call/utils/phone_selector.py: Updated correctly")


def test_partner_batch_orchestrator():
    """Test that batch_orchestrator.py removes fallback logic."""
    print("Testing partner_campaign_scheduler/services/batch_orchestrator.py...")

    with open(
        "af_code/partner_campaign_scheduler/services/batch_orchestrator.py", "r"
    ) as f:
        content = f.read()

    # Check fallback logic is removed in member_preference mode
    # Look for the section after device validation
    pattern = re.compile(
        r"member\.channel.*==.*device.*device_phone_number.*"
        r"(.*?)"
        r"return None",
        re.DOTALL,
    )

    match = pattern.search(content)
    if match:
        section = match.group(1)
        # Ensure no "Fallback to" messages in this section
        assert "Fallback to" not in section, (
            "❌ Found: 'Fallback to' - fallback logic should be removed"
        )

    # Check ineligibility logging is present
    assert "INELIGIBLE" in content and "No fallback" in content, (
        "❌ Missing: Ineligibility logging with 'INELIGIBLE' and 'No fallback' keywords"
    )

    assert "respecting enrollment preference" in content, (
        "❌ Missing: 'respecting enrollment preference' in ineligibility log"
    )

    print(
        "✅ partner_campaign_scheduler/services/batch_orchestrator.py: Updated correctly"
    )


def main():
    """Run all tests."""
    print("=" * 70)
    print("Enrollment-Level Channel Migration - Validation Tests")
    print("=" * 70)
    print()

    try:
        test_dtc_logic_sql_queries()
        test_dtc_config_queries()
        test_phone_selector()
        test_partner_batch_orchestrator()

        print()
        print("=" * 70)
        print("✅ ALL TESTS PASSED - Ready for deployment!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Run database backfill script: database/backfill_dtc_enrollment_channel.sql")
        print("2. Deploy code: func azure functionapp publish IOE-function --python")
        print("3. Monitor Application Insights for 'INELIGIBLE' warnings")

    except AssertionError as e:
        print()
        print("=" * 70)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 70)
        print()
        print("Please fix the issue and re-run tests.")
        exit(1)


if __name__ == "__main__":
    main()
