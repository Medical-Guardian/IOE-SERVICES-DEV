-- =====================================================================================
-- Database Migration: Rename battery_status to powersaver_mode
-- =====================================================================================
-- Purpose: Align column naming with actual data semantics (powersaver mode settings)
-- Created: 2025-12-22
-- Tables Affected:
--   1. engage360.member_devices (production)
--   2. engage360_stg.stg_device_activation_delta (staging)
-- =====================================================================================

PRINT '📋 Starting battery_status → powersaver_mode column rename migration...';
PRINT '';

-- =====================================================================================
-- PART 1: Production Table (engage360.member_devices)
-- =====================================================================================

PRINT '🔧 [PRODUCTION] Renaming column in engage360.member_devices...';

-- Check if old column exists
IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
      AND TABLE_NAME = 'member_devices'
      AND COLUMN_NAME = 'battery_status'
)
BEGIN
    -- Check if new column already exists
    IF NOT EXISTS (
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'engage360'
          AND TABLE_NAME = 'member_devices'
          AND COLUMN_NAME = 'powersaver_mode'
    )
    BEGIN
        -- Rename the column
        EXEC sp_rename
            'engage360.member_devices.battery_status',
            'powersaver_mode',
            'COLUMN';

        PRINT '✅ [PRODUCTION] Column renamed: battery_status → powersaver_mode';
    END
    ELSE
    BEGIN
        PRINT '⚠️  [PRODUCTION] Column powersaver_mode already exists. Skipping rename.';
        PRINT '⚠️  [PRODUCTION] Manual intervention may be required if both columns exist.';
    END
END
ELSE
BEGIN
    PRINT 'ℹ️  [PRODUCTION] Column battery_status does not exist. Already migrated or not created yet.';
END

PRINT '';

-- =====================================================================================
-- PART 2: Staging Table (engage360_stg.stg_device_activation_delta)
-- =====================================================================================

PRINT '🔧 [STAGING] Renaming column in engage360_stg.stg_device_activation_delta...';

-- Check if old column exists
IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'battery_status'
)
BEGIN
    -- Check if new column already exists
    IF NOT EXISTS (
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'engage360_stg'
          AND TABLE_NAME = 'stg_device_activation_delta'
          AND COLUMN_NAME = 'powersaver_mode'
    )
    BEGIN
        -- Rename the column
        EXEC sp_rename
            'engage360_stg.stg_device_activation_delta.battery_status',
            'powersaver_mode',
            'COLUMN';

        PRINT '✅ [STAGING] Column renamed: battery_status → powersaver_mode';
    END
    ELSE
    BEGIN
        PRINT '⚠️  [STAGING] Column powersaver_mode already exists. Skipping rename.';
        PRINT '⚠️  [STAGING] Manual intervention may be required if both columns exist.';
    END
END
ELSE
BEGIN
    PRINT 'ℹ️  [STAGING] Column battery_status does not exist. Already migrated or not created yet.';
END

PRINT '';
PRINT '✅ Migration complete!';
PRINT '';

-- =====================================================================================
-- VERIFICATION QUERIES
-- =====================================================================================

PRINT '🔍 Verifying column rename in production table...';
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'member_devices'
  AND COLUMN_NAME IN ('battery_status', 'powersaver_mode')
ORDER BY COLUMN_NAME;

PRINT '';
PRINT '🔍 Verifying column rename in staging table...';
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME IN ('battery_status', 'powersaver_mode')
ORDER BY COLUMN_NAME;

PRINT '';
PRINT '📊 Expected results:';
PRINT '   Production: Should show ONLY powersaver_mode (NVARCHAR(50), YES)';
PRINT '   Staging: Should show ONLY powersaver_mode (NVARCHAR(50), YES)';
PRINT '';

-- =====================================================================================
-- END OF MIGRATION SCRIPT
-- =====================================================================================
