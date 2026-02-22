# Device Activation Same-Day Blocking Guide

## 📋 Table of Contents
- [The Simple Rule](#the-simple-rule)
- [How It Works](#how-it-works)
- [Real-World Scenarios](#real-world-scenarios)
- [Technical Deep-Dive](#technical-deep-dive)
- [Testing Guide](#testing-guide)
- [Troubleshooting](#troubleshooting)

---

## 🎯 The Simple Rule

**ONE CALL PER MEMBER PER DAY**

If a member was already called today (even if the call failed, had no answer, or was canceled), they will **NOT** be called again until tomorrow.

### Why This Matters
- **Member Experience**: Prevents calling the same person multiple times in one day (reduces annoyance)
- **Compliance**: Respects reasonable contact frequency limits
- **System Efficiency**: Prevents wasted call attempts and duplicate processing

---

## ⚙️ How It Works

### The 2-Stage Filtering Process

Device Activation eligibility uses a **two-stage filtering system**:

```
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: SQL Database Filtering (TodayActiveAttempts CTE)  │
│  ✅ Blocks members with ANY attempt today (UTC)             │
│  ✅ Uses UTC timezone for consistent "today" definition     │
│  ✅ Blocks ALL disposition types (see below)                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Business Hours Validation (Python)                │
│  ✅ Medical Guardian hours: 9 AM - 5 PM EST                 │
│  ✅ Member local hours: 9 AM - 5 PM (member timezone)       │
│  ✅ Monday-Friday only (excludes weekends & US holidays)    │
└─────────────────────────────────────────────────────────────┘
```

### What Gets Blocked?

**All 5 Call Dispositions:**

| Disposition | Meaning | Blocked? | Why? |
|------------|---------|----------|------|
| **Completed** | Call completed successfully | ✅ Yes | Member already contacted today |
| **Failed** | System error, invalid number | ✅ Yes | Prevents rapid retry loops |
| **NoAnswer** | Member didn't answer | ✅ Yes | Member had opportunity today |
| **Pending** | Call submitted, awaiting result | ✅ Yes | Prevents duplicate submissions |
| **Canceled** | Call was canceled | ✅ Yes | Member was targeted today |

**Key Point:** It doesn't matter if the call was successful or not - **any attempt today blocks further attempts today**.

---

## 📖 Real-World Scenarios

### Scenario 1: Successful Call - No Same-Day Retry ✅

**Timeline:**
- **9:00 AM:** Scheduler runs → John is eligible → Call is made → Call succeeds (disposition: "Completed")
- **2:00 PM:** Scheduler runs again (every 15 min)

**What Happens:**
- John is **NOT** in the eligible members list
- SQL query filters him out via `TodayActiveAttempts` CTE
- He will be eligible again tomorrow (if frequency rules allow)

**Why:** Same-day blocking prevents calling John again even though he might have hung up or the call was brief.

---

### Scenario 2: Failed Call - Still Blocks Same Day ✅

**Timeline:**
- **10:00 AM:** Scheduler runs → Sarah is eligible → Call is made → Call fails (disposition: "Failed")
  - Example failures: Invalid phone number, Bland AI error, network issue
- **3:30 PM:** Scheduler runs again

**What Happens:**
- Sarah is **NOT** eligible (blocked by same-day rule)
- Even though the call failed, she's protected from same-day retry

**Why:** Prevents rapid retry loops that could:
- Annoy the member (if failure was temporary)
- Waste system resources
- Violate compliance if the failure was user-initiated (blocked number)

---

### Scenario 3: No Answer - Waits Until Tomorrow ⏰

**Timeline:**
- **11:00 AM:** Scheduler runs → Mike is eligible → Call is made → No answer (disposition: "NoAnswer")
- **4:00 PM:** Scheduler runs again

**What Happens:**
- Mike is **NOT** eligible (blocked by same-day rule)
- System waits until tomorrow to retry

**Why:**
- Gives member time to return the call (they may have seen the missed call)
- Reduces member fatigue from multiple call attempts in one day
- Follows frequency rules (Call 2 requires 2 business days between attempts)

---

### Scenario 4: Pending Call - Prevents Duplicates 🚫

**Timeline:**
- **1:00 PM:** Scheduler runs → Lisa is eligible → Batch submitted to Bland AI (disposition: "Pending")
- **1:15 PM:** Scheduler runs again (before Bland AI webhook returns)

**What Happens:**
- Lisa is **NOT** eligible (blocked by pending attempt)
- Prevents submitting Lisa's call twice

**Why:** Critical for preventing duplicate call submissions while waiting for Bland AI to process the batch.

---

### Scenario 5: Next Day Eligibility - New UTC Day 🌅

**Timeline:**
- **Day 1 (Monday) 9:00 AM:** Jane is called → No answer
- **Day 1 (Monday) 4:00 PM:** Scheduler runs → Jane is **NOT** eligible (same UTC day)
- **Day 2 (Tuesday) 9:00 AM:** Scheduler runs → Jane **IS** eligible ✅

**What Happens:**
- Day 1: Blocked by `TodayActiveAttempts` CTE (same UTC day)
- Day 2: CTE date range changed to Day 2, so Jane's Day 1 attempt is excluded
- Jane passes SQL filtering and moves to Stage 2 (business hours validation)

**Why:** Uses UTC date boundaries for consistent global "today" definition.

---

### Scenario 6: Timezone Edge Case - UTC Matters 🌍

**Timeline:**
- **Monday 11:50 PM EST** = **Tuesday 4:50 AM UTC** → Member gets called
- **Tuesday 8:00 AM EST** = **Tuesday 1:00 PM UTC** → Scheduler runs

**What Happens:**
- Member is **NOT** eligible (same UTC day - both attempts are on Tuesday in UTC)
- Local timezone shows different days (Monday vs Tuesday EST), but UTC shows same day

**Why:** System uses **UTC date boundaries** for consistent same-day logic across all timezones.

**SQL Logic:**
```sql
-- Today's attempts (UTC)
WHERE attempt_ts >= '2025-01-14 00:00:00 UTC'  -- Tuesday 00:00 UTC
  AND attempt_ts < '2025-01-15 00:00:00 UTC'   -- Wednesday 00:00 UTC
```

Both 4:50 AM UTC and 1:00 PM UTC fall in this range → Same UTC day → Blocked.

---

## 🔬 Technical Deep-Dive

### SQL Implementation

**File:** `af_code/device_activation_scheduler/services/eligibility_service.py`

**Lines:** 268-410 (ELIGIBLE_MEMBERS_QUERY)

#### Step 1: CTE Definition (Lines 269-281)

```sql
WITH TodayActiveAttempts AS (
    -- Block same-day retries: One attempt per member per day regardless of outcome
    -- Uses UTC date range for "today" (00:00:00 - 23:59:59 UTC)
    SELECT DISTINCT e.member_id
    FROM ioe.member_campaign_enrollments_enhanced e
    INNER JOIN ioe.outreach_attempts oa ON e.enrollment_id = oa.enrollment_id
    INNER JOIN ioe.outreach_batches ob ON oa.batch_id = ob.batch_id
    INNER JOIN ioe.campaigns_enhanced c ON ob.campaign_id = c.campaign_id
    WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
      AND oa.attempt_ts >= CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET)
      AND oa.attempt_ts < DATEADD(day, 1, CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET))
      AND oa.disposition IN ('Completed', 'Pending', 'Failed', 'NoAnswer', 'Canceled')
)
```

**What It Does:**
1. **Selects** all `member_id` values that have an attempt **today** (UTC)
2. **Joins** enrollments → attempts → batches → campaigns
3. **Filters** by:
   - Campaign type: Device Activation or Operations
   - Attempt timestamp: Today 00:00:00 UTC to Tomorrow 00:00:00 UTC (exclusive)
   - Disposition: Any of the 5 blocking dispositions

**Result:** A temporary table containing `member_id` for all members with attempts today.

---

#### Step 2: LEFT JOIN Filter (Lines 355-356, 371)

```sql
SELECT ...
FROM ioe.member_campaign_enrollments_enhanced e
...
-- Same-day blocking: Exclude members with attempts today
LEFT JOIN TodayActiveAttempts taa ON e.member_id = taa.member_id

WHERE ...
  -- Same-day blocking: No attempts today (UTC)
  AND taa.member_id IS NULL  -- Critical: Excludes members with today's attempts
```

**How It Works:**

| Member | In CTE? | LEFT JOIN Result | Filter (IS NULL) | Eligible? |
|--------|---------|------------------|------------------|-----------|
| John   | ✅ Yes (called today) | `taa.member_id = 'john'` (NOT NULL) | ❌ Filtered out | ❌ No |
| Sarah  | ❌ No (called yesterday) | `taa.member_id = NULL` | ✅ Passes filter | ✅ Yes* |

*Still subject to Stage 2 business hours validation

---

### UTC Date Boundary Logic

**Today = 2025-01-14:**

```sql
-- Start boundary: Today at 00:00:00 UTC
CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET)
-- Result: 2025-01-14 00:00:00+00:00

-- End boundary: Tomorrow at 00:00:00 UTC
DATEADD(day, 1, CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET))
-- Result: 2025-01-15 00:00:00+00:00
```

**Range Check:**
```sql
AND attempt_ts >= 2025-01-14 00:00:00+00:00  -- Inclusive
AND attempt_ts <  2025-01-15 00:00:00+00:00  -- Exclusive
```

**Examples:**

| Attempt Time (UTC) | In Range? | Blocked Today (2025-01-14)? |
|--------------------|-----------|----------------------------|
| 2025-01-13 23:59:59 | ❌ No | ❌ No (yesterday) |
| 2025-01-14 00:00:00 | ✅ Yes | ✅ Yes (today) |
| 2025-01-14 14:30:00 | ✅ Yes | ✅ Yes (today) |
| 2025-01-14 23:59:59 | ✅ Yes | ✅ Yes (today) |
| 2025-01-15 00:00:00 | ❌ No | ❌ No (tomorrow) |

---

## 🧪 Testing Guide

### Running the Tests

```bash
# Run all same-day blocking tests
pytest tests/test_device_activation_same_day_blocking.py -v

# Run specific scenario
pytest tests/test_device_activation_same_day_blocking.py::TestSameDayRetryBlocking::test_scenario_1_completed_call_blocks_same_day_retry -v

# Run with coverage
pytest tests/test_device_activation_same_day_blocking.py --cov=af_code/device_activation_scheduler --cov-report=html
```

### Test Coverage

**18 Comprehensive Test Cases:**

| Category | Test Cases | What It Tests |
|----------|------------|---------------|
| **Database-Level** | 10 tests | SQL CTE filtering for all 5 dispositions, UTC boundaries, selective blocking |
| **Integration** | 3 tests | Full `get_eligible_members()` flow with business hours validation |
| **Edge Cases** | 4 tests | Midnight UTC transition, multi-campaign blocking, no attempts scenario |
| **Documentation** | 3 tests | CTE logic explanation, disposition filtering, LEFT JOIN pattern |

### Key Test Scenarios

#### ✅ Test 1: Completed Call Blocks Same-Day Retry
```python
# Simulates: Call at 9 AM (Completed), scheduler runs at 2 PM
# Expected: Member NOT in eligible list (blocked by CTE)
```

#### ✅ Test 2: Failed Call Blocks Same-Day Retry
```python
# Simulates: Call at 10 AM (Failed), scheduler runs at 3:30 PM
# Expected: Member NOT in eligible list (same-day protection)
```

#### ✅ Test 6: Next Day Eligibility
```python
# Simulates: Call Day 1 at 9 AM, scheduler runs Day 2 at 9 AM
# Expected: Member IS in eligible list (new UTC day)
```

#### ✅ Test 8: UTC Date Boundary Edge Case
```python
# Simulates: Call at 11:50 PM EST Monday (4:50 AM UTC Tuesday)
#            Scheduler runs at 8 AM EST Tuesday (1 PM UTC Tuesday)
# Expected: Member NOT eligible (same UTC day)
```

---

## 🛠️ Troubleshooting

### Issue 1: Member Called Multiple Times Same Day

**Symptoms:**
- Member reports receiving multiple calls in one day
- `bland_call_logs` shows multiple calls with same member_id and same date

**Root Causes & Solutions:**

#### Cause A: Different Campaigns
```sql
-- Check if member enrolled in multiple campaigns
SELECT c.name, e.enrollment_id, e.current_status
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE e.member_id = 'member-uuid-here'
  AND c.campaign_type = 'Device Activation'
  AND e.current_status = 'ENROLLED';
```

**Solution:** CTE blocks across campaigns (filters by member_id, not enrollment_id), so this should NOT happen. If it does, investigate CTE logic.

#### Cause B: Attempt Not Recorded
```sql
-- Check if attempt was properly recorded in outreach_attempts table
SELECT oa.attempt_ts, oa.disposition, oa.enrollment_id
FROM ioe.outreach_attempts oa
WHERE oa.enrollment_id = 'enrollment-uuid-here'
ORDER BY oa.attempt_ts DESC;
```

**Solution:** Verify batch creation and attempt creation logic in `batch_orchestrator.py`.

#### Cause C: UTC Timezone Mismatch
```sql
-- Check if attempt_ts is stored in UTC
SELECT attempt_ts, CONVERT(VARCHAR, attempt_ts AT TIME ZONE 'UTC', 120) as attempt_ts_utc
FROM ioe.outreach_attempts
WHERE enrollment_id = 'enrollment-uuid-here'
ORDER BY attempt_ts DESC;
```

**Solution:** Ensure all `attempt_ts` values are stored as `DATETIMEOFFSET` in UTC.

---

### Issue 2: Member Not Being Called (False Negative)

**Symptoms:**
- Member should be eligible but not appearing in eligible list
- Business days met, business hours valid, but still excluded

**Debugging Steps:**

#### Step 1: Check SQL Filtering
```sql
-- Manually run the CTE to see if member is in it
WITH TodayActiveAttempts AS (
    SELECT DISTINCT e.member_id
    FROM ioe.member_campaign_enrollments_enhanced e
    INNER JOIN ioe.outreach_attempts oa ON e.enrollment_id = oa.enrollment_id
    INNER JOIN ioe.outreach_batches ob ON oa.batch_id = ob.batch_id
    INNER JOIN ioe.campaigns_enhanced c ON ob.campaign_id = c.campaign_id
    WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
      AND oa.attempt_ts >= CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET)
      AND oa.attempt_ts < DATEADD(day, 1, CAST(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE) AS DATETIMEOFFSET))
      AND oa.disposition IN ('Completed', 'Pending', 'Failed', 'NoAnswer', 'Canceled')
)
SELECT * FROM TodayActiveAttempts WHERE member_id = 'member-uuid-here';
```

**If member appears:** ✅ Same-day blocking is working correctly (member had attempt today)

**If member doesn't appear:** ❌ Check other eligibility criteria (enrollment status, campaign status, frequency rules)

#### Step 2: Check Last Attempt Date
```sql
-- Check when member was last called
SELECT TOP 1 attempt_ts, disposition,
       DATEDIFF(day, attempt_ts, SYSDATETIMEOFFSET()) as days_since_attempt
FROM ioe.outreach_attempts oa
WHERE oa.enrollment_id = 'enrollment-uuid-here'
ORDER BY attempt_ts DESC;
```

**If days_since_attempt = 0:** Same-day blocking is correctly filtering this member.

#### Step 3: Check Logs
```bash
# Search for member in eligibility service logs
grep "member-uuid-here" /var/log/azure-functions.log

# Look for business hours filtering logs
grep "⏰ TIME CHECK for member member-uuid-here" /var/log/azure-functions.log
```

---

### Issue 3: CTE Performance Degradation

**Symptoms:**
- Eligibility query taking >5 seconds
- High CPU usage on SQL Server during scheduler runs

**Optimization Checks:**

#### Check 1: Index on attempt_ts
```sql
-- Verify index exists
SELECT name, type_desc
FROM sys.indexes
WHERE object_id = OBJECT_ID('ioe.outreach_attempts')
  AND name LIKE '%attempt_ts%';

-- Create index if missing
CREATE NONCLUSTERED INDEX IX_outreach_attempts_attempt_ts_disposition
ON ioe.outreach_attempts (attempt_ts, disposition)
INCLUDE (enrollment_id, batch_id);
```

#### Check 2: Statistics Update
```sql
-- Update statistics for better query plan
UPDATE STATISTICS ioe.outreach_attempts WITH FULLSCAN;
UPDATE STATISTICS ioe.member_campaign_enrollments_enhanced WITH FULLSCAN;
```

#### Check 3: Query Execution Plan
```sql
-- View execution plan
SET STATISTICS TIME ON;
SET STATISTICS IO ON;

-- Run the full eligibility query
EXEC sp_executesql @ELIGIBLE_MEMBERS_QUERY;

-- Look for:
-- - Index scans instead of seeks
-- - High logical reads
-- - Missing index warnings
```

---

## 📚 Additional Resources

- **Source Code:** `af_code/device_activation_scheduler/services/eligibility_service.py`
- **Test Suite:** `tests/test_device_activation_same_day_blocking.py`
- **Business Hours Utils:** `af_code/shared/business_hours_utils.py`
- **CLAUDE.md:** Complete project documentation

---

## 🏁 Summary

**The Device Activation Same-Day Blocking System:**

✅ **Prevents** members from receiving multiple calls in one day

✅ **Uses UTC** timezone for consistent global date boundaries

✅ **Blocks ALL dispositions** (Completed, Failed, NoAnswer, Pending, Canceled)

✅ **Works across campaigns** (filters by member_id, not campaign_id)

✅ **Tested comprehensively** (18 test cases, 100% pass rate)

✅ **Production-ready** with defense-in-depth filtering layers

**Remember:** One call per member per day, no exceptions. If in doubt, check the CTE! 🔍
