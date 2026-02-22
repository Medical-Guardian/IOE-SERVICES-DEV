# Enrollment-Level Channel Migration - Deployment Guide

**Status:** ✅ Ready for Deployment
**Date:** 2026-02-13
**Validation:** All tests passed

---

## 🎯 What Was Implemented

Successfully migrated DTC campaigns from member-level channel to enrollment-level channel with strict preference enforcement (no fallback).

### Key Changes

1. **Database Migration:** Backfill script to populate `mce.channel` from `members.Channel`
2. **CSV Processing:** DTC files now write `channel_type` → `mce.channel`
3. **Eligibility Queries:** Read `mce.channel` + validate device status
4. **Phone Selection:** Removed fallback logic - strict preference enforcement
5. **Consistency:** Partner and DTC campaigns now have identical channel behavior

---

## 📦 Files Modified

| File | Purpose | Status |
|------|---------|--------|
| `database/backfill_dtc_enrollment_channel.sql` | **NEW** - Database migration | ✅ Created |
| `af_code/af_dtc_logic.py` | Add channel to enrollment MERGE | ✅ Updated |
| `af_code/af_dtc_intro_call/utils/config.py` | Use mce.channel + device validation | ✅ Updated |
| `af_code/af_dtc_intro_call/utils/phone_selector.py` | Remove fallback logic | ✅ Updated |
| `af_code/partner_campaign_scheduler/services/batch_orchestrator.py` | Remove fallback logic | ✅ Updated |
| `test_enrollment_channel_migration.py` | **NEW** - Validation tests | ✅ Passed |
| `IMPLEMENTATION_SUMMARY_ENROLLMENT_CHANNEL_MIGRATION.md` | **NEW** - Documentation | ✅ Created |

**Total:** 7 files (4 existing modified + 3 new)

---

## ✅ Pre-Deployment Validation

All quality checks passed:

```bash
✅ Black formatting: PASSED (4 files)
✅ Ruff linting: PASSED (4 files)
✅ Validation tests: PASSED (4 test cases)
```

---

## 🚀 Deployment Steps

### Step 1: Database Migration (15 minutes)

**⚠️ IMPORTANT: Run this BEFORE deploying code changes**

```bash
# 1. Backup database
# (Coordinate with DBA team)

# 2. Run migration script on production database
# Execute: database/backfill_dtc_enrollment_channel.sql

# 3. Verify migration success
# Expected: Zero NULL channels for DTC enrollments
```

**Verification Query:**
```sql
SELECT COUNT(*) AS null_channels_remaining
FROM engage360.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
AND channel IS NULL;
-- Expected: 0
```

### Step 2: Code Deployment (30 minutes)

```bash
# 1. Navigate to project directory
cd /home/zubair-ashfaque/MG-IOE/Azure\ Function/Azure_function_Deployment/IOE-functions

# 2. Verify you're on the correct branch
git status

# 3. Run quality checks one final time
black --line-length 100 --check af_code/af_dtc_logic.py \
  af_code/af_dtc_intro_call/utils/config.py \
  af_code/af_dtc_intro_call/utils/phone_selector.py \
  af_code/partner_campaign_scheduler/services/batch_orchestrator.py

ruff check af_code/

# 4. Deploy to Azure Functions
func azure functionapp publish IOE-function --python

# 5. Verify function registration
# Check Azure logs for: "✅ Successfully registered DTC File Processor blueprint"
# Check Azure logs for: "✅ Successfully registered DTC Intro Call"
```

### Step 3: Post-Deployment Verification (1 hour)

**A. Test CSV Upload**

```bash
# Upload test DTC file with channel_type field
az storage blob upload \
  --account-name <storage-account> \
  --container-name fs-dtc/landing \
  --name "medical_guardian_dtc_wellness_20260213_test.csv" \
  --file test_data/dtc_channel_test.csv
```

**Test CSV Format:**
```csv
salesforce_account_number,enrollment_status,channel_type,checkin_time,first_name,last_name
SF-TEST-001,ENROLL,device,AM,John,Doe
SF-TEST-002,ENROLL,phone,PM,Jane,Smith
```

**B. Verify Enrollment Creation**

```sql
SELECT
    mce.enrollment_id,
    mce.channel,
    m.salesforce_account_number,
    m.first_name,
    m.last_name
FROM engage360.member_campaign_enrollments_enhanced mce
JOIN engage360.members m ON mce.member_id = m.member_id
WHERE m.salesforce_account_number IN ('SF-TEST-001', 'SF-TEST-002')
  AND mce.campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC';
-- Expected: SF-TEST-001 has channel='device', SF-TEST-002 has channel='phone'
```

**C. Monitor Application Insights**

```kusto
// 1. Check for ineligibility warnings (expected)
traces
| where message contains "INELIGIBLE"
| where message contains "No fallback"
| project timestamp, message
| order by timestamp desc
| take 20

// 2. Verify NO fallback logs (should be zero)
traces
| where message contains "Using fallback"
| where timestamp > ago(1h)
| count
// Expected: 0 results

// 3. Monitor batch submission counts
traces
| where message contains "BATCH-ORCHESTRATOR"
| where message contains "Building batch request"
| summarize batch_count=count() by bin(timestamp, 1h)
| order by timestamp desc
```

### Step 4: Monitor (24-48 hours)

**Key Metrics to Watch:**

1. **Call Volume:**
   - May decrease (expected - respecting device preferences strictly)
   - Monitor batch sizes in Application Insights

2. **Error Logs:**
   - Should see "INELIGIBLE" warnings (normal - members with device preference but no active device)
   - Should NOT see unexpected errors

3. **Member Complaints:**
   - Should decrease (no unwanted phone calls if device preferred)
   - Track via operations team

---

## 📊 Expected Behavior Changes

### Before Migration
```
Scenario: Member prefers device, but device unavailable

Old Behavior:
1. Check enrollment channel: device
2. Device validation: FAILED (no active device)
3. Fallback: ✅ Call primary phone anyway
4. Result: Member receives unwanted phone call
```

### After Migration
```
Scenario: Member prefers device, but device unavailable

New Behavior:
1. Check enrollment channel: device
2. Device validation: FAILED (no active device)
3. SQL query: ❌ Member excluded from eligibility
4. Result: No call placed (respects preference)

Alternative flow (if SQL filter missed):
1. Check enrollment channel: device
2. Device validation: FAILED (no active device)
3. Phone selector: ❌ Returns None (no fallback)
4. Log: "⚠️ INELIGIBLE: No fallback - respecting member preference"
5. Result: No call placed
```

---

## 🔄 Rollback Plan

### If Issues Arise

**Database Rollback:**
```sql
-- Clear enrollment channel values (revert to member-level)
UPDATE mce
SET mce.channel = NULL
FROM engage360.member_campaign_enrollments_enhanced mce
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'
);
```

**Code Rollback:**
```bash
# Revert to previous commit
git checkout HEAD~1 -- af_code/af_dtc_logic.py
git checkout HEAD~1 -- af_code/af_dtc_intro_call/utils/config.py
git checkout HEAD~1 -- af_code/af_dtc_intro_call/utils/phone_selector.py
git checkout HEAD~1 -- af_code/partner_campaign_scheduler/services/batch_orchestrator.py

# Redeploy
func azure functionapp publish IOE-function --python
```

---

## 📋 Success Criteria

### Must Pass (Before Declaring Success)

- ✅ Database migration completes without errors
- ✅ Verification query shows 0 NULL channels
- ✅ Test CSV upload creates enrollments with correct channel values
- ✅ Eligibility queries return expected members
- ✅ No unexpected errors in Application Insights
- ✅ "INELIGIBLE" warnings appear with clear reasons
- ✅ NO "Using fallback" messages in logs

### Acceptable Outcomes

- ⚠️ Call volume decreases (expected)
- ⚠️ More "INELIGIBLE" warnings (expected)
- ✅ Zero member complaints about unwanted calls

---

## 🆘 Troubleshooting

### Issue 1: High number of "INELIGIBLE" warnings

**Cause:** Members with device preference but no active device
**Action:**
1. Query database to count affected members
2. Assess if data quality issue (devices not marked 'In Service')
3. If expected, communicate to operations team

**Query:**
```sql
SELECT COUNT(*) AS ineligible_device_members
FROM engage360.member_campaign_enrollments_enhanced mce
JOIN engage360.members m ON mce.member_id = m.member_id
LEFT JOIN engage360.member_devices md
    ON mce.member_id = md.member_id
    AND md.service_status = 'In Service'
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'
)
AND mce.channel = 'device'
AND md.device_id IS NULL;
```

### Issue 2: Call volume drops significantly (>50%)

**Cause:** Possible data quality issue or unexpected device status
**Action:**
1. Check device status distribution
2. Verify `service_status` values in `member_devices` table
3. Review recent device status changes

**Query:**
```sql
SELECT
    md.service_status,
    COUNT(*) AS device_count
FROM engage360.member_devices md
JOIN engage360.member_campaign_enrollments_enhanced mce
    ON md.member_id = mce.member_id
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'
)
AND mce.channel = 'device'
GROUP BY md.service_status;
```

### Issue 3: CSV processing fails

**Cause:** Missing `channel_type_clean` field in staging table
**Action:**
1. Verify staging table schema has `channel_type_clean` column
2. Check DTC file processor logs for validation errors
3. Ensure test CSV has `channel_type` column

---

## 📞 Support Contacts

**Database Issues:**
- DBA Team: [Contact Info]
- Escalation: IT Operations

**Code Deployment Issues:**
- AI-POD Team - Data Science
- DevOps Team: [Contact Info]

**Production Monitoring:**
- Operations Team: [Contact Info]
- On-Call: [Contact Info]

---

## 📚 Additional Resources

- **Implementation Summary:** `IMPLEMENTATION_SUMMARY_ENROLLMENT_CHANNEL_MIGRATION.md`
- **Database Schema:** `database/Context Engage360 schema.txt`
- **Project Instructions:** `CLAUDE.md`
- **Partner Campaign Reference:** `PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md`
- **Validation Tests:** `test_enrollment_channel_migration.py`

---

**Deployment Timeline:**

| Phase | Duration | Responsible Team |
|-------|----------|------------------|
| Database Migration | 15 min | DBA Team |
| Code Deployment | 30 min | DevOps Team |
| Verification | 1 hour | QA Team |
| Monitoring | 24-48 hours | Operations Team |

**Total:** ~2 hours active work + 48 hours monitoring

---

**Last Updated:** 2026-02-13
**Prepared By:** Claude Code
**Review Status:** Ready for deployment

---

## ✅ Pre-Deployment Checklist

- [ ] Database backup completed
- [ ] Migration script reviewed by DBA team
- [ ] Operations team notified of potential call volume change
- [ ] Test CSV file prepared
- [ ] Rollback plan documented and reviewed
- [ ] On-call team alerted
- [ ] Application Insights queries configured
- [ ] All quality checks passed

**Once all boxes checked, proceed with deployment.**
