# Device Activation Callback Scheduler - Detailed Guide

**Created:** 2025-12-07
**BusinessCaseID:** BC-TBD (Device Activation System)
**File:** `af_code/device_activation_scheduler/services/callback_scheduler.py`

---

## Table of Contents

1. [Overview](#overview)
2. [When Callbacks Are Created](#when-callbacks-are-created)
3. [Callback Lifecycle](#callback-lifecycle)
4. [How Callback Scheduler Works](#how-callback-scheduler-works)
5. [Real-World Examples](#real-world-examples)
6. [Database Tables](#database-tables)
7. [Integration with Main Scheduler](#integration-with-main-scheduler)
8. [Business Rules](#business-rules)

---

## Overview

The **Callback Scheduler** handles scheduled callbacks for Device Activation campaign members who request to be called back at a later time.

### Purpose:
- Member requests callback during AI call (e.g., "I'm busy, call me in 2 hours")
- System schedules callback for requested time
- Callback scheduler processes pending callbacks
- Maximum 3 attempts within 24 hours
- After timeout, member returns to main calling sequence

### Key Features:
- ✅ Business hours validation (dual-timezone)
- ✅ Automatic rescheduling (if outside business hours)
- ✅ Attempt tracking (max 3 attempts)
- ✅ Timeout handling (24 hours or 3 attempts)
- ✅ Priority over main sequence (callbacks processed first)

---

## When Callbacks Are Created

Callbacks are created during AI calls when members request to be called back.

### Scenario 1: Member is Busy

**AI Call Transcript:**
```
AI Grace: "Hi John, this is Grace from Medical Guardian. I'm calling to help
           you activate your new device. Are you ready to get started?"

Member John: "Oh, I'm really busy right now. Can you call me back in 2 hours?"

AI Grace: "Of course! I'll call you back at 2:00 PM today. Does that work?"

Member John: "Yes, that's perfect. Thank you!"

AI Grace: "Great! I'll talk to you at 2:00 PM. Have a great day!"
```

**What Happens in Database:**
```sql
-- Webhook creates callback entry
INSERT INTO engage360.outreach_callback_queue (
    callback_id,
    enrollment_id,
    member_id,
    campaign_id,
    scheduled_callback_time,
    callback_reason,
    attempt_count,
    status
) VALUES (
    NEWID(),
    '<enrollment-id>',
    '<member-id>',
    '<campaign-id>',
    '2025-12-07 14:00:00-05:00',  -- 2:00 PM EST
    'BUSY',
    0,
    'PENDING'
);
```

### Scenario 2: Member is Unboxing Device

**AI Call Transcript:**
```
AI Grace: "Hi Maria, I'm calling to help you activate your Medical Guardian device."

Member Maria: "I just got the package! I'm opening it now. Can you give me
               30 minutes to get everything unpacked?"

AI Grace: "Absolutely! I'll call you back in 30 minutes at 10:30 AM."

Member Maria: "Thank you!"
```

**Database Entry:**
```sql
INSERT INTO engage360.outreach_callback_queue (
    ...
    scheduled_callback_time = '2025-12-07 10:30:00-05:00',  -- 30 minutes later
    callback_reason = 'UNBOXING',
    ...
);
```

### Scenario 3: Device Needs Charging

**AI Call Transcript:**
```
AI Grace: "Is your device charged and ready to activate?"

Member Robert: "No, the battery is dead. It's charging now."

AI Grace: "No problem! The device usually takes about 2 hours to charge fully.
           Shall I call you back in 2 hours?"

Member Robert: "Yes, that would be great."
```

**Database Entry:**
```sql
INSERT INTO engage360.outreach_callback_queue (
    ...
    scheduled_callback_time = '2025-12-07 14:00:00-05:00',  -- 2 hours later
    callback_reason = 'CHARGING',
    ...
);
```

---

## Callback Lifecycle

### Status Flow Diagram

```
┌─────────────┐
│   PENDING   │  ← Callback created by webhook
└──────┬──────┘
       │
       │ ⏰ Scheduled time arrives
       │ ✅ Business hours validated
       │
       ▼
┌─────────────┐
│ IN_PROGRESS │  ← Callback batch submitted to Bland AI
└──────┬──────┘
       │
       ├─────────────────────────────────────┐
       │                                     │
       │ ✅ Device activated                │ ❌ No answer / Failed
       ▼                                     ▼
┌─────────────┐                       ┌─────────────┐
│  COMPLETED  │                       │   Retry?    │
└─────────────┘                       └──────┬──────┘
                                             │
                                  ┌──────────┼──────────┐
                                  │                     │
                        attempt < 3              attempt >= 3
                        AND < 24 hours           OR >= 24 hours
                                  │                     │
                                  ▼                     ▼
                          Back to PENDING       ┌─────────────┐
                          (retry later)         │  TIMED_OUT  │
                                                └─────────────┘
                                                      │
                                                      ▼
                                            Return to main
                                            call sequence
```

### Status Definitions

| Status | Description | Next Step |
|--------|-------------|-----------|
| **PENDING** | Callback scheduled, waiting for scheduled_callback_time | Move to IN_PROGRESS when time arrives |
| **IN_PROGRESS** | Callback batch submitted to Bland AI, call in progress | Wait for webhook result |
| **COMPLETED** | Device successfully activated during callback | Campaign ends, no further action |
| **FAILED** | All 3 attempts failed (no answer/unsuccessful) | Return to main sequence |
| **TIMED_OUT** | 24 hours elapsed OR 3 attempts exhausted | Return to main sequence |

---

## How Callback Scheduler Works

### Step-by-Step Process

#### Step 1: Query Pending Callbacks

**SQL Query:**
```sql
SELECT
    cq.callback_id,
    cq.enrollment_id,
    cq.scheduled_callback_time,
    cq.callback_reason,
    cq.attempt_count,
    cq.max_attempts,
    m.first_name,
    m.last_name,
    m.primary_phone,
    m.timezone
FROM engage360.outreach_callback_queue cq
JOIN engage360.members m ON cq.member_id = m.member_id
WHERE
    cq.status = 'PENDING'
    AND cq.attempt_count < cq.max_attempts
    AND SYSDATETIMEOFFSET() >= cq.scheduled_callback_time  -- Time has arrived
    AND DATEDIFF(HOUR, cq.created_ts, SYSDATETIMEOFFSET()) < 24  -- Not timed out
ORDER BY cq.scheduled_callback_time
```

**Example Result:**
```
callback_id: abc-123-def
enrollment_id: xyz-789
scheduled_callback_time: 2025-12-07 14:00:00-05:00
callback_reason: BUSY
attempt_count: 0
max_attempts: 3
first_name: John
last_name: Smith
primary_phone: +15551234567
timezone: America/New_York
```

#### Step 2: Validate Business Hours

**Python Code:**
```python
from af_code.shared.business_hours_utils import can_make_call
import pytz
from datetime import datetime

# Get current time in UTC
now_utc = datetime.now(pytz.UTC)

# Member timezone
member_tz = pytz.timezone('America/New_York')

# Validate dual-timezone business hours
# (MG EST 9 AM - 5 PM AND member timezone 9 AM - 5 PM)
can_call, reason = can_make_call(now_utc, member_tz)

if can_call:
    # Add to eligible callbacks list
    eligible_callbacks.append(callback)
else:
    # Reschedule to next business day
    reschedule_callback(callback_id, member_timezone)
```

**Example Validation:**

**Scenario A: Within Business Hours**
```
Current time UTC: 2025-12-07 19:00:00 UTC
Current time EST: 2025-12-07 14:00:00 EST (2 PM)
Current time Member (EST): 2025-12-07 14:00:00 EST (2 PM)

Medical Guardian hours: 9 AM - 5 PM EST ✅ (2 PM is within)
Member hours: 9 AM - 5 PM EST ✅ (2 PM is within)

Result: can_call = True, "Within business hours for both MG and member"
```

**Scenario B: Outside Business Hours**
```
Current time UTC: 2025-12-07 23:00:00 UTC
Current time EST: 2025-12-07 18:00:00 EST (6 PM)
Current time Member (EST): 2025-12-07 18:00:00 EST (6 PM)

Medical Guardian hours: 9 AM - 5 PM EST ❌ (6 PM is AFTER 5 PM)
Member hours: 9 AM - 5 PM EST ❌ (6 PM is AFTER 5 PM)

Result: can_call = False, "Outside business hours - after 5 PM EST"
Action: Reschedule to tomorrow 9:00 AM EST
```

#### Step 3: Handle Timeouts

**SQL Update:**
```sql
UPDATE engage360.outreach_callback_queue
SET status = 'TIMED_OUT', updated_ts = SYSDATETIMEOFFSET()
WHERE status = 'PENDING'
AND (
    -- 24-hour timeout
    DATEDIFF(HOUR, created_ts, SYSDATETIMEOFFSET()) >= 24
    OR
    -- Max attempts exhausted
    attempt_count >= max_attempts
);
```

**Example:**
```
Callback created: 2025-12-07 10:00:00
Current time: 2025-12-08 11:00:00 (25 hours later)

Result: Marked as TIMED_OUT
Member: Returns to main Device Activation call sequence
```

#### Step 4: Return Eligible Callbacks

**Python Return:**
```python
return {
    "eligible_callbacks": [
        {
            "callback_id": "abc-123-def",
            "enrollment_id": "xyz-789",
            "member_id": "member-uuid",
            "first_name": "John",
            "last_name": "Smith",
            "primary_phone": "+15551234567",
            "device_name": "MG Classic",
            "callback_reason": "BUSY",
            "attempt_count": 0,
            ...
        }
    ],
    "rescheduled_count": 2,
    "timed_out_count": 1
}
```

---

## Real-World Examples

### Example 1: Successful Callback (1st Attempt)

**Timeline:**

**10:00 AM** - Initial Call (Call 1)
```
AI Grace: "Hi John, ready to activate your device?"
Member John: "I'm busy, call me back at 2 PM."
AI Grace: "I'll call you at 2 PM today!"

Database:
- CREATE callback entry
- scheduled_callback_time = 2025-12-07 14:00:00 EST
- callback_reason = 'BUSY'
- attempt_count = 0
- status = 'PENDING'
```

**2:00 PM** - Callback Scheduler Runs
```python
# Callback scheduler queries pending callbacks
pending_callbacks = get_pending_callbacks()
# Result: 1 callback found (John's callback)

# Validate business hours
can_call, reason = validate_callback_business_hours('abc-123', 'America/New_York')
# Result: True, "Within business hours"

# Return as eligible
return {"eligible_callbacks": [john_callback]}
```

**2:05 PM** - Batch Orchestrator Submits Callback Batch
```python
# Create callback batch for Bland AI
batch_request = {
    "calls": [{
        "to": "+15551234567",
        "metadata": {
            "callback_id": "abc-123-def",
            "callback_reason": "BUSY",
            "is_callback": True,
            ...
        }
    }]
}

# Submit to Bland AI
bland_client.submit_batch_calls(batch_request)

# Update callback status
UPDATE outreach_callback_queue
SET attempt_count = 1, status = 'IN_PROGRESS', last_attempt_ts = NOW
WHERE callback_id = 'abc-123-def'
```

**2:10 PM** - Webhook Receives Result
```python
# Webhook payload from Bland AI
webhook_data = {
    "call_id": "bland-call-12345",
    "metadata": {
        "callback_id": "abc-123-def",
        "is_callback": True
    },
    "status": "completed",
    "device_activated": True  # John activated device successfully!
}

# Update callback status
UPDATE outreach_callback_queue
SET status = 'COMPLETED'
WHERE callback_id = 'abc-123-def'

# Update enrollment
UPDATE member_campaign_enrollments_enhanced
SET current_status = 'COMPLETED', device_activated = 1
WHERE enrollment_id = 'xyz-789'
```

**Result:** ✅ Success! Device activated on 1st callback attempt.

---

### Example 2: Failed Callback, Retry 3 Times, Then Timeout

**Timeline:**

**10:00 AM** - Initial Call (Call 1)
```
Member Maria: "Call me back in 2 hours, I'm unboxing the device."

Database:
- CREATE callback (scheduled for 12:00 PM)
- callback_reason = 'UNBOXING'
- attempt_count = 0
```

**12:00 PM** - Callback Attempt 1
```
Bland AI calls: No answer (voicemail)

Webhook result:
- disposition = 'NO_ANSWER'

Database:
- attempt_count = 1 (incremented)
- status = 'PENDING' (retry later)
- last_attempt_ts = 12:00 PM
```

**1:00 PM** - Callback Attempt 2 (1 hour later)
```
Bland AI calls: No answer again

Webhook result:
- disposition = 'NO_ANSWER'

Database:
- attempt_count = 2 (incremented)
- status = 'PENDING' (retry later)
- last_attempt_ts = 1:00 PM
```

**2:00 PM** - Callback Attempt 3 (2 hours later)
```
Bland AI calls: No answer (3rd time)

Webhook result:
- disposition = 'NO_ANSWER'

Database:
- attempt_count = 3 (incremented)
- status = 'PENDING'
- last_attempt_ts = 2:00 PM
```

**2:30 PM** - Timeout Check
```sql
-- Callback scheduler handles timeouts
UPDATE outreach_callback_queue
SET status = 'TIMED_OUT'
WHERE callback_id = 'maria-callback'
AND attempt_count >= max_attempts;  -- 3 >= 3 ✅

Result: Status = 'TIMED_OUT'
```

**Next Scheduler Run (3:00 PM)** - Back to Main Sequence
```python
# EligibilityService query NO LONGER excludes Maria
# She's eligible for main sequence again

eligible_members = get_eligible_members()
# Result: Maria appears in the list (no pending callback)

# Maria will receive Call 2 from main sequence
# (2 business days after Call 1, as per normal schedule)
```

**Result:** ❌ Callback failed after 3 attempts. Maria returns to main call sequence.

---

### Example 3: Callback Outside Business Hours (Rescheduled)

**Timeline:**

**4:30 PM** - Member Requests Callback
```
Member Robert: "Call me back in 2 hours" (would be 6:30 PM)

Database:
- CREATE callback
- scheduled_callback_time = 6:30 PM EST (OUTSIDE business hours)
```

**6:30 PM** - Callback Scheduler Runs
```python
# Query finds Robert's callback
pending_callbacks = get_pending_callbacks()

# Validate business hours
now_utc = datetime.now(pytz.UTC)  # 23:30 UTC
member_tz = pytz.timezone('America/New_York')

can_call, reason = can_make_call(now_utc, member_tz)
# Result: False, "Outside business hours - after 5 PM EST"

# Reschedule to next business day
next_day = now_utc + timedelta(days=1)
next_day_9am = next_day.replace(hour=9, minute=0)  # 9:00 AM tomorrow

UPDATE outreach_callback_queue
SET scheduled_callback_time = '2025-12-08 09:00:00-05:00'
WHERE callback_id = 'robert-callback'
```

**9:00 AM Next Day** - Callback Executed
```
Callback scheduler finds Robert's rescheduled callback
Business hours validated: ✅ (9 AM is within hours)
Batch created and submitted to Bland AI
```

**Result:** ✅ Callback rescheduled to next business day and executed successfully.

---

## Database Tables

### Main Table: `engage360.outreach_callback_queue`

```sql
CREATE TABLE engage360.outreach_callback_queue (
    callback_id UNIQUEIDENTIFIER PRIMARY KEY,
    enrollment_id UNIQUEIDENTIFIER NOT NULL,
    member_id UNIQUEIDENTIFIER NOT NULL,
    campaign_id UNIQUEIDENTIFIER NOT NULL,

    -- Scheduling
    scheduled_callback_time DATETIMEOFFSET NOT NULL,
    callback_reason VARCHAR(100),  -- BUSY, UNBOXING, CHARGING, etc.
    preferred_contact_method VARCHAR(50),

    -- Attempt Tracking
    attempt_count INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    last_attempt_ts DATETIMEOFFSET,

    -- Status
    status VARCHAR(50) DEFAULT 'PENDING',

    -- Timestamps
    created_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),
    updated_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET()
);
```

### Sample Data:

```sql
-- Example 1: Pending callback
callback_id: abc-123-def
enrollment_id: xyz-789
member_id: member-uuid-1
campaign_id: device-activation-campaign-id
scheduled_callback_time: 2025-12-07 14:00:00-05:00
callback_reason: BUSY
attempt_count: 0
max_attempts: 3
status: PENDING
created_ts: 2025-12-07 10:00:00-05:00

-- Example 2: In-progress callback (1st attempt)
callback_id: def-456-ghi
enrollment_id: abc-111
member_id: member-uuid-2
scheduled_callback_time: 2025-12-07 12:00:00-05:00
callback_reason: UNBOXING
attempt_count: 1
status: IN_PROGRESS
last_attempt_ts: 2025-12-07 12:00:00-05:00

-- Example 3: Timed out callback (3 attempts failed)
callback_id: ghi-789-jkl
enrollment_id: def-222
member_id: member-uuid-3
scheduled_callback_time: 2025-12-07 10:00:00-05:00
callback_reason: CHARGING
attempt_count: 3
status: TIMED_OUT
created_ts: 2025-12-06 10:00:00-05:00 (24+ hours ago)
```

---

## Integration with Main Scheduler

### How Callbacks Have Priority

**Main Scheduler Flow (`device_activation_scheduler.py`):**

```python
def create_device_activation_batch():
    # STEP 1: Process callbacks FIRST
    callback_results = callback_scheduler.process_callbacks()
    eligible_callbacks = callback_results.get("eligible_callbacks", [])

    if eligible_callbacks:
        # Create callback batches
        batch_orchestrator.create_and_submit_batches(eligible_callbacks)

    # STEP 2: Process main sequence (excludes members with pending callbacks)
    eligible_members = eligibility_service.get_eligible_members()
    # SQL query has: "AND NOT EXISTS (SELECT 1 FROM outreach_callback_queue WHERE status = 'PENDING')"

    if eligible_members:
        # Create main sequence batches
        batch_orchestrator.create_and_submit_batches(eligible_members)
```

### SQL Query Exclusion (Eligibility Service):

```sql
-- From eligibility_service.py
SELECT ...
FROM engage360.member_campaign_enrollments_enhanced e
...
WHERE
    -- Standard eligibility criteria
    e.current_status = 'ENROLLED'
    AND e.device_activated = 0

    -- ✅ EXCLUSION: Members with pending callbacks
    AND NOT EXISTS (
        SELECT 1
        FROM engage360.outreach_callback_queue cq
        WHERE cq.enrollment_id = e.enrollment_id
        AND cq.status = 'PENDING'
    )
```

**Result:** Members with pending callbacks are EXCLUDED from main sequence until callback completes or times out.

---

## Business Rules

### Rule 1: Maximum 3 Callback Attempts
- **Limit:** 3 attempts per callback
- **Enforcement:** `attempt_count < max_attempts` in SQL query
- **After 3 attempts:** Callback marked as TIMED_OUT or FAILED

### Rule 2: 24-Hour Timeout Window
- **Limit:** 24 hours from callback creation
- **Enforcement:** `DATEDIFF(HOUR, created_ts, NOW()) < 24`
- **After 24 hours:** Callback marked as TIMED_OUT

### Rule 3: Business Hours Validation
- **Medical Guardian:** 9 AM - 5 PM EST
- **Member Timezone:** 9 AM - 5 PM in member's local timezone
- **Both must be met:** Dual-timezone validation
- **Outside hours:** Callback rescheduled to next business day 9 AM

### Rule 4: Priority Over Main Sequence
- **Callbacks processed first** before main sequence
- **Main query excludes** members with pending callbacks
- **After timeout:** Member returns to main sequence

### Rule 5: Status Transitions
- **PENDING → IN_PROGRESS:** When batch submitted to Bland AI
- **IN_PROGRESS → COMPLETED:** Device activated successfully
- **IN_PROGRESS → PENDING:** No answer, retry if under 3 attempts
- **PENDING → TIMED_OUT:** 24 hours elapsed OR 3 attempts exhausted
- **TIMED_OUT → (none):** Member returns to main sequence

---

## Code Methods Summary

### `callback_scheduler.py` Methods:

| Method | Purpose | Returns |
|--------|---------|---------|
| `get_pending_callbacks()` | Query pending callbacks due now | List[Dict] |
| `process_callbacks()` | Process all pending callbacks | Dict (eligible, rescheduled, timed_out) |
| `_validate_callback_business_hours()` | Check if callback can be made now | Tuple(bool, str) |
| `_reschedule_callback()` | Reschedule to next business day | bool |
| `_handle_callback_timeouts()` | Mark timed-out callbacks | int (count) |
| `increment_callback_attempt()` | Increment attempt count after call | bool |
| `mark_callback_completed()` | Mark callback as successful | bool |
| `mark_callback_failed()` | Mark callback as failed | bool |

---

## Summary

The **Callback Scheduler** is a critical component of the Device Activation system that:

1. ✅ **Handles member requests** for scheduled callbacks
2. ✅ **Validates business hours** (dual-timezone)
3. ✅ **Manages retry logic** (max 3 attempts, 24-hour window)
4. ✅ **Prioritizes callbacks** over main sequence calls
5. ✅ **Returns timed-out members** to main sequence gracefully

**Key Integration Points:**
- 🔗 **Main Scheduler:** Processes callbacks BEFORE main sequence
- 🔗 **Batch Orchestrator:** Creates callback batches with metadata
- 🔗 **Webhook:** Creates callbacks, updates status, marks completed/failed
- 🔗 **Eligibility Service:** Excludes members with pending callbacks

**Next Steps:**
- ⏳ Update webhook for callback handling (Phase 6 remaining)
- ⏳ Create unit tests (Phase 7)
- ⏳ Integration testing (Phase 7)

---

**Last Updated:** 2025-12-07
**File Location:** `af_code/device_activation_scheduler/services/callback_scheduler.py` (570 lines)

