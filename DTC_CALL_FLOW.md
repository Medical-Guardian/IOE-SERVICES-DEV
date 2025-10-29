# DTC (Direct-to-Consumer) Call Flow - Complete Guide

## How DTC Makes Calls via Bland AI

This document traces the **complete journey** from timer trigger to actual phone calls being made.

---

## Overview

DTC intro calls are made through a **timer-triggered Azure Function** that runs **every 10 minutes**:

```
Timer (Every 10 min) → Get Qualified Members → Create Batch → Submit to Bland AI → Bland Makes Calls
```

**Key Point:** The Azure Function only **submits** the batch to Bland AI. The actual phone calls are made by **Bland AI** asynchronously after submission.

---

## Complete Call Flow Diagram

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

## Key Files Involved

### 1. Timer Trigger
**File:** `functions/dtc_intro_call_scheduler.py`
- **Purpose:** Runs every 10 minutes
- **Schedule:** `0 */10 * * * *` (at :00, :10, :20, :30, :40, :50 of each hour)
- **Campaign ID:** `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC`

### 2. Main Logic
**File:** `af_code/af_dtc_intro_call/main_logic.py`
- **Function:** `create_bland_ai_batch_call()`
- **Purpose:** Orchestrates the entire batch creation flow

### 3. Member Qualification
**File:** `af_code/af_dtc_intro_call/services/member_service.py`
- **Function:** `get_qualified_members()`
- **Purpose:** Query database for eligible members

### 4. Bland AI Service
**File:** `af_code/af_dtc_intro_call/services/blandai_service.py`
- **Functions:**
  - `create_outreach_batch()` - Create batch record
  - `create_outreach_attempts()` - Create attempt records
  - `build_bland_payload()` - Build API payload
  - `call_bland_ai_api()` - **MAKES THE ACTUAL API CALL**
  - `update_batch_with_vendor_id()` - Update database

### 5. Webhook Handler
**File:** `functions/bland_ai_webhook.py`
- **Endpoint:** `POST /api/bland_ai_webhook`
- **Purpose:** Receive call completion notifications from Bland AI

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

### Campaign ID
```python
campaign_id = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"
```

### Timer Schedule
```python
schedule="0 */10 * * * *"  # Every 10 minutes
```
- Runs at: :00, :10, :20, :30, :40, :50 of every hour
- 6 times per hour
- 144 times per day

### Batch Limits
```python
MEMBER_LIMIT = 1000  # Max members per batch
```

### API Endpoints

**Bland AI Batch Submit:**
```
POST https://api.bland.ai/v1/batches
```

**Webhook Callback:**
```
POST https://ioe-function-xxx.azurewebsites.net/api/bland_ai_webhook
```

---

## Summary

1. **Timer triggers every 10 minutes** (`functions/dtc_intro_call_scheduler.py`)
2. **Main logic executes** (`af_code/af_dtc_intro_call/main_logic.py`)
3. **Get qualified members** from database (up to 1000)
4. **Create batch and attempt records** in database
5. **Build Bland AI payload** with member data
6. **Submit to Bland AI API** (SYNCHRONOUS - wait for confirmation)
7. **Update database** with vendor_batch_id
8. **Azure Function completes** (~5-10 seconds total)
9. **Bland AI makes calls** (ASYNCHRONOUS - 30 min to 2 hours)
10. **Webhooks received** as each call completes
11. **Database updated** with call outcomes

**The actual phone calls are made by Bland AI's infrastructure, not by our Azure Functions!**

---

**Document Version**: 1.0
**Last Updated**: 2025-10-17
**Campaign ID**: 34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC
**Schedule**: Every 10 minutes
