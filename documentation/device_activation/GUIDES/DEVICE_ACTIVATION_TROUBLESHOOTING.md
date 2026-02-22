# Device Activation - Troubleshooting Guide

**Date:** 2025-12-24
**Version:** 1.0
**BusinessCaseIDs:** BC-DA-001 through BC-DA-008
**Audience:** DevOps, Support Engineers, Developers

---

## Table of Contents

1. [Troubleshooting Overview](#1-troubleshooting-overview)
2. [File Processing Issues](#2-file-processing-issues)
3. [Scheduler Issues](#3-scheduler-issues)
4. [Eligibility Query Issues](#4-eligibility-query-issues)
5. [Batch Submission Issues](#5-batch-submission-issues)
6. [Webhook Processing Issues](#6-webhook-processing-issues)
7. [Database Connection Issues](#7-database-connection-issues)
8. [Bland AI Integration Issues](#8-bland-ai-integration-issues)
9. [Performance Issues](#9-performance-issues)
10. [Data Quality Issues](#10-data-quality-issues)
11. [Monitoring & Alerting](#11-monitoring-alerting)
12. [Emergency Procedures](#12-emergency-procedures)

---

## 1. Troubleshooting Overview

### 1.1 General Diagnostic Steps

**Standard troubleshooting workflow:**

1. **Identify the symptom:** What is not working as expected?
2. **Check Application Insights:** Review logs for errors/exceptions
3. **Verify database state:** Query relevant tables to understand data state
4. **Check external dependencies:** Bland AI API, Key Vault, Blob Storage
5. **Reproduce issue:** Attempt to reproduce in lower environment
6. **Apply fix:** Implement solution and verify
7. **Document resolution:** Update this guide if new issue pattern

### 1.2 Quick Diagnostic Commands

**Check Function App Health:**

```bash
# Check all functions status
az functionapp function list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?contains(name, 'device_activation')].{Name:name, Disabled:config.disabled}" -o table

# Check recent function executions
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "requests | where name contains 'device_activation' | top 10 by timestamp desc | project timestamp, name, success, duration" \
  --offset 1h
```

**Check Database Connectivity:**

```sql
-- Test database connection
SELECT @@VERSION;
SELECT SYSDATETIMEOFFSET() AS current_time;

-- Check Key Vault secret retrieval (via Function App logs)
-- Look for: "✅ [CONFIG] Key Vault secret retrieved: SqlConnectionStringIOE"
```

**Check Blob Storage:**

```bash
# List recent files in landing folder
az storage blob list \
  --account-name stioefstorage \
  --container-name fs-ops \
  --prefix landing/ \
  --auth-mode login \
  --query "[].{Name:name, Size:properties.contentLength, Modified:properties.lastModified}" -o table
```

### 1.3 Log Levels and Emoji Prefixes

**Log emoji prefixes used in Device Activation code:**

| Emoji | Meaning | Severity | Example |
|-------|---------|----------|---------|
| ✅ | Success | Info | `✅ [FILE-PROC] CSV validation passed` |
| ⚠️ | Warning | Warning | `⚠️ [ELIGIBILITY] No eligible members found` |
| ❌ | Error | Error | `❌ [BATCH-ORCH] Bland AI submission failed` |
| 🚨 | Critical | Critical | `🚨 [DB] Database connection lost` |
| ℹ️ | Info | Info | `ℹ️ [SCHEDULER] Timer trigger fired` |
| 🔍 | Debug | Debug | `🔍 [CALLBACK] Checking business hours` |

**Search logs by component:**

```kusto
traces
| where message contains "[FILE-PROC]"  // File processing
| where message contains "[SCHEDULER]"  // Scheduler
| where message contains "[ELIGIBILITY]"  // Eligibility service
| where message contains "[BATCH-ORCH]"  // Batch orchestrator
| where message contains "[WEBHOOK]"  // Webhook processing
| where message contains "[CALLBACK]"  // Callback scheduler
| where message contains "[DB]"  // Database operations
```

---

## 2. File Processing Issues

### Issue 2.1: CSV Files Not Processing (Blob Trigger Not Firing)

**Symptoms:**
- CSV uploaded to `fs-ops/landing/` but no processing occurs
- No logs in Application Insights for `device_activation_file_processor`
- File remains in `landing/` folder indefinitely

**Root Causes:**

1. **Blob trigger disabled**
2. **Incorrect filename pattern** (must match: `MedicalGuardian_DeviceActivation_*_Delta.csv`)
3. **Function App connection to storage broken**
4. **Function App stopped or unhealthy**

**Diagnostic Steps:**

```bash
# Step 1: Check if function is enabled
az functionapp function show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_file_processor \
  --query "config.disabled" -o tsv

# Expected: false (function enabled)
# If true: Function is disabled

# Step 2: Check filename pattern
az storage blob list \
  --account-name stioefstorage \
  --container-name fs-ops \
  --prefix landing/ \
  --auth-mode login \
  --query "[].name" -o tsv

# Expected filename: landing/MedicalGuardian_DeviceActivation_20251224_Delta.csv
# If different pattern: File won't trigger

# Step 3: Check storage connection string
az functionapp config appsettings list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?name=='AzureWebJobsStorage'].value" -o tsv

# Should return valid connection string starting with "DefaultEndpointsProtocol=https..."

# Step 4: Check Function App status
az functionapp show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "state" -o tsv

# Expected: Running
```

**Resolution:**

```bash
# Fix 1: Enable function if disabled
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_file_processor \
  --set config.disabled=false

# Fix 2: Rename file to match pattern
az storage blob copy start \
  --account-name stioefstorage \
  --destination-container fs-ops \
  --destination-blob landing/MedicalGuardian_DeviceActivation_20251224_Delta.csv \
  --source-container fs-ops \
  --source-blob landing/wrong_filename.csv \
  --auth-mode login

# Delete old file
az storage blob delete \
  --account-name stioefstorage \
  --container-name fs-ops \
  --name landing/wrong_filename.csv \
  --auth-mode login

# Fix 3: Restart Function App (if unhealthy)
az functionapp restart \
  --name ioe-function \
  --resource-group rg-ioe-prod
```

---

### Issue 2.2: CSV Validation Failures (Pandera Schema Errors)

**Symptoms:**
- File moved to `error/` folder
- Logs show: `❌ [FILE-PROC] Pandera validation failed`
- Error details: Column missing, data type mismatch, or value constraint violation

**Root Causes:**

1. **Missing required column** (e.g., `member_id`, `first_name`, `device_name`)
2. **Data type mismatch** (e.g., `delivery_date` not in YYYY-MM-DD format)
3. **Invalid enum value** (e.g., `device_status` not in allowed list)
4. **Null value in required field**

**Diagnostic Steps:**

```bash
# Step 1: Download error file from blob storage
az storage blob download \
  --account-name stioefstorage \
  --container-name fs-ops \
  --name error/MedicalGuardian_DeviceActivation_20251224_Delta.csv \
  --file /tmp/error_file.csv \
  --auth-mode login

# Step 2: Check Application Insights for detailed error
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Pandera validation' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h
```

**Example Error Log:**

```
❌ [FILE-PROC] Pandera validation failed:
   - Column 'delivery_date' not found in DataFrame
   - Column 'device_status' contains invalid value: 'Unknown' (expected: Activated, Not Activated, Unknown Status)
   - Column 'primary_phone' contains non-E.164 format: '555-1234' (expected: +15551234567)
```

**Resolution:**

**Fix 1: Missing Column**

```python
# Add missing column to CSV (manual fix by data provider)
# Or adjust Pandera schema if column is newly optional

# In af_device_activation_logic.py, update schema:
def get_device_activation_schema() -> pa.DataFrameSchema:
    return pa.DataFrameSchema({
        ...
        "delivery_date": pa.Column(pa.DateTime, nullable=True),  # Make nullable if optional
        ...
    })
```

**Fix 2: Data Type Mismatch**

```python
# Fix date format in CSV
# Wrong: 12/24/2025
# Correct: 2025-12-24

# Or add date parsing to extract() function:
df["delivery_date"] = pd.to_datetime(df["delivery_date"], format="%m/%d/%Y")
```

**Fix 3: Invalid Enum Value**

```python
# Update allowed values in schema
device_status_allowed = ["Activated", "Not Activated", "Unknown Status", "Pending"]  # Add "Pending"

# Or map invalid values:
df["device_status"] = df["device_status"].replace({"Unknown": "Unknown Status"})
```

**Fix 4: Null Value in Required Field**

```python
# Add data cleansing in validate_and_cleanse_data_before_insert():
df["first_name"] = df["first_name"].fillna("Unknown")  # Default value for null
```

---

### Issue 2.3: Staging Load Failures (10% Error Threshold Exceeded)

**Symptoms:**
- Logs show: `❌ [FILE-PROC] Error threshold exceeded: 15.2% > 10%`
- File moved to `error/` folder
- Staging table has rows with `processing_status = 'Failed'`

**Root Causes:**

1. **Database constraint violations** (UNIQUE, FOREIGN KEY, CHECK)
2. **Data type mismatches** (string too long, invalid UUID format)
3. **Connection timeouts** (large file, slow network)

**Diagnostic Steps:**

```sql
-- Step 1: Check staging table for failed rows
SELECT TOP 20
    id,
    member_id_raw,
    processing_status,
    error_message,
    created_at
FROM ioe_stg.stg_device_activation_delta
WHERE processing_status = 'Failed'
ORDER BY created_at DESC;

-- Step 2: Analyze error patterns
SELECT
    error_message,
    COUNT(*) as occurrence_count
FROM ioe_stg.stg_device_activation_delta
WHERE processing_status = 'Failed'
  AND created_at > DATEADD(hour, -1, SYSDATETIMEOFFSET())
GROUP BY error_message
ORDER BY COUNT(*) DESC;

-- Example output:
-- error_message                                           | occurrence_count
-- --------------------------------------------------------|------------------
-- Violation of UNIQUE KEY constraint 'UQ_members_email'  | 120
-- String truncation: member_id exceeds 50 characters     | 45
-- Invalid UUID format: 'abc-123'                         | 12
```

**Resolution:**

**Fix 1: UNIQUE Constraint Violation (Duplicate Member)**

```sql
-- Option A: Update existing member instead of INSERT (change to MERGE)
MERGE ioe.members AS target
USING ioe_stg.stg_device_activation_delta AS source
ON target.member_id = source.member_id_clean
WHEN MATCHED THEN
    UPDATE SET
        first_name = source.first_name_clean,
        last_name = source.last_name_clean,
        updated_at = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (member_id, first_name, last_name, created_at)
    VALUES (source.member_id_clean, source.first_name_clean, source.last_name_clean, SYSDATETIMEOFFSET());

-- Option B: Deduplicate staging data before INSERT
WITH Deduplicated AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY member_id_clean ORDER BY created_at DESC) as rn
    FROM ioe_stg.stg_device_activation_delta
)
INSERT INTO ioe.members (...)
SELECT ... FROM Deduplicated WHERE rn = 1;
```

**Fix 2: String Truncation**

```python
# In af_device_activation_logic.py, add truncation to cleansing:
df["member_id_clean"] = df["member_id_clean"].str[:50]  # Truncate to 50 chars
df["first_name_clean"] = df["first_name_clean"].str[:100]  # Truncate to 100 chars
```

**Fix 3: Invalid UUID Format**

```python
# Add UUID validation and regeneration:
def validate_and_fix_uuid(uuid_str: str) -> str:
    try:
        uuid.UUID(uuid_str)  # Validate format
        return uuid_str
    except ValueError:
        return str(uuid.uuid4())  # Generate new UUID if invalid

df["member_id_clean"] = df["member_id_raw"].apply(validate_and_fix_uuid)
```

**Fix 4: Increase Error Threshold (Temporary)**

```python
# In af_device_activation_logic.py, adjust threshold:
ERROR_THRESHOLD = 0.15  # Increase from 0.10 (10%) to 0.15 (15%)

# WARNING: This is a temporary fix. Root cause should be addressed.
```

---

## 3. Scheduler Issues

### Issue 3.1: Scheduler Not Running (Timer Trigger Not Firing)

**Symptoms:**
- No scheduler logs in Application Insights for 15+ minutes
- No batches created in `outreach_batches` table
- Members remain eligible but not called

**Root Causes:**

1. **Timer trigger disabled**
2. **Function App in stopped state**
3. **Schedule expression incorrect**
4. **Distributed lock stuck** (system_locks table)

**Diagnostic Steps:**

```bash
# Step 1: Check scheduler enabled
az functionapp function show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_scheduler \
  --query "config.disabled" -o tsv

# Expected: false

# Step 2: Check last execution time
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "requests | where name == 'device_activation_scheduler' | top 5 by timestamp desc | project timestamp, success, duration" \
  --offset 1h

# Expected: Executions every 15 minutes

# Step 3: Check schedule expression
grep -A 5 "timer_trigger" functions/device_activation_scheduler.py

# Expected: schedule="0 */15 * * * *"  (every 15 minutes)

# Step 4: Check distributed lock (if using)
# SQL query:
```

```sql
SELECT *
FROM ioe.system_locks
WHERE lock_name = 'device_activation_scheduler'
  AND lock_expiration > SYSDATETIMEOFFSET();

-- If row exists: Lock is still held (may be stuck)
```

**Resolution:**

```bash
# Fix 1: Enable scheduler
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_scheduler \
  --set config.disabled=false

# Fix 2: Start Function App
az functionapp start \
  --name ioe-function \
  --resource-group rg-ioe-prod

# Fix 3: Restart Function App (if schedule not triggering)
az functionapp restart \
  --name ioe-function \
  --resource-group rg-ioe-prod
```

```sql
-- Fix 4: Clear stuck lock
DELETE FROM ioe.system_locks
WHERE lock_name = 'device_activation_scheduler';
```

---

### Issue 3.2: Scheduler Runs But No Batches Created

**Symptoms:**
- Scheduler logs show: `⚠️ [SCHEDULER] No eligible members found`
- `outreach_batches` table has no new rows
- Members exist in `member_campaign_enrollments_enhanced` with `current_status = 'ENROLLED'`

**Root Causes:**

1. **Eligibility query returns 0 results** (too restrictive filters)
2. **Business hours filter excludes all members** (timezone misconfiguration)
3. **Campaign not active** (campaign status, start_ts/end_ts)
4. **All members already in pending batches**

**Diagnostic Steps:**

```bash
# Step 1: Check scheduler logs for details
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains '[SCHEDULER]' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h
```

```sql
-- Step 2: Check enrolled members count
SELECT COUNT(*) as enrolled_members
FROM ioe.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    SELECT campaign_id
    FROM ioe.campaigns_enhanced
    WHERE name LIKE '%Device Activation%'
)
AND current_status = 'ENROLLED';

-- Expected: > 0

-- Step 3: Check activation_start_date distribution
SELECT
    CASE
        WHEN activation_start_date IS NULL THEN 'NULL'
        WHEN activation_start_date > CAST(SYSDATETIMEOFFSET() AS DATE) THEN 'FUTURE'
        ELSE 'PAST_OR_TODAY'
    END AS activation_status,
    COUNT(*) as member_count
FROM ioe.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    SELECT campaign_id
    FROM ioe.campaigns_enhanced
    WHERE name LIKE '%Device Activation%'
)
AND current_status = 'ENROLLED'
GROUP BY
    CASE
        WHEN activation_start_date IS NULL THEN 'NULL'
        WHEN activation_start_date > CAST(SYSDATETIMEOFFSET() AS DATE) THEN 'FUTURE'
        ELSE 'PAST_OR_TODAY'
    END;

-- Expected: Most members in 'PAST_OR_TODAY'
-- If 'FUTURE': activation_start_date not yet reached
-- If 'NULL': activation_start_date not set (file processing issue)

-- Step 4: Check campaign configuration
SELECT
    name,
    campaign_type,
    current_status,
    start_ts,
    end_ts,
    operating_tz,
    operating_start_time,
    operating_end_time
FROM ioe.campaigns_enhanced
WHERE name LIKE '%Device Activation%';

-- Expected:
-- current_status = 'Active'
-- start_ts <= NOW <= end_ts
-- operating_start_time < operating_end_time (e.g., 09:00:00 < 17:00:00)

-- Step 5: Run eligibility query manually (from eligibility_service.py)
-- Copy full SQL query from af_code/device_activation_scheduler/services/eligibility_service.py
-- Execute in SSMS to see actual results
```

**Resolution:**

```sql
-- Fix 1: Set activation_start_date for members with NULL
UPDATE ioe.member_campaign_enrollments_enhanced
SET activation_start_date = CAST(DATEADD(DAY, 2, SYSDATETIMEOFFSET()) AS DATE)  -- delivery_date + 2 days
WHERE activation_start_date IS NULL
  AND campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%');

-- Fix 2: Activate campaign if inactive
UPDATE ioe.campaigns_enhanced
SET current_status = 'Active',
    updated_at = SYSDATETIMEOFFSET()
WHERE name LIKE '%Device Activation%'
  AND current_status != 'Active';

-- Fix 3: Adjust operating hours (if too restrictive)
UPDATE ioe.campaigns_enhanced
SET operating_start_time = '08:00:00',  -- Expand from 9 AM to 8 AM
    operating_end_time = '18:00:00',    -- Expand from 5 PM to 6 PM
    updated_at = SYSDATETIMEOFFSET()
WHERE name LIKE '%Device Activation%';

-- Fix 4: Clear pending batches (if stuck)
UPDATE ioe.outreach_batches
SET batch_status = 'Completed',
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_status IN ('Pending', 'Submitted')
  AND created_at < DATEADD(hour, -2, SYSDATETIMEOFFSET())  -- Older than 2 hours
  AND campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%');
```

---

## 4. Eligibility Query Issues

### Issue 4.1: Eligibility Query Timeout (Slow Performance)

**Symptoms:**
- Scheduler runs but takes 5+ minutes (expected: <1 minute)
- Logs show: `⚠️ [ELIGIBILITY] Query execution time: 320 seconds`
- Application Insights shows high database query duration

**Root Causes:**

1. **Missing indexes** on key tables
2. **Large dataset** (millions of enrollments/attempts)
3. **Inefficient subqueries** (N+1 query pattern)
4. **Database resource constraints** (CPU, memory)

**Diagnostic Steps:**

```sql
-- Step 1: Check table sizes
SELECT
    t.name AS TableName,
    p.rows AS RowCount,
    (SUM(a.total_pages) * 8) / 1024 AS TotalSpaceMB
FROM sys.tables t
INNER JOIN sys.indexes i ON t.object_id = i.object_id
INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE t.name IN (
    'member_campaign_enrollments_enhanced',
    'outreach_attempts',
    'outreach_callback_queue'
)
GROUP BY t.name, p.rows
ORDER BY p.rows DESC;

-- If rows > 1M: Large dataset may need optimization

-- Step 2: Check existing indexes
SELECT
    t.name AS TableName,
    i.name AS IndexName,
    i.type_desc AS IndexType,
    c.name AS ColumnName
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
INNER JOIN sys.tables t ON i.object_id = t.object_id
WHERE t.name IN (
    'member_campaign_enrollments_enhanced',
    'outreach_attempts',
    'outreach_callback_queue'
)
ORDER BY t.name, i.name, ic.key_ordinal;

-- Expected indexes:
-- IX_enrollments_eligibility (current_status, activation_start_date, call_5_timestamp)
-- IX_attempts_enrollment_ts (enrollment_id, attempt_ts)
-- IX_callbacks_pending (status, scheduled_callback_time)

-- Step 3: Analyze query execution plan
SET STATISTICS TIME ON;
SET STATISTICS IO ON;

-- Run eligibility query (copy from eligibility_service.py)
-- Check execution plan for:
-- - Table scans (should be index seeks)
-- - High row counts in intermediate results
-- - Missing index warnings
```

**Resolution:**

```sql
-- Fix 1: Create missing indexes (if not exist)
CREATE NONCLUSTERED INDEX IX_enrollments_eligibility
ON ioe.member_campaign_enrollments_enhanced (
    current_status,
    activation_start_date,
    call_5_timestamp
)
INCLUDE (enrollment_id, member_id, campaign_id, campaign_end_date);

CREATE NONCLUSTERED INDEX IX_attempts_enrollment_ts
ON ioe.outreach_attempts (
    enrollment_id,
    attempt_ts DESC
)
INCLUDE (disposition);

CREATE NONCLUSTERED INDEX IX_callbacks_pending
ON ioe.outreach_callback_queue (
    status,
    scheduled_callback_time
)
INCLUDE (enrollment_id, attempt_count, created_at);

-- Fix 2: Update statistics (ensure index usage)
UPDATE STATISTICS ioe.member_campaign_enrollments_enhanced;
UPDATE STATISTICS ioe.outreach_attempts;
UPDATE STATISTICS ioe.outreach_callback_queue;

-- Fix 3: Optimize subqueries (in eligibility_service.py)
-- Replace correlated subqueries with JOINs or window functions
-- Example:
-- Before (slow):
SELECT enrollment_id,
    (SELECT COUNT(*) FROM outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) as attempt_count
FROM member_campaign_enrollments_enhanced e;

-- After (fast):
SELECT e.enrollment_id,
    COUNT(oa.attempt_id) as attempt_count
FROM member_campaign_enrollments_enhanced e
LEFT JOIN outreach_attempts oa ON e.enrollment_id = oa.enrollment_id
GROUP BY e.enrollment_id;
```

---

### Issue 4.2: Incorrect Call Frequency (Members Called Too Often/Not Often Enough)

**Symptoms:**
- Members called before minimum BUSINESS days elapsed (Calls 1-4 should use business days, not calendar days)
- Call 5+ members called before 7 CALENDAR days elapsed (frequency issue)
- Call 5+ members called on weekends or holidays (should only call on business days)
- Call 5+ members not called after 90 days (should stop at campaign_end_date)

**Root Causes:**

1. **Frequency logic error** in Python business days filtering (eligibility_service.py:666-730)
2. **Call 5+ business day validation missing** - members eligible on weekend/holiday not being filtered (eligibility_service.py:680-695)
3. **call_5_timestamp not set** (batch_orchestrator issue)
4. **campaign_end_date miscalculated** (should be call_5_timestamp + 90 days)
5. ⚠️ **DEPRECATED:** Business days function missing - **NO LONGER USED** (now calculated in Python)
6. ⚠️ **DEPRECATED:** Holidays table missing - **NO LONGER USED** (Python `holidays` library used instead)

**Diagnostic Steps:**

⚠️ **NOTE: Business day filtering now happens in PYTHON, not SQL.**

```sql
-- Step 1: Check recent attempt frequency for specific member
DECLARE @enrollment_id UNIQUEIDENTIFIER = '<enrollment-id-here>';

-- Check attempt history (CALENDAR days only - business days calculated in Python)
SELECT
    attempt_ts,
    DATEDIFF(DAY, LAG(attempt_ts) OVER (ORDER BY attempt_ts), attempt_ts) as calendar_days_since_last,
    disposition,
    ROW_NUMBER() OVER (ORDER BY attempt_ts) as attempt_number
FROM ioe.outreach_attempts
WHERE enrollment_id = @enrollment_id
ORDER BY attempt_ts DESC;

-- ⚠️ Business days calculation removed from SQL - now in Python (eligibility_service.py:666-730)
-- Python code uses get_business_days_between() function to filter:
-- Calls 2-3: business_days >= 2
-- Call 4: business_days >= 5
-- Call 5+: calendar_days >= 7 (frequency), calls ONLY on business days (timing via is_business_day())

-- Step 2: ⚠️ DEPRECATED - dbo.GetBusinessDaysBetween function NO LONGER USED
-- Business day filtering is now in Python code (af_code/shared/business_hours_utils.py)

-- Step 3: ⚠️ DEPRECATED - Holidays table NO LONGER USED
-- Holiday detection uses Python 'holidays' library instead

-- Step 2: Check call_5_timestamp set correctly
SELECT
    e.enrollment_id,
    e.member_id,
    COUNT(oa.attempt_id) as total_attempts,
    e.call_5_timestamp,
    e.campaign_end_date,
    DATEDIFF(DAY, e.call_5_timestamp, e.campaign_end_date) as days_in_window
FROM ioe.member_campaign_enrollments_enhanced e
LEFT JOIN ioe.outreach_attempts oa ON e.enrollment_id = oa.enrollment_id
WHERE e.campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%')
GROUP BY e.enrollment_id, e.member_id, e.call_5_timestamp, e.campaign_end_date
HAVING COUNT(oa.attempt_id) >= 5;

-- Expected:
-- call_5_timestamp: NOT NULL (set when 5th attempt created)
-- days_in_window: 90

-- Step 3: Check eligibility query DATEDIFF logic
-- Review SQL in eligibility_service.py lines 80-140
```

**Resolution:**

```sql
-- Fix 0: Deploy business days function and holidays table (if missing)
-- Run these scripts in order:
-- 1. database/create_business_days_function.sql
-- 2. database/create_us_federal_holidays_table.sql

-- Fix 1: Correct call_5_timestamp for existing enrollments (if missing)
UPDATE e
SET
    e.call_5_timestamp = (
        SELECT attempt_ts
        FROM (
            SELECT attempt_ts,
                ROW_NUMBER() OVER (ORDER BY attempt_ts) as rn
            FROM ioe.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ) ranked
        WHERE rn = 5
    ),
    e.campaign_end_date = DATEADD(DAY, 90, (
        SELECT attempt_ts
        FROM (
            SELECT attempt_ts,
                ROW_NUMBER() OVER (ORDER BY attempt_ts) as rn
            FROM ioe.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ) ranked
        WHERE rn = 5
    ))
FROM ioe.member_campaign_enrollments_enhanced e
WHERE e.campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%')
  AND e.call_5_timestamp IS NULL
  AND (SELECT COUNT(*) FROM ioe.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) >= 5;

-- Fix 2: ⚠️ DEPRECATED - Business day filtering is now in PYTHON (eligibility_service.py:666-730)
-- The SQL query NO LONGER filters by business days.
-- Business day filtering happens AFTER SQL query execution in Python code.

-- OLD SQL APPROACH (NO LONGER USED):
-- Calls 2-3: Used dbo.GetBusinessDaysBetween for BUSINESS days
-- Call 4: Used dbo.GetBusinessDaysBetween for BUSINESS days

-- NEW PYTHON APPROACH (CURRENT):
-- SQL query returns all members with correct attempt counts
-- Python code filters by business days using get_business_days_between()
-- See: eligibility_service.py:666-730

-- Call 5+: Use DATEDIFF(day, ...) for CALENDAR days frequency (includes weekends/holidays) - STILL IN SQL
AND DATEDIFF(DAY, last_attempt_ts, SYSDATETIMEOFFSET()) >= 7

-- Call 5+ business day validation: Explicit check in Python (eligibility_service.py:680-695)
-- Filters out weekends/holidays even if 7 calendar days have passed
-- Uses is_business_day(now_utc) to check if current day is a business day

-- IMPORTANT DISTINCTION:
-- Calls 1-4: BUSINESS days for both frequency AND timing (PYTHON)
-- Call 5+: CALENDAR days for frequency (SQL), BUSINESS days for timing (PYTHON)
-- Example: If 7 calendar days pass but today is Saturday → member skipped until Monday
```

---

## 5. Batch Submission Issues

### Issue 5.1: Bland AI Submission Fails (API Error)

**Symptoms:**
- Logs show: `❌ [BATCH-ORCH] Bland AI submission failed: 401 Unauthorized`
- Batches stuck in 'Pending' status (never move to 'Submitted')
- `vendor_batch_id` remains NULL in `outreach_batches`

**Root Causes:**

1. **Invalid API key** (BlandAIkey secret expired or incorrect)
2. **Missing/incorrect headers** (authorization, encrypted_key, twilio_account_sid)
3. **Bland AI API outage**
4. **Request payload validation error**

**Diagnostic Steps:**

```bash
# Step 1: Check Bland AI API key in Key Vault
az keyvault secret show \
  --vault-name kv-ioe-prod \
  --name BlandAIkey \
  --query "value" -o tsv | head -c 20

# Expected: sk_... (starts with "sk_")

# Step 2: Check Application Insights for error details
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Bland AI submission failed' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h

# Step 3: Test Bland AI API manually
curl -X POST https://api.bland.ai/v1/batches \
  -H "authorization: <bland-ai-key>" \
  -H "encrypted_key: <twilio-encryption-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "base_prompt": "Test",
    "campaign_id": "test-campaign",
    "phone_numbers": ["+15551234567"]
  }'

# Expected: 200 OK with batch_id
# If 401: API key invalid
# If 403: Insufficient permissions
# If 400: Request payload error
```

```sql
-- Step 4: Check batches stuck in Pending
SELECT
    batch_id,
    campaign_id,
    batch_status,
    vendor_batch_id,
    created_at,
    DATEDIFF(MINUTE, created_at, SYSDATETIMEOFFSET()) as minutes_pending
FROM ioe.outreach_batches
WHERE batch_status = 'Pending'
  AND campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%')
ORDER BY created_at DESC;

-- If minutes_pending > 10: Submission likely failed
```

**Resolution:**

```bash
# Fix 1: Update Bland AI API key (if expired)
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name BlandAIkey \
  --value "sk_new_valid_api_key_here"

# Fix 2: Restart Function App (to pick up new secret)
az functionapp restart \
  --name ioe-function \
  --resource-group rg-ioe-prod

# Fix 3: Verify 3-header authentication (in bland_ai_client.py)
# Headers required:
# - authorization: {BlandAIkey}
# - encrypted_key: {Blandaitwilio}
# - twilio_account_sid: (hardcoded or from config)
```

```python
# Fix 4: Add retry logic to batch_orchestrator.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def submit_to_bland_ai(batch_request):
    response = bland_ai_client.submit_batch_calls(batch_request)
    if not response.get("success"):
        raise Exception(f"Bland AI submission failed: {response.get('error')}")
    return response
```

```sql
-- Fix 5: Manually mark failed batches as Failed (cleanup)
UPDATE ioe.outreach_batches
SET batch_status = 'Failed',
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_status = 'Pending'
  AND created_at < DATEADD(hour, -1, SYSDATETIMEOFFSET())  -- Older than 1 hour
  AND vendor_batch_id IS NULL;
```

---

### Issue 5.2: Batch Created But vendor_batch_id Not Set (Phase 3 Failure)

**Symptoms:**
- Batch exists in `outreach_batches` with `batch_status = 'Pending'`
- `vendor_batch_id` is NULL
- Attempts created with `disposition = 'Pending'`
- Logs show: `✅ [BATCH-ORCH] Batch submitted to Bland AI` but no Phase 3 update

**Root Causes:**

1. **Bland AI returned batch_id but Phase 3 UPDATE failed** (database error)
2. **Transaction rollback** (error after Bland AI submission but before UPDATE)
3. **vendor_batch_id extraction error** (response parsing issue)

**Diagnostic Steps:**

```bash
# Step 1: Check logs for Phase 3 execution
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Phase 3' or message contains 'vendor_batch_id' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h
```

```sql
-- Step 2: Check batch records
SELECT
    batch_id,
    campaign_id,
    batch_status,
    vendor_batch_id,
    batch_size,
    created_at
FROM ioe.outreach_batches
WHERE batch_status = 'Pending'
  AND vendor_batch_id IS NULL
  AND created_at > DATEADD(hour, -2, SYSDATETIMEOFFSET())
ORDER BY created_at DESC;

-- Step 3: Check attempt records (should exist for these batches)
SELECT
    COUNT(*) as attempt_count,
    batch_id
FROM ioe.outreach_attempts
WHERE batch_id IN (
    SELECT batch_id
    FROM ioe.outreach_batches
    WHERE batch_status = 'Pending'
      AND vendor_batch_id IS NULL
)
GROUP BY batch_id;

-- If attempt_count > 0: Phase 1 and 2 succeeded, Phase 3 failed
```

**Resolution:**

```python
# Fix 1: Add error handling to Phase 3 (in batch_orchestrator.py)
try:
    # Phase 3: Update batch with vendor_batch_id
    vendor_batch_id = response.get("batch_id") or response.get("vendor_batch_id")
    if not vendor_batch_id:
        raise ValueError("Bland AI response missing batch_id")

    self._update_batch_with_vendor_id(batch_id, vendor_batch_id)
    logger.info(f"✅ [BATCH-ORCH] Phase 3 completed: vendor_batch_id = {vendor_batch_id}")
except Exception as e:
    logger.error(f"❌ [BATCH-ORCH] Phase 3 failed: {str(e)}")
    # Mark batch as Failed instead of leaving in Pending
    self._mark_batch_failed(batch_id, str(e))
    raise
```

```sql
-- Fix 2: Manually set vendor_batch_id (if known from Bland AI dashboard)
UPDATE ioe.outreach_batches
SET
    vendor_batch_id = 'bland_batch_abc123',  -- From Bland AI dashboard
    batch_status = 'Submitted',
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_id = '<batch-id-here>';

-- Fix 3: Cleanup orphaned batches (if vendor_batch_id unknown)
-- Mark as Failed to allow re-processing
UPDATE ioe.outreach_batches
SET batch_status = 'Failed',
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_status = 'Pending'
  AND vendor_batch_id IS NULL
  AND created_at < DATEADD(hour, -2, SYSDATETIMEOFFSET());

-- Delete orphaned attempts (allow re-creation)
DELETE FROM ioe.outreach_attempts
WHERE batch_id IN (
    SELECT batch_id
    FROM ioe.outreach_batches
    WHERE batch_status = 'Failed'
      AND vendor_batch_id IS NULL
);
```

---

## 6. Webhook Processing Issues

### Issue 6.1: Webhooks Not Received (Bland AI Not Calling Webhook)

**Symptoms:**
- Calls completed in Bland AI dashboard but no webhook logs
- `outreach_attempts` stuck in 'Pending' disposition
- `bland_call_logs` table not updated

**Root Causes:**

1. **Webhook URL incorrect** in Bland AI configuration
2. **Webhook URL not publicly accessible** (firewall, HTTPS issue)
3. **Bland AI webhook disabled** for campaign
4. **Function App endpoint down**

**Diagnostic Steps:**

```bash
# Step 1: Check webhook endpoint accessibility
curl -X POST https://ioe-function.azurewebsites.net/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -d '{"call_id": "test-123"}'

# Expected: 200 OK or 400 (duplicate) - NOT 404 or 500

# Step 2: Check Bland AI webhook configuration
# Login to: https://app.bland.ai/settings/webhooks
# Verify:
# - Webhook URL: https://ioe-function.azurewebsites.net/api/bland_ai_webhook
# - Events: All checked (call.completed, call.failed, etc.)
# - Status: Active

# Step 3: Check Application Insights for webhook requests
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "requests | where name == 'bland_ai_webhook' | where timestamp > ago(1h) | top 10 by timestamp desc" \
  --offset 1h

# If count == 0: Webhooks not reaching Function App
```

```sql
-- Step 4: Check attempts stuck in Pending
SELECT COUNT(*) as pending_count
FROM ioe.outreach_attempts
WHERE disposition = 'Pending'
  AND attempt_ts < DATEADD(hour, -1, SYSDATETIMEOFFSET());

-- If pending_count > 0: Webhooks not processing
```

**Resolution:**

```bash
# Fix 1: Update webhook URL in Bland AI dashboard
# Navigate to: https://app.bland.ai/settings/webhooks
# Update URL to: https://ioe-function.azurewebsites.net/api/bland_ai_webhook
# Save changes

# Fix 2: Verify Function App HTTPS endpoint
# Check Function App URL pattern:
az functionapp show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "defaultHostName" -o tsv

# Expected: ioe-function.azurewebsites.net

# Fix 3: Test webhook manually (simulate Bland AI call)
curl -X POST https://ioe-function.azurewebsites.net/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "test-call-456",
    "to": "+15551234567",
    "from": "+15559876543",
    "status": "completed",
    "answered_by": "human",
    "call_length": 120,
    "metadata": {
      "member_id": "test-member",
      "enrollment_id": "test-enrollment",
      "campaign_id": "test-campaign",
      "batch_id": "test-batch",
      "attempt_id": "test-attempt"
    }
  }'

# Expected: 200 OK (if call_id not duplicate)
```

---

### Issue 6.2: Webhook Received But Not Processed (Database Update Fails)

**Symptoms:**
- Webhook logs show: `✅ [WEBHOOK] Webhook received`
- But: `❌ [WEBHOOK] Database update failed`
- `outreach_attempts.disposition` remains 'Pending'
- `member_campaign_enrollments_enhanced.current_status` not updated

**Root Causes:**

1. **Metadata missing or invalid** (enrollment_id, attempt_id not found in database)
2. **Database transaction fails** (constraint violation, deadlock)
3. **Disposition mapping error** (unknown Bland AI disposition)
4. **call_id duplicate** (webhook retried by Bland AI)

**Diagnostic Steps:**

```bash
# Step 1: Check webhook error logs
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains '[WEBHOOK]' and message contains 'failed' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h
```

```sql
-- Step 2: Check if attempt_id exists in database
SELECT *
FROM ioe.outreach_attempts
WHERE attempt_id = '<attempt-id-from-webhook-metadata>';

-- If no rows: Metadata incorrect or attempt not created

-- Step 3: Check bland_call_logs for webhook data
SELECT TOP 10
    call_id,
    to_number,
    disposition,
    answered_by,
    created_at
FROM ioe.bland_call_logs
ORDER BY created_at DESC;

-- If call_id exists: Webhook was logged but database update failed

-- Step 4: Check for disposition mapping issues
SELECT DISTINCT disposition
FROM ioe.bland_call_logs
WHERE created_at > DATEADD(hour, -24, SYSDATETIMEOFFSET());

-- Check if all dispositions are known (INTERESTED, NOT_INTERESTED, etc.)
-- If unknown disposition: StatusMapper needs update
```

**Resolution:**

```python
# Fix 1: Add metadata validation (in database_orchestrator.py)
def validate_metadata(metadata: dict) -> bool:
    required_fields = ["enrollment_id", "attempt_id", "member_id", "campaign_id", "batch_id"]
    for field in required_fields:
        if field not in metadata or not metadata[field]:
            logger.error(f"❌ [WEBHOOK] Missing required metadata field: {field}")
            return False
    return True

# In webhook handler:
if not validate_metadata(webhook_data.get("metadata", {})):
    return func.HttpResponse("Missing required metadata", status_code=400)
```

```python
# Fix 2: Add disposition mapping for unknown values (in status_mapper.py)
BLAND_TO_INTERNAL_DISPOSITION = {
    "INTERESTED": "Completed",
    "NOT_INTERESTED": "Completed",
    "NO_ANSWER": "NoAnswer",
    "BUSY": "Busy",
    "VOICEMAIL": "VoicemailLeft",
    "DO_NOT_CONTACT": "OptedOut",
    "CALL_BACK_SCHEDULED": "CallbackScheduled",
    "FAILED": "Failed",
    "UNKNOWN": "Failed",  # Add fallback for unknown dispositions
}

def map_disposition(bland_disposition: str) -> str:
    return BLAND_TO_INTERNAL_DISPOSITION.get(bland_disposition, "Failed")  # Default to Failed
```

```sql
-- Fix 3: Manually update attempts if metadata correct
-- Get attempt_id from webhook payload metadata
UPDATE ioe.outreach_attempts
SET
    disposition = 'Completed',  -- From webhook
    updated_at = SYSDATETIMEOFFSET()
WHERE attempt_id = '<attempt-id-from-webhook>';

-- Also update enrollment status
UPDATE ioe.member_campaign_enrollments_enhanced
SET
    current_status = 'COMPLETED',
    updated_at = SYSDATETIMEOFFSET()
WHERE enrollment_id = '<enrollment-id-from-webhook>';
```

---

## 7. Database Connection Issues

### Issue 7.1: Database Connection Timeout

**Symptoms:**
- Logs show: `🚨 [DB] Database connection timeout after 30 seconds`
- Any database query fails with timeout error
- Scheduler/webhook processing hangs indefinitely

**Root Causes:**

1. **Azure SQL firewall blocking Function App IP**
2. **Connection string incorrect** (server, database, credentials)
3. **Azure SQL database paused or inaccessible**
4. **Network connectivity issue**

**Diagnostic Steps:**

```bash
# Step 1: Check Azure SQL firewall rules
az sql server firewall-rule list \
  --server sql-ioe-prod \
  --resource-group rg-ioe-prod \
  --query "[].{Name:name, StartIP:startIpAddress, EndIP:endIpAddress}" -o table

# Expected: Rule allowing Function App outbound IPs or "Allow Azure Services"

# Step 2: Check connection string in Key Vault
az keyvault secret show \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --query "value" -o tsv

# Verify:
# - Server: sql-ioe-prod.database.windows.net
# - Database: ioe
# - User ID: correct username
# - Password: correct (test by connecting via SSMS)

# Step 3: Check Azure SQL database status
az sql db show \
  --name ioe \
  --server sql-ioe-prod \
  --resource-group rg-ioe-prod \
  --query "{Name:name, Status:status, State:state}" -o table

# Expected: Status=Online, State=Online
# If Paused: Database needs to be resumed
```

**Resolution:**

```bash
# Fix 1: Add Function App IPs to firewall (if specific IPs needed)
# Get Function App outbound IPs
az functionapp show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "outboundIpAddresses" -o tsv

# Add each IP to firewall
az sql server firewall-rule create \
  --server sql-ioe-prod \
  --resource-group rg-ioe-prod \
  --name AllowFunctionApp \
  --start-ip-address 52.x.x.x \
  --end-ip-address 52.x.x.x

# Fix 2: Enable "Allow Azure Services" (simpler approach)
az sql server firewall-rule create \
  --server sql-ioe-prod \
  --resource-group rg-ioe-prod \
  --name AllowAllAzureIps \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Fix 3: Resume database if paused
az sql db resume \
  --name ioe \
  --server sql-ioe-prod \
  --resource-group rg-ioe-prod

# Fix 4: Update connection string (if incorrect)
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --value "Server=tcp:sql-ioe-prod.database.windows.net,1433;Database=ioe;User ID=correct_user;Password=correct_password;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
```

---

## 8. Bland AI Integration Issues

### Issue 8.1: Calls Not Being Made (Batches Submitted But No Calls)

**Symptoms:**
- Batches in `outreach_batches` with status='Submitted' and `vendor_batch_id` populated
- No calls showing in Bland AI dashboard
- No webhooks received after 10+ minutes

**Root Causes:**

1. **Bland AI batch stuck in queue** (high volume, API delay)
2. **Invalid phone numbers** (non-E.164 format, disconnected numbers)
3. **Pathway configuration error** (pathway_id invalid or deleted)
4. **Bland AI account credit exhausted**

**Diagnostic Steps:**

```bash
# Step 1: Check Bland AI dashboard
# Login to: https://app.bland.ai/batches
# Find batch by vendor_batch_id
# Check status: Queued, Processing, Completed, Failed

# Step 2: Check Bland AI API for batch status
curl -X GET "https://api.bland.ai/v1/batches/<vendor_batch_id>" \
  -H "authorization: <bland-ai-key>"

# Expected response:
# {
#   "batch_id": "bland_batch_abc123",
#   "status": "completed",
#   "calls_total": 100,
#   "calls_completed": 95,
#   "calls_failed": 5
# }

# Step 3: Check phone number format in database
```

```sql
SELECT TOP 10
    m.member_id,
    m.primary_phone,
    CASE
        WHEN m.primary_phone NOT LIKE '+%' THEN 'Missing +'
        WHEN LEN(m.primary_phone) < 12 OR LEN(m.primary_phone) > 16 THEN 'Invalid length'
        ELSE 'Valid'
    END AS phone_validation
FROM ioe.members m
INNER JOIN ioe.member_campaign_enrollments_enhanced e ON m.member_id = e.member_id
WHERE e.campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%')
  AND e.current_status = 'ENROLLED';

-- If phone_validation != 'Valid': Phone numbers invalid
```

**Resolution:**

```bash
# Fix 1: Contact Bland AI support (if batch stuck)
# Email: support@bland.ai
# Provide: vendor_batch_id, account email, issue description

# Fix 2: Check Bland AI account balance
# Navigate to: https://app.bland.ai/settings/billing
# If balance low: Add credits

# Fix 3: Verify pathway configuration
# Navigate to: https://app.bland.ai/pathways
# Find pathway by pathway_id
# Ensure: Status=Active, no errors in script
```

```sql
-- Fix 4: Correct phone number format in database
UPDATE ioe.members
SET
    primary_phone = CONCAT('+1', REPLACE(REPLACE(REPLACE(primary_phone, '-', ''), '(', ''), ')', ''))
WHERE primary_phone NOT LIKE '+%'
  AND LEN(REPLACE(REPLACE(REPLACE(primary_phone, '-', ''), '(', ''), ')', '')) = 10;  -- US numbers only

-- Verify correction
SELECT TOP 10 primary_phone
FROM ioe.members
WHERE member_id IN (
    SELECT member_id
    FROM ioe.member_campaign_enrollments_enhanced
    WHERE campaign_id IN (SELECT campaign_id FROM ioe.campaigns_enhanced WHERE name LIKE '%Device Activation%')
);
-- All should start with '+1'
```

---

## 9. Performance Issues

### Issue 9.1: File Processing Takes 10+ Minutes (Should Be <2 Minutes)

**Symptoms:**
- CSV files remain in `landing/` folder for extended time
- Logs show: `⏱️ [FILE-PROC] Processing time: 650 seconds`
- Function timeout warnings (max 10 minutes for Consumption Plan)

**Root Causes:**

1. **Large file size** (50,000+ rows)
2. **Row-by-row INSERT** in Phase 2 (slow for large datasets)
3. **Database connection latency**
4. **Inefficient validation** (excessive API calls, complex regex)

**Diagnostic Steps:**

```bash
# Step 1: Check file size
az storage blob show \
  --account-name stioefstorage \
  --container-name fs-ops \
  --name landing/MedicalGuardian_DeviceActivation_20251224_Delta.csv \
  --auth-mode login \
  --query "properties.contentLength" -o tsv

# If > 10MB: Large file (may need optimization)

# Step 2: Check processing time breakdown
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Phase' and message contains 'completed' | where timestamp > ago(1h) | project timestamp, message" \
  --offset 1h

# Expected output:
# Phase 1 (Extract): 10 seconds
# Phase 2 (Load to Staging): 120 seconds  <-- Slowest
# Phase 3 (Validate): 30 seconds
# Phase 4 (Transform): 60 seconds
# Phase 5 (Audit): 5 seconds
```

**Resolution:**

```python
# Fix 1: Batch INSERT instead of row-by-row (in af_device_activation_logic.py)
# Before (slow):
for idx, row in df.iterrows():
    db_service.execute_query(insert_query, (row['member_id'], row['first_name'], ...))

# After (fast):
# Build VALUES list for bulk INSERT
values_list = []
for idx, row in df.iterrows():
    values_list.append(f"('{row['member_id']}', '{row['first_name']}', ...)")

# Single INSERT with multiple VALUES
bulk_insert_query = f"""
INSERT INTO ioe_stg.stg_device_activation_delta (member_id, first_name, ...)
VALUES {', '.join(values_list)};
"""
db_service.execute_query(bulk_insert_query)

# Fix 2: Use pandas to_sql() for bulk INSERT (alternative)
from sqlalchemy import create_engine

# Create SQLAlchemy engine from connection string
engine = create_engine(f"mssql+pymssql://{connection_string}")

# Bulk insert using pandas
df.to_sql(
    name='stg_device_activation_delta',
    schema='ioe_stg',
    con=engine,
    if_exists='append',
    index=False,
    method='multi',  # Multi-row INSERT
    chunksize=1000   # Insert 1000 rows at a time
)
```

```bash
# Fix 3: Increase Function App timeout (if under 10 min limit)
az functionapp config set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --timeout 600  # 10 minutes (max for Consumption Plan)

# Or upgrade to Premium Plan for longer timeout (up to 60 minutes)
```

---

## 10. Data Quality Issues

### Issue 10.1: Duplicate Members Created (Same Member ID, Different Data)

**Symptoms:**
- `members` table has duplicate `member_id` entries (should be UNIQUE)
- Constraint violation error: `Violation of UNIQUE KEY constraint 'UQ_members_member_id'`
- File processing fails at Phase 4 (Transform)

**Root Causes:**

1. **CSV contains duplicate member_id rows** (data provider issue)
2. **MERGE statement not working** (INSERT instead of UPDATE for existing members)
3. **member_id not unique** in source data (UUID collision, manual entry error)

**Diagnostic Steps:**

```sql
-- Step 1: Check for duplicate member_ids in members table
SELECT
    member_id,
    COUNT(*) as duplicate_count
FROM ioe.members
GROUP BY member_id
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC;

-- If duplicate_count > 1: Duplicates exist

-- Step 2: Check staging data for duplicates
SELECT
    member_id_clean,
    COUNT(*) as row_count
FROM ioe_stg.stg_device_activation_delta
WHERE file_id = '<most-recent-file-id>'
  AND validation_status = 'Valid'
GROUP BY member_id_clean
HAVING COUNT(*) > 1;

-- If row_count > 1: Source CSV has duplicates

-- Step 3: Analyze duplicate data differences
SELECT
    member_id,
    first_name,
    last_name,
    primary_phone,
    email,
    created_at
FROM ioe.members
WHERE member_id IN (
    SELECT member_id
    FROM ioe.members
    GROUP BY member_id
    HAVING COUNT(*) > 1
)
ORDER BY member_id, created_at;

-- Check if data differs (phone, email, name changes)
```

**Resolution:**

```sql
-- Fix 1: Remove duplicates from members table (keep latest)
WITH Duplicates AS (
    SELECT
        member_id,
        ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY created_at DESC) as rn
    FROM ioe.members
)
DELETE FROM ioe.members
WHERE EXISTS (
    SELECT 1
    FROM Duplicates d
    WHERE d.member_id = members.member_id
      AND d.rn > 1
);

-- Fix 2: Deduplicate staging data before MERGE (in af_device_activation_logic.py)
WITH Deduplicated AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY member_id_clean ORDER BY created_at DESC) as rn
    FROM ioe_stg.stg_device_activation_delta
    WHERE file_id = %s
      AND validation_status = 'Valid'
)
MERGE ioe.members AS target
USING (SELECT * FROM Deduplicated WHERE rn = 1) AS source
ON target.member_id = source.member_id_clean
WHEN MATCHED THEN UPDATE ...
WHEN NOT MATCHED THEN INSERT ...;
```

```python
# Fix 3: Add duplicate detection in extract() phase (fail fast)
# In af_device_activation_logic.py:
def extract(context: ProcessingContext) -> pd.DataFrame:
    df = download_blob_as_dataframe(...)

    # Check for duplicate member_ids
    duplicate_count = df.duplicated(subset=['member_id'], keep=False).sum()
    if duplicate_count > 0:
        duplicates = df[df.duplicated(subset=['member_id'], keep=False)][['member_id', 'first_name', 'last_name']]
        logger.error(f"❌ [FILE-PROC] CSV contains {duplicate_count} duplicate member_id entries:")
        logger.error(duplicates.to_string())
        raise ValueError(f"CSV validation failed: {duplicate_count} duplicate member_ids found")

    return df
```

---

## 11. Monitoring & Alerting

### Creating Custom Alerts for Common Issues

```bash
# Alert #1: High File Processing Failure Rate
az monitor metrics alert create \
  --name "DeviceActivation-FileProcessingFailures" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "count FunctionExecutionCount where FunctionName == 'device_activation_file_processor' and Success == false > 3" \
  --window-size 1h \
  --evaluation-frequency 15m \
  --action-group <action-group-id>

# Alert #2: Scheduler Not Running
az monitor metrics alert create \
  --name "DeviceActivation-SchedulerNotRunning" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "count FunctionExecutionCount where FunctionName == 'device_activation_scheduler' < 1" \
  --window-size 30m \
  --evaluation-frequency 15m \
  --action-group <action-group-id>

# Alert #3: Database Connection Failures
az monitor metrics alert create \
  --name "DeviceActivation-DatabaseErrors" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<sub-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "count traces where message contains '[DB]' and message contains 'failed' > 5" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --action-group <action-group-id>
```

---

## 12. Emergency Procedures

### Emergency Stop: Disable All Device Activation Processing

```bash
# Disable file processors (stop CSV processing)
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_file_processor \
  --set config.disabled=true

az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name operations_device_activation_file_processor \
  --set config.disabled=true

# Disable scheduler (stop batch creation and calls)
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_scheduler \
  --set config.disabled=true

# Verify all disabled
az functionapp function list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?contains(name, 'device_activation')].{Name:name, Disabled:config.disabled}" -o table
```

### Emergency Rollback: Revert to Previous Deployment

```bash
# List recent deployments
az functionapp deployment list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[].{ID:id, Status:status, Time:received_time}" -o table

# Rollback to specific deployment
az functionapp deployment source sync \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --deployment-id <previous-stable-deployment-id>

# Restart Function App
az functionapp restart \
  --name ioe-function \
  --resource-group rg-ioe-prod
```

---

## Related Documentation

**Architecture:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md) - System design and components
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md) - Database schema and SQL

**Deployment:**
- [Deployment Guide](DEVICE_ACTIVATION_DEPLOYMENT_GUIDE.md) - Deployment procedures and configuration

**Testing:**
- [Testing Guide](DEVICE_ACTIVATION_TESTING_GUIDE.md) - Unit, integration, and E2E testing

**Reference:**
- [BusinessCaseID Mapping](../REFERENCE/DEVICE_ACTIVATION_BUSINESSCASEID_MAPPING.md) - BC-DA-001 through BC-DA-008

---

**Document Version:** 1.0
**Last Updated:** 2025-12-24
**Maintained By:** AI-POD Team - Data Science
**Review Schedule:** Quarterly or after major incidents
