-- =====================================================
-- Migration: Add call_5_timestamp to member_campaign_enrollments_enhanced
-- Date: 2025-12-22
-- Purpose: Track when Call 5 was made for Device Activation 90-day window
-- =====================================================
--
-- BACKGROUND:
-- Device Activation campaigns need to enforce a 90-day window starting FROM Call 5,
-- not from activation_start_date. This allows Calls 1-4 to happen without time limits
-- (only frequency rules apply), while Call 5+ have a hard 90-day cutoff.
--
-- NEW LOGIC:
-- - Calls 1-4: No 90-day limit (call_5_timestamp = NULL)
-- - Call 5+: 90-day window from call_5_timestamp (call_5_timestamp + 90 days)
--
-- This migration adds:
-- 1. call_5_timestamp column (DATETIMEOFFSET) to track when Call 5 was created
-- 2. Index for efficient eligibility queries
-- =====================================================

USE engage360;
GO

PRINT '========================================';
PRINT 'Starting migration: Add call_5_timestamp';
PRINT '========================================';
PRINT '';

-- =====================================================
-- Step 1: Add call_5_timestamp column
-- =====================================================
PRINT 'Step 1: Adding call_5_timestamp column...';

IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
      AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
      AND COLUMN_NAME = 'call_5_timestamp'
)
BEGIN
    ALTER TABLE engage360.member_campaign_enrollments_enhanced
    ADD call_5_timestamp DATETIMEOFFSET(7) NULL;

    PRINT '✓ Column call_5_timestamp added successfully';
END
ELSE
BEGIN
    PRINT '⚠ Column call_5_timestamp already exists - skipping';
END

PRINT '';

-- =====================================================
-- Step 2: Add index for eligibility query performance
-- =====================================================
PRINT 'Step 2: Creating index IX_enrollments_call5_device_activation...';

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_enrollments_call5_device_activation'
      AND object_id = OBJECT_ID('engage360.member_campaign_enrollments_enhanced')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_enrollments_call5_device_activation
    ON engage360.member_campaign_enrollments_enhanced (call_5_timestamp ASC)
    INCLUDE (campaign_end_date, device_activated, current_status)
    WHERE call_5_timestamp IS NOT NULL;

    PRINT '✓ Index IX_enrollments_call5_device_activation created successfully';
END
ELSE
BEGIN
    PRINT '⚠ Index IX_enrollments_call5_device_activation already exists - skipping';
END

PRINT '';

-- =====================================================
-- Step 3: Add extended property (column description)
-- =====================================================
PRINT 'Step 3: Adding column description...';

IF NOT EXISTS (
    SELECT 1
    FROM sys.extended_properties
    WHERE major_id = OBJECT_ID('engage360.member_campaign_enrollments_enhanced')
      AND name = N'MS_Description'
      AND minor_id = (
          SELECT column_id
          FROM sys.columns
          WHERE object_id = OBJECT_ID('engage360.member_campaign_enrollments_enhanced')
            AND name = 'call_5_timestamp'
      )
)
BEGIN
    EXEC sp_addextendedproperty
        @name = N'MS_Description',
        @value = N'Timestamp when Call 5 was made. Used to calculate 90-day window for Calls 5+ (call_5_timestamp + 90 days). NULL for enrollments that haven''t reached Call 5 yet. Set automatically by batch_orchestrator when 5th outreach attempt is created.',
        @level0type = N'SCHEMA', @level0name = N'engage360',
        @level1type = N'TABLE', @level1name = N'member_campaign_enrollments_enhanced',
        @level2type = N'COLUMN', @level2name = N'call_5_timestamp';

    PRINT '✓ Column description added successfully';
END
ELSE
BEGIN
    PRINT '⚠ Column description already exists - skipping';
END

PRINT '';

-- =====================================================
-- Step 4: Verify migration
-- =====================================================
PRINT 'Step 4: Verifying migration...';
PRINT '';

-- Verify column exists
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
  AND COLUMN_NAME = 'call_5_timestamp';

PRINT '';

-- Verify index exists
SELECT
    i.name AS index_name,
    i.type_desc AS index_type,
    i.is_unique,
    i.filter_definition
FROM sys.indexes i
WHERE i.object_id = OBJECT_ID('engage360.member_campaign_enrollments_enhanced')
  AND i.name = 'IX_enrollments_call5_device_activation';

PRINT '';

-- Verify all existing enrollments have NULL call_5_timestamp
DECLARE @null_count INT;
DECLARE @total_count INT;

SELECT @null_count = COUNT(*)
FROM engage360.member_campaign_enrollments_enhanced
WHERE call_5_timestamp IS NULL;

SELECT @total_count = COUNT(*)
FROM engage360.member_campaign_enrollments_enhanced;

PRINT 'Enrollment counts:';
PRINT '  Total enrollments: ' + CAST(@total_count AS VARCHAR(10));
PRINT '  With call_5_timestamp = NULL: ' + CAST(@null_count AS VARCHAR(10));

IF @null_count = @total_count
BEGIN
    PRINT '  ✓ All existing enrollments have call_5_timestamp = NULL (correct)';
END
ELSE
BEGIN
    PRINT '  ⚠ WARNING: Some enrollments have call_5_timestamp set (unexpected)';
END

PRINT '';
PRINT '========================================';
PRINT '✅ Migration completed successfully!';
PRINT '========================================';
PRINT '';
PRINT 'Next steps:';
PRINT '1. Deploy eligibility_service.py (handles NULL call_5_timestamp)';
PRINT '2. Deploy batch_orchestrator.py (sets call_5_timestamp for Call 5)';
PRINT '3. Deploy af_device_activation_logic.py (new enrollments with NULL campaign_end_date)';
PRINT '';
GO
