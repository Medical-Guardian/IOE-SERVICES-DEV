-- =====================================================
-- Batch Monitoring System - Database Schema Updates
-- =====================================================
-- Purpose: Add necessary tables and columns for batch completion monitoring
-- Compatible with existing IOE database structure

-- =====================================================
-- 1. CREATE SYSTEM LOCKS TABLE
-- =====================================================
-- Purpose: Distributed locking to prevent overlapping timer executions

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES 
               WHERE TABLE_SCHEMA = 'engage360' AND TABLE_NAME = 'system_locks')
BEGIN
    CREATE TABLE engage360.system_locks (
        lock_id UNIQUEIDENTIFIER DEFAULT NEWID() PRIMARY KEY,
        lock_name NVARCHAR(255) NOT NULL UNIQUE,
        lock_expiry DATETIMEOFFSET NOT NULL,
        locked_by NVARCHAR(255) NOT NULL,
        created_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET()
    );
    
    PRINT '✅ Created system_locks table';
END
ELSE
BEGIN
    PRINT '⚠️ system_locks table already exists';
END

-- Create index for performance
IF NOT EXISTS (SELECT * FROM sys.indexes 
               WHERE name = 'IX_system_locks_name_expiry' 
               AND object_id = OBJECT_ID('engage360.system_locks'))
BEGIN
    CREATE INDEX IX_system_locks_name_expiry 
    ON engage360.system_locks(lock_name, lock_expiry);
    
    PRINT '✅ Created index IX_system_locks_name_expiry';
END

-- =====================================================
-- 2. ENHANCE OUTREACH_BATCHES TABLE
-- =====================================================
-- Purpose: Add columns for batch monitoring and API reconciliation

-- Add last_status_check_ts column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_batches' 
               AND COLUMN_NAME = 'last_status_check_ts')
BEGIN
    ALTER TABLE engage360.outreach_batches 
    ADD last_status_check_ts DATETIMEOFFSET;
    
    PRINT '✅ Added last_status_check_ts column to outreach_batches';
END

-- Add total_calls_completed column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_batches' 
               AND COLUMN_NAME = 'total_calls_completed')
BEGIN
    ALTER TABLE engage360.outreach_batches 
    ADD total_calls_completed INTEGER DEFAULT 0;
    
    PRINT '✅ Added total_calls_completed column to outreach_batches';
END

-- Add total_calls_failed column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_batches' 
               AND COLUMN_NAME = 'total_calls_failed')
BEGIN
    ALTER TABLE engage360.outreach_batches 
    ADD total_calls_failed INTEGER DEFAULT 0;
    
    PRINT '✅ Added total_calls_failed column to outreach_batches';
END

-- Add avg_call_duration column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_batches' 
               AND COLUMN_NAME = 'avg_call_duration')
BEGIN
    ALTER TABLE engage360.outreach_batches 
    ADD avg_call_duration INTEGER;
    
    PRINT '✅ Added avg_call_duration column to outreach_batches';
END

-- Add api_reconciled flag
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_batches' 
               AND COLUMN_NAME = 'api_reconciled')
BEGIN
    ALTER TABLE engage360.outreach_batches 
    ADD api_reconciled BIT DEFAULT 0;
    
    PRINT '✅ Added api_reconciled column to outreach_batches';
END

-- =====================================================
-- 3. ENHANCE OUTREACH_ATTEMPTS TABLE
-- =====================================================
-- Purpose: Add columns for detailed call tracking

-- Add call_duration column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_attempts' 
               AND COLUMN_NAME = 'call_duration')
BEGIN
    ALTER TABLE engage360.outreach_attempts 
    ADD call_duration INTEGER;
    
    PRINT '✅ Added call_duration column to outreach_attempts';
END

-- Add api_call_id column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_attempts' 
               AND COLUMN_NAME = 'api_call_id')
BEGIN
    ALTER TABLE engage360.outreach_attempts 
    ADD api_call_id NVARCHAR(255);
    
    PRINT '✅ Added api_call_id column to outreach_attempts';
END

-- Add detailed_disposition column
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_attempts' 
               AND COLUMN_NAME = 'detailed_disposition')
BEGIN
    ALTER TABLE engage360.outreach_attempts 
    ADD detailed_disposition NVARCHAR(255);
    
    PRINT '✅ Added detailed_disposition column to outreach_attempts';
END

-- Add api_reconciled flag
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
               WHERE TABLE_SCHEMA = 'engage360' 
               AND TABLE_NAME = 'outreach_attempts' 
               AND COLUMN_NAME = 'api_reconciled')
BEGIN
    ALTER TABLE engage360.outreach_attempts 
    ADD api_reconciled BIT DEFAULT 0;
    
    PRINT '✅ Added api_reconciled column to outreach_attempts';
END

-- =====================================================
-- 4. CREATE PERFORMANCE INDEXES
-- =====================================================
-- Purpose: Optimize queries for batch monitoring

-- Index for finding stale batches
IF NOT EXISTS (SELECT * FROM sys.indexes 
               WHERE name = 'IX_outreach_batches_status_submitted' 
               AND object_id = OBJECT_ID('engage360.outreach_batches'))
BEGIN
    CREATE INDEX IX_outreach_batches_status_submitted 
    ON engage360.outreach_batches(batch_status, submitted_ts) 
    INCLUDE (vendor_batch_id, campaign_id, last_status_check_ts);
    
    PRINT '✅ Created index IX_outreach_batches_status_submitted';
END

-- Index for batch reconciliation queries
IF NOT EXISTS (SELECT * FROM sys.indexes 
               WHERE name = 'IX_outreach_batches_vendor_reconciled' 
               AND object_id = OBJECT_ID('engage360.outreach_batches'))
BEGIN
    CREATE INDEX IX_outreach_batches_vendor_reconciled 
    ON engage360.outreach_batches(vendor_batch_id, api_reconciled);
    
    PRINT '✅ Created index IX_outreach_batches_vendor_reconciled';
END

-- Index for recent attempt updates
IF NOT EXISTS (SELECT * FROM sys.indexes 
               WHERE name = 'IX_outreach_attempts_batch_updated' 
               AND object_id = OBJECT_ID('engage360.outreach_attempts'))
BEGIN
    CREATE INDEX IX_outreach_attempts_batch_updated 
    ON engage360.outreach_attempts(batch_id, updated_ts);
    
    PRINT '✅ Created index IX_outreach_attempts_batch_updated';
END

-- =====================================================
-- 5. CREATE MONITORING VIEWS (OPTIONAL)
-- =====================================================
-- Purpose: Convenient views for monitoring batch status

-- View: Active batches summary
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.VIEWS 
               WHERE TABLE_SCHEMA = 'engage360' AND TABLE_NAME = 'v_active_batches_summary')
BEGIN
    EXEC('
    CREATE VIEW engage360.v_active_batches_summary AS
    SELECT 
        ob.batch_id,
        ob.vendor_batch_id,
        ob.campaign_id,
        ce.name as campaign_name,
        ob.batch_status,
        ob.total_calls_intended,
        ob.total_calls_completed,
        ob.total_calls_failed,
        ob.submitted_ts,
        ob.last_status_check_ts,
        ob.api_reconciled,
        DATEDIFF(minute, ob.submitted_ts, SYSDATETIMEOFFSET()) as minutes_since_submission,
        CASE 
            WHEN ob.total_calls_intended > 0 
            THEN CAST((ob.total_calls_completed + ob.total_calls_failed) * 100.0 / ob.total_calls_intended AS DECIMAL(5,2))
            ELSE 0 
        END as completion_percentage
    FROM engage360.outreach_batches ob
    LEFT JOIN engage360.campaigns_enhanced ce ON ob.campaign_id = ce.campaign_id
    WHERE ob.batch_status IN (''Submitted'', ''In Progress'')
      AND ob.submitted_ts >= DATEADD(day, -7, SYSDATETIMEOFFSET())
    ');
    
    PRINT '✅ Created view v_active_batches_summary';
END

-- =====================================================
-- 6. INSERT SAMPLE DATA FOR TESTING (OPTIONAL)
-- =====================================================
-- Uncomment this section if you want to test the locking mechanism

/*
-- Test the locking mechanism
INSERT INTO engage360.system_locks (lock_name, lock_expiry, locked_by)
VALUES ('test_lock', DATEADD(minute, 5, SYSDATETIMEOFFSET()), 'test_process');

-- Clean up test data after verification
-- DELETE FROM engage360.system_locks WHERE lock_name = 'test_lock';
*/

-- =====================================================
-- 7. PERMISSIONS (ADJUST AS NEEDED)
-- =====================================================
-- Grant necessary permissions for the function app service account

-- Example (adjust role name as needed):
-- GRANT SELECT, INSERT, UPDATE, DELETE ON engage360.system_locks TO [your_function_app_service_account];
-- GRANT SELECT, UPDATE ON engage360.outreach_batches TO [your_function_app_service_account];
-- GRANT SELECT, UPDATE ON engage360.outreach_attempts TO [your_function_app_service_account];

PRINT '🎉 Batch monitoring schema setup completed successfully!';

-- =====================================================
-- SUMMARY OF CHANGES
-- =====================================================
PRINT '';
PRINT '📊 SUMMARY OF CHANGES:';
PRINT '1. ✅ Created system_locks table for distributed locking';
PRINT '2. ✅ Enhanced outreach_batches with monitoring columns';
PRINT '3. ✅ Enhanced outreach_attempts with detailed tracking';
PRINT '4. ✅ Created performance indexes for efficient queries';
PRINT '5. ✅ Created monitoring views for operational visibility';
PRINT '';
PRINT '🚀 Ready to deploy batch monitoring system!';
PRINT '📝 Next step: Register batch_completion_reconciler in function_app.py';