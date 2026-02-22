# Campaign Auto-Completion Implementation Plan

**Document Purpose**: Implementation plan for automatically marking Partner campaigns as "Completed" when all conditions are met

**Date Created**: 2025-10-22
**Status**: PENDING ANSWERS - Awaiting stakeholder decisions on 4 critical questions
**Priority**: Medium
**Related Docs**:
- PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md
- PARTNER_CAMPAIGN_IMPLEMENTATION.md
- CAMPAIGN_QUALIFICATION_LOGIC.md

---

## 📋 **Table of Contents**

1. [Requirements Summary](#requirements-summary)
2. [Current System Analysis](#current-system-analysis)
3. [Critical Questions (NEEDS ANSWERS)](#critical-questions-needs-answers)
4. [Proposed Solution](#proposed-solution)
5. [Implementation Steps](#implementation-steps)
6. [Testing Plan](#testing-plan)
7. [Deployment Strategy](#deployment-strategy)

---

## ✅ **Requirements Summary**

### **Business Requirements:**
1. ✅ Campaign should be marked "Completed" automatically when all outbound calls are done
2. ✅ Each partner campaign has enrolled members who need outbound calls
3. ✅ Calls have conditions: when to call, what care gaps to cover, etc.
4. ✅ If call was successful AND all conditions met → mark campaign as "Completed"
5. ✅ Failed/NoAnswer calls have retry policy (handle per existing policy)
6. ✅ Recurring campaigns (monthly, twice monthly, etc.) need special handling
7. ✅ Use status = 'Completed' in campaigns_enhanced table
8. ✅ Process should be automatic (no manual intervention)

### **Success Criteria:**
- Campaign stops appearing in scheduler when marked "Completed"
- All enrolled members have been successfully contacted OR retry policy exhausted
- Recurring campaigns continue to run (don't auto-complete)
- Historical reporting shows completion timestamp and metrics

---

## 🔍 **Current System Analysis**

### **Campaign Lifecycle (Current):**
```
Draft → Active → (Manual) Inactive
         ↓
         (Runs every 30 min until end_ts reached)
         ↓
         (No automatic completion currently)
```

### **Campaign Status Values (Current):**
```sql
-- From campaigns_enhanced.status column:
'Active'    -- ✅ Campaign is running (scheduler processes it)
'Inactive'  -- ❌ Campaign is paused
'Draft'     -- 📝 Campaign not yet launched
'Completed' -- 🎯 NEW STATUS (to be implemented)
```

### **Current Qualification Logic:**
```sql
-- From campaign_qualifier.py (line 63-68)
WHERE c.campaign_type = 'Partner'
  AND c.status = 'Active'              -- ← Only Active campaigns run
  AND c.primary_channel = 'voice'
  AND (c.start_ts IS NULL OR c.start_ts <= SYSDATETIMEOFFSET())
  AND (c.end_ts IS NULL OR c.end_ts >= SYSDATETIMEOFFSET())  -- ← Stops after end_ts
  AND c.audience_file_batch IS NOT NULL
```

**Key Insight**: System already stops processing campaigns when `end_ts` is reached, but doesn't change status to "Completed".

### **Disposition Types (from StatusMapper):**

| Disposition | Meaning | Can Retry? | Counts as "Done"? |
|-------------|---------|------------|-------------------|
| `Completed` | ✅ Successful call (contact made) | No | YES |
| `NoAnswer` | ⚠️ Voicemail, busy, no answer | Yes | TBD (Question 2) |
| `Failed` | ⚠️ Call failed (technical error) | Yes | TBD (Question 2) |
| `Pending` | ⏳ Call in progress | N/A | NO |
| `OptOut` | 🚫 Member opted out | No | TBD (Question 4) |

### **Current Retry Logic:**
```python
# From member_eligibility.py (line 153-160)
# Failed and NoAnswer don't count toward frequency limits
# These dispositions can be retried per policy:
- 'Failed' → Allow retry
- 'NoAnswer' → Allow retry

# These dispositions block same-day attempts:
- 'Completed' → No retry (success)
- 'Pending' → No retry (in progress)
```

### **Database Schema (Relevant Tables):**

#### **campaigns_enhanced**
```sql
campaign_id             uniqueidentifier  -- PK
status                  nvarchar(50)      -- 'Active', 'Inactive', 'Draft', 'Completed'
campaign_type           nvarchar(50)      -- 'Partner'
start_ts                datetimeoffset    -- Campaign start date
end_ts                  datetimeoffset    -- Campaign end date (NULL = ongoing)
scheduling_mode         nvarchar(50)      -- 'Flexible', 'Fixed'
frequency_value         int               -- 2, 1, etc.
frequency_unit          nvarchar(50)      -- 'day', 'week', 'month'
```

#### **member_campaign_enrollments_enhanced**
```sql
enrollment_id           uniqueidentifier  -- PK
member_id               uniqueidentifier  -- FK to members
campaign_id             uniqueidentifier  -- FK to campaigns
current_status          nvarchar(50)      -- 'Active', 'Inactive'
```

#### **outreach_attempts**
```sql
attempt_id              uniqueidentifier  -- PK
enrollment_id           uniqueidentifier  -- FK to enrollments
batch_id                uniqueidentifier  -- FK to batches
disposition             nvarchar(100)     -- 'Completed', 'Failed', 'NoAnswer', 'Pending', 'OptOut'
retry_seq               int               -- 0, 1, 2, 3... (retry attempt number)
attempt_ts              datetimeoffset    -- When attempt was made
```

---

## ❓ **Critical Questions (NEEDS ANSWERS)**

### **Question 1: How to Identify Recurring Campaigns?**

**Context**: Some campaigns run monthly, twice per month, or ongoing. These should NOT auto-complete.

**Current Data Available:**
```sql
end_ts: NULL or specific date
scheduling_mode: 'Flexible' or 'Fixed'
frequency_value: 2
frequency_unit: 'week'
```

**Options:**

**□ Option A**: Campaigns with `end_ts = NULL` are recurring (never auto-complete)
- Logic: If `end_ts IS NULL` → keep status = 'Active' forever
- Example: "Monthly wellness calls - ongoing program"
- **Pros**: Simple, uses existing field
- **Cons**: Assumes NULL = recurring (may not be accurate)

**□ Option B**: Need new database field like `is_recurring = 1`
- Logic: Add new column to campaigns_enhanced table
- Example: `is_recurring BIT DEFAULT 0`
- **Pros**: Explicit, clear intent
- **Cons**: Requires schema change, data migration

**□ Option C**: Specific `scheduling_mode` pattern
- Logic: `scheduling_mode = 'Recurring'` (new value)
- **Pros**: Uses existing field
- **Cons**: Requires updating existing campaigns

**□ Option D**: All campaigns eventually complete (including recurring)
- Logic: Even recurring campaigns complete when `end_ts` reached OR all members called
- **Pros**: Consistent completion logic
- **Cons**: May require re-activating recurring campaigns

**👉 YOUR ANSWER:** _______________

**👉 RATIONALE:** _______________

---

### **Question 2: Completion Criteria - What About Failed Members?**

**Context**: Not all members can be successfully reached. Need to define when campaign is "done".

**Scenario Example:**
```
Campaign: "Flu Shot Reminder 2025"
Total Enrolled Members: 1000

After 30 days:
- 900 have disposition = 'Completed' (successful calls)
- 50 have disposition = 'NoAnswer' after 5 retry attempts (exhausted)
- 50 have disposition = 'Failed' after 5 retry attempts (exhausted)

Should this campaign be marked "Completed"?
```

**Options:**

**□ Option A**: 100% Attempt Coverage (Recommended)
- **Logic**: Mark "Completed" when every member has ≥1 attempt AND (success OR exhausted retries)
- **Formula**: `completed_members + exhausted_retries = total_enrolled`
- **Success Rate**: 900/1000 = 90% (acceptable)
- **Pros**: Realistic, acknowledges some calls fail
- **Cons**: May complete with <100% success

**□ Option B**: 100% Success Rate (Strict)
- **Logic**: Mark "Completed" ONLY when every member has disposition = 'Completed'
- **Formula**: `completed_members = total_enrolled`
- **Success Rate**: Must be 100%
- **Pros**: Ensures everyone contacted successfully
- **Cons**: May never complete if some members never answer

**□ Option C**: Threshold-Based (80% or 90%)
- **Logic**: Mark "Completed" when ≥ X% of members have disposition = 'Completed'
- **Formula**: `(completed_members / total_enrolled) >= 0.80`
- **Example**: 800/1000 = 80% → Complete
- **Pros**: Flexible, configurable threshold
- **Cons**: Arbitrary threshold, may leave members uncontacted

**□ Option D**: Time-Based + Best Effort
- **Logic**: Mark "Completed" when `end_ts` reached AND all eligible members attempted at least once
- **Formula**: `end_ts <= NOW() AND all_members_attempted >= 1`
- **Pros**: Guaranteed completion by end date
- **Cons**: May not maximize contact attempts

**👉 YOUR ANSWER:** _______________

**👉 THRESHOLD (if Option C):** _____%

**👉 MAX RETRY ATTEMPTS:** _____ (current system uses this value)

**👉 RATIONALE:** _______________

---

### **Question 3: Where Should This Logic Run?**

**Context**: Need to decide which Azure Function should handle campaign completion checks.

**Options:**

**□ Option A**: Inside existing `partner_campaign_scheduler` (runs every 30 min)
- **Flow**:
  1. Process qualified campaigns
  2. Submit batches to Bland AI
  3. Check if any Active campaigns should be marked Completed
  4. Update status if criteria met
- **Pros**: Centralized, no new function, frequent checks (every 30 min)
- **Cons**: Adds processing time to scheduler, mixed responsibilities

**□ Option B**: New dedicated function `campaign_completion_checker` (runs every 2 hours) ✅ RECOMMENDED
- **Flow**:
  1. Separate Azure Function with timer trigger
  2. Queries all Active Partner campaigns
  3. Checks completion criteria for each
  4. Updates status = 'Completed' where applicable
  5. Logs completion details
- **Schedule**: `0 0 */2 * * *` (every 2 hours on the hour)
- **Pros**:
  - ✅ Dedicated responsibility (Single Responsibility Principle)
  - ✅ Doesn't slow down scheduler
  - ✅ Independent scaling and monitoring
  - ✅ Easier to test and debug
  - ✅ Follows existing pattern (like batch_completion_reconciler)
- **Cons**: New function to maintain (minimal overhead)

**□ Option C**: Extend existing `batch_completion_reconciler` (runs every 5 min)
- **Flow**:
  1. Add campaign completion logic to existing reconciler
  2. Check campaigns after batch reconciliation
- **Pros**: Reuse existing infrastructure, frequent checks (every 5 min)
- **Cons**: Mixed responsibilities, reconciler is already complex

**👉 YOUR ANSWER:** _______________

**👉 RUN FREQUENCY (if Option B):** Every _____ hours

**👉 RATIONALE:** _______________

---

### **Question 4: OptOut Members - Count as "Done"?**

**Context**: Members can opt out during calls (disposition = 'OptOut'). Need to clarify how this affects completion.

**Scenario:**
```
Member received call, asked to opt out of future communications.
Disposition = 'OptOut'
next_action = 'Close'

Should this member count toward campaign completion?
```

**Options:**

**□ Option A**: YES - OptOut counts as "done"
- **Logic**: Member was contacted, made a choice (opt out)
- **Completion Formula**: `completed_members + optout_members + exhausted_retries = total_enrolled`
- **Pros**: Realistic, member was reached
- **Cons**: Lower "success" rate in reports

**□ Option B**: NO - OptOut excluded from completion calculation
- **Logic**: OptOut members don't count toward completion
- **Completion Formula**: `completed_members + exhausted_retries = (total_enrolled - optout_members)`
- **Pros**: Higher "success" rate
- **Cons**: May never complete if many opt-outs

**□ Option C**: Separate tracking
- **Logic**: Track OptOut separately in completion metrics
- **Report**: "900 completed, 50 opted out, 50 failed = 100% contacted"
- **Pros**: Detailed reporting
- **Cons**: More complex logic

**👉 YOUR ANSWER:** _______________

**👉 RATIONALE:** _______________

---

## 🎯 **Proposed Solution** (Will finalize after answers)

Based on most common scenarios, here's the recommended approach:

### **Recommended Completion Logic:**

```python
"""
Mark campaign status = 'Completed' when:

1. Campaign is NOT recurring (end_ts IS NOT NULL)
   AND
2. One of these conditions is met:
   a) end_ts has been reached (time-based completion)
      OR
   b) All enrolled members have been fully processed:
      - disposition IN ('Completed', 'OptOut') (successful contact)
        OR
      - (disposition IN ('Failed', 'NoAnswer') AND retry_seq >= MAX_RETRIES)
"""
```

### **Proposed SQL Query (Draft):**

```sql
-- Find campaigns ready to be marked as Completed
WITH CampaignEnrollmentStats AS (
    SELECT
        c.campaign_id,
        c.name as campaign_name,
        c.end_ts,
        COUNT(DISTINCT mce.member_id) as total_enrolled_members,

        -- Successful contacts
        COUNT(DISTINCT CASE
            WHEN oa.disposition = 'Completed' THEN mce.member_id
        END) as completed_members,

        -- OptOut members (may count as done - see Question 4)
        COUNT(DISTINCT CASE
            WHEN oa.disposition = 'OptOut' THEN mce.member_id
        END) as optout_members,

        -- Exhausted retry attempts (Failed/NoAnswer after max retries)
        COUNT(DISTINCT CASE
            WHEN oa.disposition IN ('Failed', 'NoAnswer')
             AND oa.retry_seq >= 5  -- TODO: Replace with config value
            THEN mce.member_id
        END) as exhausted_retry_members,

        -- Members with at least one attempt
        COUNT(DISTINCT CASE
            WHEN oa.attempt_id IS NOT NULL THEN mce.member_id
        END) as attempted_members

    FROM ioe.campaigns_enhanced c
    INNER JOIN ioe.member_campaign_enrollments_enhanced mce
        ON c.campaign_id = mce.campaign_id
        AND mce.current_status = 'Active'
    LEFT JOIN ioe.outreach_attempts oa
        ON mce.enrollment_id = oa.enrollment_id
    WHERE c.status = 'Active'
      AND c.campaign_type = 'Partner'
      AND c.primary_channel = 'voice'
    GROUP BY c.campaign_id, c.name, c.end_ts
)
SELECT
    campaign_id,
    campaign_name,
    total_enrolled_members,
    completed_members,
    optout_members,
    exhausted_retry_members,
    attempted_members,
    CAST(completed_members AS FLOAT) / NULLIF(total_enrolled_members, 0) * 100 as success_rate_pct
FROM CampaignEnrollmentStats
WHERE
    -- Condition 1: Not a recurring campaign (has end_ts)
    end_ts IS NOT NULL
    AND
    -- Condition 2: Either time-based OR attempt-based completion
    (
        -- Option A: End date reached
        (end_ts <= SYSDATETIMEOFFSET())
        OR
        -- Option B: All members processed (TODO: Adjust based on Question 2 answer)
        (total_enrolled_members = (completed_members + optout_members + exhausted_retry_members))
    )
```

**Note**: This query will be finalized after Question 2 and 4 are answered.

---

## 🔧 **Implementation Steps** (After answers received)

### **Step 1: Database Schema Updates (if needed)**

**Option 1: No schema changes needed** (if using existing fields)
- Use `end_ts IS NOT NULL` to identify non-recurring campaigns
- No migration required

**Option 2: Add `is_recurring` flag** (if Question 1 = Option B)
```sql
-- Add new column to campaigns_enhanced
ALTER TABLE ioe.campaigns_enhanced
ADD is_recurring BIT DEFAULT 0;

-- Update existing campaigns
UPDATE ioe.campaigns_enhanced
SET is_recurring = CASE
    WHEN end_ts IS NULL THEN 1  -- Ongoing campaigns
    ELSE 0                       -- Time-bound campaigns
END;

-- Add index for performance
CREATE INDEX IX_campaigns_recurring_status
ON ioe.campaigns_enhanced(is_recurring, status, campaign_type)
WHERE status = 'Active' AND campaign_type = 'Partner';
```

**Option 3: Add completion metadata fields** (optional, for reporting)
```sql
ALTER TABLE ioe.campaigns_enhanced
ADD completed_ts DATETIMEOFFSET NULL,           -- When campaign was marked completed
    completion_reason NVARCHAR(255) NULL,        -- 'end_date_reached' or 'all_members_contacted'
    final_success_rate DECIMAL(5,2) NULL,        -- e.g., 87.50 (%)
    final_members_completed INT NULL,            -- Count at completion
    final_members_total INT NULL;                -- Total enrolled at completion
```

---

### **Step 2: Create CampaignCompletionChecker Service**

**File**: `af_code/partner_campaign_scheduler/services/campaign_completion_checker.py`

```python
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any
from af_code.bland_ai_webhook.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class CampaignCompletionChecker:
    """
    Service to check and auto-complete Partner campaigns when criteria are met.

    Purpose:
    - Identifies Active campaigns that meet completion criteria
    - Updates campaign status to 'Completed'
    - Logs completion metrics for reporting

    BusinessCaseID: BC-XXX (TBD)
    """

    def __init__(self, db_service: DatabaseService):
        """
        Initialize the campaign completion checker.

        Args:
            db_service: DatabaseService instance for database operations
        """
        self.db_service = db_service
        self.max_retry_attempts = 5  # TODO: Move to configuration

    def check_and_complete_campaigns(self) -> List[Dict[str, Any]]:
        """
        Check all Active Partner campaigns and mark completed ones.

        Returns:
            List of completed campaign details with metrics
        """
        logger.info("=" * 80)
        logger.info("🔍 [COMPLETION-CHECKER] Starting campaign completion check...")
        logger.info("=" * 80)

        try:
            # Step 1: Find campaigns ready to be completed
            candidates = self._find_completion_candidates()

            if not candidates:
                logger.info("📋 [COMPLETION-CHECKER] No campaigns ready for completion")
                return []

            logger.info(f"📊 [COMPLETION-CHECKER] Found {len(candidates)} campaigns ready for completion")

            # Step 2: Mark each campaign as Completed
            completed_campaigns = []

            for candidate in candidates:
                campaign_id = candidate['campaign_id']
                campaign_name = candidate['campaign_name']

                try:
                    logger.info(f"✅ [COMPLETION-CHECKER] Marking campaign as Completed: {campaign_name}")

                    # Update campaign status
                    self._mark_campaign_completed(candidate)

                    # Log metrics
                    self._log_completion_metrics(candidate)

                    completed_campaigns.append(candidate)

                except Exception as e:
                    logger.error(f"❌ [COMPLETION-CHECKER] Failed to complete campaign {campaign_name}: {str(e)}")
                    continue

            logger.info("=" * 80)
            logger.info(f"🎉 [COMPLETION-CHECKER] Successfully completed {len(completed_campaigns)} campaigns")
            logger.info("=" * 80)

            return completed_campaigns

        except Exception as e:
            logger.error(f"🚨 [COMPLETION-CHECKER] Error during completion check: {str(e)}")
            raise

    def _find_completion_candidates(self) -> List[Dict[str, Any]]:
        """
        Find Active campaigns that meet completion criteria.

        Returns:
            List of campaign records with metrics
        """
        # TODO: Finalize this query based on answers to Questions 1, 2, 4
        query = """
            -- Query will be finalized after stakeholder decisions
            -- Placeholder for now
            SELECT
                c.campaign_id,
                c.name as campaign_name,
                c.end_ts,
                0 as total_enrolled_members,
                0 as completed_members,
                0 as optout_members,
                0 as exhausted_retry_members
            FROM ioe.campaigns_enhanced c
            WHERE c.status = 'Active'
              AND c.campaign_type = 'Partner'
              AND 1=0  -- Disabled until finalized
        """

        logger.info("🔍 [COMPLETION-CHECKER] Executing completion candidate query...")
        results = self.db_service.execute_query(query, fetch_results=True)
        logger.info(f"📊 [COMPLETION-CHECKER] Found {len(results)} candidates")

        return results

    def _mark_campaign_completed(self, campaign: Dict[str, Any]) -> None:
        """
        Update campaign status to 'Completed' with metadata.

        Args:
            campaign: Campaign record with metrics
        """
        campaign_id = campaign['campaign_id']
        campaign_name = campaign['campaign_name']

        # Determine completion reason
        end_ts = campaign.get('end_ts')
        if end_ts and end_ts <= datetime.now():
            completion_reason = 'end_date_reached'
        else:
            completion_reason = 'all_members_contacted'

        # Calculate success rate
        total = campaign['total_enrolled_members']
        completed = campaign['completed_members']
        success_rate = (completed / total * 100) if total > 0 else 0

        query = """
            UPDATE ioe.campaigns_enhanced
            SET
                status = 'Completed',
                completed_ts = SYSDATETIMEOFFSET(),
                completion_reason = %s,
                final_success_rate = %s,
                final_members_completed = %s,
                final_members_total = %s
            WHERE campaign_id = %s
        """

        params = [
            completion_reason,
            success_rate,
            completed,
            total,
            str(campaign_id)
        ]

        self.db_service.execute_query(query, params=params, fetch_results=False)
        logger.info(f"✅ [COMPLETION-CHECKER] Campaign marked as Completed: {campaign_name}")

    def _log_completion_metrics(self, campaign: Dict[str, Any]) -> None:
        """
        Log detailed completion metrics for reporting.

        Args:
            campaign: Campaign record with metrics
        """
        campaign_name = campaign['campaign_name']
        total = campaign['total_enrolled_members']
        completed = campaign['completed_members']
        optout = campaign['optout_members']
        exhausted = campaign['exhausted_retry_members']
        success_rate = (completed / total * 100) if total > 0 else 0

        logger.info("=" * 60)
        logger.info(f"📊 [COMPLETION-CHECKER] Campaign Completion Metrics:")
        logger.info(f"   Campaign: {campaign_name}")
        logger.info(f"   Total Enrolled: {total}")
        logger.info(f"   ✅ Completed: {completed} ({completed/total*100:.1f}%)")
        logger.info(f"   🚫 Opted Out: {optout} ({optout/total*100:.1f}%)")
        logger.info(f"   ⚠️ Exhausted Retries: {exhausted} ({exhausted/total*100:.1f}%)")
        logger.info(f"   📈 Success Rate: {success_rate:.2f}%")
        logger.info("=" * 60)
```

---

### **Step 3: Create Azure Function (Option B - Recommended)**

**File**: `functions/campaign_completion_checker.py`

```python
import azure.functions as func
import logging
from datetime import datetime

# Create blueprint
campaign_completion_bp = func.Blueprint()

# Import services
try:
    from af_code.partner_campaign_scheduler.services.campaign_completion_checker import CampaignCompletionChecker
    from af_code.bland_ai_webhook.services.config_manager import ConfigManager
    from af_code.bland_ai_webhook.services.database_service import DatabaseService
    logging.info("✅ Campaign Completion Checker imports successful")
except ImportError as e:
    logging.error(f"❌ Import error in Campaign Completion Checker: {e}")
    raise


@campaign_completion_bp.timer_trigger(
    schedule="0 0 */2 * * *",  # Every 2 hours on the hour (staggered from scheduler)
    arg_name="timer",
    run_on_startup=False
)
def campaign_completion_checker_timer(timer: func.TimerRequest) -> None:
    """
    Campaign Completion Checker - Timer Function

    Runs every 2 hours to check Active Partner campaigns and mark completed ones.

    BusinessCaseID: BC-XXX (TBD)
    """
    start_time = datetime.utcnow()
    request_id = f"completion-checker-{start_time.strftime('%Y%m%d-%H%M%S')}"

    logging.info("=" * 80)
    logging.info(f"🔍 [COMPLETION-CHECKER] Timer triggered at {start_time.isoformat()}")
    logging.info(f"📋 [COMPLETION-CHECKER] Request ID: {request_id}")
    logging.info("=" * 80)

    try:
        # Initialize services
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        checker = CampaignCompletionChecker(db_service)

        # Check and complete campaigns
        completed_campaigns = checker.check_and_complete_campaigns()

        # Log summary
        duration = (datetime.utcnow() - start_time).total_seconds()
        logging.info("=" * 80)
        logging.info(f"🎉 [COMPLETION-CHECKER] Execution completed successfully")
        logging.info(f"⏱️ [COMPLETION-CHECKER] Duration: {duration:.2f} seconds")
        logging.info(f"✅ [COMPLETION-CHECKER] Campaigns completed: {len(completed_campaigns)}")
        logging.info(f"📋 [COMPLETION-CHECKER] Request ID: {request_id}")
        logging.info("=" * 80)

    except Exception as e:
        logging.error(f"🚨 [COMPLETION-CHECKER] Error during execution: {str(e)}")
        import traceback
        logging.error(f"🚨 [COMPLETION-CHECKER] Traceback: {traceback.format_exc()}")
```

**Register in `function_app.py`:**
```python
# Add after other blueprint registrations
try:
    from functions.campaign_completion_checker import campaign_completion_bp
    app.register_functions(campaign_completion_bp)
    logging.info("✅ Successfully registered Campaign Completion Checker blueprint")
except Exception as e:
    logging.error(f"❌ Failed to register Campaign Completion Checker blueprint: {e}")
```

---

### **Step 4: Update campaign_qualifier.py (Already Done)**

No changes needed! The existing query already excludes Completed campaigns:

```python
# Line 64 in campaign_qualifier.py
WHERE c.status = 'Active'  # ← Only Active campaigns (not Completed)
```

---

### **Step 5: Add Configuration for Max Retries**

**Option A**: Add to Azure Key Vault (Recommended)
```python
# In ConfigManager
max_retry_attempts = config_manager.get_config("MaxRetryAttempts", default=5)
```

**Option B**: Add to environment variables
```json
// In local.settings.json
{
  "Values": {
    "MAX_RETRY_ATTEMPTS": "5"
  }
}
```

---

## 🧪 **Testing Plan** (After implementation)

### **Test Case 1: Time-Based Completion**
```yaml
Scenario: Campaign with end_ts reached
Given:
  - Campaign end_ts = '2025-10-20 23:59:59'
  - Current time = '2025-10-21 00:00:00'
  - 500/1000 members have been called
Expected:
  - Campaign status updated to 'Completed'
  - completion_reason = 'end_date_reached'
  - final_success_rate = 50%
```

### **Test Case 2: All Members Contacted**
```yaml
Scenario: All enrolled members processed
Given:
  - Total enrolled: 1000
  - Completed: 900
  - OptOut: 50
  - Exhausted retries (Failed/NoAnswer): 50
  - Sum: 900 + 50 + 50 = 1000
Expected:
  - Campaign status updated to 'Completed'
  - completion_reason = 'all_members_contacted'
  - final_success_rate = 90%
```

### **Test Case 3: Recurring Campaign (Should NOT Complete)**
```yaml
Scenario: Recurring campaign with end_ts = NULL
Given:
  - Campaign end_ts = NULL
  - All 1000 members have been contacted
Expected:
  - Campaign status remains 'Active'
  - Campaign continues to run
```

### **Test Case 4: In-Progress Campaign**
```yaml
Scenario: Campaign still in progress
Given:
  - Total enrolled: 1000
  - Completed: 600
  - Pending: 200
  - Not yet attempted: 200
  - end_ts = '2025-12-31'
Expected:
  - Campaign status remains 'Active'
  - Campaign continues to run
```

### **Test Case 5: Multiple Campaigns**
```yaml
Scenario: Batch processing multiple campaigns
Given:
  - Campaign A: Ready to complete (end_ts reached)
  - Campaign B: Ready to complete (all members contacted)
  - Campaign C: Still in progress
  - Campaign D: Recurring (end_ts = NULL)
Expected:
  - Campaign A status → 'Completed'
  - Campaign B status → 'Completed'
  - Campaign C status → 'Active'
  - Campaign D status → 'Active'
```

---

## 🚀 **Deployment Strategy**

### **Phase 1: Development & Testing**
1. ✅ Get answers to 4 critical questions
2. ✅ Finalize SQL completion query
3. ✅ Implement CampaignCompletionChecker service
4. ✅ Create Azure Function with timer trigger
5. ✅ Add unit tests
6. ✅ Add integration tests
7. ✅ Test in local environment

### **Phase 2: Staging Deployment**
1. Deploy to staging Azure Function App
2. Run manual tests with staging data
3. Monitor logs for 24 hours
4. Verify no unintended completions
5. Test with real campaign scenarios

### **Phase 3: Production Deployment**
1. Deploy to production
2. Monitor first execution closely
3. Verify expected campaigns complete
4. Check for any errors or edge cases
5. Generate completion reports

### **Phase 4: Monitoring & Iteration**
1. Monitor completion metrics weekly
2. Gather feedback from stakeholders
3. Adjust completion criteria if needed
4. Update documentation

---

## 📊 **Success Metrics**

### **KPIs to Track:**
1. **Completion Rate**: % of campaigns auto-completed vs manually updated
2. **Accuracy**: % of correctly completed campaigns (no false positives)
3. **Timeliness**: Average time between meeting criteria and status update
4. **Error Rate**: % of completion check executions with errors

### **Monitoring Queries:**
```sql
-- Campaigns completed in last 7 days
SELECT
    name,
    completed_ts,
    completion_reason,
    final_success_rate,
    final_members_completed,
    final_members_total
FROM ioe.campaigns_enhanced
WHERE status = 'Completed'
  AND completed_ts >= DATEADD(day, -7, SYSDATETIMEOFFSET())
ORDER BY completed_ts DESC;

-- Active campaigns near completion
SELECT
    c.name,
    c.end_ts,
    COUNT(DISTINCT mce.member_id) as total_enrolled,
    COUNT(DISTINCT CASE WHEN oa.disposition = 'Completed' THEN mce.member_id END) as completed_count,
    CAST(COUNT(DISTINCT CASE WHEN oa.disposition = 'Completed' THEN mce.member_id END) AS FLOAT)
        / NULLIF(COUNT(DISTINCT mce.member_id), 0) * 100 as completion_pct
FROM ioe.campaigns_enhanced c
INNER JOIN ioe.member_campaign_enrollments_enhanced mce ON c.campaign_id = mce.campaign_id
LEFT JOIN ioe.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id
WHERE c.status = 'Active'
  AND c.campaign_type = 'Partner'
GROUP BY c.campaign_id, c.name, c.end_ts
HAVING COUNT(DISTINCT CASE WHEN oa.disposition = 'Completed' THEN mce.member_id END) > 0
ORDER BY completion_pct DESC;
```

---

## 📝 **Next Steps**

### **Action Items:**

**PRIORITY 1: Answer Critical Questions**
- [ ] **Question 1**: How to identify recurring campaigns? (Answer: _______)
- [ ] **Question 2**: Completion criteria for failed members? (Answer: _______)
- [ ] **Question 3**: Where should logic run? (Answer: _______)
- [ ] **Question 4**: OptOut members count as done? (Answer: _______)

**PRIORITY 2: Review & Approve Plan**
- [ ] Review this document with stakeholders
- [ ] Approve completion criteria
- [ ] Approve retry policy
- [ ] Approve max retry attempts value

**PRIORITY 3: Implementation**
- [ ] Finalize SQL completion query based on answers
- [ ] Implement CampaignCompletionChecker service
- [ ] Create Azure Function (or extend scheduler)
- [ ] Add database schema changes (if needed)
- [ ] Write unit tests
- [ ] Write integration tests

**PRIORITY 4: Testing & Deployment**
- [ ] Test in local environment
- [ ] Deploy to staging
- [ ] Run staging tests
- [ ] Deploy to production
- [ ] Monitor first 48 hours

**PRIORITY 5: Documentation**
- [ ] Update PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md
- [ ] Add completion checker to README.md
- [ ] Create user guide for completion reports
- [ ] Update BusinessCaseID mapping

---

## 📞 **Contacts & Resources**

**Document Owner**: AI-POD Team - Data Science
**Technical Lead**: TBD
**Stakeholders**: TBD

**Related Documentation:**
- `PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md` - Complete technical reference
- `PARTNER_CAMPAIGN_IMPLEMENTATION.md` - Implementation summary
- `CAMPAIGN_QUALIFICATION_LOGIC.md` - Timezone and qualification logic
- `IOE_TABLE_USAGE_REFERENCE.md` - Database schema reference

**Related BusinessCaseIDs:**
- BC-109: Partner Campaign Scheduler
- BC-XXX: Campaign Auto-Completion (TBD)

---

## 📅 **Revision History**

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2025-10-22 | 1.0 | Claude Code | Initial draft - awaiting stakeholder answers |
| TBD | 2.0 | TBD | Finalized after answers received |

---

**END OF DOCUMENT**

**Status**: ⏳ PENDING ANSWERS - Please review and provide answers to the 4 critical questions above.

Once answers are received, this document will be updated with:
- ✅ Finalized SQL queries
- ✅ Complete implementation code
- ✅ Detailed test cases
- ✅ Deployment timeline
