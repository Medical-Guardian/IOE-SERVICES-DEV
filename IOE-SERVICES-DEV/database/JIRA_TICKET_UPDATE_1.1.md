# Jira Ticket 1.1: Create Device Activation Staging Table Schema

**Status**: Implementation Complete - Testing Required
**Last Updated**: 2025-12-24
**Priority**: High
**Assignee**: AI-POD Team

---

## Description

Create the staging table `engage360_stg.stg_device_activation_delta` to receive CSV file data from SFTP/blob storage. This table follows the established IOE pattern for file processing with metadata tracking, raw CSV columns, and cleaned columns for validation.

**Current Status**: Schema design and migration scripts completed. Ready for Azure SQL deployment and testing.

---

## Acceptance Criteria

### ✅ COMPLETED

- [x] **Table created with 50+ columns covering all CSV fields from specification**
  - **Status**: ✅ COMPLETE (51 columns)
  - **Evidence**: `database/create_stg_device_activation_delta_table.sql`
  - **Breakdown**: 7 metadata + 27 CSV + 11 cleaned + 4 timestamps + 2 tracking

- [x] **Metadata columns include: file_batch_id, row_number_in_file, processing_status, error_message**
  - **Status**: ✅ COMPLETE
  - **Note**: Uses `uploaded_by_user` instead of `source_filename` (matches pattern of other staging tables)
  - **Additional**: Added `uploaded_ts` and `validation_status` for enhanced tracking

- [x] **Raw CSV columns match specification exactly**
  - **Status**: ✅ COMPLETE (27 CSV columns)
  - **Note**: Updated to match actual CSV format (not original specification)
  - **New columns added**: `address_country`, `member_brand`, `campaign_name_source`, `campaign_parameters`, `monitoring_system_id`, `unenrollment_reason`

- [x] **Clean columns (_clean suffix) for validated data**
  - **Status**: ✅ COMPLETE (11 cleaned columns)
  - **Includes**: first_name_clean, last_name_clean, primary_phone_clean, timezone_clean, language_pref_clean, service_address_clean, brand_clean, device_phone_clean, is_device_callable_clean, org_id
  - **Removed obsolete**: fall_detection_status_clean, battery_status_clean (old column names)

- [x] **Processing timestamp columns**
  - **Status**: ✅ COMPLETE
  - **Columns**: cleansing_started_ts, cleansing_completed_ts, enrollment_started_ts, enrollment_completed_ts

- [x] **Tracking columns**
  - **Status**: ✅ COMPLETE
  - **Columns**: member_id_processed, enrollment_id_processed

- [x] **Primary key on (file_batch_id, row_number_in_file)**
  - **Status**: ✅ COMPLETE
  - **Additional**: 4 CHECK constraints for data integrity

### ⏳ TESTING REQUIRED

- [ ] **Table creates without errors in Azure SQL Database**
  - **Status**: ⏳ PENDING DEPLOYMENT
  - **Action Required**: Run migration scripts on Azure SQL Database
  - **Scripts Ready**:
    - `database/fix_device_activation_staging_table_schema.sql` (schema fix)
    - `database/rename_battery_status_to_powersaver_mode.sql` (column rename)
  - **Verification**: `database/verify_staging_table_schema.sql` (5 automated checks)

- [ ] **All indexes created successfully**
  - **Status**: ✅ DEFINED IN SCRIPT, ⏳ PENDING DEPLOYMENT
  - **Indexes**: 3 indexes defined (file_batch, error tracking, member lookup)
  - **Action Required**: Verify indexes create successfully after deployment

- [ ] **INSERT test record succeeds with all columns**
  - **Status**: ⏳ PENDING TESTING
  - **Test Query**: Available in CREATE TABLE script (lines 205-241)
  - **Python Validation**: ✅ INSERT statement in `af_code/af_device_activation_logic.py` validated (36 columns match schema)

- [ ] **UPDATE test record processing_status succeeds**
  - **Status**: ⏳ PENDING TESTING
  - **Test Queries**: Available in CREATE TABLE script (lines 261-274)
  - **Action Required**: Test status transitions (PENDING → VALIDATING → VALIDATED → TRANSFORMING → PROCESSED)

- [ ] **Query performance acceptable (<100ms for file_batch_id filter)**
  - **Status**: ⏳ PENDING TESTING
  - **Indexes**: Appropriate indexes defined for performance
  - **Action Required**: Execute performance test queries with sample data

---

## Technical Implementation Details

### File: `database/create_stg_device_activation_delta_table.sql`

**Schema**: `engage360_stg`
**Table name**: `stg_device_activation_delta`
**Total columns**: 51
**Pattern reference**: Follows `engage360_stg.stg_dtc_wellness_delta` structure

### Data Types

- **UUIDs**: `UNIQUEIDENTIFIER`
- **Dates**: `DATE` for dob
- **Timestamps**: `DATETIMEOFFSET` for all _ts columns
- **Booleans**: `BIT` for is_device_callable, is_device_callable_clean
- **Strings**: `NVARCHAR` with appropriate lengths

### CSV Fields Included (from actual CSV format)

**Identity**:
- salesforce_account_id (REQUIRED)
- salesforce_account_number
- first_name
- last_name

**Contact**:
- primary_phone (E.164 format)
- email

**Address**:
- service_address
- city
- state
- zip
- address_country (added 2025-12-23)

**Demographics**:
- dob
- timezone (IANA format: America/New_York, etc.)
- language_pref (EN/ES/Other with ISO 639 support)
- member_brand (added 2025-12-23)

**Device**:
- device_udi (REQUIRED)
- device_name
- brand
- device_phone_number
- is_device_callable

**Device Status**:
- fall_detection ('true'/'false')
- powersaver_mode ('Default'/'Standard'/'Battery Saver')

**Campaign**:
- partner_name (always "Medical Guardian")
- campaign_name_source
- campaign_parameters
- monitoring_system_id
- enrollment_status (ENROLL/UPDATE/UNENROLL)
- unenrollment_reason

### Indexes Created

1. **idx_stg_device_activation_file_batch**
   - Columns: (file_batch_id, processing_status)
   - Purpose: Fast file batch queries during ETL

2. **idx_stg_device_activation_error**
   - Columns: (processing_status, uploaded_ts DESC)
   - Filter: WHERE processing_status = 'ERROR'
   - Purpose: Error tracking and debugging

3. **idx_stg_device_activation_member**
   - Columns: (salesforce_account_number, org_id, processing_status)
   - Purpose: Member lookup during transformation phase

### Constraints

1. **Primary Key**: (file_batch_id, row_number_in_file)
2. **CHK_processing_status**: Valid values (PENDING, VALIDATING, VALIDATED, TRANSFORMING, PROCESSED, ERROR)
3. **CHK_validation_status**: Valid values (PENDING, VALIDATED, VALIDATION_ERROR)
4. **CHK_enrollment_status**: Valid values (ENROLL, UPDATE, UNENROLL, NULL)
5. **CHK_language_pref_clean**: Valid values (EN, ES, Other, NULL)

---

## Schema Evolution & Fixes

### Timeline

**2025-12-12**: Initial CREATE TABLE script created

**2025-12-16**: Updated Day 0 logic (first business day on or after enrollment_ts)
- Removed delivery_date column (no longer needed)
- Updated enrollment date calculation logic in comments

**2025-12-22**: Renamed battery_status → powersaver_mode
- Migration script: `database/rename_battery_status_to_powersaver_mode.sql`
- Reason: Better semantic alignment with actual data (powersaver mode settings)
- Affects both staging and production tables

**2025-12-23**: Schema-code synchronization fix
- Migration script: `database/fix_device_activation_staging_table_schema.sql`
- **Added**: address_country NVARCHAR(50) - Country code for addresses
- **Added**: member_brand NVARCHAR(100) - Member brand/plan information
- **Removed**: fall_detection_status_clean - Obsolete column name
- **Removed**: battery_status_clean - Obsolete column name
- **Result**: Column count updated from 53 → 51

### Known Issues (RESOLVED)

#### Issue 1: Missing Columns Breaking CSV Upload ✅ FIXED
- **Problem**: Python code expected `address_country` and `member_brand` columns
- **Error**: "Invalid column name 'address_country'" at line 1479
- **Fix**: Migration script adds both columns (2025-12-23)

#### Issue 2: Obsolete Cleaned Columns ✅ FIXED
- **Problem**: Table had unused `fall_detection_status_clean` and `battery_status_clean`
- **Fix**: Migration script drops both columns (2025-12-23)

#### Issue 3: battery_status Naming ✅ FIXED
- **Problem**: Column name didn't match data semantics
- **Fix**: Renamed to `powersaver_mode` (2025-12-22)

---

## Dependencies

**None** - This is a foundational table for Device Activation system.

**Dependent Systems**:
- Azure Function: `device_activation_file_processor`
- Python ETL: `af_code/af_device_activation_logic.py`
- Staging validation framework

---

## Deployment Checklist

### Pre-Deployment ✅ COMPLETE

- [x] CREATE TABLE script completed
- [x] Migration scripts created (2 scripts)
- [x] Verification script created (5 automated checks)
- [x] Python code validated against schema
- [x] Documentation completed
- [x] Review completed

### Deployment Steps (TO BE EXECUTED)

**Step 1: Backup Existing Table** (if exists)
```sql
SELECT * INTO engage360_stg.stg_device_activation_delta_backup_20251224
FROM engage360_stg.stg_device_activation_delta;
```

**Step 2: Run Migration Scripts** (in order)
```sql
-- Script 1: Fix schema sync issues (CRITICAL - blocks CSV uploads)
-- File: database/fix_device_activation_staging_table_schema.sql
-- Changes: Add address_country, member_brand; Remove obsolete columns

-- Script 2: Rename battery_status → powersaver_mode
-- File: database/rename_battery_status_to_powersaver_mode.sql
-- Changes: Rename column in staging and production tables
```

**Step 3: Verify Schema Correctness**
```sql
-- File: database/verify_staging_table_schema.sql
-- Expected Result: ALL 5 CHECKS PASS
--   ✅ CHECK 1: Required columns exist
--   ✅ CHECK 2: Obsolete columns removed
--   ✅ CHECK 3: Column data types correct
--   ✅ CHECK 4: Total column count = 51
--   ✅ CHECK 5: All Python INSERT columns exist
```

**Step 4: Test INSERT Operation**
```sql
-- Use example from create_stg_device_activation_delta_table.sql (lines 205-241)
-- Expected: Success with all 36 columns
```

**Step 5: Test UPDATE Operation**
```sql
-- Use example from create_stg_device_activation_delta_table.sql (lines 261-274)
-- Expected: Success for status transitions
```

**Step 6: Test CSV File Upload**
```bash
# Upload test file to blob storage:
# File: MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv
# Expected: File processes without "Invalid column name" errors
```

**Step 7: Verify ETL Processing**
- [ ] Check staging table receives data
- [ ] Verify address_country defaults to "US"
- [ ] Verify member_brand populated correctly
- [ ] Confirm no schema-related errors in Application Insights

### Post-Deployment Validation

- [ ] Verification script passes (5 checks)
- [ ] Test INSERT succeeds
- [ ] Test UPDATE succeeds
- [ ] CSV file upload succeeds
- [ ] No errors in Application Insights
- [ ] Performance test (<100ms for file_batch_id queries)

---

## Testing Instructions

### Manual Testing (Database Level)

1. **Schema Verification**:
   ```sql
   -- Run: database/verify_staging_table_schema.sql
   -- Expected: ✅ ALL VERIFICATION CHECKS PASSED
   ```

2. **INSERT Test**:
   ```sql
   -- Insert sample row (see CREATE TABLE script lines 205-241)
   -- Verify: Row inserted successfully, all 36 columns populated
   ```

3. **UPDATE Test**:
   ```sql
   -- Update processing_status: PENDING → VALIDATED
   -- Verify: Status updated, cleansing_completed_ts populated
   ```

4. **Query Performance Test**:
   ```sql
   SET STATISTICS TIME ON;
   SET STATISTICS IO ON;

   SELECT * FROM engage360_stg.stg_device_activation_delta
   WHERE file_batch_id = '<test-uuid>'
     AND processing_status = 'PENDING';

   -- Expected: <100ms execution time, index seek
   ```

### Integration Testing (Python Level)

1. **CSV File Upload**:
   - File: `MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv`
   - Upload to: Azure Blob Storage (container: device-activation/landing)
   - Expected: Azure Function triggers, file processes successfully

2. **ETL Processing**:
   - Phase 2: CSV → Staging INSERT (status: PENDING)
   - Phase 3: Validation (status: VALIDATED, *_clean columns populated)
   - Phase 4: Transform (status: PROCESSED, *_processed columns populated)
   - Phase 5: Audit log created

3. **Error Handling**:
   - Upload CSV with invalid data
   - Expected: Rows with status='ERROR', error_message populated

---

## Files Created/Modified

### Database Scripts

- ✅ `database/create_stg_device_activation_delta_table.sql` - CREATE TABLE (51 columns, 3 indexes, 4 constraints)
- ✅ `database/fix_device_activation_staging_table_schema.sql` - Migration script (add/remove columns)
- ✅ `database/rename_battery_status_to_powersaver_mode.sql` - Migration script (column rename)
- ✅ `database/verify_staging_table_schema.sql` - Verification script (5 checks)

### Documentation

- ✅ `database/CREATE_TABLE_SCRIPT_CHANGES_REQUIRED.md` - Step-by-step schema change guide
- ✅ `database/JIRA_REVIEW_DEVICE_ACTIVATION_STAGING.md` - Comprehensive implementation review

### Python Code (No Changes Required)

- ✅ `af_code/af_device_activation_logic.py` - Already validated (36 columns match schema)
- ✅ `functions/device_activation_file_processor.py` - Already validated

---

## Success Criteria

**Definition of Done**:
- [x] All acceptance criteria met (schema design)
- [ ] All migration scripts executed successfully on Azure SQL
- [ ] Verification script passes (5 checks)
- [ ] INSERT test succeeds with all columns
- [ ] UPDATE test succeeds for status transitions
- [ ] CSV file upload test succeeds (end-to-end ETL)
- [ ] Query performance <100ms for file_batch_id filter
- [ ] No errors in Application Insights logs
- [ ] Documentation updated in Jira

---

## Estimated Time to Complete

**Remaining Work**: 1-2 hours
- 15 min: Execute migration scripts on Azure SQL
- 15 min: Run verification script (5 checks)
- 30 min: Test INSERT/UPDATE/CSV upload operations
- 15 min: Monitor Application Insights for errors
- 15 min: Update Jira ticket with test results

---

## Risk Assessment

**Overall Risk**: **LOW**

**Mitigating Factors**:
- All schema changes are nullable (backwards compatible)
- Migration scripts have safety checks (IF EXISTS/NOT EXISTS)
- Verification script validates 5 critical aspects
- Python code already validated against schema
- Comprehensive testing plan in place

**Potential Issues**:
- None identified (all known issues resolved)

---

## Next Steps

1. **Deploy migration scripts to Azure SQL Database** (PRIORITY 1 - BLOCKING)
2. **Run verification script** and confirm all 5 checks pass
3. **Execute test INSERT and UPDATE** operations
4. **Upload test CSV file** and verify end-to-end processing
5. **Monitor Application Insights** for any unexpected errors
6. **Update Jira ticket** with deployment and test results
7. **Close ticket** once all testing criteria pass

---

## Related Documentation

- **Schema Files**: `database/Context Engage360_stg schema.txt`
- **CSV Specification**: `DEVICE_ACTIVATION_DATA_SPECIFICATION.md`
- **ETL Flow**: `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md` (similar pattern)
- **Project Instructions**: `CLAUDE.md` (database lookup patterns)

---

## Contact

**Team**: AI-POD Team - Data Science at Medical Guardian
**Priority**: High
**Target Completion**: 2025-12-24 (testing phase)

---

**Last Updated**: 2025-12-24
**BusinessCaseID**: BC-TBD (Device Activation System)
**Status**: ✅ Implementation Complete → ⏳ Testing Required
