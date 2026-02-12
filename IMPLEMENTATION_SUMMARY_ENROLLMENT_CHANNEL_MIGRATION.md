# DTC Enrollment-Level Channel Migration - Implementation Summary

**Date:** 2026-02-13
**Status:** ✅ Implementation Complete - Ready for Deployment
**Impact:** DTC campaigns now use enrollment-level channel preferences with strict enforcement (no fallback)

---

## 🎯 Implementation Overview

Successfully migrated DTC campaigns from **member-level channel** (`members.Channel`) to **enrollment-level channel** (`member_campaign_enrollments_enhanced.channel`) and removed all fallback logic when member preferences cannot be honored.

### Key Changes

1. **Database Migration:** Backfill script to populate enrollment channel from member channel
2. **CSV Processing:** DTC files now write `channel_type` → `mce.channel` (enrollment-level)
3. **Eligibility Queries:** Read `mce.channel` + enforce device status validation
4. **Phone Selection:** Remove fallback logic - strict preference enforcement
5. **Logging:** Clear warnings when members are ineligible due to preference constraints

---

## 📋 Files Modified

### 1. Database Migration (NEW)

**File:** `database/backfill_dtc_enrollment_channel.sql`
**Purpose:** Migrate existing DTC enrollments from member-level to enrollment-level channel
**Status:** ✅ Created - Ready to run before code deployment

**What it does:**
- Copies `members.Channel` → `member_campaign_enrollments_enhanced.channel` for all DTC enrollments
- Defaults to `'phone'` if member channel is NULL
- Includes verification queries to confirm success

**Campaigns affected:**
- `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC` (DTC Intro)
- `E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B` (DTC Wellness)

---

### 2. DTC CSV Processing

**File:** `af_code/af_dtc_logic.py`
**Lines Modified:** 2063-2096 (intro), 2146-2167 (wellness)
**Status:** ✅ Updated

**Changes:**
- **Added to source CTE:** `stg.channel_type_clean AS channel`
- **Updated WHEN MATCHED:** `channel = ISNULL(src.channel, tgt.channel)`
- **Updated WHEN NOT MATCHED:** Added `channel` to INSERT statement

**Result:** CSV field `channel_type` now populates `member_campaign_enrollments_enhanced.channel`

---

### 3. DTC Eligibility Queries

**File:** `af_code/af_dtc_intro_call/utils/config.py`
**Lines Modified:** 50-147 (intro), 150-207 (wellness)
**Status:** ✅ Updated

**Changes:**

#### GET_MEMBERS_WITH_ATTEMPTS_QUERY (line 56)
```sql
-- BEFORE:
m.Channel,  -- Member's routing preference (phone/device)

-- AFTER:
mce.channel,  -- Enrollment-level channel (phone/device)
```

#### ELIGIBLE_MEMBERS_QUERY_INTRO & ELIGIBLE_MEMBERS_QUERY_WELLNESS

**Added to SELECT:**
- `mce.channel`
- `md.device_phone_number`
- `md.is_device_callable`

**Added LEFT JOIN:**
```sql
LEFT JOIN engage360.member_devices md
    ON m.member_id = md.member_id
    AND md.service_status = 'In Service'
```

**Added to WHERE clause:**
```sql
AND (
    -- Channel validation: enforce device status
    mce.channel != 'device'  -- Phone channel: always eligible
    OR (mce.channel = 'device' AND md.device_id IS NOT NULL)  -- Device channel: must have active device
)
```

**Result:** Members with `channel='device'` but no active device (`service_status='In Service'`) are excluded from eligibility

---

### 4. DTC Phone Selection - Remove Fallback

**File:** `af_code/af_dtc_intro_call/utils/phone_selector.py`
**Lines Modified:** 61, 68, 111-127
**Status:** ✅ Updated + Formatted (black + ruff)

**Changes:**

**Field name update:**
```python
# BEFORE:
member_channel = member_data.get("Channel")

# AFTER:
member_channel = member_data.get("channel")  # Enrollment-level channel
```

**Removed fallback logic (lines 111-124):**
- ❌ Deleted: Fallback to primary phone if preference not available
- ❌ Deleted: Fallback to device if primary not available

**Added ineligibility logging:**
```python
logger.warning(
    f"⚠️ [PHONE-SELECTOR] Member {member_id} INELIGIBLE: "
    f"Enrollment channel='{member_channel}' but channel unavailable. "
    f"primary_phone={bool(primary_phone)}, "
    f"device_phone={bool(device_phone)}, "
    f"device_callable={bool(is_callable)}. "
    f"No fallback - respecting member preference."
)
return None
```

**Result:** DTC campaigns strictly respect enrollment channel - no fallback calls

---

### 5. Partner Phone Selection - Remove Fallback

**File:** `af_code/partner_campaign_scheduler/services/batch_orchestrator.py`
**Lines Modified:** 729-755
**Status:** ✅ Updated

**Changes:**

**Removed fallback logic (lines 729-755):**
- ❌ Deleted: Fallback to primary phone
- ❌ Deleted: Fallback to device if callable

**Added ineligibility logging:**
```python
logger.warning(
    f"⚠️ [BATCH-ORCHESTRATOR] Member {member.member_id} INELIGIBLE: "
    f"Enrollment channel='{member.channel}' but channel unavailable. "
    f"primary_phone={bool(member.primary_phone)}, "
    f"device_phone={bool(member.device_phone_number)}, "
    f"device_callable={bool(member.is_device_callable)}. "
    f"No fallback - respecting enrollment preference."
)
return None
```

**Result:** Partner campaigns also strictly respect enrollment channel (consistent behavior across all campaigns)

---

## ✅ Quality Checks

All code quality checks passed:

```bash
✅ Black formatting: PASSED (4 files)
✅ Ruff linting: PASSED (4 files)
```

**Files verified:**
- `af_code/af_dtc_logic.py`
- `af_code/af_dtc_intro_call/utils/config.py`
- `af_code/af_dtc_intro_call/utils/phone_selector.py`
- `af_code/partner_campaign_scheduler/services/batch_orchestrator.py`

---

## 🚀 Deployment Checklist

### Pre-Deployment (Database Migration)

- [ ] **Backup database:** Full backup of `engage360` schema
- [ ] **Run migration script:** `database/backfill_dtc_enrollment_channel.sql`
- [ ] **Verify migration success:** Check verification queries (should show 0 NULL channels)
- [ ] **Notify operations:** "Call volume may decrease - expected behavior (strict preference enforcement)"

**Estimated time:** 15 minutes

### Code Deployment

- [ ] **Deploy Azure Functions:** `func azure functionapp publish IOE-function --python`
- [ ] **Verify function registration:** Check logs for successful blueprint registration
- [ ] **Upload test CSV:** Test DTC file with `channel_type` field
- [ ] **Verify enrollment creation:** Query `member_campaign_enrollments_enhanced.channel` for test members
- [ ] **Check batch orchestrator logs:** Next scheduler run (verify no fallback messages)

**Estimated time:** 30 minutes

### Post-Deployment Monitoring (24-48 hours)

- [ ] **Application Insights:** Monitor "INELIGIBLE" warnings
- [ ] **Call volume comparison:** Compare batch sizes before/after deployment
- [ ] **Error logs:** Verify zero unexpected errors
- [ ] **Data quality audit:** Review 100 random enrollments

---

## 📊 Expected Behavior Changes

### Before Migration (Member-Level Channel + Fallback)

```
Member prefers device → Device unavailable → ✅ Falls back to phone (unwanted call)
```

### After Migration (Enrollment-Level Channel + No Fallback)

```
Member prefers device → Device unavailable → ❌ No call (respects preference)
```

**Impact:**
- ✅ Members receive calls ONLY on their preferred channel
- ✅ No unwanted phone calls if device preferred
- ✅ Per-campaign channel flexibility (e.g., device for wellness, phone for reminders)
- ⚠️ Call volume may decrease (members with device preference but no active device excluded)

---

## 🔍 Verification Queries

### 1. Database Migration Verification

```sql
-- Check all DTC enrollments have channel values
SELECT
    campaign_id,
    COUNT(*) AS total_enrollments,
    COUNT(CASE WHEN channel IS NOT NULL THEN 1 END) AS with_channel,
    COUNT(CASE WHEN channel = 'phone' THEN 1 END) AS phone_channel,
    COUNT(CASE WHEN channel = 'device' THEN 1 END) AS device_channel
FROM engage360.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
GROUP BY campaign_id;
-- Expected: Zero NULL channels
```

### 2. Device Validation Test

```sql
-- Test device validation logic
SELECT
    mce.enrollment_id,
    mce.channel,
    m.Channel AS member_channel_legacy,
    COUNT(md.device_id) AS active_devices,
    CASE
        WHEN mce.channel = 'device' AND COUNT(md.device_id) = 0 THEN 'INELIGIBLE'
        ELSE 'ELIGIBLE'
    END AS eligibility_status
FROM engage360.member_campaign_enrollments_enhanced mce
JOIN engage360.members m ON mce.member_id = m.member_id
LEFT JOIN engage360.member_devices md
    ON mce.member_id = md.member_id
    AND md.service_status = 'In Service'
WHERE mce.campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'
  AND mce.current_status = 'ENROLLED'
GROUP BY mce.enrollment_id, mce.channel, m.Channel;
```

### 3. Application Insights Queries

```kusto
// Find ineligibility warnings (new behavior)
traces
| where message contains "INELIGIBLE"
| where message contains "No fallback"
| project timestamp, message, customDimensions
| order by timestamp desc
| take 50

// Verify NO fallback logs (should be zero results)
traces
| where message contains "Using fallback"
| where timestamp > ago(1h)
| count
// Expected: 0 results
```

---

## 🔄 Rollback Plan

### If Database Migration Fails

```sql
-- Rollback: Clear enrollment channel values
UPDATE mce
SET mce.channel = NULL
FROM engage360.member_campaign_enrollments_enhanced mce
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'
);
```

### If Code Deployment Breaks Functionality

```bash
# Revert specific files to previous commit
git checkout HEAD~1 -- af_code/af_dtc_logic.py
git checkout HEAD~1 -- af_code/af_dtc_intro_call/utils/config.py
git checkout HEAD~1 -- af_code/af_dtc_intro_call/utils/phone_selector.py
git checkout HEAD~1 -- af_code/partner_campaign_scheduler/services/batch_orchestrator.py

# Redeploy
func azure functionapp publish IOE-function --python
```

---

## 📈 Success Criteria

### Must Pass Before Deployment

- ✅ Database backfill completes successfully
- ✅ Verification query confirms zero NULL channels in DTC enrollments
- ✅ Code quality checks pass (black, ruff)
- ✅ All modified files formatted and linted

### Must Verify After Deployment

- ✅ CSV upload creates enrollments with channel from `channel_type` field
- ✅ Eligibility queries read `mce.channel` instead of `m.Channel`
- ✅ Device validation excludes members with `channel='device'` + no active devices
- ✅ Phone selector returns None (no fallback behavior)
- ✅ Logs show "INELIGIBLE" warnings with clear reasons
- ✅ Logs do NOT show "Using fallback" messages

### Acceptable Outcomes

- ⚠️ Call volume decreases (expected - respecting device preference strictly)
- ⚠️ More "INELIGIBLE" warnings in logs (expected - no fallback behavior)
- ✅ No errors in Application Insights
- ✅ No members receive calls on unwanted channels

---

## 🔑 Key Technical Decisions

### 1. Data Migration Strategy
**Decision:** Copy from `members.Channel` to `mce.channel` during backfill
**Reason:** Safest approach, maintains continuity with existing member preferences

### 2. Fallback Behavior
**Decision:** Remove ALL fallback logic
**Reason:** Respects member preferences strictly, consistent with user requirements

### 3. Device Validation Location
**Decision:** Add to SQL eligibility queries (filter before phone_selector)
**Reason:** Better performance (fewer members to process), clear audit trail

### 4. Logging Approach
**Decision:** WARNING level logs with detailed ineligibility reasons
**Reason:** Operational visibility, troubleshooting support, no database overhead

---

## 📚 Related Documentation

- **Plan:** Full implementation plan in plan mode transcript
- **Database Schema:** `database/Context Engage360 schema.txt`
- **Project Instructions:** `CLAUDE.md` (section on enrollment-level channel)
- **Partner Campaign Reference:** `PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md` (already uses enrollment-level channel)

---

**Implementation completed by:** Claude Code
**Review required by:** AI-POD Team - Data Science
**Deployment target:** IOE-function (Azure Functions v4, Python 3.12)

---

## 🎯 Next Steps

1. **Database team:** Run backfill script on production database
2. **Operations team:** Prepare for potential call volume decrease
3. **DevOps team:** Deploy code to Azure Functions
4. **Monitoring team:** Set up Application Insights alerts for "INELIGIBLE" warnings
5. **QA team:** Verify test CSV upload and enrollment creation

**Estimated total deployment time:** 1 hour active work + 24-48 hours monitoring
