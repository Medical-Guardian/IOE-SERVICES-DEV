-- ============================================================================
-- Verification Script: transfer_phone_number Column Implementation
-- ============================================================================
-- Purpose: Verify that transfer_phone_number columns exist and are properly configured
-- Run this AFTER executing add_transfer_phone_number_column.sql migration
-- Expected: 2 rows (1 for staging, 1 for enrollments)
-- ============================================================================

-- Check staging table column
SELECT
    'Staging Table' AS table_location,
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'transfer_phone_number'

UNION ALL

-- Check enrollments table column
SELECT
    'Enrollments Table' AS table_location,
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
  AND COLUMN_NAME = 'transfer_phone_number';

-- ============================================================================
-- Expected Results:
-- ============================================================================
-- table_location         TABLE_SCHEMA    TABLE_NAME                              COLUMN_NAME             DATA_TYPE   MAX_LENGTH  IS_NULLABLE  DEFAULT
-- Staging Table          engage360_stg   stg_device_activation_delta             transfer_phone_number   varchar     20          YES          NULL
-- Enrollments Table      engage360       member_campaign_enrollments_enhanced    transfer_phone_number   varchar     20          YES          NULL
-- ============================================================================

-- ============================================================================
-- If no rows are returned, the migration has NOT been run yet.
-- If only 1 row is returned, one of the tables is missing the column.
-- If 2 rows are returned with correct data types, migration is successful.
-- ============================================================================
