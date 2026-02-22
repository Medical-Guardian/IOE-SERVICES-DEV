# Implementation Summary: Add transfer_phone_number Support

**Date:** 2026-02-05
**Feature:** Add end-to-end support for `transfer_phone_number` column in Device Activation pipeline

---

## Overview

This implementation adds complete support for an optional `transfer_phone_number` field throughout the Device Activation pipeline, from CSV ingestion through to the Bland AI payload. The field allows capturing an alternate phone number for transferring calls during device activation.

**Key Characteristics:**
- **Optional field** - does NOT cause row-level validation errors if missing or invalid
- **E.164 format** - same normalization as other phone fields (+1XXXXXXXXXX)
- **Stored in enrollments table** - per-enrollment data, not member-level
- **NULL handling** - invalid/missing values become NULL with warning log only

---

## Files Modified

### 1. Database Migration Script (NEW)
**File:** `database/add_transfer_phone_number_column.sql`

Adds `transfer_phone_number VARCHAR(20) NULL` column to:
- `ioe_stg.stg_device_activation_delta` (staging table)
- `ioe.member_campaign_enrollments_enhanced` (core table)

**⚠️ CRITICAL:** This migration MUST be run BEFORE code deployment.

### 2. CSV Schema Update
**File:** `af_code/af_device_activation_logic.py`
**Function:** `get_device_activation_schema()` (line ~926)

**Change:** Added column definition to Pandera schema
```python
"transfer_phone_number": Column(str, nullable=True),  # OPTIONAL
```

**Position:** After `powersaver_mode`, before `campaign_parameters`

### 3. Validation and Normalization
**File:** `af_code/af_device_activation_logic.py`
**Function:** `validate_and_cleanse_data_before_insert()` (line ~991)

**Change:** Added validation block after device_phone validation (after line ~1109)
```python
# Transfer phone validation (optional - does NOT cause row error)
transfer_phone_raw = row.get("transfer_phone_number", "")
if transfer_phone_raw:
    transfer_phone_clean = standardize_phone_device_activation(transfer_phone_raw)
    if not transfer_phone_clean:
        # Log warning but do NOT add to row_errors
        logger.warning(
            f"Row {idx}: Invalid transfer_phone_number: '{transfer_phone_raw}'. Setting to NULL."
        )
        transfer_phone_clean = None
else:
    transfer_phone_clean = None

df.at[idx, "transfer_phone_clean"] = transfer_phone_clean
```

**Key Points:**
- Uses existing `standardize_phone_device_activation()` utility
- Invalid values → NULL + warning (NO row error)
- Missing values → NULL (NO row error)
- Never calls `row_errors.append()`

### 4. Staging Table INSERT
**File:** `af_code/af_device_activation_logic.py`
**Function:** `load_to_staging()` (line ~1830)

**Changes:**

#### A. Added to INSERT column list (line ~1877):
```sql
fall_detection, powersaver_mode,
transfer_phone_number,  -- NEW
campaign_parameters, monitoring_system_id,
```

#### B. Added placeholder to VALUES (line ~1892):
```sql
%s, %s,  -- fall_detection, powersaver_mode
%s,      -- transfer_phone_number (NEW)
%s, %s,  -- campaign_parameters, monitoring_system_id
```

#### C. Added to parameter tuple (line ~1948):
```python
safe_value(df.at[idx, "fall_detection_clean"]),
safe_value(df.at[idx, "powersaver_mode_clean"]),
# Transfer phone (optional)
safe_value(row.get("transfer_phone_clean")),  -- NEW
# Campaign tracking
safe_value(row.get("campaign_parameters")) or None,
```

### 5. Enrollments Table MERGE
**File:** `af_code/af_device_activation_logic.py`
**Function:** `transform_and_load_core()` (line ~2024)

#### A. ENROLL MERGE - USING Clause (line ~2379)
**Change:** Added to SELECT
```sql
SELECT
    m.member_id,
    %s AS campaign_id,
    %s AS activation_start_date,
    %s AS campaign_end_date,
    %s AS call_5_timestamp,
    stg.transfer_phone_number  -- NEW
FROM ioe_stg.stg_device_activation_delta stg
```

#### B. ENROLL MERGE - UPDATE SET (line ~2396)
**Change:** Added update statement
```sql
-- Update transfer phone number
transfer_phone_number = src.transfer_phone_number,
```

**Position:** After call_5_timestamp CASE, before current_status CASE

#### C. ENROLL MERGE - INSERT (line ~2431)
**Change:** Added to columns and values
```sql
INSERT (
    enrollment_id, member_id, campaign_id, enrollment_ts, current_status,
    activation_start_date, campaign_end_date, call_5_timestamp,
    transfer_phone_number, device_activated  -- NEW position
)
VALUES (
    NEWID(),
    src.member_id,
    src.campaign_id,
    SYSDATETIMEOFFSET(),
    'ENROLLED',
    src.activation_start_date,
    src.campaign_end_date,
    src.call_5_timestamp,
    src.transfer_phone_number,  -- NEW
    0
);
```

#### D. UPDATE Query (line ~2468)
**Change:** Added to SET clause
```sql
UPDATE e
SET e.activation_start_date = %s,
    e.campaign_end_date = %s,
    e.transfer_phone_number = stg.transfer_phone_number,  -- NEW
    e.enrollment_ts = SYSDATETIMEOFFSET()
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.members m ON e.member_id = m.member_id
JOIN ioe_stg.stg_device_activation_delta stg
    ON m.org_id = stg.org_id
    AND m.salesforce_account_number = stg.salesforce_account_number
WHERE stg.file_batch_id = %s
  AND stg.processing_status = 'TRANSFORMING'
  AND stg.enrollment_status = 'UPDATE'
  AND e.campaign_id = %s
```

**Note:** No parameter added - pulls directly from staging table JOIN

### 6. Eligibility Query Update
**File:** `af_code/device_activation_scheduler/services/eligibility_service.py`
**Constant:** `ELIGIBLE_MEMBERS_QUERY` (line ~271)

**Change:** Added to SELECT clause (line ~314)
```sql
e.activation_start_date,
e.campaign_end_date,
e.call_5_timestamp,  -- Timestamp when Call 5 was made (NULL until Call 5)
e.transfer_phone_number,  -- NEW
c.name AS campaign_name,
```

### 7. Bland API Payload Update
**File:** `af_code/device_activation_scheduler/services/batch_orchestrator.py`
**Function:** `_build_batch_request()` (line ~530)

**Change:** Added to request_data dict (line ~725)
```python
request_data = {
    # Member demographics (from members table)
    "first_name": member.get("first_name"),
    "last_name": member.get("last_name"),
    "primary_phone": member.get("primary_phone"),
    "transfer_phone_number": member.get("transfer_phone_number") or "",  -- NEW
    "email": member.get("email"),
    "dob": member.get("dob").strftime("%m-%d-%Y") if member.get("dob") else "",
    ...
}
```

**Position:** After `primary_phone`, before `email`
**NULL Handling:** Converted to empty string `""` using `or ""`

---

## Data Flow

```
1. CSV Upload (transfer_phone_number column - optional)
   ↓
2. Schema Validation (nullable=True)
   ↓
3. Row Validation (standardize_phone_device_activation)
   - Valid: +1XXXXXXXXXX format
   - Invalid: NULL + warning log
   - Missing: NULL
   ↓
4. Staging Table (transfer_phone_clean)
   - ioe_stg.stg_device_activation_delta
   ↓
5. Enrollments MERGE (src.transfer_phone_number)
   - ioe.member_campaign_enrollments_enhanced
   ↓
6. Eligibility Query (e.transfer_phone_number)
   - SQL SELECT for eligible members
   ↓
7. Bland API Payload (request_data.transfer_phone_number)
   - Sent to Bland AI agent
   - Empty string if NULL
```

---

## Testing Checklist

### Unit Tests
- [ ] Valid phone number: `"5551234567"` → `"+15551234567"`
- [ ] Missing column: No column → `NULL`, no validation error
- [ ] Invalid format: `"123"` → `NULL` + warning, no validation error
- [ ] Empty string: `""` → `NULL`, no validation error
- [ ] International: `"+447911123456"` → `NULL` (US-only validator)

### Integration Tests
- [ ] CSV processing with valid transfer_phone_number
- [ ] CSV processing without transfer_phone_number column
- [ ] CSV processing with mix of valid/invalid/missing values
- [ ] Staging table contains correct values (NULL for invalid)
- [ ] Enrollments table populated via MERGE
- [ ] Eligibility query returns transfer_phone_number
- [ ] Bland API payload includes field (empty string for NULL)

### Database Verification
```sql
-- Check staging table
SELECT enrollment_id, transfer_phone_number
FROM ioe_stg.stg_device_activation_delta
WHERE file_batch_id = '<test_batch_id>';

-- Check enrollments table
SELECT enrollment_id, transfer_phone_number, primary_phone
FROM ioe.member_campaign_enrollments_enhanced
WHERE enrollment_id IN ('<test_enrollment_ids>');

-- Verify E.164 format compliance
SELECT
    enrollment_id,
    transfer_phone_number,
    CASE
        WHEN transfer_phone_number LIKE '+1__________' THEN 'Valid E.164'
        WHEN transfer_phone_number IS NULL THEN 'NULL'
        ELSE 'Invalid Format'
    END as format_check
FROM ioe.member_campaign_enrollments_enhanced
WHERE enrollment_ts > DATEADD(day, -7, GETDATE());
```

---

## Deployment Steps

### Phase 1: Database Migration (MUST BE FIRST)
1. Backup tables:
   - `ioe_stg.stg_device_activation_delta`
   - `ioe.member_campaign_enrollments_enhanced`

2. Run migration script:
   ```bash
   # Execute database/add_transfer_phone_number_column.sql
   # Verify output shows successful column addition
   ```

3. Verify columns exist:
   ```sql
   -- Should return 1 row each
   SELECT * FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA = 'ioe_stg'
     AND TABLE_NAME = 'stg_device_activation_delta'
     AND COLUMN_NAME = 'transfer_phone_number';

   SELECT * FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA = 'ioe'
     AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
     AND COLUMN_NAME = 'transfer_phone_number';
   ```

4. Test INSERT with sample data:
   ```sql
   -- Test staging INSERT
   INSERT INTO ioe_stg.stg_device_activation_delta (
       file_batch_id, transfer_phone_number, processing_status
   ) VALUES ('test-batch', '+15551234567', 'TEST');

   -- Test enrollments INSERT
   INSERT INTO ioe.member_campaign_enrollments_enhanced (
       enrollment_id, member_id, campaign_id, transfer_phone_number
   ) VALUES (NEWID(), '<test_member_id>', '<test_campaign_id>', '+15551234567');

   -- Clean up test data
   DELETE FROM ioe_stg.stg_device_activation_delta WHERE file_batch_id = 'test-batch';
   DELETE FROM ioe.member_campaign_enrollments_enhanced WHERE transfer_phone_number = '+15551234567';
   ```

5. **BLOCK code deployment until verification complete**

### Phase 2: Code Deployment
1. Deploy to staging environment
2. Run smoke tests with sample CSV
3. Verify end-to-end flow
4. Deploy to production
5. Monitor Application Insights for errors

### Phase 3: Post-Deployment Validation
1. Process test file with transfer_phone_number column
2. Verify staging table population
3. Verify enrollments MERGE
4. Check Bland AI batch submission logs
5. Validate E.164 format compliance in database

---

## Rollback Plan

### Option 1: Code Rollback (Preserve Data)
```bash
# Revert to previous Azure Function version
# Database columns remain (unused but safe)
# No data loss
```

### Option 2: Full Rollback (Remove Everything)
```sql
-- Remove columns
ALTER TABLE ioe_stg.stg_device_activation_delta
DROP COLUMN transfer_phone_number;

ALTER TABLE ioe.member_campaign_enrollments_enhanced
DROP COLUMN transfer_phone_number;

-- Restore from backup if needed
```

**Decision Criteria:**
- Code issues → Option 1 (code rollback only)
- Database corruption → Option 2 (full rollback)

---

## Edge Cases

| Scenario | Handling | Risk |
|----------|----------|------|
| Missing CSV column | nullable=True, defaults to NULL | LOW |
| Invalid phone format | Returns None, logs warning, stores NULL | LOW |
| International numbers | Rejected by US-only validator, stores NULL | MEDIUM |
| Duplicate across members | No uniqueness constraint, stores independently | LOW |
| Same as primary_phone | Both stored, no validation preventing duplicates | LOW |
| NULL in Bland payload | Converted to empty string `""` | LOW |
| Very long string | Rejected by validator, stores NULL (not truncated) | LOW |

**Note:** International numbers support requires updating `standardize_phone_device_activation()` to accept non-US formats.

---

## Performance Impact

- **CSV Processing:** Minimal (<1% overhead) - one additional validation per row
- **Database INSERT:** One additional column in staging INSERT
- **MERGE Performance:** One additional column in SELECT/UPDATE/INSERT
- **Eligibility Query:** One additional column in SELECT (no JOIN impact)
- **Bland API:** One additional field in JSON payload

**Expected:** No measurable performance degradation

---

## Key Design Decisions

### 1. Optional Field (Never Fails)
Unlike required phone fields (`primary_phone`, `device_phone_number`), `transfer_phone_number` is fully optional:
- Missing → NULL (no error)
- Invalid → NULL + warning (no error)
- Never causes row-level validation error

**Rationale:** Transfer number is a convenience feature, not required for device activation

### 2. Same Normalization Rules
Uses existing `standardize_phone_device_activation()` utility:
- Same E.164 formatting (+15551234567)
- Same validation rules as other phone fields
- Reuses proven, tested code

**Rationale:** Consistency across all phone number handling

### 3. Stored on Enrollments, Not Members
Field stored on `member_campaign_enrollments_enhanced`, NOT `members` table.

**Rationale:** Transfer number may be campaign-specific or change per enrollment

### 4. Bland Payload Empty String for NULL
NULL values sent as empty string `""` to Bland AI:
```python
"transfer_phone_number": member.get("transfer_phone_number") or ""
```

**Rationale:** Consistent with other optional fields (email, address_street)

---

## Success Criteria

- [x] Database migration script created
- [ ] Migration completes without errors
- [ ] CSV with `transfer_phone_number` processes successfully
- [ ] Valid phone numbers normalize to E.164 format
- [ ] Missing/invalid values become NULL without row errors
- [ ] Staging table contains `transfer_phone_number` data
- [ ] Enrollments table contains `transfer_phone_number` data
- [ ] Eligibility query returns `transfer_phone_number`
- [ ] Bland AI payload includes `transfer_phone_number` field
- [ ] NULL values sent to Bland AI as empty string
- [ ] No increase in file processing errors
- [ ] No performance degradation

---

## Questions & Answers

**Q: Why is this field optional when primary_phone is required?**
A: Transfer number is a convenience feature for call routing, not essential for device activation. Primary phone is required for member contact.

**Q: What happens if transfer_phone_number equals primary_phone?**
A: Both are stored independently. No validation prevents duplicates. This is acceptable as they serve different purposes.

**Q: Can we support international numbers?**
A: Not currently. The shared `standardize_phone_device_activation()` utility only supports US phone numbers (E.164 with +1 prefix). To support international, update the utility function.

**Q: Where does transfer_phone_number get used in the call flow?**
A: It's passed to Bland AI in the `request_data` payload. The AI pathway determines how/when to use it during the call (e.g., "Would you like me to transfer you to this number?").

**Q: Why not store in members table?**
A: Transfer number may be campaign-specific (e.g., different support lines for different campaigns) or may change between enrollments. Storing per-enrollment provides flexibility.

---

**Implementation Completed:** 2026-02-05
**Implemented By:** Claude Code (Sonnet 4.5)
**Next Steps:** Run database migration, deploy to staging, test end-to-end
