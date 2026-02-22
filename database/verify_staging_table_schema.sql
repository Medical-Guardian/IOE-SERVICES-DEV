-- =====================================================================================
-- Verify Device Activation Staging Table Schema
-- =====================================================================================
-- Purpose: Quick verification that staging table schema matches Python code expectations
-- Date: 2025-12-23
-- Usage: Run this after applying fix_device_activation_staging_table_schema.sql
-- =====================================================================================

USE ioe;
GO

PRINT '🔍 [VERIFICATION] Starting schema verification for stg_device_activation_delta...'
PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- CHECK 1: Required Columns Exist
-- =====================================================================================

PRINT '📋 CHECK 1: Verifying required columns exist...'
PRINT ''

DECLARE @address_country_exists INT = 0
DECLARE @member_brand_exists INT = 0
DECLARE @check1_pass BIT = 0

SELECT @address_country_exists = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'address_country';

SELECT @member_brand_exists = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'member_brand';

IF @address_country_exists = 1
    PRINT '   ✅ address_country column exists'
ELSE
    PRINT '   ❌ FAIL: address_country column MISSING'

IF @member_brand_exists = 1
    PRINT '   ✅ member_brand column exists'
ELSE
    PRINT '   ❌ FAIL: member_brand column MISSING'

IF @address_country_exists = 1 AND @member_brand_exists = 1
BEGIN
    SET @check1_pass = 1
    PRINT ''
    PRINT '   ✅ CHECK 1 PASSED: All required columns exist'
END
ELSE
BEGIN
    SET @check1_pass = 0
    PRINT ''
    PRINT '   ❌ CHECK 1 FAILED: Missing required columns'
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- CHECK 2: Obsolete Columns Removed
-- =====================================================================================

PRINT '📋 CHECK 2: Verifying obsolete columns removed...'
PRINT ''

DECLARE @obsolete_count INT = 0
DECLARE @check2_pass BIT = 0

SELECT @obsolete_count = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME IN ('fall_detection_status_clean', 'battery_status_clean');

IF @obsolete_count = 0
BEGIN
    PRINT '   ✅ fall_detection_status_clean removed (obsolete)'
    PRINT '   ✅ battery_status_clean removed (obsolete)'
    PRINT ''
    PRINT '   ✅ CHECK 2 PASSED: All obsolete columns removed'
    SET @check2_pass = 1
END
ELSE
BEGIN
    PRINT '   ❌ FAIL: Found ' + CAST(@obsolete_count AS VARCHAR(10)) + ' obsolete column(s) still in table'
    PRINT ''

    SELECT '   ❌ Obsolete column: ' + COLUMN_NAME AS status
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME IN ('fall_detection_status_clean', 'battery_status_clean');

    PRINT ''
    PRINT '   ❌ CHECK 2 FAILED: Obsolete columns still exist'
    SET @check2_pass = 0
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- CHECK 3: Column Data Types Correct
-- =====================================================================================

PRINT '📋 CHECK 3: Verifying column data types...'
PRINT ''

DECLARE @address_country_type NVARCHAR(50)
DECLARE @address_country_len INT
DECLARE @member_brand_type NVARCHAR(50)
DECLARE @member_brand_len INT
DECLARE @check3_pass BIT = 0

SELECT
    @address_country_type = DATA_TYPE,
    @address_country_len = CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'address_country';

SELECT
    @member_brand_type = DATA_TYPE,
    @member_brand_len = CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'member_brand';

-- Check address_country
IF @address_country_type = 'nvarchar' AND @address_country_len = 50
    PRINT '   ✅ address_country: NVARCHAR(50) ✓'
ELSE
    PRINT '   ❌ address_country: Expected NVARCHAR(50), Found ' + ISNULL(@address_country_type, 'NULL') + '(' + ISNULL(CAST(@address_country_len AS VARCHAR(10)), 'NULL') + ')'

-- Check member_brand
IF @member_brand_type = 'nvarchar' AND @member_brand_len = 100
    PRINT '   ✅ member_brand: NVARCHAR(100) ✓'
ELSE
    PRINT '   ❌ member_brand: Expected NVARCHAR(100), Found ' + ISNULL(@member_brand_type, 'NULL') + '(' + ISNULL(CAST(@member_brand_len AS VARCHAR(10)), 'NULL') + ')'

IF @address_country_type = 'nvarchar' AND @address_country_len = 50
   AND @member_brand_type = 'nvarchar' AND @member_brand_len = 100
BEGIN
    PRINT ''
    PRINT '   ✅ CHECK 3 PASSED: All data types correct'
    SET @check3_pass = 1
END
ELSE
BEGIN
    PRINT ''
    PRINT '   ❌ CHECK 3 FAILED: Incorrect data types'
    SET @check3_pass = 0
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- CHECK 4: Total Column Count
-- =====================================================================================

PRINT '📋 CHECK 4: Verifying total column count...'
PRINT ''

DECLARE @total_columns INT = 0
DECLARE @check4_pass BIT = 0

SELECT @total_columns = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta';

PRINT '   Total columns: ' + CAST(@total_columns AS VARCHAR(10))
PRINT '   Expected: 51 columns'
PRINT '   Breakdown:'
PRINT '     - 7 metadata columns'
PRINT '     - 27 CSV source columns (including address_country, member_brand)'
PRINT '     - 11 cleaned columns (excluding obsolete fall_detection_status_clean, battery_status_clean)'
PRINT '     - 4 timestamp columns'
PRINT '     - 2 tracking columns'
PRINT ''

IF @total_columns = 51
BEGIN
    PRINT '   ✅ CHECK 4 PASSED: Column count matches expected value (51)'
    SET @check4_pass = 1
END
ELSE IF @total_columns > 51
BEGIN
    PRINT '   ⚠️  CHECK 4 WARNING: More columns than expected (' + CAST(@total_columns AS VARCHAR(10)) + ' > 51)'
    PRINT '   ℹ️  This may indicate obsolete columns still exist'
    SET @check4_pass = 0
END
ELSE
BEGIN
    PRINT '   ❌ CHECK 4 FAILED: Fewer columns than expected (' + CAST(@total_columns AS VARCHAR(10)) + ' < 51)'
    PRINT '   ℹ️  This may indicate missing required columns'
    SET @check4_pass = 0
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- CHECK 5: All 36 CSV Columns Expected by Python Exist
-- =====================================================================================

PRINT '📋 CHECK 5: Verifying all 36 CSV columns expected by Python...'
PRINT ''

DECLARE @csv_columns_missing TABLE (column_name NVARCHAR(100))
DECLARE @missing_csv_count INT = 0
DECLARE @check5_pass BIT = 0

-- List of all 36 columns Python expects in INSERT statement (lines 1156-1169 in af_device_activation_logic.py)
-- Excluding metadata columns (file_batch_id, row_number_in_file, etc.)
INSERT INTO @csv_columns_missing (column_name)
VALUES
    ('partner_name'),
    ('campaign_name_source'),
    ('salesforce_account_id'),
    ('salesforce_account_number'),
    ('org_id'),
    ('first_name'),
    ('last_name'),
    ('primary_phone'),
    ('email'),
    ('service_address'),
    ('city'),
    ('state'),
    ('zip'),
    ('address_country'),  -- NEW
    ('dob'),
    ('timezone'),
    ('language_pref'),
    ('member_brand'),  -- NEW
    ('device_udi'),
    ('device_name'),
    ('brand'),
    ('device_phone_number'),
    ('is_device_callable'),
    ('fall_detection'),
    ('powersaver_mode'),
    ('campaign_parameters'),
    ('monitoring_system_id'),
    ('enrollment_status'),
    ('unenrollment_reason');

-- Remove columns that exist
DELETE csv FROM @csv_columns_missing csv
WHERE EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS col
    WHERE col.TABLE_SCHEMA = 'ioe_stg'
      AND col.TABLE_NAME = 'stg_device_activation_delta'
      AND col.COLUMN_NAME = csv.column_name
);

SELECT @missing_csv_count = COUNT(*) FROM @csv_columns_missing;

IF @missing_csv_count = 0
BEGIN
    PRINT '   ✅ All 36 CSV source columns exist'
    PRINT ''
    PRINT '   ✅ CHECK 5 PASSED: Python INSERT will succeed'
    SET @check5_pass = 1
END
ELSE
BEGIN
    PRINT '   ❌ FAIL: Missing ' + CAST(@missing_csv_count AS VARCHAR(10)) + ' CSV column(s)'
    PRINT ''
    SELECT '   ❌ Missing: ' + column_name AS status FROM @csv_columns_missing;
    PRINT ''
    PRINT '   ❌ CHECK 5 FAILED: Python INSERT will fail with "Invalid column name" error'
    SET @check5_pass = 0
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- FINAL SUMMARY
-- =====================================================================================

DECLARE @all_checks_pass BIT = 0

IF @check1_pass = 1 AND @check2_pass = 1 AND @check3_pass = 1 AND @check4_pass = 1 AND @check5_pass = 1
    SET @all_checks_pass = 1

IF @all_checks_pass = 1
BEGIN
    PRINT '✅ ✅ ✅  ALL VERIFICATION CHECKS PASSED  ✅ ✅ ✅'
    PRINT ''
    PRINT '📊 Summary:'
    PRINT '   ✅ CHECK 1: Required columns exist'
    PRINT '   ✅ CHECK 2: Obsolete columns removed'
    PRINT '   ✅ CHECK 3: Column data types correct'
    PRINT '   ✅ CHECK 4: Total column count matches'
    PRINT '   ✅ CHECK 5: All Python INSERT columns exist'
    PRINT ''
    PRINT '🚀 Next Steps:'
    PRINT '   1. Upload test CSV: MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv'
    PRINT '   2. Verify file processes without errors'
    PRINT '   3. Check staging table receives data correctly'
    PRINT '   4. Update create_stg_device_activation_delta_table.sql for future'
    PRINT ''
    PRINT '✅ Schema is ready for CSV file processing!'
END
ELSE
BEGIN
    PRINT '❌ ❌ ❌  VERIFICATION FAILED - SOME CHECKS DID NOT PASS  ❌ ❌ ❌'
    PRINT ''
    PRINT '📊 Summary:'

    IF @check1_pass = 1
        PRINT '   ✅ CHECK 1: Required columns exist'
    ELSE
        PRINT '   ❌ CHECK 1: Required columns missing'

    IF @check2_pass = 1
        PRINT '   ✅ CHECK 2: Obsolete columns removed'
    ELSE
        PRINT '   ❌ CHECK 2: Obsolete columns still exist'

    IF @check3_pass = 1
        PRINT '   ✅ CHECK 3: Column data types correct'
    ELSE
        PRINT '   ❌ CHECK 3: Incorrect data types'

    IF @check4_pass = 1
        PRINT '   ✅ CHECK 4: Total column count matches'
    ELSE
        PRINT '   ❌ CHECK 4: Column count mismatch'

    IF @check5_pass = 1
        PRINT '   ✅ CHECK 5: All Python INSERT columns exist'
    ELSE
        PRINT '   ❌ CHECK 5: Missing Python INSERT columns'

    PRINT ''
    PRINT '⚠️  Please review the failed checks above and:'
    PRINT '   1. Re-run fix_device_activation_staging_table_schema.sql'
    PRINT '   2. Or manually fix the schema issues'
    PRINT '   3. Then run this verification script again'
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- DETAILED COLUMN LIST (Optional - Comment out if not needed)
-- =====================================================================================

PRINT '📋 OPTIONAL: Full column list for reference...'
PRINT ''
PRINT 'ℹ️  To see complete column details, uncomment the SELECT query below'
PRINT ''

/*
-- Uncomment this to see full column details
SELECT
    ORDINAL_POSITION AS position,
    COLUMN_NAME AS column_name,
    DATA_TYPE AS data_type,
    CHARACTER_MAXIMUM_LENGTH AS max_length,
    IS_NULLABLE AS nullable
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
ORDER BY ORDINAL_POSITION;
*/

-- =====================================================================================
-- END OF VERIFICATION SCRIPT
-- =====================================================================================
