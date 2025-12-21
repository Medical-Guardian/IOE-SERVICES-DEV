-- =====================================================================================
-- Add Device Activation Columns to member_devices Table
-- =====================================================================================
-- Purpose: Add support for Device Activation data (brand, battery status, fall detection)
-- BusinessCaseID: BC-TBD (Device Activation System)
-- Created: 2025-12-21
--
-- Adds 4 columns to engage360.member_devices table:
-- 1. brand - Device brand (MedScope, MG State Pay, etc.)
-- 2. battery_status - Battery status (Good/Low/Critical)
-- 3. fall_detection_status - Fall detection status (Active/Inactive)
-- 4. updated_ts - Last update timestamp
--
-- Note: Existing fall_detection BIT column is kept for backward compatibility
-- =====================================================================================

-- Add brand column
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'member_devices'
    AND COLUMN_NAME = 'brand'
)
BEGIN
    PRINT '✅ Adding column: brand'
    ALTER TABLE engage360.member_devices
    ADD brand NVARCHAR(100) NULL;
    PRINT '   Added: brand NVARCHAR(100) NULL'
END
ELSE
    PRINT '⚠️  Column brand already exists'

-- Add battery_status column
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'member_devices'
    AND COLUMN_NAME = 'battery_status'
)
BEGIN
    PRINT '✅ Adding column: battery_status'
    ALTER TABLE engage360.member_devices
    ADD battery_status NVARCHAR(50) NULL;
    PRINT '   Added: battery_status NVARCHAR(50) NULL'
END
ELSE
    PRINT '⚠️  Column battery_status already exists'

-- Add fall_detection_status column (string version of fall_detection BIT)
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'member_devices'
    AND COLUMN_NAME = 'fall_detection_status'
)
BEGIN
    PRINT '✅ Adding column: fall_detection_status'
    ALTER TABLE engage360.member_devices
    ADD fall_detection_status NVARCHAR(50) NULL;
    PRINT '   Added: fall_detection_status NVARCHAR(50) NULL'
END
ELSE
    PRINT '⚠️  Column fall_detection_status already exists'

-- Add updated_ts column
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'member_devices'
    AND COLUMN_NAME = 'updated_ts'
)
BEGIN
    PRINT '✅ Adding column: updated_ts'
    ALTER TABLE engage360.member_devices
    ADD updated_ts DATETIMEOFFSET(7) NULL;
    PRINT '   Added: updated_ts DATETIMEOFFSET(7) NULL'
END
ELSE
    PRINT '⚠️  Column updated_ts already exists'

PRINT ''
PRINT '✅ MIGRATION COMPLETE'
PRINT ''
PRINT '📋 Columns Added to engage360.member_devices:'
PRINT '   1. brand NVARCHAR(100) NULL'
PRINT '   2. battery_status NVARCHAR(50) NULL'
PRINT '   3. fall_detection_status NVARCHAR(50) NULL'
PRINT '   4. updated_ts DATETIMEOFFSET(7) NULL'
PRINT ''
PRINT '📝 Note: Existing fall_detection BIT column is kept for backward compatibility'
