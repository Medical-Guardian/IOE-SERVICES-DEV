-- Migration: Add address_country column to Device Activation staging table
-- Date: 2025-12-21
-- Purpose: Support storing country data from Device Activation CSV files
-- IMPORTANT: This migration MUST be run BEFORE deploying code changes

-- Check if column already exists
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
    AND TABLE_NAME = 'stg_device_activation_delta'
    AND COLUMN_NAME = 'address_country'
)
BEGIN
    -- Add address_country column to staging table
    ALTER TABLE ioe_stg.stg_device_activation_delta
    ADD address_country NVARCHAR(50) NULL;

    PRINT '✅ Successfully added address_country column to stg_device_activation_delta table';
END
ELSE
BEGIN
    PRINT '⚠️ Column address_country already exists in stg_device_activation_delta table';
END
GO
