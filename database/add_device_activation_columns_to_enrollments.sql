-- =====================================================================================
-- Migration: Add Device Activation Columns to member_campaign_enrollments_enhanced
-- =====================================================================================
-- Purpose: Support Device Activation campaign lifecycle and call scheduling
-- Date: 2025-12-21
-- BusinessCaseID: BC-TBD (Device Activation System)
--
-- IMPORTANT: This migration MUST be run BEFORE deploying Device Activation code
--
-- Columns Added:
-- 1. activation_start_date - First business day on or after enrollment (Day 0)
-- 2. campaign_end_date - activation_start_date + 90 calendar days
-- 3. device_activated - Boolean flag for device activation status
-- =====================================================================================

-- Check if columns already exist before adding
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe'
    AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
    AND COLUMN_NAME = 'activation_start_date'
)
BEGIN
    -- Add activation_start_date column
    ALTER TABLE ioe.member_campaign_enrollments_enhanced
    ADD activation_start_date DATE NULL;

    PRINT '✅ Successfully added activation_start_date column';
END
ELSE
BEGIN
    PRINT '⚠️ Column activation_start_date already exists';
END
GO

-- Check if campaign_end_date column exists
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe'
    AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
    AND COLUMN_NAME = 'campaign_end_date'
)
BEGIN
    -- Add campaign_end_date column
    ALTER TABLE ioe.member_campaign_enrollments_enhanced
    ADD campaign_end_date DATE NULL;

    PRINT '✅ Successfully added campaign_end_date column';
END
ELSE
BEGIN
    PRINT '⚠️ Column campaign_end_date already exists';
END
GO

-- Check if device_activated column exists
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe'
    AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
    AND COLUMN_NAME = 'device_activated'
)
BEGIN
    -- Add device_activated column with default value 0
    ALTER TABLE ioe.member_campaign_enrollments_enhanced
    ADD device_activated BIT NULL DEFAULT 0;

    PRINT '✅ Successfully added device_activated column (default: 0)';
END
ELSE
BEGIN
    PRINT '⚠️ Column device_activated already exists';
END
GO

-- Verify all columns were added successfully
PRINT ''
PRINT '📋 Verification - Current Columns in member_campaign_enrollments_enhanced:'
PRINT '-------------------------------------------------------------------'

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe'
AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
AND COLUMN_NAME IN ('activation_start_date', 'campaign_end_date', 'device_activated')
ORDER BY COLUMN_NAME;

PRINT ''
PRINT '✅ MIGRATION COMPLETE'
PRINT ''
PRINT '📝 Next Steps:'
PRINT '   1. Verify columns exist in table (see output above)'
PRINT '   2. Deploy Device Activation file processor code'
PRINT '   3. Test CSV file upload and member enrollment'
PRINT '   4. Verify activation_start_date and campaign_end_date are populated correctly'
GO

-- =====================================================================================
-- Column Usage Documentation
-- =====================================================================================
--
-- activation_start_date (DATE NULL)
-- ---------------------------------
-- - First business day on or after enrollment_ts (Day 0)
-- - Calculated using business_hours_utils.is_business_day() and add_business_days()
-- - Used by scheduler to determine call eligibility
-- - Used by call sequence logic to calculate Day 2, Day 4, Day 9, etc.
-- - Example: enrollment_ts = 2025-12-20 (Friday) → activation_start_date = 2025-12-20
-- - Example: enrollment_ts = 2025-12-21 (Saturday) → activation_start_date = 2025-12-23 (Monday)
--
-- campaign_end_date (DATE NULL)
-- ------------------------------
-- - activation_start_date + 90 calendar days
-- - Enforces 90-day campaign lifecycle
-- - Used by scheduler to filter out expired enrollments
-- - Example: activation_start_date = 2025-12-20 → campaign_end_date = 2026-03-18
--
-- device_activated (BIT NULL DEFAULT 0)
-- --------------------------------------
-- - Boolean flag: 0 = not activated, 1 = activated
-- - Set to 0 on enrollment creation
-- - Updated to 1 when device activation is confirmed (via webhook or manual process)
-- - Used for reporting and status tracking
--
-- =====================================================================================
