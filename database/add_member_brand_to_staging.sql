-- =====================================================================================
-- Migration: Add member_brand Column to stg_device_activation_delta
-- =====================================================================================
-- Purpose: Support member_brand CSV column (member's plan brand like "Medical Guardian")
--          This is separate from device brand (device model like "MG Mini")
-- Date: 2025-12-21
-- BusinessCaseID: BC-TBD (Device Activation System)
--
-- IMPORTANT: This migration MUST be run BEFORE deploying code that uses member_brand
--
-- Context:
-- - CSV has TWO brand columns: member_brand (member's plan) and device_name (device model)
-- - member_brand → saved to members.member_brand table
-- - device_name → saved to member_devices.brand table
-- - Both columns should exist separately
-- =====================================================================================

-- Check if column already exists before adding
IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
    AND TABLE_NAME = 'stg_device_activation_delta'
    AND COLUMN_NAME = 'member_brand'
)
BEGIN
    -- Add member_brand column to staging table
    ALTER TABLE ioe_stg.stg_device_activation_delta
    ADD member_brand NVARCHAR(100) NULL;

    PRINT '✅ Successfully added member_brand column to stg_device_activation_delta';
    PRINT 'ℹ️  Column: member_brand NVARCHAR(100) NULL';
    PRINT 'ℹ️  Purpose: Stores member plan brand (e.g., "Medical Guardian", "MedScope")';
END
ELSE
BEGIN
    PRINT '⚠️ Column member_brand already exists in stg_device_activation_delta';
END
GO

-- Verify column was added successfully
PRINT ''
PRINT '📋 Verification - member_brand Column Details:'
PRINT '-------------------------------------------------------------------'

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe_stg'
AND TABLE_NAME = 'stg_device_activation_delta'
AND COLUMN_NAME = 'member_brand';

PRINT ''
PRINT '✅ MIGRATION COMPLETE'
PRINT ''
PRINT '📝 Next Steps:'
PRINT '   1. Verify column exists in table (see output above)'
PRINT '   2. Deploy updated Device Activation file processor code'
PRINT '   3. Test CSV file upload with member_brand column'
PRINT '   4. Verify member_brand is saved to members.member_brand table'
GO

-- =====================================================================================
-- Column Usage Documentation
-- =====================================================================================
--
-- member_brand (NVARCHAR(100) NULL) - NEW COLUMN
-- ----------------------------------------------
-- - Stores member's plan brand from CSV column "member_brand"
-- - Examples: "Medical Guardian", "MedScope", "MG State Pay"
-- - This is the member's subscription/plan brand, NOT the device model
-- - Will be saved to members.member_brand table during Phase 4 (Transform & Load)
--
-- IMPORTANT: This is different from the existing "brand" column:
-- - "brand" column stores device brand (from CSV column "device_name")
-- - "member_brand" column stores member plan brand (from CSV column "member_brand")
-- - Both columns are needed and serve different purposes
--
-- CSV Mapping:
-- - CSV column "member_brand" → staging.member_brand → members.member_brand
-- - CSV column "device_name" → staging.brand → member_devices.brand
--
-- =====================================================================================
