-- =====================================================================================
-- Create Table: engage360.bland_raw_response
-- Purpose: Store raw Bland AI webhook JSON payloads separately from bland_call_logs
-- Reason: Optimize bland_call_logs table size by moving large JSON blobs
-- Date: 2025-01-03
-- =====================================================================================

-- Create the table
CREATE TABLE engage360.bland_raw_response (
    raw_response_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    call_id NVARCHAR(255) NOT NULL UNIQUE,  -- Links to bland_call_logs.call_id
    raw_response NVARCHAR(MAX) NOT NULL,     -- Full webhook JSON payload
    created_at DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),

    -- Foreign key to bland_call_logs (ensures referential integrity)
    CONSTRAINT FK_bland_raw_response_call_id
        FOREIGN KEY (call_id)
        REFERENCES engage360.bland_call_logs(call_id)
        ON DELETE CASCADE  -- If call log deleted, delete raw response too
);

-- Create index for fast lookups by call_id
CREATE INDEX IX_bland_raw_response_call_id
ON engage360.bland_raw_response(call_id);

-- Create index for filtering by creation date (for data retention queries)
CREATE INDEX IX_bland_raw_response_created_at
ON engage360.bland_raw_response(created_at);

-- Verify table creation
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'bland_raw_response'
ORDER BY ORDINAL_POSITION;

-- =====================================================================================
-- Post-Deployment Validation Queries
-- =====================================================================================

-- Check table exists
IF OBJECT_ID('engage360.bland_raw_response', 'U') IS NOT NULL
    PRINT '✅ Table engage360.bland_raw_response created successfully'
ELSE
    PRINT '❌ ERROR: Table engage360.bland_raw_response not found';

-- Check indexes exist
SELECT
    i.name AS index_name,
    i.type_desc AS index_type,
    OBJECT_NAME(i.object_id) AS table_name
FROM sys.indexes i
WHERE OBJECT_NAME(i.object_id) = 'bland_raw_response'
  AND i.name IS NOT NULL;

-- =====================================================================================
-- Sample Queries for Testing
-- =====================================================================================

-- Query to verify data after deployment (should start getting records after code deployment)
-- SELECT
--     COUNT(*) as total_records,
--     MIN(created_at) as first_record,
--     MAX(created_at) as last_record,
--     AVG(LEN(raw_response)) as avg_json_size_bytes
-- FROM engage360.bland_raw_response;

-- Query to check relationship with bland_call_logs
-- SELECT
--     bcl.call_id,
--     bcl.status,
--     bcl.created_at as call_log_created,
--     brr.created_at as raw_response_created,
--     CASE
--         WHEN brr.call_id IS NOT NULL THEN 'Has raw response'
--         ELSE 'Missing raw response'
--     END as audit_status
-- FROM engage360.bland_call_logs bcl
-- LEFT JOIN engage360.bland_raw_response brr ON bcl.call_id = brr.call_id
-- WHERE bcl.created_at > DATEADD(day, -1, GETDATE())
-- ORDER BY bcl.created_at DESC;
