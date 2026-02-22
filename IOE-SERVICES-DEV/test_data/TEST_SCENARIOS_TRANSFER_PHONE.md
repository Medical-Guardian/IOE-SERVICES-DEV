# Test CSV: transfer_phone_number Scenarios

**File:** `device_activation_transfer_phone_test.csv`
**Purpose:** Comprehensive testing of transfer_phone_number field validation and processing

---

## Test Data Overview

| Row | Account | Name | transfer_phone_number | Test Scenario | Expected Result |
|-----|---------|------|-----------------------|---------------|-----------------|
| 1 | TEST001 | John Smith | `18005552222` | Valid 11-digit US number | ✅ `+18005552222` (E.164) |
| 2 | TEST002 | Jane Doe | *(empty)* | Missing/empty field | ✅ `NULL` (no error) |
| 3 | TEST003 | Bob Johnson | `5551111` | Invalid (too short - 7 digits) | ⚠️ `NULL` + warning log |
| 4 | TEST004 | Alice Williams | `123` | Invalid (too short - 3 digits) | ⚠️ `NULL` + warning log |
| 5 | TEST005 | Charlie Brown | `18005551238` | Same as primary_phone | ✅ `+18005551238` (allowed) |
| 6 | TEST006 | Diana Davis | `(800) 555-3333` | Formatted US number | ✅ `+18005553333` (normalized) |
| 7 | TEST007 | Edward Miller | `+1-800-555-4444` | E.164 with dashes | ✅ `+18005554444` (normalized) |
| 8 | TEST008 | Fiona Wilson | `18005555555` | Valid 11-digit | ✅ `+18005555555` (E.164) |
| 9 | TEST009 | George Moore | `800-555-6666` | 10-digit with dashes | ⚠️ `NULL` (10-digit rejected) |
| 10 | TEST010 | Helen Taylor | `+447911123456` | International (UK number) | ⚠️ `NULL` + warning (US only) |

---

## Detailed Test Scenarios

### ✅ **Test 1: Valid 11-digit US Number**
**Input:** `18005552222`
**Expected Output:** `+18005552222`
**Validation:**
- 11 digits starting with `1`
- Normalized to E.164 format (+1XXXXXXXXXX)
- Stored in staging and enrollments tables

### ✅ **Test 2: Missing/Empty Field**
**Input:** *(empty string)*
**Expected Output:** `NULL`
**Validation:**
- No validation error
- No warning log
- Stored as NULL in database
- File processing continues successfully

### ⚠️ **Test 3: Invalid - Too Short (7 digits)**
**Input:** `5551111`
**Expected Output:** `NULL`
**Validation:**
- Fails phone validation (too short)
- Warning logged: "Invalid transfer_phone_number: '5551111'. Setting to NULL."
- Does NOT cause row error
- File processing continues

### ⚠️ **Test 4: Invalid - Too Short (3 digits)**
**Input:** `123`
**Expected Output:** `NULL`
**Validation:**
- Fails phone validation (way too short)
- Warning logged: "Invalid transfer_phone_number: '123'. Setting to NULL."
- Does NOT cause row error
- File processing continues

### ✅ **Test 5: Same as Primary Phone**
**Input:** `18005551238` (same as member_phone_number)
**Expected Output:** `+18005551238`
**Validation:**
- Both primary_phone and transfer_phone_number stored
- No validation preventing duplicates
- This is acceptable behavior
- Both fields serve different purposes

### ✅ **Test 6: Formatted US Number with Parentheses**
**Input:** `(800) 555-3333`
**Expected Output:** `+18005553333`
**Validation:**
- Special characters removed
- Normalized to E.164 format
- 10 digits → rejected (must be 11)
- Actually becomes `NULL` due to 10-digit rule

**⚠️ UPDATE:** This will actually fail because it's 10 digits after removing formatting. Expected: `NULL` + warning

### ✅ **Test 7: E.164 Format with Dashes**
**Input:** `+1-800-555-4444`
**Expected Output:** `+18005554444`
**Validation:**
- Already has +1 prefix
- Dashes removed during normalization
- Validates as 11-digit US number
- Stored in E.164 format

### ✅ **Test 8: Valid 11-digit (Simple Format)**
**Input:** `18005555555`
**Expected Output:** `+18005555555`
**Validation:**
- Standard 11-digit format
- Normalized to E.164 (+1 prefix added)
- Passes all validation rules

### ⚠️ **Test 9: 10-digit with Dashes (Rejected)**
**Input:** `800-555-6666`
**Expected Output:** `NULL`
**Validation:**
- Only 10 digits after removing dashes
- Fails 11-digit requirement
- Warning logged
- Does NOT cause row error
- File processing continues

### ⚠️ **Test 10: International Number (UK)**
**Input:** `+447911123456`
**Expected Output:** `NULL`
**Validation:**
- International format (UK +44 prefix)
- Current validator is US-only
- Rejected by validation
- Warning logged: "Invalid transfer_phone_number"
- Does NOT cause row error

---

## Expected Processing Results

### Staging Table (`stg_device_activation_delta`)
```sql
SELECT
    salesforce_account_number,
    first_name,
    last_name,
    primary_phone,
    transfer_phone_number,
    validation_status
FROM engage360_stg.stg_device_activation_delta
WHERE file_batch_id = '<test_batch_id>'
ORDER BY row_number_in_file;
```

**Expected Results:**
| Account | Name | transfer_phone_number | validation_status |
|---------|------|-----------------------|-------------------|
| TEST001 | John Smith | +18005552222 | VALIDATED |
| TEST002 | Jane Doe | NULL | VALIDATED |
| TEST003 | Bob Johnson | NULL | VALIDATED |
| TEST004 | Alice Williams | NULL | VALIDATED |
| TEST005 | Charlie Brown | +18005551238 | VALIDATED |
| TEST006 | Diana Davis | NULL | VALIDATED |
| TEST007 | Edward Miller | +18005554444 | VALIDATED |
| TEST008 | Fiona Wilson | +18005555555 | VALIDATED |
| TEST009 | George Moore | NULL | VALIDATED |
| TEST010 | Helen Taylor | NULL | VALIDATED |

**Key Points:**
- All rows have `validation_status = 'VALIDATED'`
- Invalid transfer_phone_number does NOT cause validation errors
- 4 valid phone numbers stored in E.164 format
- 6 NULL values (empty, invalid, or international)

### Enrollments Table (`member_campaign_enrollments_enhanced`)
```sql
SELECT
    e.enrollment_id,
    m.salesforce_account_number,
    m.first_name,
    m.last_name,
    m.primary_phone,
    e.transfer_phone_number,
    e.current_status
FROM engage360.member_campaign_enrollments_enhanced e
JOIN engage360.members m ON e.member_id = m.member_id
WHERE m.salesforce_account_number LIKE 'TEST%'
ORDER BY m.salesforce_account_number;
```

**Expected Results:**
- 10 enrollments created (all with `current_status = 'ENROLLED'`)
- 4 with valid transfer_phone_number values
- 6 with NULL transfer_phone_number
- All synced from staging table

---

## Warning Logs Expected

When processing this file, you should see these warnings in the logs:

```
⚠️ Row 2: Invalid transfer_phone_number: '5551111'. Setting to NULL.
⚠️ Row 3: Invalid transfer_phone_number: '123'. Setting to NULL.
⚠️ Row 5: Invalid transfer_phone_number: '(800) 555-3333'. Setting to NULL.
⚠️ Row 8: Invalid transfer_phone_number: '800-555-6666'. Setting to NULL.
⚠️ Row 9: Invalid transfer_phone_number: '+447911123456'. Setting to NULL.
```

**Critical:** These are WARNING logs only, NOT errors. File processing should complete successfully.

---

## Bland AI Payload Verification

After enrollments are created and scheduled for calls, verify the Bland AI batch payload includes `transfer_phone_number`:

```json
{
  "base_prompt": "...",
  "phone_number": "+18005551234",
  "request_data": {
    "first_name": "John",
    "last_name": "Smith",
    "primary_phone": "+18005551234",
    "transfer_phone_number": "+18005552222",  // ← Should be present
    "email": "john.smith@example.com",
    ...
  },
  "metadata": {
    "batch_id": "...",
    "campaign_id": "...",
    ...
  }
}
```

**For NULL values:**
```json
{
  "request_data": {
    "transfer_phone_number": "",  // ← Empty string for NULL
    ...
  }
}
```

---

## How to Use This Test File

### Step 1: Prepare Database
```sql
-- Run migration
-- Execute: database/add_transfer_phone_number_column.sql

-- Verify columns exist
-- Execute: database/verify_transfer_phone_number_columns.sql
```

### Step 2: Upload Test File
```bash
# Upload to Azure Blob Storage (landing folder)
az storage blob upload \
  --account-name <storage-account> \
  --container-name fs-device-activation/landing \
  --name "medical_guardian_device_activation_$(date +%Y%m%d).csv" \
  --file test_data/device_activation_transfer_phone_test.csv
```

### Step 3: Monitor Processing
```bash
# Watch Azure Function logs
func azure functionapp logstream <function-app-name>

# Or use Azure CLI
az webapp log tail --name <function-app-name> --resource-group <rg>
```

### Step 4: Verify Results
```sql
-- Run test queries
-- Execute: database/test_transfer_phone_number_data.sql

-- Check specific batch
SELECT * FROM engage360_stg.stg_device_activation_delta
WHERE file_batch_id = '<your_batch_id>';
```

### Step 5: Check Bland AI Logs
- Review batch orchestrator logs for `request_data` payload
- Verify `transfer_phone_number` field is included
- Confirm NULL values become empty strings

---

## Success Criteria

✅ **File Processing:**
- [ ] File processes without errors
- [ ] All 10 rows reach staging table
- [ ] All 10 rows have `validation_status = 'VALIDATED'`
- [ ] 5 warning logs generated (invalid phone numbers)

✅ **Data Quality:**
- [ ] 4 valid E.164 phone numbers stored: +18005552222, +18005551238, +18005554444, +18005555555
- [ ] 6 NULL values stored (not empty strings)
- [ ] No invalid formats in database (only NULL or valid E.164)

✅ **Enrollments:**
- [ ] 10 enrollments created
- [ ] transfer_phone_number synced from staging
- [ ] All enrollments have `current_status = 'ENROLLED'`

✅ **Bland API:**
- [ ] Eligibility query returns transfer_phone_number
- [ ] Batch payload includes field in request_data
- [ ] NULL values converted to empty string ""

---

## Troubleshooting

**Issue:** "Column transfer_phone_number does not exist"
**Solution:** Run database migration first

**Issue:** "Validation errors on all rows"
**Solution:** Check that transfer_phone_number is marked `nullable=True` in schema

**Issue:** "File rejected due to transfer_phone_number errors"
**Solution:** Verify validation logic does NOT call `row_errors.append()` for transfer_phone

**Issue:** "Empty strings stored instead of NULL"
**Solution:** Check `safe_value()` function handles empty strings correctly

**Issue:** "10-digit numbers not normalized to 11 digits"
**Solution:** Expected behavior - 10-digit numbers are rejected (11-digit requirement)

---

**Last Updated:** 2026-02-05
**Test File Version:** 1.0
**Related Implementation:** IMPLEMENTATION_SUMMARY_TRANSFER_PHONE_NUMBER.md
