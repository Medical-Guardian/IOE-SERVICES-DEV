-- =====================================================================================
-- Fix Device Activation Staging Table Schema - Add Missing & Remove Obsolete Columns
-- =====================================================================================
-- Purpose: Fix schema-code sync issues in stg_device_activation_delta table
-- Date: 2025-12-23
-- BusinessCaseID: BC-TBD (Device Activation System)
--
-- RCA: Python code expects 36 columns but staging table only has 34:
--   - Missing: address_country, member_brand
--   - Obsolete: fall_detection_status_clean, battery_status_clean
--
-- Impact: CRITICAL - CSV file uploads completely broken until this is applied
--
-- Changes:
--   1. ADD address_country NVARCHAR(50) NULL
--   2. ADD member_brand NVARCHAR(100) NULL
--   3. DROP fall_detection_status_clean (obsolete column from old code)
--   4. DROP battery_status_clean (obsolete column from old code)
--
-- Safety: All changes are backwards compatible:
--   - New columns are nullable (won't break existing data)
--   - Removed columns are unused (no code references)
--   - Python has default handling for all fields
-- =====================================================================================

USE ioe;
GO

PRINT '🔧 [MIGRATION] Starting staging table schema fix...'
PRINT ''

-- =====================================================================================
-- STEP 1: Add address_country Column
-- =====================================================================================

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'address_country'
)
BEGIN
    PRINT '➕ [STEP 1/4] Adding address_country NVARCHAR(50) NULL...'

    ALTER TABLE ioe_stg.stg_device_activation_delta
    ADD address_country NVARCHAR(50) NULL;

    PRINT '   ✅ address_country column added successfully'
    PRINT '   ℹ️  Location: After zip field (Address section)'
    PRINT '   ℹ️  Purpose: Store country code (defaults to "US")'
END
ELSE
BEGIN
    PRINT 'ℹ️  [STEP 1/4] address_country column already exists - skipping'
END

PRINT ''

-- =====================================================================================
-- STEP 2: Add member_brand Column
-- =====================================================================================

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'member_brand'
)
BEGIN
    PRINT '➕ [STEP 2/4] Adding member_brand NVARCHAR(100) NULL...'

    ALTER TABLE ioe_stg.stg_device_activation_delta
    ADD member_brand NVARCHAR(100) NULL;

    PRINT '   ✅ member_brand column added successfully'
    PRINT '   ℹ️  Location: After language_pref field (Demographics section)'
    PRINT '   ℹ️  Purpose: Store member brand/plan (MedScope, MG State Pay, etc.)'
END
ELSE
BEGIN
    PRINT 'ℹ️  [STEP 2/4] member_brand column already exists - skipping'
END

PRINT ''

-- =====================================================================================
-- STEP 3: Remove Obsolete fall_detection_status_clean Column
-- =====================================================================================

IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'fall_detection_status_clean'
)
BEGIN
    PRINT '🗑️  [STEP 3/4] Removing obsolete fall_detection_status_clean column...'

    ALTER TABLE ioe_stg.stg_device_activation_delta
    DROP COLUMN fall_detection_status_clean;

    PRINT '   ✅ fall_detection_status_clean column removed successfully'
    PRINT '   ℹ️  Reason: Old column name from previous code version (unused)'
    PRINT '   ℹ️  Replacement: Python now uses fall_detection_clean instead'
END
ELSE
BEGIN
    PRINT 'ℹ️  [STEP 3/4] fall_detection_status_clean column already removed - skipping'
END

PRINT ''

-- =====================================================================================
-- STEP 4: Remove Obsolete battery_status_clean Column
-- =====================================================================================

IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'battery_status_clean'
)
BEGIN
    PRINT '🗑️  [STEP 4/4] Removing obsolete battery_status_clean column...'

    ALTER TABLE ioe_stg.stg_device_activation_delta
    DROP COLUMN battery_status_clean;

    PRINT '   ✅ battery_status_clean column removed successfully'
    PRINT '   ℹ️  Reason: Old column name from previous code version (unused)'
    PRINT '   ℹ️  Replacement: Python now uses powersaver_mode_clean instead'
END
ELSE
BEGIN
    PRINT 'ℹ️  [STEP 4/4] battery_status_clean column already removed - skipping'
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- VERIFICATION: Check New Columns Were Added
-- =====================================================================================

PRINT '📋 [VERIFICATION] Checking new columns...'
PRINT ''

DECLARE @address_country_exists INT
DECLARE @member_brand_exists INT

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
    PRINT '   ❌ ERROR: address_country column NOT found!'

IF @member_brand_exists = 1
    PRINT '   ✅ member_brand column exists'
ELSE
    PRINT '   ❌ ERROR: member_brand column NOT found!'

PRINT ''
PRINT '📊 Column Details:'
PRINT ''

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    CHARACTER_MAXIMUM_LENGTH,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME IN ('address_country', 'member_brand')
ORDER BY COLUMN_NAME;

PRINT ''

-- =====================================================================================
-- VERIFICATION: Check Obsolete Columns Were Removed
-- =====================================================================================

PRINT '📋 [VERIFICATION] Checking obsolete columns were removed...'
PRINT ''

DECLARE @obsolete_count INT

SELECT @obsolete_count = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME IN ('fall_detection_status_clean', 'battery_status_clean');

IF @obsolete_count = 0
BEGIN
    PRINT '   ✅ All obsolete columns removed successfully'
END
ELSE
BEGIN
    PRINT '   ⚠️  WARNING: Found obsolete columns still in table!'
    PRINT ''
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME IN ('fall_detection_status_clean', 'battery_status_clean');
END

PRINT ''

-- =====================================================================================
-- VERIFICATION: Total Column Count
-- =====================================================================================

PRINT '📋 [VERIFICATION] Total column count...'
PRINT ''

DECLARE @total_columns INT

SELECT @total_columns = COUNT(*)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
  AND TABLE_NAME = 'stg_device_activation_delta';

PRINT '   Total columns in table: ' + CAST(@total_columns AS VARCHAR(10))
PRINT '   Expected: 51 columns (7 metadata + 27 CSV + 11 cleaned + 4 timestamps + 2 tracking)'
PRINT ''

IF @total_columns = 51
    PRINT '   ✅ Column count matches expected value'
ELSE IF @total_columns > 51
    PRINT '   ⚠️  WARNING: More columns than expected (may have obsolete columns)'
ELSE
    PRINT '   ⚠️  WARNING: Fewer columns than expected (may be missing columns)'

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
PRINT ''

-- =====================================================================================
-- SUCCESS SUMMARY
-- =====================================================================================

IF @address_country_exists = 1 AND @member_brand_exists = 1 AND @obsolete_count = 0
BEGIN
    PRINT '✅ ✅ ✅  MIGRATION COMPLETE - ALL CHECKS PASSED  ✅ ✅ ✅'
    PRINT ''
    PRINT '📌 Summary of Changes:'
    PRINT '   ✅ Added: address_country NVARCHAR(50) NULL'
    PRINT '   ✅ Added: member_brand NVARCHAR(100) NULL'
    PRINT '   ✅ Removed: fall_detection_status_clean (obsolete)'
    PRINT '   ✅ Removed: battery_status_clean (obsolete)'
    PRINT ''
    PRINT '🚀 Next Steps:'
    PRINT '   1. Test CSV file upload: MedicalGuardian_DeviceActivationMedicaid_20251216_DELTA.csv'
    PRINT '   2. Verify file processes successfully (no errors at line 1479)'
    PRINT '   3. Check staging table has address_country = "US" values'
    PRINT '   4. Check members table receives data correctly'
    PRINT '   5. Update create_stg_device_activation_delta_table.sql script to include these changes'
    PRINT ''
    PRINT '✅ CSV file uploads should now work!'
END
ELSE
BEGIN
    PRINT '⚠️  ⚠️  ⚠️  MIGRATION INCOMPLETE - SOME CHECKS FAILED  ⚠️  ⚠️  ⚠️'
    PRINT ''
    PRINT '❌ Please review the verification output above and re-run this script'
END

PRINT ''
PRINT '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'

-- =====================================================================================
-- END OF MIGRATION SCRIPT
-- =====================================================================================
