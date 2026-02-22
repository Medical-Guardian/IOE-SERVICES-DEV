"""
Verification Script: Intro → Wellness Channel Copy Implementation
Purpose: Validate that channel field is properly copied during auto-transition
Date: 2026-02-16
"""

import re


def verify_database_orchestrator_changes():
    """Verify all required changes are present in database_orchestrator.py"""
    
    print("=" * 80)
    print("Verifying Intro → Wellness Channel Copy Implementation")
    print("=" * 80)
    print()
    
    file_path = "af_code/bland_ai_webhook/services/database_orchestrator.py"
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    checks = []
    
    # Check 1: SELECT query includes channel (inline logic)
    check1 = "SELECT current_status, preferred_window, channel" in content
    checks.append(("SELECT query includes channel (inline)", check1))
    
    # Check 2: channel variable extraction (inline logic)
    check2 = 'channel = intro_data[0].get("channel")' in content
    checks.append(("Channel variable extraction (inline)", check2))
    
    # Check 3: Logging channel value (inline logic)
    check3 = 'logger.info(f"📊 [DB-ORCH]   - Channel: {channel}")' in content
    checks.append(("Logging channel value (inline)", check3))
    
    # Check 4: MERGE query source CTE includes channel
    check4 = "SELECT %s as member_id, %s as campaign_id, %s as new_status, %s as preferred_window, %s as channel" in content
    checks.append(("MERGE source CTE includes channel", check4))
    
    # Check 5: MERGE UPDATE sets channel
    check5 = "channel = ISNULL(src.channel, tgt.channel)" in content
    checks.append(("MERGE UPDATE sets channel", check5))
    
    # Check 6: MERGE INSERT includes channel
    check6 = "INSERT (enrollment_id, member_id, campaign_id, enrollment_ts, current_status, last_attempt_ts, preferred_window, channel)" in content
    checks.append(("MERGE INSERT includes channel", check6))
    
    # Check 7: Execute query passes channel parameter
    check7 = '(member_id, WELLNESS_CAMPAIGN_ID, "ENROLLED", preferred_window, channel)' in content
    checks.append(("Execute query passes channel parameter", check7))
    
    # Check 8: Audit log mentions channel (intro)
    check8 = "copied: preferred_window='{preferred_window}', channel='{channel}'" in content
    checks.append(("Audit log mentions channel (intro)", check8))
    
    # Check 9: Audit log mentions channel (wellness)
    check9 = "inherited: preferred_window='{preferred_window}', channel='{channel}'" in content
    checks.append(("Audit log mentions channel (wellness)", check9))
    
    # Check 10: Logging message mentions channel copy
    check10 = "Copying from intro campaign" in content and "channel='{channel}'" in content
    checks.append(("Logging message mentions channel copy", check10))
    
    # Count occurrences to verify both inline and method implementations
    inline_count = content.count("SELECT current_status, preferred_window, channel")
    checks.append((f"Both implementations updated (found {inline_count} SELECT queries)", inline_count >= 2))
    
    # Print results
    print("Verification Results:")
    print("-" * 80)
    
    all_passed = True
    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {check_name}")
        if not result:
            all_passed = False
    
    print("-" * 80)
    print()
    
    if all_passed:
        print("🎉 All checks PASSED! Implementation is complete.")
    else:
        print("⚠️ Some checks FAILED. Please review the implementation.")
    
    print()
    print("=" * 80)
    
    return all_passed


def verify_documentation_updates():
    """Verify documentation was updated"""
    
    print()
    print("Verifying Documentation Updates:")
    print("-" * 80)
    
    checks = []
    
    # Check DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md
    try:
        with open("DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md", 'r') as f:
            content = f.read()
        check1 = "Copies `preferred_window` AND `channel` from intro to wellness" in content
        checks.append(("DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md updated", check1))
    except FileNotFoundError:
        checks.append(("DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md updated", False))
    
    # Check implementation summary exists
    try:
        with open("INTRO_WELLNESS_CHANNEL_COPY_IMPLEMENTATION.md", 'r') as f:
            content = f.read()
        check2 = "Intro → Wellness Channel Copy Implementation Summary" in content
        checks.append(("Implementation summary document created", check2))
    except FileNotFoundError:
        checks.append(("Implementation summary document created", False))
    
    for check_name, result in checks:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {check_name}")
    
    print("-" * 80)
    print()


if __name__ == "__main__":
    code_ok = verify_database_orchestrator_changes()
    verify_documentation_updates()
    
    if code_ok:
        print("✨ Implementation verification complete!")
        print()
        print("Next Steps:")
        print("1. Run unit tests: pytest tests/test_intro_wellness_channel_transition.py -v")
        print("2. Deploy to staging environment")
        print("3. Test with sample webhook payloads")
        print("4. Run database validation queries (see INTRO_WELLNESS_CHANNEL_COPY_IMPLEMENTATION.md)")
        print("5. Monitor Application Insights for 'channel=' in webhook logs")
    else:
        print("⚠️ Please fix the failed checks before proceeding.")
