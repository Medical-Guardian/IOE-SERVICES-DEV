-- =====================================================================================
-- Outreach Callback Queue Table Creation
-- =====================================================================================
-- Purpose: Create callback queue table for scheduled callbacks during Device Activation calls
-- BusinessCaseID: BC-TBD (Device Activation System)
-- Created: 2025-12-07
--
-- This table tracks callback requests from Device Activation AI calls:
-- - Member requests callback for later (busy, unboxing device, charging device, etc.)
-- - System schedules callback based on member's requested time
-- - Maximum 3 callback attempts within 24 hours
-- - After timeout/max attempts, member returns to main calling sequence
--
-- Pattern: Follows existing IOE database patterns (outreach_batches, outreach_attempts)
-- =====================================================================================

-- Step 1: Check if table already exists
IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'outreach_callback_queue'
)
BEGIN
    PRINT '⚠️  Table engage360.outreach_callback_queue already exists.'
    PRINT 'ℹ️  Skipping table creation.'
    PRINT 'ℹ️  To modify the table, use ALTER TABLE statements.'

    -- Display existing table structure
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        IS_NULLABLE,
        COLUMN_DEFAULT
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
    AND TABLE_NAME = 'outreach_callback_queue'
    ORDER BY ORDINAL_POSITION;
END
ELSE
BEGIN
    PRINT '✅ Creating outreach_callback_queue table...'

    -- Step 2: Create callback queue table
    CREATE TABLE engage360.outreach_callback_queue (
        -- Primary Key
        callback_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        -- Foreign Keys
        enrollment_id UNIQUEIDENTIFIER NOT NULL,
        member_id UNIQUEIDENTIFIER NOT NULL,
        campaign_id UNIQUEIDENTIFIER NOT NULL,

        -- Callback Scheduling
        scheduled_callback_time DATETIMEOFFSET NOT NULL,
        callback_reason VARCHAR(100),  -- 'BUSY', 'UNBOXING', 'CHARGING', 'WRONG_PERSON', 'OTHER'
        preferred_contact_method VARCHAR(50),  -- 'SAME_NUMBER', 'ALTERNATIVE_NUMBER'

        -- Attempt Tracking
        attempt_count INT DEFAULT 0,
        max_attempts INT DEFAULT 3,
        last_attempt_ts DATETIMEOFFSET,
        last_attempt_disposition VARCHAR(50),  -- Last disposition from outreach_attempts

        -- Status Management
        status VARCHAR(50) DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, COMPLETED, FAILED, TIMED_OUT

        -- Metadata
        created_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),
        updated_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),

        -- Foreign Key Constraints
        CONSTRAINT FK_callback_queue_enrollment
            FOREIGN KEY (enrollment_id)
            REFERENCES engage360.member_campaign_enrollments_enhanced(enrollment_id),

        CONSTRAINT FK_callback_queue_member
            FOREIGN KEY (member_id)
            REFERENCES engage360.members(member_id),

        CONSTRAINT FK_callback_queue_campaign
            FOREIGN KEY (campaign_id)
            REFERENCES engage360.campaigns_enhanced(campaign_id),

        -- Business Rule Constraints
        CONSTRAINT CHK_callback_attempt_count
            CHECK (attempt_count >= 0 AND attempt_count <= max_attempts),

        CONSTRAINT CHK_callback_status
            CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'TIMED_OUT'))
    );

    PRINT '✅ Table created successfully!'

    -- Step 3: Create indexes for efficient queries
    PRINT '📊 Creating indexes...'

    -- Index for scheduler queries (find pending callbacks due now)
    CREATE INDEX idx_callback_queue_status_scheduled
    ON engage360.outreach_callback_queue(status, scheduled_callback_time);

    PRINT '✅ Index created: idx_callback_queue_status_scheduled'

    -- Index for enrollment lookup (check if member has pending callback)
    CREATE INDEX idx_callback_queue_enrollment
    ON engage360.outreach_callback_queue(enrollment_id, status);

    PRINT '✅ Index created: idx_callback_queue_enrollment'

    -- Index for member lookup (find all callbacks for a member)
    CREATE INDEX idx_callback_queue_member
    ON engage360.outreach_callback_queue(member_id, created_ts DESC);

    PRINT '✅ Index created: idx_callback_queue_member'

    -- Index for campaign reporting
    CREATE INDEX idx_callback_queue_campaign_status
    ON engage360.outreach_callback_queue(campaign_id, status, created_ts DESC);

    PRINT '✅ Index created: idx_callback_queue_campaign_status'

    PRINT ''
    PRINT '✅ CALLBACK QUEUE TABLE CREATION COMPLETE'
    PRINT ''
    PRINT '📋 Table Details:'
    PRINT '   Schema: engage360'
    PRINT '   Table: outreach_callback_queue'
    PRINT '   Indexes: 4 created'
    PRINT '   Foreign Keys: 3 created'
    PRINT ''
    PRINT '📝 Next Steps:'
    PRINT '   1. Verify table structure (query INFORMATION_SCHEMA.COLUMNS)'
    PRINT '   2. Test INSERT/SELECT operations'
    PRINT '   3. Proceed to Phase 6: callback_scheduler.py implementation'
END

-- =====================================================================================
-- Usage Examples (Optional - Run Separately)
-- =====================================================================================

-- Example 1: Insert a callback request
/*
DECLARE @enrollment_id UNIQUEIDENTIFIER = (SELECT TOP 1 enrollment_id FROM engage360.member_campaign_enrollments_enhanced WHERE current_status = 'ENROLLED')
DECLARE @member_id UNIQUEIDENTIFIER = (SELECT member_id FROM engage360.member_campaign_enrollments_enhanced WHERE enrollment_id = @enrollment_id)
DECLARE @campaign_id UNIQUEIDENTIFIER = (SELECT campaign_id FROM engage360.member_campaign_enrollments_enhanced WHERE enrollment_id = @enrollment_id)

INSERT INTO engage360.outreach_callback_queue (
    enrollment_id,
    member_id,
    campaign_id,
    scheduled_callback_time,
    callback_reason,
    status
) VALUES (
    @enrollment_id,
    @member_id,
    @campaign_id,
    DATEADD(HOUR, 2, SYSDATETIMEOFFSET()),  -- Schedule callback 2 hours from now
    'BUSY',
    'PENDING'
);

SELECT * FROM engage360.outreach_callback_queue WHERE enrollment_id = @enrollment_id;
*/

-- Example 2: Query pending callbacks due now
/*
SELECT
    cq.callback_id,
    cq.enrollment_id,
    cq.scheduled_callback_time,
    cq.callback_reason,
    cq.attempt_count,
    m.first_name,
    m.last_name,
    m.primary_phone
FROM engage360.outreach_callback_queue cq
JOIN engage360.members m ON cq.member_id = m.member_id
WHERE
    cq.status = 'PENDING'
    AND cq.attempt_count < cq.max_attempts
    AND SYSDATETIMEOFFSET() >= cq.scheduled_callback_time
    AND DATEDIFF(HOUR, cq.created_ts, SYSDATETIMEOFFSET()) < 24  -- 24-hour timeout
ORDER BY cq.scheduled_callback_time;
*/

-- Example 3: Check if enrollment has pending callback
/*
SELECT COUNT(*)
FROM engage360.outreach_callback_queue
WHERE enrollment_id = '<enrollment-id-here>'
AND status = 'PENDING';
*/

-- Example 4: Mark callback as timed out
/*
UPDATE engage360.outreach_callback_queue
SET status = 'TIMED_OUT', updated_ts = SYSDATETIMEOFFSET()
WHERE status = 'PENDING'
AND (
    DATEDIFF(HOUR, created_ts, SYSDATETIMEOFFSET()) >= 24
    OR attempt_count >= max_attempts
);
*/

-- Example 5: Callback queue statistics by campaign
/*
SELECT
    c.campaign_name,
    cq.status,
    COUNT(*) as callback_count,
    AVG(cq.attempt_count) as avg_attempts
FROM engage360.outreach_callback_queue cq
JOIN engage360.campaigns_enhanced c ON cq.campaign_id = c.campaign_id
GROUP BY c.campaign_name, cq.status
ORDER BY c.campaign_name, cq.status;
*/

-- =====================================================================================
-- Callback Queue Business Rules
-- =====================================================================================
--
-- Callback Reasons (from AI call):
-- - 'BUSY': Member is busy, wants callback later
-- - 'UNBOXING': Member is unboxing device, needs time
-- - 'CHARGING': Member is charging device, will be ready later
-- - 'WRONG_PERSON': Wrong person answered, schedule callback for right person
-- - 'OTHER': Other reason for callback
--
-- Status Lifecycle:
-- 1. PENDING → Callback scheduled, waiting for scheduled_callback_time
-- 2. IN_PROGRESS → Callback attempt in progress (batch submitted to Bland AI)
-- 3. COMPLETED → Callback successful (member spoke with AI, device activated)
-- 4. FAILED → Callback failed after 3 attempts
-- 5. TIMED_OUT → Callback timed out (24 hours elapsed or 3 attempts exhausted)
--
-- Timeout Rules:
-- - Maximum 3 callback attempts (max_attempts = 3)
-- - Maximum 24 hours from callback creation (created_ts + 24 hours)
-- - Whichever limit is reached first triggers TIMED_OUT status
-- - Timed out members return to main Device Activation call sequence
--
-- Priority Rules:
-- - Callbacks have HIGHER priority than main sequence calls
-- - EligibilityService excludes members with pending callbacks from main query
-- - Callback scheduler runs as part of main scheduler logic
--
-- Integration Points:
-- - Device Activation Scheduler: Checks for pending callbacks BEFORE main query
-- - Bland AI Webhook: Creates callback queue entries when member requests callback
-- - Callback Scheduler: Processes pending callbacks and submits to Bland AI
--
-- =====================================================================================
