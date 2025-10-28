# DTC (Direct-to-Consumer) Call Flow - Complete Guide

## How DTC Makes Calls via Bland AI

This document traces the **complete journey** from timer trigger to actual phone calls being made for **BOTH** DTC campaigns:
- **DTC Intro Call** - First contact with new Medical Guardian device owners
- **DTC Wellness Check** - Follow-up calls to members after intro call completion

---

## Overview

DTC calls are made through **timer-triggered Azure Functions** that run **every 10 minutes**:

```
Timer (Every 10 min) → Get Qualified Members → Create Batch → Submit to Bland AI → Bland Makes Calls
```

**Key Point:** The Azure Function only **submits** the batch to Bland AI. The actual phone calls are made by **Bland AI** asynchronously after submission.

---

## DTC Campaign Types

| Aspect | DTC Intro Call | DTC Wellness Check |
|--------|----------------|-------------------|
| **Campaign ID** | `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC` | `E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B` |
| **Purpose** | First contact with new device owners | Follow-up wellness checks |
| **Phone Used** | `primary_phone` (member's personal phone) | `primary_phone` (member's personal phone) |
| **Eligibility Status** | `current_status = 'ENROLLED'` | `current_status = 'ENROLLED'` |
| **Prerequisites** | None | Intro campaign must be `UNENROLLED` |
| **call_type_code** | `"not_completed"` | `"completed"` |
| **Timer File** | `functions/dtc_intro_call_scheduler.py` | `functions/dtc_wellness_check_scheduler.py` |
| **Service File** | `af_dtc_intro_call/services/blandai_service.py` | `af_dtc_wellness_check/services/blandai_service_wellness.py` |
| **SQL Query** | `ELIGIBLE_MEMBERS_QUERY_INTRO` | `ELIGIBLE_MEMBERS_QUERY_WELLNESS` |

---

## Complete Call Flow Diagram (DTC INTRO CALL)

```
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Timer Trigger (Every 10 minutes)                         │
│ File: functions/dtc_intro_call_scheduler.py                      │
│                                                                   │
│ @dtc_intro_call_bp.timer_trigger(                                │
│     schedule="0 */10 * * * *",  # Every 10 minutes at :00        │
│     run_on_startup=False                                         │
│ )                                                                │
│ def timer_dtc_intro_call(timer):                                 │
│     campaign_id = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"         │
│     create_bland_ai_batch_call(campaign_id, ...)                 │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2: Execute Main Logic                                       │
│ File: af_code/af_dtc_intro_call/main_logic.py                    │
│ Function: create_bland_ai_batch_call()                           │
│                                                                   │
│ def create_bland_ai_batch_call(campaign_id, member_service,      │
│                                  bland_service):                 │
│     # Main orchestration function                                │
│     qualified_members = member_service.get_qualified_members()   │
│     batch_id = bland_service.create_outreach_batch()             │
│     bland_service.create_outreach_attempts()                     │
│     payload = bland_service.build_bland_payload()                │
│     response = bland_service.call_bland_ai_api(payload)          │
│     bland_service.update_batch_with_vendor_id()                  │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 3: Get Qualified Members                                    │
│ File: af_code/af_dtc_intro_call/services/member_service.py       │
│                                                                   │
│ Query Database:                                                  │
│   SELECT members                                                 │
│   FROM engage360.member_campaign_enrollments_enhanced            │
│   WHERE campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'     │
│     AND current_status = 'ENROLLED'                              │
│     AND current_day IN call_days_of_week                         │
│     AND current_time IN member.preferred_window                  │
│     AND NOT attempted_today                                      │
│     AND frequency_rules_met                                      │
│   LIMIT 1000                                                     │
│                                                                   │
│ Returns: List of qualified members (0-1000)                      │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 4: Create Database Records                                  │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│                                                                   │
│ 4a. Create Batch Record:                                         │
│     INSERT INTO engage360.outreach_batches                       │
│     (batch_id, campaign_id, total_calls_intended, batch_status)  │
│     VALUES (UUID(), campaign_id, 150, 'Pending')                 │
│                                                                   │
│     Returns: batch_id = "550e8400-e29b-41d4-a716-446655440000"   │
│                                                                   │
│ 4b. Create Attempt Records (for each member):                    │
│     INSERT INTO engage360.outreach_attempts                      │
│     (attempt_id, enrollment_id, batch_id, disposition)           │
│     VALUES (UUID(), enrollment_id, batch_id, 'Pending')          │
│                                                                   │
│     Creates 150 records (one per member)                         │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 5: Get Campaign Configuration                               │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│                                                                   │
│ Query:                                                           │
│   SELECT bland_parameters_global                                 │
│   FROM engage360.campaign_call_configs_enhanced                  │
│   WHERE campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'     │
│     AND config_status = 'active'                                 │
│                                                                   │
│ Returns JSON config:                                             │
│ {                                                                │
│     "pathway_id": "pathway-dtc-intro-v1",                        │
│     "voice": "maya",                                             │
│     "model": "enhanced",                                         │
│     "webhook": "https://ioe-function-xxx.azurewebsites.net/api/  │
│                  bland_ai_webhook",                              │
│     "max_duration": 600,                                         │
│     "temperature": 0.7                                           │
│ }                                                                │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 6: Build Bland AI Payload                                   │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│ Function: build_bland_payload()                                  │
│                                                                   │
│ Payload Structure:                                               │
│ {                                                                │
│     "global": {                                                  │
│         "pathway_id": "pathway-dtc-intro-v1",                    │
│         "voice": "maya",                                         │
│         "model": "enhanced",                                     │
│         "webhook": "https://...com/api/bland_ai_webhook",        │
│         "max_duration": 600,                                     │
│         "temperature": 0.7,                                      │
│         "from": "+19876543210"  // Caller ID                     │
│     },                                                           │
│     "call_objects": [                                            │
│         {                                                        │
│             "phone_number": "+12125551234",                      │
│             "request_data": {                                    │
│                 "first_name": "John",                            │
│                 "last_name": "Doe",                              │
│                 "language_pref": "English",                      │
│                 "call_type_code": "not_completed"                │
│             },                                                   │
│             "metadata": {                                        │
│                 "batch_id": "550e8400-...",                      │
│                 "campaign_id": "34CC9155-...",                   │
│                 "attempt_id": "660e8400-...",                    │
│                 "member_id": "770e8400-..."                      │
│             }                                                    │
│         },                                                       │
│         ... 149 more call objects ...                            │
│     ]                                                            │
│ }                                                                │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 7: Get Bland AI API Key                                     │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│                                                                   │
│ Connect to Azure Key Vault:                                      │
│   URL: https://kv-careflow190379178112.vault.azure.net/          │
│   Secret Name: "BlandAIkey"                                      │
│   Secret Name: "Blandaitwilio" (encrypted Twilio key)            │
│                                                                   │
│ Returns:                                                         │
│   api_key = "sk-bland-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"          │
│   encrypted_key = "enc-twilio-xxxxxxxxxxxxxxxxx"                 │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 8: SUBMIT TO BLAND AI (SYNCHRONOUS)                         │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│ Function: call_bland_ai_api()                                    │
│                                                                   │
│ HTTP Request:                                                    │
│   POST https://api.bland.ai/v1/batches                           │
│   Headers:                                                       │
│     Authorization: Bearer sk-bland-xxxxxxxxxxxx                  │
│     Content-Type: application/json                               │
│     encrypted_key: enc-twilio-xxxxxxxxx                          │
│   Body: <payload from Step 6>                                    │
│   Timeout: 30 seconds                                            │
│                                                                   │
│ ⏳ WAIT FOR RESPONSE (BLOCKING)                                  │
│                                                                   │
│ Response from Bland AI:                                          │
│ {                                                                │
│     "status": "success",                                         │
│     "data": {                                                    │
│         "batch_id": "bland_batch_abc123xyz789",                  │
│         "calls_queued": 150,                                     │
│         "estimated_completion": "2025-10-17T14:30:00Z"           │
│     }                                                            │
│ }                                                                │
│                                                                   │
│ ✅ Batch Accepted by Bland AI!                                   │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 9: Update Database with Vendor Batch ID                     │
│ File: af_code/af_dtc_intro_call/services/blandai_service.py      │
│                                                                   │
│ UPDATE engage360.outreach_batches                                │
│ SET vendor_batch_id = 'bland_batch_abc123xyz789',                │
│     batch_status = 'Submitted',                                  │
│     submitted_ts = SYSDATETIMEOFFSET()                           │
│ WHERE batch_id = '550e8400-e29b-41d4-a716-446655440000'          │
│                                                                   │
│ Now we can track this batch using Bland's batch_id!              │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 10: Azure Function Completes                                │
│                                                                   │
│ Return result:                                                   │
│ {                                                                │
│     "success": true,                                             │
│     "message": "Batch submitted successfully.",                  │
│     "batch_id": "550e8400-e29b-41d4-a716-446655440000",          │
│     "vendor_batch_id": "bland_batch_abc123xyz789",               │
│     "processed_count": 150,                                      │
│     "qualified_count": 150                                       │
│ }                                                                │
│                                                                   │
│ ✅ Azure Function Execution Ends                                 │
│    Total Time: ~5-10 seconds                                     │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ 🚀 Function is done, but calls haven't started yet!
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 11: Bland AI Processes Batch (ASYNCHRONOUS)                 │
│ This happens AFTER Azure Function has finished                   │
│                                                                   │
│ Bland AI Backend:                                                │
│   - Receives batch_id: bland_batch_abc123xyz789                  │
│   - Validates all 150 phone numbers                              │
│   - Queues calls in their system                                 │
│   - Starts making calls (within 1-5 minutes)                     │
│                                                                   │
│ For each call (150 times):                                       │
│   1. Dial phone number                                           │
│   2. Wait for answer/voicemail/no-answer                         │
│   3. If answered:                                                │
│      - Run AI pathway conversation                               │
│      - Record conversation                                       │
│      - Capture pathway outcomes                                  │
│   4. Send webhook to our endpoint                                │
│                                                                   │
│ Timeline: 30 minutes - 2 hours for all 150 calls                 │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 12: Webhooks Received (ASYNCHRONOUS)                        │
│ File: functions/bland_ai_webhook.py                              │
│ Endpoint: POST /api/bland_ai_webhook                             │
│                                                                   │
│ For each completed call, Bland AI sends:                         │
│ {                                                                │
│     "batch_id": "bland_batch_abc123xyz789",                      │
│     "call_id": "call_xyz123",                                    │
│     "to": "+12125551234",                                        │
│     "status": "completed",                                       │
│     "answered": true,                                            │
│     "duration": 180,                                             │
│     "metadata": {                                                │
│         "attempt_id": "660e8400-...",                            │
│         "member_id": "770e8400-..."                              │
│     },                                                           │
│     "pathway_logs": [...]                                        │
│ }                                                                │
│                                                                   │
│ Webhook Handler:                                                 │
│   1. Parse webhook payload                                       │
│   2. Extract attempt_id from metadata                            │
│   3. Determine disposition (Completed, No Answer, Failed)        │
│   4. Update database:                                            │
│      UPDATE engage360.outreach_attempts                          │
│      SET disposition = 'Completed',                              │
│          vendor_session_id = 'call_xyz123',                      │
│          call_duration = 180,                                    │
│          pathway_data = {...}                                    │
│      WHERE attempt_id = '660e8400-...'                           │
│                                                                   │
│ This runs 150 times (once per call)                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Complete Wellness Check Flow (DTC WELLNESS CHECK)

### Wellness Check SQL Eligibility Query

**File:** `af_code/af_dtc_intro_call/utils/config.py:142-200`

```sql
DECLARE @CurrentUtcTimestamp DATETIMEOFFSET = SYSDATETIMEOFFSET();
DECLARE @TodayStartUtc DATETIMEOFFSET = CAST(CAST(@CurrentUtcTimestamp AS DATE) AS DATETIMEOFFSET);
DECLARE @TodayEndUtc DATETIMEOFFSET = DATEADD(DAY, 1, @TodayStartUtc);

SELECT
    m.member_id,
    m.primary_phone,           -- ⚠️ PRIMARY PHONE (member's personal phone)
    m.timezone,
    mce.enrollment_id,
    mce.preferred_window,
    c.name as campaign_name,
    c.campaign_id,
    c.call_days_of_week,
    ISNULL(failed_attempts.failed_count, 0) as todays_failed_attempts
FROM
    engage360.members AS m
JOIN
    engage360.member_campaign_enrollments_enhanced AS mce
    ON m.member_id = mce.member_id
JOIN
    engage360.campaigns_enhanced AS c
    ON mce.campaign_id = c.campaign_id
LEFT JOIN (
    -- Count today's failed attempts
    SELECT
        oa.enrollment_id,
        COUNT(*) as failed_count
    FROM engage360.outreach_attempts oa
    WHERE oa.attempt_ts >= @TodayStartUtc
      AND oa.attempt_ts < @TodayEndUtc
      AND oa.disposition != 'Completed'
    GROUP BY oa.enrollment_id
) failed_attempts ON mce.enrollment_id = failed_attempts.enrollment_id
WHERE
    -- ✅ CHECK 1: Campaign is Active
    c.status = 'Active'

    -- ✅ CHECK 2: Member is ENROLLED in wellness campaign
    AND mce.current_status = 'ENROLLED'

    -- ✅ CHECK 3: Member has timezone
    AND m.timezone IS NOT NULL

    -- ✅ CHECK 4: Member has preferred window
    AND mce.preferred_window IS NOT NULL

    -- ✅ CHECK 5: Correct campaign
    AND c.campaign_id = %s  -- E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B

    -- ✅ CHECK 6: CRITICAL - Intro campaign must be UNENROLLED (intro call completed)
    AND EXISTS (
        SELECT 1
        FROM engage360.member_campaign_enrollments_enhanced intro_mce
        WHERE intro_mce.member_id = m.member_id
          AND intro_mce.campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'  -- DTC Intro
          AND intro_mce.current_status = 'UNENROLLED'
    )

    -- ✅ CHECK 7: No DTC attempts today (intro OR wellness)
    AND NOT EXISTS (
        SELECT 1
        FROM engage360.outreach_attempts oa
        JOIN engage360.member_campaign_enrollments_enhanced other_mce
            ON oa.enrollment_id = other_mce.enrollment_id
        WHERE other_mce.member_id = m.member_id
          AND other_mce.campaign_id IN (
              '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro Campaign
              'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness Campaign
          )
          AND oa.attempt_ts >= @TodayStartUtc
          AND oa.attempt_ts < @TodayEndUtc
    );
```

### Wellness Check Python Time Filtering

**File:** `af_code/af_dtc_intro_call/services/member_service.py:139-193`

After the SQL query returns potential members, Python performs additional filtering:

#### Time Window Check
```python
def _is_member_eligible_now(self, member_data: Dict, current_utc: datetime) -> Tuple[bool, str]:
    # 1. Timezone Validation
    iana_timezone = member_data.get("timezone")  # e.g., "America/New_York"
    member_tz = pytz.timezone(iana_timezone)
    member_local_time = current_utc.replace(tzinfo=pytz.UTC).astimezone(member_tz)

    # 2. Call Days of Week Check
    call_days_of_week = member_data.get("call_days_of_week")  # "Monday,Tuesday,Wednesday,Thursday,Friday"
    current_day_name = member_local_time.strftime("%A")  # "Wednesday"
    if current_day_name not in call_days_of_week:
        return False, f"Today ({current_day_name}) not in call_days_of_week"

    # 3. Time Window Check
    preferred_window = member_data.get("preferred_window")  # "Morning"
    start_time, end_time = TimeWindowHelper.get_time_window_bounds(preferred_window)
    # Morning = 08:00:00 to 12:00:00

    current_time = member_local_time.time()  # 10:35:00
    if not (start_time <= current_time <= end_time):
        return False, f"Current time ({current_time}) outside window"

    return True, f"Eligible - Day: {current_day_name}, Time: {current_time}"
```

### Wellness Check Step-by-Step Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Wellness Timer Trigger (Every 10 minutes)                │
│ File: functions/dtc_wellness_check_scheduler.py                  │
│                                                                   │
│ @dtc_wellness_check_bp.timer_trigger(                            │
│     schedule="0 */10 * * * *",  # Every 10 minutes               │
│     run_on_startup=False                                         │
│ )                                                                │
│ def timer_dtc_wellness_check(timer):                             │
│     campaign_id = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"         │
│     bland_service = BlandAIServiceWellness(db_service)           │
│     create_bland_ai_batch_call(campaign_id, ...)                 │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2: Execute Main Logic (SHARED WITH INTRO)                   │
│ File: af_code/af_dtc_intro_call/main_logic.py                    │
│                                                                   │
│ WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"    │
│ is_wellness_campaign = campaign_id == WELLNESS_CAMPAIGN_ID       │
│                                                                   │
│ if is_wellness_campaign:                                         │
│     logging.info("🩺 Starting DTC Wellness Check qualification") │
│                                                                   │
│ qualified_members = member_service.get_qualified_members()       │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 3: Get Qualified Members (WELLNESS-SPECIFIC QUERY)          │
│ File: af_code/af_dtc_intro_call/services/member_service.py       │
│                                                                   │
│ if is_wellness_campaign:                                         │
│     query_to_use = ELIGIBLE_MEMBERS_QUERY_WELLNESS               │
│ else:                                                            │
│     query_to_use = ELIGIBLE_MEMBERS_QUERY_INTRO                  │
│                                                                   │
│ potential_members = db_service.execute_query(query_to_use)       │
│                                                                   │
│ CRITICAL WELLNESS REQUIREMENTS:                                  │
│   ✅ Member enrolled in wellness campaign (ENROLLED)             │
│   ✅ Intro campaign must be UNENROLLED (intro completed)         │
│   ✅ No DTC attempts today (intro OR wellness)                   │
│   ✅ Has timezone and preferred_window                           │
│   ✅ Campaign is Active                                          │
│                                                                   │
│ Log Output:                                                      │
│ 🩺 [MemberQualificationService-DEBUG] Database query returned    │
│    1 potential members                                           │
│ 🩺 [MemberQualificationService-DEBUG] Member ID: 0FFD2F68...     │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 4: Python Time Window Filtering                             │
│ File: member_service.py:87-193                                   │
│                                                                   │
│ For each potential member:                                       │
│   1. Convert current UTC to member's local timezone              │
│      UTC: 2025-10-29 14:35:00                                    │
│      Member TZ: America/New_York                                 │
│      Member Local: 2025-10-29 10:35:00 EDT                       │
│                                                                   │
│   2. Check call_days_of_week:                                    │
│      Current Day: Wednesday                                      │
│      Allowed: Monday,Tuesday,Wednesday,Thursday,Friday           │
│      ✅ PASS                                                     │
│                                                                   │
│   3. Check time window:                                          │
│      preferred_window: "Morning"                                 │
│      Window: 08:00:00 - 12:00:00                                 │
│      Current Time: 10:35:00                                      │
│      ✅ PASS - 10:35 is between 08:00 and 12:00                 │
│                                                                   │
│ Log Output:                                                      │
│ ✅ Member 0FFD2F68... is eligible: Day: Wednesday,               │
│    Time: 10:35:00 in window 08:00:00-12:00:00                    │
│ 🩺 [MemberQualificationService-DEBUG] ✅ WELLNESS member         │
│    QUALIFIED!                                                    │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 5: Create Batch Record                                      │
│ File: af_dtc_wellness_check/services/blandai_service_wellness.py │
│                                                                   │
│ batch_id = str(uuid.uuid4())                                     │
│ # e.g., "a1b2c3d4-e5f6-7890-abcd-ef1234567890"                   │
│                                                                   │
│ INSERT INTO engage360.outreach_batches                           │
│ (batch_id, campaign_id, batch_status, total_calls_intended)      │
│ VALUES (batch_id, 'E5ABE3F0...', 'Pending', 1)                   │
│                                                                   │
│ Log Output:                                                      │
│ 📦 [BlandAIServiceWellness] Creating outreach batch:             │
│    a1b2c3d4-e5f6-7890-abcd-ef1234567890                          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 6: Create Attempt Records                                   │
│                                                                   │
│ For each qualified member:                                       │
│   attempt_id = str(uuid.uuid4())                                 │
│                                                                   │
│   INSERT INTO engage360.outreach_attempts                        │
│   (attempt_id, enrollment_id, batch_id, channel, disposition)    │
│   VALUES (attempt_id, 'E67A94B5...', batch_id, 'Voice',          │
│           'Pending')                                             │
│                                                                   │
│ Log Output:                                                      │
│ 📝 [BlandAIServiceWellness] Creating 1 outreach attempts         │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 7: Build Wellness Payload                                   │
│ File: blandai_service_wellness.py:123-206                        │
│                                                                   │
│ WELLNESS-SPECIFIC PAYLOAD DETAILS:                               │
│                                                                   │
│ {                                                                │
│     "global": {                                                  │
│         "pathway_id": "pathway-wellness-v1",                     │
│         "voice": "maya",                                         │
│         "webhook": "https://.../api/bland_ai_webhook",           │
│         "from": "+19378882446"                                   │
│     },                                                           │
│     "call_objects": [                                            │
│         {                                                        │
│             "phone_number": "+13334445555",  ⚠️ primary_phone    │
│             "request_data": {                                    │
│                 "call_type_code": "completed",  ⚠️ WELLNESS      │
│                 "first_name": "Ali",                             │
│                 "last_name": "Hamza",                            │
│                 "primary_phone": "+13334445555",                 │
│                 "language_pref": "English"                       │
│             },                                                   │
│             "metadata": {                                        │
│                 "batch_id": "a1b2c3d4...",                       │
│                 "campaign_id": "E5ABE3F0...",                    │
│                 "attempt_id": "b2c3d4e5...",                     │
│                 "member_id": "0FFD2F68...",                      │
│                 "call_type_code": "wellness_check"               │
│             }                                                    │
│         }                                                        │
│     ]                                                            │
│ }                                                                │
│                                                                   │
│ Log Output:                                                      │
│ 🏗️ [BlandAIServiceWellness] Building Wellness Check payload     │
│    for 1 members                                                 │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 8: Submit to Bland AI                                       │
│                                                                   │
│ POST https://api.bland.ai/v2/batches/create                      │
│ Headers:                                                         │
│   Authorization: Bearer sk-bland-xxxx                            │
│   encrypted_key: enc-twilio-xxxx                                 │
│                                                                   │
│ Response:                                                        │
│ {                                                                │
│     "status": "success",                                         │
│     "data": {                                                    │
│         "batch_id": "bland-batch-xyz789",                        │
│         "calls_queued": 1                                        │
│     }                                                            │
│ }                                                                │
│                                                                   │
│ Log Output:                                                      │
│ 🚀 [BlandAIServiceWellness] Making Bland AI API call with        │
│    1 calls                                                       │
│ ✅ [BlandAIServiceWellness] API call successful                  │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 9: Update Database with Vendor Batch ID                     │
│                                                                   │
│ UPDATE engage360.outreach_batches                                │
│ SET vendor_batch_id = 'bland-batch-xyz789',                      │
│     batch_status = 'Submitted'                                   │
│ WHERE batch_id = 'a1b2c3d4...'                                   │
│                                                                   │
│ Log Output:                                                      │
│ 🔄 [BlandAIServiceWellness] Updating batch with vendor ID        │
│ ✅ [BlandAIServiceWellness] Batch updated successfully           │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ STEP 10: Wellness Check Complete                                 │
│                                                                   │
│ Return result:                                                   │
│ {                                                                │
│     "success": true,                                             │
│     "message": "Batch submitted successfully.",                  │
│     "batch_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",          │
│     "vendor_batch_id": "bland-batch-xyz789",                     │
│     "processed_count": 1,                                        │
│     "qualified_count": 1                                         │
│ }                                                                │
│                                                                   │
│ Log Output:                                                      │
│ 🎉 [MAIN] Success: Batch submitted                               │
│ 🩺 [TIMER] DTC Wellness Check Scheduler COMPLETED                │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ 🚀 Bland AI now makes actual phone calls
                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ Bland AI calls member's primary_phone: +13334445555              │
│ Runs wellness check conversation pathway                         │
│ Sends webhook when call completes                                │
└──────────────────────────────────────────────────────────────────┘
```

### Key Wellness Check Differences

| Feature | Value | Notes |
|---------|-------|-------|
| **Phone Number** | `primary_phone` | Member's personal phone (NOT device_phone) |
| **call_type_code** | `"completed"` | Indicates intro call was completed |
| **Critical Prerequisite** | Intro campaign `UNENROLLED` | Member must have completed intro call first |
| **No DTC Attempts Today** | Blocks both intro AND wellness | Can only have 1 DTC call per day total |
| **Service Class** | `BlandAIServiceWellness` | Wellness-specific Bland AI service |
| **Timer Schedule** | Every 10 minutes | Same as intro call |
| **Batch Limit** | 1000 members | Same as intro call |

### Wellness Check Logging Examples

**Success Case:**
```
🩺 [TIMER] DTC Wellness Check Scheduler TRIGGERED
🩺 [MAIN-DEBUG] Starting DTC Wellness Check qualification
🩺 [MemberQualificationService-DEBUG] WELLNESS CAMPAIGN detected
🩺 [MemberQualificationService-DEBUG] Database query returned 1 potential members
🩺 [MemberQualificationService-DEBUG] Member ID: 0FFD2F68-DD56-4F3D-8CA3-BBA05D21BAD9
✅ [MemberQualificationService] Member 0FFD2F68... is eligible: Day: Wednesday, Time: 10:35:00 in window 08:00:00-12:00:00
🩺 [MemberQualificationService-DEBUG] ✅ WELLNESS member QUALIFIED!
📦 [BlandAIServiceWellness] Creating outreach batch
✅ [BlandAIServiceWellness] Outreach batch created
📝 [BlandAIServiceWellness] Creating 1 outreach attempts
✅ [BlandAIServiceWellness] Created 1 outreach attempts
🏗️ [BlandAIServiceWellness] Building Wellness Check payload for 1 members
✅ [BlandAIServiceWellness] Wellness payload built: 1 call objects
🚀 [BlandAIServiceWellness] Making Bland AI API call with 1 calls
✅ [BlandAIServiceWellness] API call successful
🔄 [BlandAIServiceWellness] Updating batch with vendor ID: bland-batch-xyz789
✅ [BlandAIServiceWellness] Batch updated successfully
🎉 [MAIN] Success: Batch submitted successfully
🩺 [TIMER] DTC Wellness Check Scheduler COMPLETED
```

**Failure Case - Outside Time Window:**
```
🩺 [TIMER] DTC Wellness Check Scheduler TRIGGERED
🩺 [MAIN-DEBUG] Starting DTC Wellness Check qualification
🩺 [MemberQualificationService-DEBUG] Database query returned 1 potential members
❌ [MemberQualificationService] Member 0FFD2F68... is not eligible: Current time (14:35:00) outside window (08:00:00-12:00:00)
🩺 [MemberQualificationService-DEBUG] ❌ WELLNESS member NOT qualified: Current time outside window
🩺 [MemberQualificationService-DEBUG] Qualified members: 0
⚠️ [MAIN] No members qualified at the current time.
```

**Failure Case - Intro Campaign Not UNENROLLED:**
```
🩺 [TIMER] DTC Wellness Check Scheduler TRIGGERED
🩺 [MAIN-DEBUG] Starting DTC Wellness Check qualification
🩺 [MemberQualificationService-DEBUG] Database query returned 0 potential members
⚠️ [MemberQualificationService] No potential members found
🩺 [MemberQualificationService-DEBUG] WELLNESS CAMPAIGN - No potential members from database!
🩺 [MemberQualificationService-DEBUG] Possible reasons:
🩺 [MemberQualificationService-DEBUG] 1. No members enrolled in wellness campaign
🩺 [MemberQualificationService-DEBUG] 2. Intro campaign not UNENROLLED
⚠️ [MAIN] No members qualified at the current time.
```

---

## Key Files Involved

### DTC Intro Call Files

#### 1. Timer Trigger (Intro)
**File:** `functions/dtc_intro_call_scheduler.py`
- **Purpose:** Runs every 10 minutes for intro calls
- **Schedule:** `0 */10 * * * *` (at :00, :10, :20, :30, :40, :50 of each hour)
- **Campaign ID:** `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC`

#### 2. Main Logic (Shared)
**File:** `af_code/af_dtc_intro_call/main_logic.py`
- **Function:** `create_bland_ai_batch_call()`
- **Purpose:** Orchestrates the entire batch creation flow
- **Used By:** BOTH intro and wellness campaigns

#### 3. Member Qualification (Shared)
**File:** `af_code/af_dtc_intro_call/services/member_service.py`
- **Function:** `get_qualified_members()`
- **Purpose:** Query database for eligible members
- **Queries:** `ELIGIBLE_MEMBERS_QUERY_INTRO` or `ELIGIBLE_MEMBERS_QUERY_WELLNESS`
- **Used By:** BOTH intro and wellness campaigns

#### 4. Bland AI Service (Intro)
**File:** `af_code/af_dtc_intro_call/services/blandai_service.py`
- **Functions:**
  - `create_outreach_batch()` - Create batch record
  - `create_outreach_attempts()` - Create attempt records
  - `build_bland_payload()` - Build API payload
  - `call_bland_ai_api()` - **MAKES THE ACTUAL API CALL**
  - `update_batch_with_vendor_id()` - Update database
- **Used By:** Intro campaign only

#### 5. Configuration (Shared)
**File:** `af_code/af_dtc_intro_call/utils/config.py`
- **Contains:**
  - `ELIGIBLE_MEMBERS_QUERY_INTRO` - SQL query for intro calls
  - `ELIGIBLE_MEMBERS_QUERY_WELLNESS` - SQL query for wellness calls
  - Database query constants
  - API endpoint configurations

### DTC Wellness Check Files

#### 6. Timer Trigger (Wellness)
**File:** `functions/dtc_wellness_check_scheduler.py`
- **Purpose:** Runs every 10 minutes for wellness calls
- **Schedule:** `0 */10 * * * *` (same as intro)
- **Campaign ID:** `E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B`

#### 7. Bland AI Service (Wellness)
**File:** `af_code/af_dtc_wellness_check/services/blandai_service_wellness.py`
- **Functions:**
  - `create_outreach_batch()` - Create batch record
  - `create_outreach_attempts()` - Create attempt records
  - `build_bland_payload()` - Build wellness-specific payload
  - `call_bland_ai_api()` - **MAKES THE ACTUAL API CALL**
  - `update_batch_with_vendor_id()` - Update database
- **Used By:** Wellness campaign only
- **Differences from Intro Service:**
  - Sets `call_type_code = "completed"`
  - Uses different pathway configuration

### Shared Files (Used by BOTH)

#### 8. Webhook Handler
**File:** `functions/bland_ai_webhook.py`
- **Endpoint:** `POST /api/bland_ai_webhook`
- **Purpose:** Receive call completion notifications from Bland AI
- **Used By:** ALL campaigns (intro, wellness, partner)

---

## Where Calls Are Actually Made

### Answer: Calls are made by **Bland AI**, NOT by our Azure Function!

```
Our Azure Function:
  ✅ Finds qualified members
  ✅ Creates database records
  ✅ Builds payload
  ✅ Submits to Bland AI API
  ❌ Does NOT make phone calls

Bland AI (External Service):
  ✅ Receives our batch request
  ✅ Queues calls
  ✅ Makes actual phone calls
  ✅ Runs AI conversation
  ✅ Sends webhooks when done
```

---

## Timeline Breakdown

```
00:00 - Timer triggers (every 10 minutes)
00:01 - Query qualified members
00:02 - Create batch & attempt records
00:03 - Build payload
00:04 - Submit to Bland AI API (SYNC - wait for response)
00:05 - Update database with vendor_batch_id
00:06 - Azure Function completes ✅

--- ASYNC BOUNDARY ---

00:07 - Bland AI validates batch
00:10 - First call starts
00:13 - First call completes → Webhook received
00:15 - More calls completing → More webhooks
...
02:00 - All 150 calls complete
02:00 - Final webhooks received
```

---

## Configuration

### Campaign IDs

**DTC Intro Call:**
```python
campaign_id = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
```

**DTC Wellness Check:**
```python
campaign_id = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
```

### Timer Schedule (Both Campaigns)
```python
schedule="0 */10 * * * *"  # Every 10 minutes
```
- Runs at: :00, :10, :20, :30, :40, :50 of every hour
- 6 times per hour
- 144 times per day
- **NOTE:** Both timers run on the same schedule but independently

### Batch Limits (Both Campaigns)
```python
MEMBER_LIMIT = 1000  # Max members per batch
```

### API Endpoints

**Bland AI Batch Submit:**
```
POST https://api.bland.ai/v2/batches/create
```

**Webhook Callback:**
```
POST https://ioe-function-xxx.azurewebsites.net/api/bland_ai_webhook
```

### Phone Numbers Used

**DTC Intro Call:**
- Uses: `primary_phone` (member's personal phone)
- Example: `+13334445555`

**DTC Wellness Check:**
- Uses: `primary_phone` (member's personal phone)
- Example: `+13334445555`

**NOTE:** Both campaigns call the member's personal phone, NOT the device phone.

---

## Summary

### General Flow (Both Campaigns)

1. **Timer triggers every 10 minutes**
   - Intro: `functions/dtc_intro_call_scheduler.py`
   - Wellness: `functions/dtc_wellness_check_scheduler.py`
2. **Main logic executes** (`af_code/af_dtc_intro_call/main_logic.py`)
3. **Get qualified members** from database (up to 1000)
   - Intro: Uses `ELIGIBLE_MEMBERS_QUERY_INTRO`
   - Wellness: Uses `ELIGIBLE_MEMBERS_QUERY_WELLNESS`
4. **Create batch and attempt records** in database
5. **Build Bland AI payload** with member data
   - Intro: `BlandAIService.build_bland_payload()`
   - Wellness: `BlandAIServiceWellness.build_bland_payload()`
6. **Submit to Bland AI API** (SYNCHRONOUS - wait for confirmation)
7. **Update database** with vendor_batch_id
8. **Azure Function completes** (~5-10 seconds total)
9. **Bland AI makes calls** (ASYNCHRONOUS - 30 min to 2 hours)
10. **Webhooks received** as each call completes
11. **Database updated** with call outcomes

**The actual phone calls are made by Bland AI's infrastructure, not by our Azure Functions!**

### Key Differences Between Campaigns

| Step | Intro Call | Wellness Check |
|------|------------|----------------|
| **Eligibility** | `current_status = 'ENROLLED'` | `current_status = 'ENROLLED'` AND intro `UNENROLLED` |
| **Phone** | `primary_phone` | `primary_phone` |
| **call_type_code** | `"not_completed"` | `"completed"` |
| **Service** | `BlandAIService` | `BlandAIServiceWellness` |
| **Prerequisites** | None | Must complete intro call first |
| **Daily Limit** | 1 DTC call per day (intro OR wellness) | 1 DTC call per day (intro OR wellness) |

### Important Notes

1. **Cross-Campaign Cooldown**: Members can only receive ONE DTC call per day total (intro OR wellness, not both)
2. **Wellness Prerequisite**: Wellness calls require intro campaign status = `UNENROLLED`
3. **Same Phone Number**: Both campaigns call `primary_phone` (not device_phone)
4. **Independent Timers**: Both timers run every 10 minutes but create separate batches
5. **Shared Logic**: Both use the same main orchestration logic and member qualification service

---

**Document Version**: 2.0
**Last Updated**: 2025-10-29
**Campaigns Covered:**
- **DTC Intro Call**: `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC`
- **DTC Wellness Check**: `E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B`
**Schedule**: Every 10 minutes (both campaigns)
