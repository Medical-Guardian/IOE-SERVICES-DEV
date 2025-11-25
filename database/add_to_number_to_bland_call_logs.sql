/*
Database Migration: Add to_number Column to engage360.bland_call_logs Table
Purpose: Store member's phone number (the number that was called)
Date: 2025-11-25
Related Feature: Bland AI webhook processing - capture "to" field

This migration adds the to_number column to bland_call_logs to store the member's
phone number that was called (E.164 format: +1XXXXXXXXXX).
*/

-- Check if to_number column exists, add if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('engage360.bland_call_logs')
    AND name = 'to_number'
)
BEGIN
    PRINT '📋 Adding to_number column to engage360.bland_call_logs table...';

    ALTER TABLE engage360.bland_call_logs
    ADD to_number VARCHAR(20) NULL;

    PRINT '✅ to_number column added successfully';
    PRINT '   Data Type: VARCHAR(20)';
    PRINT '   Nullable: YES (backward compatible)';
    PRINT '   Format: E.164 (+1XXXXXXXXXX)';
END
ELSE
BEGIN
    PRINT 'ℹ️ to_number column already exists in engage360.bland_call_logs';
END
GO

-- Verify the migration
PRINT '📋 Verifying migration...';

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'bland_call_logs'
  AND COLUMN_NAME = 'to_number';

PRINT '✅ Migration verification complete';
GO

-- Data validation check
PRINT '📋 Checking existing records...';

SELECT
    COUNT(*) as total_call_logs,
    SUM(CASE WHEN to_number IS NULL THEN 1 ELSE 0 END) as null_to_number_count,
    SUM(CASE WHEN to_number IS NOT NULL THEN 1 ELSE 0 END) as populated_to_number_count
FROM engage360.bland_call_logs;

PRINT '✅ Data validation complete';
PRINT '';
PRINT 'NOTE: Existing records will have NULL to_number (expected)';
PRINT 'New webhook calls will populate this field automatically';
GO

PRINT '';
PRINT '======================================';
PRINT 'MIGRATION COMPLETE';
PRINT '======================================';
PRINT '';
PRINT 'Column added: engage360.bland_call_logs.to_number';
PRINT '  - Type: VARCHAR(20) NULL';
PRINT '  - Format: E.164 (+1XXXXXXXXXX)';
PRINT '  - Source: Bland AI webhook "to" field';
PRINT '';
PRINT 'Next steps:';
PRINT '  1. Deploy Python code changes to extract "to" field';
PRINT '  2. Test webhook processing';
PRINT '  3. Monitor query patterns for potential indexing needs';
PRINT '';
GO

-- =============================================================================
-- ROLLBACK SCRIPT (if needed)
-- =============================================================================

PRINT '--------------------------------------';
PRINT 'ROLLBACK SCRIPT (if needed)';
PRINT '--------------------------------------';
PRINT '';
PRINT 'To remove the column:';
PRINT '  ALTER TABLE engage360.bland_call_logs DROP COLUMN to_number;';
PRINT '';
PRINT 'WARNING: This will permanently delete all to_number data';
PRINT '';
GO
