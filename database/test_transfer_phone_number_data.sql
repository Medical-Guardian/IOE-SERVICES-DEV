-- ============================================================================
-- Test Data Query: transfer_phone_number Implementation
-- ============================================================================
-- Purpose: Verify transfer_phone_number data after processing test files
-- Run this AFTER processing a test CSV file with transfer_phone_number column
-- ============================================================================

-- ============================================================================
-- 1. Check Staging Table for Recent Data
-- ============================================================================
-- Shows last 10 rows with transfer_phone_number from staging
SELECT TOP 10
    file_batch_id,
    row_number_in_file,
    validation_status,
    salesforce_account_number,
    first_name,
    last_name,
    primary_phone,
    transfer_phone_number,
    enrollment_status,
    uploaded_ts
FROM ioe_stg.stg_device_activation_delta
WHERE uploaded_ts > DATEADD(hour, -24, GETDATE())  -- Last 24 hours
ORDER BY uploaded_ts DESC;

-- ============================================================================
-- 2. Check Enrollments Table for Recent Data
-- ============================================================================
-- Shows last 10 enrollments with transfer_phone_number
SELECT TOP 10
    e.enrollment_id,
    e.member_id,
    m.first_name,
    m.last_name,
    m.primary_phone,
    e.transfer_phone_number,
    e.current_status,
    e.enrollment_ts
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.members m ON e.member_id = m.member_id
WHERE e.enrollment_ts > DATEADD(hour, -24, GETDATE())  -- Last 24 hours
ORDER BY e.enrollment_ts DESC;

-- ============================================================================
-- 3. Compare Primary Phone vs Transfer Phone
-- ============================================================================
-- Shows members where transfer_phone_number differs from primary_phone
SELECT TOP 10
    e.enrollment_id,
    m.salesforce_account_number,
    m.first_name,
    m.last_name,
    m.primary_phone,
    e.transfer_phone_number,
    CASE
        WHEN m.primary_phone = e.transfer_phone_number THEN 'SAME'
        WHEN e.transfer_phone_number IS NULL THEN 'NULL'
        ELSE 'DIFFERENT'
    END AS phone_comparison
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.members m ON e.member_id = m.member_id
WHERE e.enrollment_ts > DATEADD(hour, -24, GETDATE())  -- Last 24 hours
ORDER BY e.enrollment_ts DESC;

-- ============================================================================
-- 4. E.164 Format Validation
-- ============================================================================
-- Verifies all transfer_phone_number values are valid E.164 format or NULL
SELECT
    COUNT(*) AS total_records,
    SUM(CASE WHEN transfer_phone_number IS NULL THEN 1 ELSE 0 END) AS null_count,
    SUM(CASE WHEN transfer_phone_number LIKE '+1__________' THEN 1 ELSE 0 END) AS valid_e164_count,
    SUM(CASE
        WHEN transfer_phone_number IS NOT NULL
        AND transfer_phone_number NOT LIKE '+1__________'
        THEN 1
        ELSE 0
    END) AS invalid_format_count
FROM ioe.member_campaign_enrollments_enhanced
WHERE enrollment_ts > DATEADD(day, -7, GETDATE());  -- Last 7 days

-- ============================================================================
-- 5. Sample Invalid Formats (If Any)
-- ============================================================================
-- Shows examples of invalid transfer_phone_number formats
-- Expected: 0 rows (all should be valid E.164 or NULL)
SELECT TOP 10
    enrollment_id,
    member_id,
    transfer_phone_number,
    LEN(transfer_phone_number) AS phone_length,
    enrollment_ts
FROM ioe.member_campaign_enrollments_enhanced
WHERE enrollment_ts > DATEADD(day, -7, GETDATE())
  AND transfer_phone_number IS NOT NULL
  AND transfer_phone_number NOT LIKE '+1__________'
ORDER BY enrollment_ts DESC;

-- ============================================================================
-- 6. Distribution Analysis
-- ============================================================================
-- Shows how many enrollments have transfer_phone_number vs NULL
SELECT
    CASE
        WHEN transfer_phone_number IS NULL THEN 'NULL'
        ELSE 'HAS_VALUE'
    END AS transfer_phone_status,
    COUNT(*) AS enrollment_count,
    CAST(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS DECIMAL(5,2)) AS percentage
FROM ioe.member_campaign_enrollments_enhanced
WHERE enrollment_ts > DATEADD(day, -7, GETDATE())  -- Last 7 days
GROUP BY
    CASE
        WHEN transfer_phone_number IS NULL THEN 'NULL'
        ELSE 'HAS_VALUE'
    END;

-- ============================================================================
-- 7. Test Specific Enrollment
-- ============================================================================
-- Replace <enrollment_id> with actual test enrollment ID
-- Uncomment and run to check specific enrollment details
/*
SELECT
    e.enrollment_id,
    e.member_id,
    m.salesforce_account_number,
    m.first_name,
    m.last_name,
    m.primary_phone,
    e.transfer_phone_number,
    e.current_status,
    e.enrollment_ts,
    e.activation_start_date,
    e.campaign_end_date
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.members m ON e.member_id = m.member_id
WHERE e.enrollment_id = '<enrollment_id>';
*/

-- ============================================================================
-- 8. Campaign-Level Analysis
-- ============================================================================
-- Shows transfer_phone_number usage by campaign
SELECT
    c.campaign_id,
    c.name AS campaign_name,
    COUNT(e.enrollment_id) AS total_enrollments,
    SUM(CASE WHEN e.transfer_phone_number IS NOT NULL THEN 1 ELSE 0 END) AS with_transfer_phone,
    SUM(CASE WHEN e.transfer_phone_number IS NULL THEN 1 ELSE 0 END) AS without_transfer_phone,
    CAST(SUM(CASE WHEN e.transfer_phone_number IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(e.enrollment_id) AS DECIMAL(5,2)) AS transfer_phone_percentage
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE e.enrollment_ts > DATEADD(day, -7, GETDATE())
  AND c.campaign_type IN ('Device Activation', 'Operations')
GROUP BY c.campaign_id, c.name
ORDER BY total_enrollments DESC;

-- ============================================================================
-- Expected Results:
-- ============================================================================
-- 1. Staging table should show transfer_phone_number values (NULL or +1XXXXXXXXXX)
-- 2. Enrollments table should show transfer_phone_number values synced from staging
-- 3. Phone comparison should show SAME/DIFFERENT/NULL distributions
-- 4. E.164 validation should show 0 invalid_format_count
-- 5. Invalid formats query should return 0 rows
-- 6. Distribution should show % of enrollments with vs without transfer_phone_number
-- 7. Test specific enrollment should show all details
-- 8. Campaign analysis should show transfer_phone_number adoption by campaign
-- ============================================================================
