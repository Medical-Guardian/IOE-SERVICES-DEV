-- =====================================================================================
-- Testing SQL Queries for bland_raw_response Table Implementation
-- Purpose: Validate the separation of raw_bland_response from bland_call_logs
-- Date: 2025-01-03
-- =====================================================================================

-- =====================================================================================
-- PRE-DEPLOYMENT TESTS
-- =====================================================================================

-- Test 1: Verify table doesn't exist yet (should return 0)
SELECT COUNT(*) as table_exists
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'bland_raw_response';
-- Expected: 0

-- =====================================================================================
-- POST-DEPLOYMENT VALIDATION
-- =====================================================================================

-- Test 2: Verify table created successfully
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'bland_raw_response'
ORDER BY ORDINAL_POSITION;
-- Expected: 4 rows (raw_response_id, call_id, raw_response, created_at)

-- Test 3: Verify indexes created
SELECT
    i.name AS index_name,
    i.type_desc AS index_type,
    c.name AS column_name
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE OBJECT_NAME(i.object_id) = 'bland_raw_response'
  AND i.name IS NOT NULL
ORDER BY i.name, ic.key_ordinal;
-- Expected: PK_bland_raw_response, IX_bland_raw_response_call_id, IX_bland_raw_response_created_at

-- Test 4: Verify foreign key constraint
SELECT
    fk.name AS foreign_key_name,
    OBJECT_NAME(fk.parent_object_id) AS table_name,
    COL_NAME(fc.parent_object_id, fc.parent_column_id) AS column_name,
    OBJECT_NAME(fk.referenced_object_id) AS referenced_table,
    COL_NAME(fc.referenced_object_id, fc.referenced_column_id) AS referenced_column
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fc
    ON fk.object_id = fc.constraint_object_id
WHERE OBJECT_NAME(fk.parent_object_id) = 'bland_raw_response';
-- Expected: FK_bland_raw_response_call_id referencing bland_call_logs(call_id)

-- =====================================================================================
-- POST-CODE-DEPLOYMENT VALIDATION
-- =====================================================================================

-- Test 5: Verify new records have NULL in bland_call_logs.raw_bland_response
SELECT
    call_id,
    status,
    created_at,
    CASE
        WHEN raw_bland_response IS NULL THEN '✅ NULL (expected)'
        ELSE '❌ Has data (unexpected)'
    END as raw_bland_response_status,
    LEN(raw_bland_response) as json_size_bytes
FROM engage360.bland_call_logs
WHERE created_at > DATEADD(hour, -1, GETDATE())  -- Last hour
ORDER BY created_at DESC;
-- Expected: raw_bland_response should be NULL for all new records

-- Test 6: Verify new records ARE being inserted to bland_raw_response
SELECT
    COUNT(*) as total_records,
    MIN(created_at) as first_record,
    MAX(created_at) as last_record,
    AVG(LEN(raw_response)) as avg_json_size_bytes,
    MAX(LEN(raw_response)) as max_json_size_bytes,
    MIN(LEN(raw_response)) as min_json_size_bytes
FROM engage360.bland_raw_response
WHERE created_at > DATEADD(hour, -1, GETDATE());
-- Expected: Records should exist if webhooks have been processed

-- Test 7: Verify 1:1 relationship - all bland_call_logs have corresponding bland_raw_response
SELECT
    bcl.call_id,
    bcl.status,
    bcl.created_at as call_log_time,
    brr.created_at as raw_response_time,
    CASE
        WHEN brr.call_id IS NOT NULL THEN '✅ Has raw response'
        WHEN bcl.created_at < DATEADD(hour, -1, GETDATE()) THEN '⚠️ Old record (before deployment)'
        ELSE '❌ Missing raw response'
    END as audit_status
FROM engage360.bland_call_logs bcl
LEFT JOIN engage360.bland_raw_response brr ON bcl.call_id = brr.call_id
WHERE bcl.created_at > DATEADD(hour, -2, GETDATE())  -- Last 2 hours
ORDER BY bcl.created_at DESC;
-- Expected: All new records (after deployment) should have raw response

-- Test 8: Find any orphaned raw_response records (shouldn't exist due to FK constraint)
SELECT
    brr.call_id,
    brr.created_at,
    '❌ Orphaned - no corresponding call_log' as issue
FROM engage360.bland_raw_response brr
LEFT JOIN engage360.bland_call_logs bcl ON brr.call_id = bcl.call_id
WHERE bcl.call_id IS NULL;
-- Expected: 0 rows (FK constraint should prevent this)

-- Test 9: Verify transaction atomicity - check for partial failures
SELECT
    'bland_call_logs' as table_name,
    COUNT(*) as records_last_hour
FROM engage360.bland_call_logs
WHERE created_at > DATEADD(hour, -1, GETDATE())
UNION ALL
SELECT
    'bland_raw_response' as table_name,
    COUNT(*) as records_last_hour
FROM engage360.bland_raw_response
WHERE created_at > DATEADD(hour, -1, GETDATE());
-- Expected: Both tables should have same count (atomic transaction)

-- =====================================================================================
-- DATA QUALITY CHECKS
-- =====================================================================================

-- Test 10: Verify raw_response contains valid JSON
SELECT
    call_id,
    created_at,
    LEN(raw_response) as json_size,
    CASE
        WHEN ISJSON(raw_response) = 1 THEN '✅ Valid JSON'
        ELSE '❌ Invalid JSON'
    END as json_validity
FROM engage360.bland_raw_response
WHERE created_at > DATEADD(hour, -1, GETDATE())
ORDER BY created_at DESC;
-- Expected: All should be valid JSON

-- Test 11: Verify raw_response contains expected webhook fields
SELECT
    call_id,
    created_at,
    CASE WHEN raw_response LIKE '%"call_id"%' THEN '✅' ELSE '❌' END as has_call_id,
    CASE WHEN raw_response LIKE '%"status"%' THEN '✅' ELSE '❌' END as has_status,
    CASE WHEN raw_response LIKE '%"metadata"%' THEN '✅' ELSE '❌' END as has_metadata,
    CASE WHEN raw_response LIKE '%"transcripts"%' THEN '✅' ELSE '❌' END as has_transcripts
FROM engage360.bland_raw_response
WHERE created_at > DATEADD(hour, -1, GETDATE())
ORDER BY created_at DESC;
-- Expected: All should have ✅ for key webhook fields

-- =====================================================================================
-- PERFORMANCE CHECKS
-- =====================================================================================

-- Test 12: Compare table sizes (after deployment)
SELECT
    t.name AS table_name,
    SUM(a.total_pages) * 8 AS total_space_kb,
    SUM(a.used_pages) * 8 AS used_space_kb,
    (SUM(a.total_pages) - SUM(a.used_pages)) * 8 AS unused_space_kb,
    p.rows AS row_count
FROM sys.tables t
INNER JOIN sys.indexes i ON t.object_id = i.object_id
INNER JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id
INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
WHERE t.name IN ('bland_call_logs', 'bland_raw_response')
  AND i.object_id > 255
  AND i.index_id <= 1
GROUP BY t.name, p.rows
ORDER BY t.name;
-- Expected: bland_raw_response should be growing, bland_call_logs should be smaller per row

-- Test 13: Query performance - lookup by call_id (should be fast with index)
SET STATISTICS TIME ON;
SET STATISTICS IO ON;

SELECT call_id, LEN(raw_response) as json_size
FROM engage360.bland_raw_response
WHERE call_id = 'test_call_id_here';  -- Replace with actual call_id

SET STATISTICS TIME OFF;
SET STATISTICS IO OFF;
-- Expected: Fast lookup due to IX_bland_raw_response_call_id index

-- =====================================================================================
-- BUSINESS LOGIC VALIDATION
-- =====================================================================================

-- Test 14: Verify duplicate detection still works (relies on bland_call_logs.call_id)
SELECT
    call_id,
    COUNT(*) as duplicate_count
FROM engage360.bland_call_logs
WHERE created_at > DATEADD(day, -1, GETDATE())
GROUP BY call_id
HAVING COUNT(*) > 1;
-- Expected: 0 rows (no duplicates should exist)

-- Test 15: Verify webhook data can be retrieved for audit (join query)
SELECT
    bcl.call_id,
    bcl.status,
    bcl.disposition_tag,
    bcl.member_id,
    bcl.campaign_id,
    bcl.created_at as call_time,
    brr.raw_response,
    LEN(brr.raw_response) as raw_json_size
FROM engage360.bland_call_logs bcl
INNER JOIN engage360.bland_raw_response brr ON bcl.call_id = brr.call_id
WHERE bcl.call_id = 'specific_call_id_here'  -- Replace with actual call_id for audit
;
-- Expected: Returns complete call data including raw webhook JSON for compliance audit

-- =====================================================================================
-- MONITORING QUERIES (Use for Ongoing Health Checks)
-- =====================================================================================

-- Monitor 1: Daily record counts (should match)
SELECT
    CAST(created_at AS DATE) as date,
    COUNT(*) as records
FROM engage360.bland_call_logs
WHERE created_at > DATEADD(day, -7, GETDATE())
GROUP BY CAST(created_at AS DATE)
ORDER BY date DESC;

SELECT
    CAST(created_at AS DATE) as date,
    COUNT(*) as records
FROM engage360.bland_raw_response
WHERE created_at > DATEADD(day, -7, GETDATE())
GROUP BY CAST(created_at AS DATE)
ORDER BY date DESC;
-- Expected: Counts should match for dates after deployment

-- Monitor 2: Storage growth tracking
SELECT
    'bland_call_logs' as table_name,
    COUNT(*) as total_rows,
    SUM(CASE WHEN raw_bland_response IS NULL THEN 1 ELSE 0 END) as rows_with_null,
    SUM(CASE WHEN raw_bland_response IS NOT NULL THEN 1 ELSE 0 END) as rows_with_data,
    AVG(CASE WHEN raw_bland_response IS NOT NULL THEN LEN(raw_bland_response) ELSE 0 END) as avg_old_json_size
FROM engage360.bland_call_logs
UNION ALL
SELECT
    'bland_raw_response' as table_name,
    COUNT(*) as total_rows,
    COUNT(*) as rows_with_null,  -- All have data
    0 as rows_with_data,
    AVG(LEN(raw_response)) as avg_json_size
FROM engage360.bland_raw_response;

-- Monitor 3: Check for failed transactions (missing pairs)
SELECT
    'Missing in bland_raw_response' as issue_type,
    COUNT(*) as count
FROM engage360.bland_call_logs bcl
LEFT JOIN engage360.bland_raw_response brr ON bcl.call_id = brr.call_id
WHERE bcl.created_at > DATEADD(hour, -24, GETDATE())
  AND brr.call_id IS NULL
UNION ALL
SELECT
    'Missing in bland_call_logs' as issue_type,
    COUNT(*) as count
FROM engage360.bland_raw_response brr
LEFT JOIN engage360.bland_call_logs bcl ON brr.call_id = bcl.call_id
WHERE brr.created_at > DATEADD(hour, -24, GETDATE())
  AND bcl.call_id IS NULL;
-- Expected: 0 for both (transaction ensures atomicity)

-- =====================================================================================
-- END OF TESTING QUERIES
-- =====================================================================================
