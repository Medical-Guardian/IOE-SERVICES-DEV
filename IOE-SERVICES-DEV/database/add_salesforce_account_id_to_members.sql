-- =====================================================================================
-- Script: Add salesforce_account_id Column to members Table
-- Purpose: Support Operations Device Activation campaigns (Medicaid, DTC/MA)
-- Date: 2025-12-18
-- Campaign Type: Operations
-- =====================================================================================

-- =====================================================================================
-- STEP 1: Check if salesforce_account_id column already exists
-- =====================================================================================
-- Run this query first to check if the column exists:
/*
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'salesforce_account_id';
*/

-- If the query returns NO ROWS, proceed with STEP 2 below
-- If the query returns 1 ROW, the column already exists - SKIP STEP 2

-- =====================================================================================
-- STEP 2: Add salesforce_account_id column (ONLY IF STEP 1 RETURNED NO ROWS)
-- =====================================================================================

-- Add salesforce_account_id column to members table
ALTER TABLE engage360.members
ADD salesforce_account_id NVARCHAR(50) NULL;

GO

-- Create index for efficient lookups
CREATE NONCLUSTERED INDEX IX_members_salesforce_account_id
ON engage360.members (salesforce_account_id)
WHERE salesforce_account_id IS NOT NULL;

GO

-- =====================================================================================
-- STEP 3: Verify the column was added successfully
-- =====================================================================================
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'salesforce_account_id';

-- Expected output:
-- COLUMN_NAME              DATA_TYPE    CHARACTER_MAXIMUM_LENGTH    IS_NULLABLE
-- salesforce_account_id    nvarchar     50                          YES

GO

-- =====================================================================================
-- STEP 4: Verify the index was created successfully
-- =====================================================================================
SELECT
    i.name AS IndexName,
    i.type_desc AS IndexType,
    OBJECT_NAME(ic.object_id) AS TableName,
    COL_NAME(ic.object_id, ic.column_id) AS ColumnName
FROM sys.indexes i
INNER JOIN sys.index_columns ic
    ON i.object_id = ic.object_id
    AND i.index_id = ic.index_id
WHERE i.name = 'IX_members_salesforce_account_id'
  AND OBJECT_NAME(ic.object_id) = 'members';

-- Expected output:
-- IndexName                            IndexType       TableName    ColumnName
-- IX_members_salesforce_account_id     NONCLUSTERED    members      salesforce_account_id

GO

-- =====================================================================================
-- NOTES:
-- =====================================================================================
-- 1. salesforce_account_id is separate from salesforce_account_number
-- 2. salesforce_account_number is the primary business key for member matching
-- 3. salesforce_account_id is an additional Salesforce identifier from CSV files
-- 4. Column is nullable to support existing members without this field
-- 5. Index uses WHERE clause to only index non-NULL values for efficiency
-- =====================================================================================
