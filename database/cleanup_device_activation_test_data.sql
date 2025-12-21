-- =====================================================================================
-- Device Activation Test Data Cleanup Queries
-- =====================================================================================
-- Purpose: Remove duplicate enrollments and test data from Device Activation campaigns
-- Created: 2025-12-21
-- BusinessCaseID: BC-TBD (Device Activation System)
--
-- IMPORTANT: These queries delete data! Always run in transactions and verify before committing.
--
-- This file contains 4 cleanup queries:
-- 1. Diagnostic - Find duplicate enrollments
-- 2. Delete duplicates (keep oldest enrollment)
-- 3. Delete specific test member data (surgical delete)
-- 4. Nuclear option - Delete ALL Device Activation test data
-- =====================================================================================

-- =====================================================================================
-- QUERY 1: DIAGNOSTIC - Find Duplicate Enrollments
-- =====================================================================================
-- Purpose: Identify members with multiple enrollments in same Device Activation campaign
-- Use this first to diagnose duplicate enrollment issues before running cleanup

SELECT
    e.member_id,
    m.first_name,
    m.last_name,
    m.salesforce_account_number,
    e.campaign_id,
    c.campaign_name,
    COUNT(*) AS enrollment_count,
    STRING_AGG(CAST(e.enrollment_id AS NVARCHAR(36)), ', ') AS enrollment_ids,
    MIN(e.enrollment_ts) AS oldest_enrollment,
    MAX(e.enrollment_ts) AS newest_enrollment
FROM engage360.member_campaign_enrollments_enhanced e
JOIN engage360.members m ON e.member_id = m.member_id
JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE c.campaign_type IN ('Device Activation', 'Operations')
  AND c.campaign_name LIKE '%Device Activation%'
GROUP BY
    e.member_id, m.first_name, m.last_name, m.salesforce_account_number,
    e.campaign_id, c.campaign_name
HAVING COUNT(*) > 1
ORDER BY enrollment_count DESC, m.salesforce_account_number;

PRINT '📋 Query 1 Complete: Review duplicate enrollments above';
PRINT '⚠️  If duplicates found, proceed to Query 2 to clean them up';
GO

-- =====================================================================================
-- QUERY 2: CLEANUP - Delete Duplicate Enrollments (Keep Oldest)
-- =====================================================================================
-- Purpose: Delete duplicate enrollments, keeping the oldest enrollment_id per member+campaign
--
-- CAUTION: This will DELETE data!
-- IMPORTANT: Run Query 1 first to identify duplicates
-- IMPORTANT: Run in a transaction and verify before committing
--
-- Logic: For each (member_id, campaign_id) pair with duplicates:
--        - Keep the enrollment with the earliest enrollment_ts
--        - Delete all newer duplicate enrollments
-- =====================================================================================

BEGIN TRANSACTION;

PRINT '🧹 Starting duplicate enrollment cleanup...';
PRINT '';

-- Show what will be deleted (for confirmation)
PRINT '📋 Enrollments that will be DELETED (keeping oldest):';
SELECT
    e2.enrollment_id AS enrollment_to_delete,
    m.salesforce_account_number,
    m.first_name + ' ' + m.last_name AS member_name,
    c.campaign_name,
    e2.enrollment_ts AS duplicate_enrollment_ts,
    e1.enrollment_ts AS oldest_enrollment_ts_kept
FROM engage360.member_campaign_enrollments_enhanced e1
JOIN engage360.member_campaign_enrollments_enhanced e2
    ON e1.member_id = e2.member_id
    AND e1.campaign_id = e2.campaign_id
JOIN engage360.members m ON e2.member_id = m.member_id
JOIN engage360.campaigns_enhanced c ON e1.campaign_id = c.campaign_id
WHERE c.campaign_type IN ('Device Activation', 'Operations')
  AND c.campaign_name LIKE '%Device Activation%'
  AND e1.enrollment_ts < e2.enrollment_ts  -- e1 is older (will be kept)
ORDER BY m.salesforce_account_number, e2.enrollment_ts;

PRINT '';
PRINT '🗑️  Deleting duplicate enrollments...';

-- Delete duplicates, keeping the oldest enrollment_id
DELETE FROM engage360.member_campaign_enrollments_enhanced
WHERE enrollment_id IN (
    SELECT e2.enrollment_id
    FROM engage360.member_campaign_enrollments_enhanced e1
    JOIN engage360.member_campaign_enrollments_enhanced e2
        ON e1.member_id = e2.member_id
        AND e1.campaign_id = e2.campaign_id
    JOIN engage360.campaigns_enhanced c ON e1.campaign_id = c.campaign_id
    WHERE c.campaign_type IN ('Device Activation', 'Operations')
      AND c.campaign_name LIKE '%Device Activation%'
      AND e1.enrollment_ts < e2.enrollment_ts  -- e1 is older (keep it)
);

PRINT '✅ Deleted ' + CAST(@@ROWCOUNT AS NVARCHAR(10)) + ' duplicate enrollments';
PRINT '';

-- Verification: Check for remaining duplicates
PRINT '🔍 Verification - Checking for remaining duplicates:';
SELECT
    member_id, campaign_id, COUNT(*) AS count
FROM engage360.member_campaign_enrollments_enhanced e
JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE c.campaign_type IN ('Device Activation', 'Operations')
  AND c.campaign_name LIKE '%Device Activation%'
GROUP BY member_id, campaign_id
HAVING COUNT(*) > 1;

PRINT '';
PRINT '⚠️  TRANSACTION OPEN - Review verification results above';
PRINT '✅ If verification shows 0 rows (no duplicates), run: COMMIT';
PRINT '❌ If issues found, run: ROLLBACK';
PRINT '';

-- IMPORTANT: Manually commit or rollback after reviewing results
-- If verification passes, commit:
-- COMMIT;

-- If issues found, rollback:
-- ROLLBACK;
GO

-- =====================================================================================
-- QUERY 3: CLEANUP - Delete Test Data for Specific Member (Surgical Delete)
-- =====================================================================================
-- Purpose: Remove all Device Activation data for a specific test member
-- Use Case: Clean up test data for one member without affecting others
--
-- INSTRUCTIONS:
-- 1. Replace '7438599' with the actual Salesforce account number
-- 2. Review the PRINT output before committing
-- 3. Run in transaction for safety
-- =====================================================================================

-- CONFIGURATION: Update this value
DECLARE @salesforce_account_number NVARCHAR(50) = '7438599';  -- ← CHANGE THIS

DECLARE @member_id UNIQUEIDENTIFIER;

-- Get member_id
SELECT @member_id = member_id
FROM engage360.members
WHERE salesforce_account_number = @salesforce_account_number;

IF @member_id IS NULL
BEGIN
    PRINT '❌ ERROR: Member not found with salesforce_account_number: ' + @salesforce_account_number;
    PRINT '⚠️  Check the account number and try again';
    RETURN;
END

BEGIN TRANSACTION;

PRINT '';
PRINT '🧹 SURGICAL DELETE - Removing data for test member';
PRINT '================================================================';
PRINT 'Salesforce Account: ' + @salesforce_account_number;
PRINT 'Member ID: ' + CAST(@member_id AS NVARCHAR(36));
PRINT '';

-- Show what will be deleted
PRINT '📋 Data to be deleted:';
SELECT 'Outreach Attempts' AS data_type, COUNT(*) AS count
FROM engage360.outreach_attempts
WHERE enrollment_id IN (
    SELECT enrollment_id
    FROM engage360.member_campaign_enrollments_enhanced e
    JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
    WHERE e.member_id = @member_id
      AND c.campaign_type IN ('Device Activation', 'Operations')
)
UNION ALL
SELECT 'Enrollments', COUNT(*)
FROM engage360.member_campaign_enrollments_enhanced
WHERE member_id = @member_id
  AND campaign_id IN (
      SELECT campaign_id FROM engage360.campaigns_enhanced
      WHERE campaign_type IN ('Device Activation', 'Operations')
  )
UNION ALL
SELECT 'Devices', COUNT(*)
FROM engage360.member_devices
WHERE member_id = @member_id
UNION ALL
SELECT 'Staging Rows', COUNT(*)
FROM engage360_stg.stg_device_activation_delta
WHERE org_id IN (SELECT org_id FROM engage360.members WHERE member_id = @member_id)
  AND salesforce_account_number = @salesforce_account_number;

PRINT '';
PRINT '🗑️  Deleting data...';

-- Delete outreach attempts
DELETE FROM engage360.outreach_attempts
WHERE enrollment_id IN (
    SELECT enrollment_id
    FROM engage360.member_campaign_enrollments_enhanced e
    JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
    WHERE e.member_id = @member_id
      AND c.campaign_type IN ('Device Activation', 'Operations')
);
PRINT '  ✓ Deleted outreach_attempts: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- Delete enrollments
DELETE FROM engage360.member_campaign_enrollments_enhanced
WHERE member_id = @member_id
  AND campaign_id IN (
      SELECT campaign_id FROM engage360.campaigns_enhanced
      WHERE campaign_type IN ('Device Activation', 'Operations')
      AND campaign_name LIKE '%Device Activation%'
  );
PRINT '  ✓ Deleted enrollments: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- Delete devices
DELETE FROM engage360.member_devices
WHERE member_id = @member_id;
PRINT '  ✓ Deleted devices: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- OPTIONAL: Delete member record (only if test member)
-- ⚠️  Uncomment ONLY if you want to delete the member record itself
-- DELETE FROM engage360.members WHERE member_id = @member_id;
-- PRINT '  ✓ Deleted member: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- Delete staging data
DELETE FROM engage360_stg.stg_device_activation_delta
WHERE org_id IN (SELECT org_id FROM engage360.members WHERE member_id = @member_id)
  AND salesforce_account_number = @salesforce_account_number;
PRINT '  ✓ Deleted staging rows: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

PRINT '';
PRINT '🔍 Verification - Remaining data for this member:';

-- Verify deletion
SELECT 'Remaining Enrollments' AS check_type, COUNT(*) AS count
FROM engage360.member_campaign_enrollments_enhanced
WHERE member_id = @member_id
UNION ALL
SELECT 'Remaining Devices', COUNT(*)
FROM engage360.member_devices
WHERE member_id = @member_id
UNION ALL
SELECT 'Remaining Staging', COUNT(*)
FROM engage360_stg.stg_device_activation_delta
WHERE salesforce_account_number = @salesforce_account_number;

PRINT '';
PRINT '⚠️  TRANSACTION OPEN - Review verification results above';
PRINT '✅ If all counts are 0, run: COMMIT';
PRINT '❌ If issues found, run: ROLLBACK';
PRINT '';

-- IMPORTANT: Manually commit or rollback after reviewing results
-- If verification passes, commit:
-- COMMIT;
-- PRINT '✅ Cleanup complete for member: ' + @salesforce_account_number;

-- If issues found, rollback:
-- ROLLBACK;
GO

-- =====================================================================================
-- QUERY 4: CLEANUP - Delete ALL Device Activation Test Data (NUCLEAR OPTION)
-- =====================================================================================
-- Purpose: Delete ALL Device Activation campaign data
--
-- ⚠️  EXTREME CAUTION: This deletes ALL Device Activation data!
-- ⚠️  Use ONLY for development/testing environments
-- ⚠️  DO NOT RUN IN PRODUCTION without explicit approval!
--
-- This query deletes:
-- - All outreach attempts for Device Activation campaigns
-- - All enrollments for Device Activation campaigns
-- - All staging data from stg_device_activation_delta
-- - Does NOT delete: members, devices, or campaigns themselves
-- =====================================================================================

BEGIN TRANSACTION;

DECLARE @campaign_ids TABLE (campaign_id UNIQUEIDENTIFIER);

PRINT '';
PRINT '☢️  NUCLEAR OPTION - DELETE ALL DEVICE ACTIVATION DATA';
PRINT '================================================================';
PRINT '⚠️  WARNING: This will delete ALL Device Activation campaign data!';
PRINT '⚠️  Use ONLY in development/testing environments!';
PRINT '';

-- Get all Device Activation campaign IDs
INSERT INTO @campaign_ids
SELECT campaign_id
FROM engage360.campaigns_enhanced
WHERE campaign_type IN ('Device Activation', 'Operations')
  AND campaign_name LIKE '%Device Activation%';

PRINT '📋 Found ' + CAST((SELECT COUNT(*) FROM @campaign_ids) AS NVARCHAR(10)) + ' Device Activation campaigns:';

SELECT
    campaign_name,
    campaign_type,
    status,
    (SELECT COUNT(*) FROM engage360.member_campaign_enrollments_enhanced WHERE campaign_id = c.campaign_id) AS enrollments,
    (SELECT COUNT(*) FROM engage360.outreach_attempts oa
     JOIN engage360.member_campaign_enrollments_enhanced e ON oa.enrollment_id = e.enrollment_id
     WHERE e.campaign_id = c.campaign_id) AS outreach_attempts
FROM engage360.campaigns_enhanced c
WHERE c.campaign_id IN (SELECT campaign_id FROM @campaign_ids)
ORDER BY campaign_name;

PRINT '';
PRINT '🗑️  Deleting all data...';

-- Delete outreach attempts
DELETE FROM engage360.outreach_attempts
WHERE enrollment_id IN (
    SELECT enrollment_id
    FROM engage360.member_campaign_enrollments_enhanced
    WHERE campaign_id IN (SELECT campaign_id FROM @campaign_ids)
);
PRINT '  ✓ Deleted outreach_attempts: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- Delete enrollments
DELETE FROM engage360.member_campaign_enrollments_enhanced
WHERE campaign_id IN (SELECT campaign_id FROM @campaign_ids);
PRINT '  ✓ Deleted enrollments: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

-- Delete staging data
DELETE FROM engage360_stg.stg_device_activation_delta;
PRINT '  ✓ Deleted staging rows: ' + CAST(@@ROWCOUNT AS NVARCHAR(10));

PRINT '';
PRINT '🔍 Verification - Remaining Device Activation data:';

-- Verify deletion
SELECT 'Remaining Enrollments' AS check_type, COUNT(*) AS count
FROM engage360.member_campaign_enrollments_enhanced
WHERE campaign_id IN (SELECT campaign_id FROM @campaign_ids)
UNION ALL
SELECT 'Remaining Outreach Attempts', COUNT(*)
FROM engage360.outreach_attempts
WHERE enrollment_id IN (
    SELECT enrollment_id FROM engage360.member_campaign_enrollments_enhanced
    WHERE campaign_id IN (SELECT campaign_id FROM @campaign_ids)
)
UNION ALL
SELECT 'Remaining Staging Rows', COUNT(*)
FROM engage360_stg.stg_device_activation_delta;

PRINT '';
PRINT '⚠️  TRANSACTION OPEN - Review verification results above';
PRINT '✅ If all counts are 0, run: COMMIT';
PRINT '❌ If issues found, run: ROLLBACK';
PRINT '';
PRINT '⚠️  NOTE: This does NOT delete campaigns, members, or devices - only enrollments and attempts';
PRINT '';

-- IMPORTANT: Default is ROLLBACK for safety
-- RECOMMENDED: Review results before committing
ROLLBACK;  -- ← CHANGE TO COMMIT after careful review

PRINT '⚠️  Transaction rolled back (default for safety)';
PRINT '✅ To actually delete data, change ROLLBACK to COMMIT above';
GO

-- =====================================================================================
-- END OF CLEANUP QUERIES
-- =====================================================================================
--
-- Usage Instructions:
--
-- 1. QUERY 1 (Diagnostic):
--    - Run first to identify duplicate enrollments
--    - Safe to run - does not modify data
--
-- 2. QUERY 2 (Delete Duplicates):
--    - Run if Query 1 shows duplicates
--    - Keeps oldest enrollment per member+campaign
--    - Run in transaction, verify before committing
--
-- 3. QUERY 3 (Surgical Delete):
--    - Remove data for specific test member
--    - Update @salesforce_account_number variable
--    - Run in transaction, verify before committing
--
-- 4. QUERY 4 (Nuclear Option):
--    - Deletes ALL Device Activation data
--    - Use ONLY in dev/test environments
--    - Default: ROLLBACK (change to COMMIT after review)
--
-- Best Practices:
-- - Always run Query 1 first to diagnose issues
-- - Always run cleanup queries in transactions
-- - Always verify results before committing
-- - Keep backups before running delete queries
-- - Test in development environment first
--
-- =====================================================================================
