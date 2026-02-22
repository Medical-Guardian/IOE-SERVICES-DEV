-- =============================================================================
-- MIGRATION: Add Gender Columns to DTC Wellness Staging Table
-- =============================================================================
-- Date Created: 2025-11-10
-- Purpose: Support optional gender field in DTC CSV file uploads
-- Related Code: af_code/af_dtc_logic.py (lines 783, 810, 1260-1275)
--
-- IMPORTANT:
-- - Run this script on Azure SQL Database before processing CSV files with gender data
-- - Production table (engage360.members) already has gender CHAR(1) column
-- - This migration ONLY adds columns to staging table
-- =============================================================================

USE [SANDBOX];
GO

PRINT '======================================';
PRINT 'STAGING TABLE: stg_dtc_wellness_delta';
PRINT '======================================';
PRINT '';

-- =============================================================================
-- SECTION 1: Verify Production Table Already Has Gender Column
-- =============================================================================

PRINT '--------------------------------------';
PRINT 'VERIFICATION: Production Table Status';
PRINT '--------------------------------------';

IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'gender'
)
BEGIN
    PRINT '✅ Production table already has gender column: engage360.members.gender (CHAR 1)';

    -- Show the column details
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
      AND TABLE_NAME = 'members'
      AND COLUMN_NAME = 'gender';
END
ELSE
BEGIN
    PRINT '⚠️  WARNING: Production table missing gender column - contact DBA';
END
GO

PRINT '';
PRINT '======================================';
PRINT 'ADDING COLUMNS TO STAGING TABLE';
PRINT '======================================';
PRINT '';

-- =============================================================================
-- SECTION 2: Add Gender Columns to Staging Table
-- =============================================================================

-- Add member_gender column (raw from CSV)
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360_stg'
      AND TABLE_NAME = 'stg_dtc_wellness_delta'
      AND COLUMN_NAME = 'member_gender'
)
BEGIN
    ALTER TABLE engage360_stg.stg_dtc_wellness_delta
    ADD member_gender VARCHAR(50) NULL;

    PRINT '✅ Added column: member_gender VARCHAR(50) NULL';
    PRINT '   Purpose: Store raw CSV gender value (M, Male, F, Female, Other, etc.)';
END
ELSE
BEGIN
    PRINT 'ℹ️  Column already exists: member_gender';
END
GO

-- Add gender_clean column (standardized value - matches production CHAR(1))
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360_stg'
      AND TABLE_NAME = 'stg_dtc_wellness_delta'
      AND COLUMN_NAME = 'gender_clean'
)
BEGIN
    ALTER TABLE engage360_stg.stg_dtc_wellness_delta
    ADD gender_clean CHAR(1) NULL;

    PRINT '✅ Added column: gender_clean CHAR(1) NULL';
    PRINT '   Purpose: Standardized gender value to match production table';
    PRINT '   Values: ''M'' (Male), ''F'' (Female), NULL (not provided/other)';
END
ELSE
BEGIN
    PRINT 'ℹ️  Column already exists: gender_clean';
END
GO

-- =============================================================================
-- SECTION 3: Verify Staging Table Columns
-- =============================================================================

PRINT '';
PRINT '--------------------------------------';
PRINT 'VERIFICATION: Staging Table Schema';
PRINT '--------------------------------------';

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_dtc_wellness_delta'
  AND COLUMN_NAME IN ('member_gender', 'gender_clean')
ORDER BY ORDINAL_POSITION;
GO

-- =============================================================================
-- SECTION 4: Data Type Compatibility Check
-- =============================================================================

PRINT '';
PRINT '======================================';
PRINT 'DATA TYPE COMPATIBILITY';
PRINT '======================================';
PRINT '';
PRINT 'Staging → Production Mapping:';
PRINT '  member_gender (VARCHAR 50) → [validation] → gender_clean (CHAR 1) → gender (CHAR 1)';
PRINT '';
PRINT 'Production Table Constraint:';
PRINT '  CK_members_gender CHECK (gender IN (''M'', ''F'', NULL))';
PRINT '';
PRINT 'IMPORTANT: Python code must map:';
PRINT '  - "Other" values from CSV → NULL in production (not ''O'')';
PRINT '  - Only ''M'' and ''F'' allowed in production table';
PRINT '';
GO

-- =============================================================================
-- SECTION 5: Data Validation Examples
-- =============================================================================

PRINT '======================================';
PRINT 'DATA VALIDATION RULES';
PRINT '======================================';
PRINT '';
PRINT 'CSV Input (member_gender) → Staging Clean (gender_clean) → Production (gender):';
PRINT '  "M", "Male", "MALE" → ''M'' → ''M''';
PRINT '  "F", "Female", "FEMALE" → ''F'' → ''F''';
PRINT '  "Other", "Non-binary", etc. → NULL → NULL';
PRINT '  Empty/blank → NULL → NULL';
PRINT '';
PRINT 'Standardization Logic (af_code/af_dtc_logic.py lines 1260-1275):';
PRINT '  1. Clean empty values → NULL';
PRINT '  2. Convert to uppercase';
PRINT '  3. Match M/MALE → ''M''';
PRINT '  4. Match F/FEMALE → ''F''';
PRINT '  5. Everything else → NULL (for production compatibility)';
PRINT '';
PRINT 'NOTE: Original "Other" mapping updated to NULL to match production constraint';
GO

-- =============================================================================
-- SECTION 6: Migration Summary
-- =============================================================================

PRINT '';
PRINT '======================================';
PRINT 'MIGRATION COMPLETE';
PRINT '======================================';
PRINT '';
PRINT 'Columns added to engage360_stg.stg_dtc_wellness_delta:';
PRINT '  1. member_gender (VARCHAR 50, NULL) - Raw CSV input';
PRINT '  2. gender_clean (CHAR 1, NULL) - Standardized value';
PRINT '';
PRINT 'Production table status:';
PRINT '  ✅ engage360.members.gender already exists (CHAR 1, NULL)';
PRINT '  ✅ Production constraint: gender IN (''M'', ''F'', NULL)';
PRINT '';
PRINT 'Next steps:';
PRINT '  1. Verify columns created successfully above';
PRINT '  2. Update Python code if it expects VARCHAR(10) instead of CHAR(1)';
PRINT '  3. Ensure "Other" values map to NULL (not ''O'')';
PRINT '  4. Test DTC CSV upload with gender field';
PRINT '  5. Verify data flows correctly from staging to members table';
PRINT '';
PRINT 'Test CSV format:';
PRINT '  Column: member_gender';
PRINT '  Position: After member_dob, before member_email';
PRINT '  Valid: "M", "F", "Male", "Female", "" (empty)';
PRINT '  Invalid for production: "Other", "O", "Non-binary" (stored as NULL)';
PRINT '';
GO

-- =============================================================================
-- SECTION 7: Rollback Instructions (If Needed)
-- =============================================================================

PRINT '--------------------------------------';
PRINT 'ROLLBACK SCRIPT (if needed)';
PRINT '--------------------------------------';
PRINT '';
PRINT 'To remove the columns:';
PRINT '  ALTER TABLE engage360_stg.stg_dtc_wellness_delta DROP COLUMN member_gender;';
PRINT '  ALTER TABLE engage360_stg.stg_dtc_wellness_delta DROP COLUMN gender_clean;';
PRINT '';
PRINT 'WARNING: This will permanently delete any gender data in staging table';
PRINT '';
GO

-- =============================================================================
-- END OF MIGRATION SCRIPT
-- =============================================================================
