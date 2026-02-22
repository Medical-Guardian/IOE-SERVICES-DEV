# Intro → Wellness Channel Copy Implementation Summary

**Date:** 2026-02-16  
**Status:** ✅ Implementation Complete  
**BusinessCaseID:** BC-DTC-CHANNEL-TRANSITION  
**Impact:** Channel preference now persists from intro to wellness campaigns

---

## 🎯 Overview

Successfully implemented channel preference copying during DTC intro → wellness auto-transition. When a member completes an intro call successfully, both `preferred_window` AND `channel` are now copied from the intro enrollment to the wellness enrollment.

### Why This Change?

**Problem:** Previously, only `preferred_window` was copied during auto-transition. The `channel` field (phone vs device) was not transferred, causing:
- Loss of member's channel preference when transitioning to wellness
- Wellness calls might use wrong contact method
- Inconsistent member experience between intro and wellness campaigns

**Solution:** Copy `channel` along with `preferred_window` during intro → wellness transition.

---

## 📋 Changes Made

### File Modified: `af_code/bland_ai_webhook/services/database_orchestrator.py`

**Two locations updated:**
1. **Inline auto-transition logic** (lines 490-635)
2. **Method: `_handle_campaign_auto_transition`** (lines 712-860)

### Specific Changes:

#### 1. **Fetch `channel` from Intro Enrollment**

**Added to SELECT query:**
```python
get_intro_data_q = """
    SELECT current_status, preferred_window, channel  -- ✅ Added channel
    FROM engage360.member_campaign_enrollments_enhanced 
    WHERE member_id = %s AND campaign_id = %s
"""
```

**Added to variable extraction:**
```python
channel = intro_data[0].get("channel")  # ✅ New
logger.info(f"📊 [DB-ORCH]   - Channel: {channel}")  # ✅ New
```

---

#### 2. **Update MERGE Query**

**Updated source CTE:**
```sql
USING (SELECT %s as member_id, %s as campaign_id, %s as new_status, %s as preferred_window, %s as channel) AS src
-- ✅ Added channel parameter
```

**Updated WHEN MATCHED:**
```sql
WHEN MATCHED THEN
    UPDATE SET 
        current_status = src.new_status, 
        last_attempt_ts = SYSDATETIMEOFFSET(),
        channel = ISNULL(src.channel, tgt.channel)  -- ✅ New: Update channel if provided
```

**Updated WHEN NOT MATCHED:**
```sql
INSERT (enrollment_id, member_id, campaign_id, enrollment_ts, current_status, last_attempt_ts, preferred_window, channel)
VALUES (NEWID(), src.member_id, src.campaign_id, SYSDATETIMEOFFSET(), src.new_status, SYSDATETIMEOFFSET(), src.preferred_window, src.channel);
-- ✅ Added channel to INSERT
```

---

#### 3. **Update Query Execution**

**Added channel parameter:**
```python
wellness_rows = self.db_service.execute_query(
    wellness_upsert_q,
    (member_id, WELLNESS_CAMPAIGN_ID, "ENROLLED", preferred_window, channel),  # ✅ Added channel
    fetch_results=False,
)
```

**Updated logging:**
```python
logger.info(
    f"🔧 [DB-ORCH] Copying from intro campaign {campaign_id}: preferred_window='{preferred_window}', channel='{channel}'"
)
```

---

#### 4. **Update Audit Logs**

**Intro campaign audit log:**
```python
change_details=f"Intro call successful - auto-transition to wellness campaign (copied: preferred_window='{preferred_window}', channel='{channel}')"
```

**Wellness campaign audit log:**
```python
change_details=f"Auto-transitioned from intro campaign after successful call (inherited: preferred_window='{preferred_window}', channel='{channel}')"
```

---

## 📊 Data Flow

### Before (Old Behavior):
```
Intro Enrollment:
  - status: ENROLLED
  - preferred_window: 'morning'
  - channel: 'device'
              ↓ (auto-transition)
Wellness Enrollment:
  - status: ENROLLED
  - preferred_window: 'morning'  ← Copied ✅
  - channel: NULL or old value   ← NOT copied ❌
```

### After (New Behavior):
```
Intro Enrollment:
  - status: ENROLLED
  - preferred_window: 'morning'
  - channel: 'device'
              ↓ (auto-transition)
Wellness Enrollment:
  - status: ENROLLED
  - preferred_window: 'morning'  ← Copied ✅
  - channel: 'device'            ← Copied ✅
```

---

## 🧪 Testing Strategy

### 1. Unit Tests

**Test Cases to Validate:**

```python
def test_intro_to_wellness_copies_channel_phone():
    """Verify channel='phone' is copied from intro to wellness"""
    # Given: Intro enrollment with channel='phone'
    # When: Auto-transition occurs
    # Then: Wellness enrollment has channel='phone'

def test_intro_to_wellness_copies_channel_device():
    """Verify channel='device' is copied from intro to wellness"""
    # Given: Intro enrollment with channel='device'
    # When: Auto-transition occurs
    # Then: Wellness enrollment has channel='device'

def test_intro_to_wellness_copies_channel_null():
    """Verify channel=NULL is handled correctly"""
    # Given: Intro enrollment with channel=NULL
    # When: Auto-transition occurs
    # Then: Wellness enrollment has channel=NULL

def test_wellness_channel_update_on_retransition():
    """Verify existing wellness channel is updated if different"""
    # Given: Wellness has channel='phone', Intro has channel='device'
    # When: Auto-transition occurs
    # Then: Wellness channel updated to 'device'
```

---

### 2. Integration Testing

**Test Scenario 1: Phone Channel Member**
```
Setup:
  1. Create intro enrollment: channel='phone', preferred_window='morning'
  2. Trigger webhook with status=ENROLLED

Verify:
  1. Intro enrollment: status='UNENROLLED'
  2. Wellness enrollment: status='ENROLLED', channel='phone', preferred_window='morning'
  3. Audit logs mention both fields in change_details
```

**Test Scenario 2: Device Channel Member**
```
Setup:
  1. Create intro enrollment: channel='device', preferred_window='evening'
  2. Trigger webhook with status=ENROLLED

Verify:
  1. Wellness enrollment: channel='device', preferred_window='evening'
  2. Member will be called via device phone in wellness campaign
```

---

### 3. Database Validation Queries

**Verify Channel Alignment:**
```sql
-- Check that intro channel matches wellness channel after transition
SELECT 
    m.salesforce_account_number,
    m.first_name,
    m.last_name,
    intro.channel AS intro_channel,
    intro.preferred_window AS intro_window,
    intro.current_status AS intro_status,
    wellness.channel AS wellness_channel,
    wellness.preferred_window AS wellness_window,
    wellness.current_status AS wellness_status
FROM engage360.members m
LEFT JOIN engage360.member_campaign_enrollments_enhanced intro 
    ON m.member_id = intro.member_id 
    AND intro.campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'  -- Intro
LEFT JOIN engage360.member_campaign_enrollments_enhanced wellness 
    ON m.member_id = wellness.member_id 
    AND wellness.campaign_id = 'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'  -- Wellness
WHERE intro.current_status = 'UNENROLLED'
  AND wellness.current_status = 'ENROLLED'
  AND wellness.enrollment_ts > DATEADD(day, -7, GETDATE())
ORDER BY wellness.enrollment_ts DESC;

-- Expected: intro_channel = wellness_channel for all recent transitions
```

**Verify Audit Trail:**
```sql
-- Check audit logs include channel in change_details
SELECT TOP 20
    h.member_id,
    c.name AS campaign_name,
    h.previous_status,
    h.new_status,
    h.change_details,  -- Should mention "channel='...'"
    h.change_timestamp
FROM engage360.member_enrollment_status_history h
JOIN engage360.campaigns_enhanced c ON h.campaign_id = c.campaign_id
WHERE h.change_source = 'WEBHOOK'
  AND h.change_details LIKE '%channel=%'
  AND h.change_timestamp > DATEADD(day, -7, GETDATE())
ORDER BY h.change_timestamp DESC;
```

---

## 🔍 Edge Cases Handled

| Edge Case | Behavior | Rationale |
|-----------|----------|-----------|
| **channel = NULL in intro** | Copy NULL to wellness | Maintain consistency; NULL = "use default" |
| **Wellness exists with different channel** | Overwrite with intro's channel | Intro is most recent source of truth |
| **Invalid channel value** | Copy as-is | Let downstream validation handle it |
| **preferred_window = NULL** | Copy NULL (existing behavior) | Same handling as before |

---

## 📚 Documentation Updated

### Files Modified:

1. **`DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md`**
   - Updated section 5.2 to mention channel is copied along with preferred_window

2. **`INTRO_WELLNESS_CHANNEL_COPY_IMPLEMENTATION.md`** (this file)
   - Complete implementation summary
   - Test cases and validation queries
   - Deployment guidance

---

## 🚀 Deployment Checklist

### Pre-Deployment:
- [x] Code changes implemented in both locations
- [x] Documentation updated
- [ ] Unit tests written and passing
- [ ] Integration tests executed
- [ ] Code review completed

### Deployment:
- [ ] Deploy to staging environment
- [ ] Test with sample webhook payloads
- [ ] Verify database records show channel copied
- [ ] Check Application Insights logs
- [ ] Deploy to production

### Post-Deployment Monitoring:
- [ ] Monitor webhook processing logs
- [ ] Run database validation queries
- [ ] Check for errors in Application Insights
- [ ] Verify member call routing uses correct channel
- [ ] Confirm audit trail shows channel in change_details

---

## 📈 Expected Outcomes

After deployment:

✅ **Channel persistence:** Member's channel preference carries over from intro to wellness  
✅ **Consistent routing:** Wellness calls use same channel as intro calls  
✅ **Audit trail:** Status history logs show channel being copied  
✅ **No data loss:** Channel preference not lost during campaign transition  
✅ **Member experience:** Seamless transition maintains communication preferences

---

## 🎯 Success Metrics

**Week 1 Post-Deployment:**
- 100% of intro → wellness transitions copy channel
- 0 errors in webhook processing related to channel
- Audit logs show channel in 100% of auto-transition records

**Week 2-4 Post-Deployment:**
- Member satisfaction: No complaints about wrong contact method in wellness calls
- Call completion rates: No degradation in wellness call success rates
- Channel distribution: Same ratio of phone/device in wellness as intro

---

## ⚠️ Risks & Mitigation

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| Existing wellness enrollments have wrong channel | Medium | Run backfill script to sync from intro | Planned |
| NULL channel breaks validation | Low | Defensive NULL handling with ISNULL() | Implemented |
| Performance impact | Very Low | Just one extra column in SELECT/INSERT | Minimal |
| Audit logs too verbose | Very Low | Concise log messages | Acceptable |

---

## 🔗 Related Components

### Files Modified:
- `af_code/bland_ai_webhook/services/database_orchestrator.py`

### Documentation Updated:
- `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md`
- `INTRO_WELLNESS_CHANNEL_COPY_IMPLEMENTATION.md` (new)

### Database Tables Affected:
- `engage360.member_campaign_enrollments_enhanced` (READ/WRITE)
- `engage360.member_enrollment_status_history` (WRITE - audit log)

### Related BusinessCaseIDs:
- **BC-ENROLLMENT-CHANNEL-MIGRATION** (enrollment-level channel)
- **BC-DTC-INTRO-WELLNESS** (auto-transition logic)
- **BC-DTC-CHANNEL-ROUTING** (channel-based call routing)

---

## 📞 Support & Questions

For questions or issues related to this implementation:

1. **Code Review:** Check `af_code/bland_ai_webhook/services/database_orchestrator.py`
2. **Logs:** Search Application Insights for "channel=" in DTC webhook logs
3. **Database:** Run validation queries in this document
4. **Documentation:** Refer to `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md`

---

**Implementation Date:** 2026-02-16  
**Implemented By:** AI Assistant  
**Reviewed By:** [Pending]  
**Approved By:** [Pending]
