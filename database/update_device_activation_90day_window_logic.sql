/*
================================================================================
Device Activation: Change 90-Day Window from "Call 5 + 90" to "Call 1 + 90"
================================================================================

BusinessCaseID: BC-DA-006 (Call Frequency & Sequencing Logic)
Created: 2026-01-17
Author: AI-POD Team

PURPOSE:
--------
This migration changes the 90-day window logic for Device Activation campaigns:

BEFORE (OLD LOGIC):
- 90-day window started from call_5_timestamp (when Call 5 was made)
- Calls 1-4 had NO 90-day limit
- campaign_end_date set dynamically at Call 5 (Day 20 → Day 110)

AFTER (NEW LOGIC):
- 90-day window starts from activation_start_date (Call 1 eligibility)
- ALL calls (1-5+) must occur within 90 days
- campaign_end_date = activation_start_date + 90 days (Day 3 → Day 93)

IMPACT:
-------
- ~20 fewer days for members to activate their devices
- Simpler logic (no dynamic campaign_end_date updates)
- Consistent window for all call attempts

DEPLOYMENT SEQUENCE:
--------------------
1. Run this migration script FIRST (before code deployment)
2. Deploy code changes to Azure Functions
3. Verify all enrollments have campaign_end_date populated
4. Monitor scheduler runs for 7 days

ROLLBACK PLAN:
--------------
If issues detected, restore from database backup:
    RESTORE DATABASE ioe FROM BACKUP

Or manually reset campaign_end_date to NULL for recent changes:
    UPDATE e
    SET e.campaign_end_date = NULL
    FROM ioe.member_campaign_enrollments_enhanced e
    WHERE e.campaign_end_date IS NOT NULL
      AND e.call_5_timestamp IS NULL
      AND e.enrollment_ts > '2026-01-17 00:00:00';

================================================================================
*/

-- ============================================================================
-- STEP 1: PRE-MIGRATION VALIDATION
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 1: PRE-MIGRATION VALIDATION';
PRINT '========================================';
PRINT '';

-- Check how many Device Activation enrollments exist
DECLARE @total_device_activation_enrollments INT;
SELECT @total_device_activation_enrollments = COUNT(*)
FROM ioe.member_campaign_enrollments_enhanced e
INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
  AND e.current_status = 'ENROLLED'
  AND e.device_activated = 0;

PRINT 'Total Device Activation enrollments (ENROLLED, not activated): ' + CAST(@total_device_activation_enrollments AS VARCHAR(10));
PRINT '';

-- Check how many have NULL campaign_end_date
DECLARE @null_campaign_end_date_count INT;
SELECT @null_campaign_end_date_count = COUNT(*)
FROM ioe.member_campaign_enrollments_enhanced e
INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
  AND e.current_status = 'ENROLLED'
  AND e.device_activated = 0
  AND e.campaign_end_date IS NULL;

PRINT 'Enrollments with NULL campaign_end_date: ' + CAST(@null_campaign_end_date_count AS VARCHAR(10));
PRINT '';

-- ============================================================================
-- STEP 2: IDENTIFY MEMBERS BEYOND NEW 90-DAY WINDOW
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 2: MEMBERS BEYOND NEW 90-DAY WINDOW';
PRINT '========================================';
PRINT '';

-- Find members who are currently beyond Day 90 from activation_start_date
-- These members require a business decision before proceeding

DECLARE @beyond_90_days_count INT;
SELECT @beyond_90_days_count = COUNT(*)
FROM ioe.member_campaign_enrollments_enhanced e
INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
  AND e.current_status = 'ENROLLED'
  AND e.device_activated = 0
  AND SYSDATETIMEOFFSET() > DATEADD(DAY, 90, e.activation_start_date);

PRINT 'Members currently BEYOND 90 days from activation_start_date: ' + CAST(@beyond_90_days_count AS VARCHAR(10));
PRINT '';

IF @beyond_90_days_count > 0
BEGIN
    PRINT '⚠️  WARNING: Some members are beyond the new 90-day window!';
    PRINT '   Business decision required before proceeding:';
    PRINT '   Option A: Set campaign_end_date = SYSDATETIMEOFFSET() + 7 days (grace period)';
    PRINT '   Option B: Set campaign_end_date = activation_start_date + 90 days (strict)';
    PRINT '   Option C: Unenroll these members (change status to UNENROLLED)';
    PRINT '';
    PRINT 'Run this query to view affected members:';
    PRINT '';
    PRINT 'SELECT TOP 10';
    PRINT '    e.enrollment_id,';
    PRINT '    m.first_name,';
    PRINT '    m.last_name,';
    PRINT '    e.activation_start_date,';
    PRINT '    e.call_5_timestamp,';
    PRINT '    DATEDIFF(day, e.activation_start_date, SYSDATETIMEOFFSET()) AS days_since_activation,';
    PRINT '    DATEDIFF(day, SYSDATETIMEOFFSET(), DATEADD(DAY, 90, e.activation_start_date)) AS days_until_new_cutoff';
    PRINT 'FROM ioe.member_campaign_enrollments_enhanced e';
    PRINT 'INNER JOIN ioe.members m ON e.member_id = m.member_id';
    PRINT 'INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id';
    PRINT 'WHERE (c.campaign_type = ''Device Activation'' OR c.campaign_type = ''Operations'')';
    PRINT '  AND e.current_status = ''ENROLLED''';
    PRINT '  AND e.device_activated = 0';
    PRINT '  AND SYSDATETIMEOFFSET() > DATEADD(DAY, 90, e.activation_start_date);';
    PRINT '';
END
ELSE
BEGIN
    PRINT '✅ All members are within the new 90-day window';
    PRINT '';
END

-- ============================================================================
-- STEP 3: BACKUP CURRENT STATE
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 3: BACKUP CURRENT STATE';
PRINT '========================================';
PRINT '';

-- Create backup table (if not exists)
IF OBJECT_ID('ioe.member_campaign_enrollments_enhanced_backup_20260117', 'U') IS NULL
BEGIN
    SELECT *
    INTO ioe.member_campaign_enrollments_enhanced_backup_20260117
    FROM ioe.member_campaign_enrollments_enhanced e
    INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
    WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
      AND e.current_status = 'ENROLLED'
      AND e.device_activated = 0;

    PRINT '✅ Backup table created: ioe.member_campaign_enrollments_enhanced_backup_20260117';
END
ELSE
BEGIN
    PRINT '⚠️  Backup table already exists: ioe.member_campaign_enrollments_enhanced_backup_20260117';
    PRINT '   Skipping backup creation to avoid overwriting existing backup';
END
PRINT '';

-- ============================================================================
-- STEP 4: UPDATE campaign_end_date FOR ENROLLMENTS WITHIN 90-DAY WINDOW
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 4: UPDATE campaign_end_date';
PRINT '========================================';
PRINT '';

-- Update NULL campaign_end_date values for members WITHIN the new 90-day window
-- These members will continue to be eligible for calls

BEGIN TRANSACTION;

BEGIN TRY
    UPDATE e
    SET e.campaign_end_date = CAST(DATEADD(DAY, 90, e.activation_start_date) AS DATE)
    FROM ioe.member_campaign_enrollments_enhanced e
    INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
    WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
      AND e.current_status = 'ENROLLED'
      AND e.device_activated = 0
      AND e.campaign_end_date IS NULL
      AND SYSDATETIMEOFFSET() <= DATEADD(DAY, 90, e.activation_start_date);  -- WITHIN 90-day window

    DECLARE @updated_within_window_count INT = @@ROWCOUNT;

    PRINT '✅ Updated campaign_end_date for ' + CAST(@updated_within_window_count AS VARCHAR(10)) + ' enrollments (WITHIN 90-day window)';
    PRINT '   Formula: campaign_end_date = activation_start_date + 90 days';
    PRINT '';

    COMMIT TRANSACTION;
    PRINT '✅ Transaction committed successfully';
    PRINT '';
END TRY
BEGIN CATCH
    ROLLBACK TRANSACTION;
    PRINT '❌ ERROR: Transaction rolled back';
    PRINT '   Error Message: ' + ERROR_MESSAGE();
    PRINT '';
    THROW;
END CATCH

-- ============================================================================
-- STEP 5: HANDLE MEMBERS BEYOND 90-DAY WINDOW (BUSINESS DECISION)
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 5: MEMBERS BEYOND 90-DAY WINDOW';
PRINT '========================================';
PRINT '';

-- ⚠️  UNCOMMENT ONE OF THE OPTIONS BELOW AFTER BUSINESS DECISION

-- ----------------------------------------------------------------------------
-- OPTION A: GRACE PERIOD (7 days from today)
-- ----------------------------------------------------------------------------
-- PRINT 'Applying OPTION A: Grace period (7 days from today)';
-- PRINT '';
--
-- BEGIN TRANSACTION;
-- BEGIN TRY
--     UPDATE e
--     SET e.campaign_end_date = CAST(DATEADD(DAY, 7, SYSDATETIMEOFFSET()) AS DATE)
--     FROM ioe.member_campaign_enrollments_enhanced e
--     INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
--     WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
--       AND e.current_status = 'ENROLLED'
--       AND e.device_activated = 0
--       AND e.campaign_end_date IS NULL
--       AND SYSDATETIMEOFFSET() > DATEADD(DAY, 90, e.activation_start_date);  -- BEYOND 90-day window
--
--     DECLARE @grace_period_count INT = @@ROWCOUNT;
--     PRINT '✅ Applied grace period to ' + CAST(@grace_period_count AS VARCHAR(10)) + ' members';
--     PRINT '   campaign_end_date = today + 7 days';
--     PRINT '';
--
--     COMMIT TRANSACTION;
--     PRINT '✅ Transaction committed successfully';
--     PRINT '';
-- END TRY
-- BEGIN CATCH
--     ROLLBACK TRANSACTION;
--     PRINT '❌ ERROR: Transaction rolled back';
--     PRINT '   Error Message: ' + ERROR_MESSAGE();
--     PRINT '';
--     THROW;
-- END CATCH

-- ----------------------------------------------------------------------------
-- OPTION B: STRICT ENFORCEMENT (activation_start_date + 90 days - in the PAST)
-- ----------------------------------------------------------------------------
-- PRINT 'Applying OPTION B: Strict enforcement (activation_start_date + 90 days)';
-- PRINT '';
--
-- BEGIN TRANSACTION;
-- BEGIN TRY
--     UPDATE e
--     SET e.campaign_end_date = CAST(DATEADD(DAY, 90, e.activation_start_date) AS DATE)
--     FROM ioe.member_campaign_enrollments_enhanced e
--     INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
--     WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
--       AND e.current_status = 'ENROLLED'
--       AND e.device_activated = 0
--       AND e.campaign_end_date IS NULL
--       AND SYSDATETIMEOFFSET() > DATEADD(DAY, 90, e.activation_start_date);  -- BEYOND 90-day window
--
--     DECLARE @strict_enforcement_count INT = @@ROWCOUNT;
--     PRINT '✅ Applied strict enforcement to ' + CAST(@strict_enforcement_count AS VARCHAR(10)) + ' members';
--     PRINT '   campaign_end_date = activation_start_date + 90 days (PAST DATE - no more calls)';
--     PRINT '';
--
--     COMMIT TRANSACTION;
--     PRINT '✅ Transaction committed successfully';
--     PRINT '';
-- END TRY
-- BEGIN CATCH
--     ROLLBACK TRANSACTION;
--     PRINT '❌ ERROR: Transaction rolled back';
--     PRINT '   Error Message: ' + ERROR_MESSAGE();
--     PRINT '';
--     THROW;
-- END CATCH

-- ----------------------------------------------------------------------------
-- OPTION C: UNENROLL MEMBERS (Manual cleanup)
-- ----------------------------------------------------------------------------
-- PRINT 'Applying OPTION C: Unenroll members beyond 90-day window';
-- PRINT '';
--
-- BEGIN TRANSACTION;
-- BEGIN TRY
--     UPDATE e
--     SET e.current_status = 'UNENROLLED',
--         e.campaign_end_date = CAST(SYSDATETIMEOFFSET() AS DATE)
--     FROM ioe.member_campaign_enrollments_enhanced e
--     INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
--     WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
--       AND e.current_status = 'ENROLLED'
--       AND e.device_activated = 0
--       AND e.campaign_end_date IS NULL
--       AND SYSDATETIMEOFFSET() > DATEADD(DAY, 90, e.activation_start_date);  -- BEYOND 90-day window
--
--     DECLARE @unenrolled_count INT = @@ROWCOUNT;
--     PRINT '✅ Unenrolled ' + CAST(@unenrolled_count AS VARCHAR(10)) + ' members';
--     PRINT '   current_status changed to UNENROLLED';
--     PRINT '';
--
--     COMMIT TRANSACTION;
--     PRINT '✅ Transaction committed successfully';
--     PRINT '';
-- END TRY
-- BEGIN CATCH
--     ROLLBACK TRANSACTION;
--     PRINT '❌ ERROR: Transaction rolled back';
--     PRINT '   Error Message: ' + ERROR_MESSAGE();
--     PRINT '';
--     THROW;
-- END CATCH

PRINT '⚠️  MANUAL ACTION REQUIRED:';
PRINT '   Uncomment ONE of the options above (A, B, or C) after business decision';
PRINT '';

-- ============================================================================
-- STEP 6: POST-MIGRATION VERIFICATION
-- ============================================================================

PRINT '========================================';
PRINT 'STEP 6: POST-MIGRATION VERIFICATION';
PRINT '========================================';
PRINT '';

-- Check how many enrollments still have NULL campaign_end_date
DECLARE @remaining_null_count INT;
SELECT @remaining_null_count = COUNT(*)
FROM ioe.member_campaign_enrollments_enhanced e
INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
  AND e.current_status = 'ENROLLED'
  AND e.device_activated = 0
  AND e.campaign_end_date IS NULL;

PRINT 'Enrollments with NULL campaign_end_date after migration: ' + CAST(@remaining_null_count AS VARCHAR(10));

IF @remaining_null_count = 0
BEGIN
    PRINT '✅ SUCCESS: All active enrollments have campaign_end_date populated';
END
ELSE
BEGIN
    PRINT '⚠️  WARNING: ' + CAST(@remaining_null_count AS VARCHAR(10)) + ' enrollments still have NULL campaign_end_date';
    PRINT '   These are likely members beyond the 90-day window (Step 5)';
    PRINT '   Ensure Step 5 (business decision) is completed';
END
PRINT '';

-- Verify date calculations are correct
PRINT 'Sample of updated enrollments (showing date calculations):';
PRINT '';

SELECT TOP 5
    e.enrollment_id,
    e.activation_start_date,
    e.campaign_end_date,
    DATEDIFF(day, e.activation_start_date, e.campaign_end_date) AS days_diff,
    e.call_5_timestamp,
    e.current_status
FROM ioe.member_campaign_enrollments_enhanced e
INNER JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
  AND e.current_status = 'ENROLLED'
  AND e.device_activated = 0
  AND e.campaign_end_date IS NOT NULL
ORDER BY e.enrollment_ts DESC;

PRINT '';
PRINT '✅ Expected: days_diff = 90 for all rows';
PRINT '';

-- ============================================================================
-- STEP 7: SUMMARY
-- ============================================================================

PRINT '========================================';
PRINT 'MIGRATION SUMMARY';
PRINT '========================================';
PRINT '';
PRINT '✅ Database migration completed successfully';
PRINT '';
PRINT 'NEXT STEPS:';
PRINT '1. Deploy code changes to Azure Functions';
PRINT '2. Monitor Application Insights for Phase 2.5 logs (should NOT appear)';
PRINT '3. Verify new enrollments have campaign_end_date = activation_start_date + 90 days';
PRINT '4. Monitor for 7 days to ensure no issues';
PRINT '';
PRINT 'ROLLBACK (if needed):';
PRINT '  RESTORE DATABASE ioe FROM BACKUP';
PRINT '  OR use the backup table: ioe.member_campaign_enrollments_enhanced_backup_20260117';
PRINT '';
PRINT '========================================';
PRINT 'Migration completed: ' + CONVERT(VARCHAR, SYSDATETIMEOFFSET(), 120);
PRINT '========================================';
