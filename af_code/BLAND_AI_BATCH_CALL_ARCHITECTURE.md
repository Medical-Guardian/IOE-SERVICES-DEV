# Bland AI Batch Call Architecture

## Table of Contents
1. [Overview](#overview)
2. [Synchronous vs Asynchronous Flow](#synchronous-vs-asynchronous-flow)
3. [Complete Code Flow](#complete-code-flow)
4. [Batch Submission (Sync)](#batch-submission-sync)
5. [Batch Processing (Async)](#batch-processing-async)
6. [Webhook Callbacks (Async)](#webhook-callbacks-async)
7. [Batch Reconciliation (Scheduled)](#batch-reconciliation-scheduled)
8. [Code Examples](#code-examples)
9. [Data Flow Diagram](#data-flow-diagram)

---

## Overview

The Bland AI batch call system uses a **hybrid synchronous/asynchronous architecture**:

- **Synchronous**: Batch submission (we wait for confirmation)
- **Asynchronous**: Call processing (Bland AI handles in background)
- **Asynchronous**: Webhook notifications (Bland AI notifies us when calls complete)
- **Scheduled**: Batch reconciliation (periodic sync to catch missed webhooks)

This design allows us to submit thousands of calls quickly without blocking, while still maintaining visibility into call status.

---

## Synchronous vs Asynchronous Flow

### Synchronous Operations (SYNC)
**We wait for response before proceeding**

```
Azure Function → Bland AI API → Response → Continue
     |                             ↑
     └─────── Wait ──────────────┘
```

**Used for:**
- Submitting batch to Bland AI
- Getting batch_id confirmation
- Initial database records creation

**Characteristics:**
- Blocks until complete
- Immediate response
- Timeout after 30 seconds
- Returns success/failure right away

---

### Asynchronous Operations (ASYNC)
**We don't wait for completion**

```
Azure Function → Bland AI API
     ↓
Continue with other work

     ... hours later ...

Bland AI → Webhook → Azure Function
```

**Used for:**
- Actual phone calls (Bland AI makes calls)
- Call completion notifications (webhooks)
- Status updates (background process)

**Characteristics:**
- Non-blocking
- Fire-and-forget submission
- Callbacks via webhooks
- Can take minutes/hours to complete

---

## Complete Code Flow

### Phase 1: Batch Submission (SYNC)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Timer Trigger (Every 30 mins)                            │
│    File: functions/af_dtc_intro_call.py                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Get Qualified Members                                    │
│    File: af_code/af_dtc_intro_call/services/               │
│          dtc_intro_call_service.py                          │
│                                                             │
│    - Query database for eligible members                    │
│    - Filter by care gaps, attempt history                   │
│    - Limit to 1000 members per batch                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Create Database Records (SYNC)                           │
│    File: af_code/af_dtc_intro_call/services/               │
│          blandai_service.py                                 │
│                                                             │
│    a. Create outreach_batch record                          │
│       INSERT INTO engage360.outreach_batches                │
│       - batch_id (UUID)                                     │
│       - campaign_id                                         │
│       - batch_status = 'Pending'                            │
│       - total_calls_intended = 1000                         │
│                                                             │
│    b. Create outreach_attempts records                      │
│       INSERT INTO engage360.outreach_attempts               │
│       - attempt_id (UUID)                                   │
│       - enrollment_id                                       │
│       - batch_id                                            │
│       - disposition = 'Pending'                             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Build Bland AI Payload (SYNC)                            │
│    File: af_code/af_dtc_intro_call/services/               │
│          blandai_service.py                                 │
│                                                             │
│    Payload Structure:                                       │
│    {                                                        │
│        "global": {                                          │
│            "pathway_id": "...",                             │
│            "voice": "maya",                                 │
│            "webhook": "https://...com/api/bland_ai_webhook" │
│        },                                                   │
│        "call_objects": [                                    │
│            {                                                │
│                "phone_number": "+1234567890",               │
│                "request_data": {...},                       │
│                "metadata": {                                │
│                    "attempt_id": "uuid",                    │
│                    "member_id": "uuid",                     │
│                    "batch_id": "uuid"                       │
│                }                                            │
│            }                                                │
│        ]                                                    │
│    }                                                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Submit to Bland AI API (SYNC - 30sec timeout)            │
│    File: af_code/af_dtc_intro_call/services/               │
│          blandai_service.py                                 │
│                                                             │
│    POST https://api.bland.ai/v1/batches                     │
│    Headers:                                                 │
│      Authorization: Bearer <api_key>                        │
│      encrypted_key: <twilio_encrypted_key>                  │
│    Body: <payload from step 4>                              │
│                                                             │
│    Response:                                                │
│    {                                                        │
│        "status": "success",                                 │
│        "batch_id": "bland_batch_xyz789",                    │
│        "calls_queued": 1000                                 │
│    }                                                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Update Database with Bland Batch ID (SYNC)               │
│    File: af_code/af_dtc_intro_call/services/               │
│          blandai_service.py                                 │
│                                                             │
│    UPDATE engage360.outreach_batches                        │
│    SET vendor_batch_id = 'bland_batch_xyz789',              │
│        batch_status = 'Submitted',                          │
│        submitted_ts = SYSDATETIMEOFFSET()                   │
│    WHERE batch_id = <our_batch_id>                          │
└─────────────────────────────────────────────────────────────┘

SYNCHRONOUS PART COMPLETE
Azure Function execution ends
Total time: ~5-10 seconds
```

---

### Phase 2: Batch Processing (ASYNC - Bland AI Side)

```
┌─────────────────────────────────────────────────────────────┐
│ Bland AI Processes Batch (ASYNC)                            │
│ This happens AFTER Azure Function has finished              │
│                                                             │
│ For each call in batch (1000 calls):                        │
│   1. Validate phone number                                  │
│   2. Queue call                                             │
│   3. Make call using AI agent                               │
│   4. Execute pathway logic                                  │
│   5. Record call result                                     │
│                                                             │
│ Timeline:                                                   │
│   - Calls start within minutes                              │
│   - May take 30 minutes to 2 hours to complete all         │
│   - Depends on: call volume, answering rates, durations     │
└─────────────────────────────────────────────────────────────┘
```

---

### Phase 3: Webhook Callbacks (ASYNC - Real-time Updates)

```
┌─────────────────────────────────────────────────────────────┐
│ Bland AI → Webhook → Azure Function                         │
│ File: functions/bland_ai_webhook.py                         │
│                                                             │
│ Webhook Endpoint:                                           │
│   POST /api/bland_ai_webhook                                │
│                                                             │
│ Webhook Payload (per call):                                 │
│ {                                                           │
│     "batch_id": "bland_batch_xyz789",                       │
│     "call_id": "call_abc123",                               │
│     "metadata": {                                           │
│         "attempt_id": "uuid",                               │
│         "member_id": "uuid",                                │
│         "batch_id": "our_batch_id"                          │
│     },                                                      │
│     "status": "completed",                                  │
│     "answered": true,                                       │
│     "duration": 180,                                        │
│     "pathway_logs": [...],                                  │
│     "error_message": null                                   │
│ }                                                           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Process Webhook (SYNC within webhook handler)               │
│ File: af_code/bland_ai_webhook/services/                    │
│       call_log_parser.py                                    │
│                                                             │
│ 1. Parse webhook payload                                    │
│ 2. Extract metadata (attempt_id, member_id)                 │
│ 3. Determine call disposition:                              │
│    - "Completed" if answered & pathway complete             │
│    - "No Answer" if unanswered                              │
│    - "Failed" if error                                      │
│    - "Voicemail" if VM detected                             │
│ 4. Extract pathway data (appointment booked, etc.)          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Update Database (SYNC within webhook handler)               │
│ File: af_code/bland_ai_webhook/services/                    │
│       database_service.py                                   │
│                                                             │
│ UPDATE engage360.outreach_attempts                          │
│ SET disposition = 'Completed',                              │
│     vendor_session_id = 'call_abc123',                      │
│     call_duration = 180,                                    │
│     pathway_data = {...},                                   │
│     updated_ts = SYSDATETIMEOFFSET()                        │
│ WHERE attempt_id = <from_metadata>                          │
└─────────────────────────────────────────────────────────────┘

This webhook fires for EACH CALL (1000 times)
Typically completes within 2 hours for full batch
```

---

### Phase 4: Batch Reconciliation (SCHEDULED - Safety Net)

```
┌─────────────────────────────────────────────────────────────┐
│ Timer Trigger (Every 30 mins)                               │
│ File: functions/batch_completion_reconciler.py              │
│                                                             │
│ Purpose: Catch any missed webhooks                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Find Stale Batches                                          │
│ File: af_code/shared/batch_sync_coordinator.py              │
│                                                             │
│ SELECT batch_id, vendor_batch_id                            │
│ FROM engage360.outreach_batches                             │
│ WHERE batch_status IN ('Submitted', 'Pending')              │
│   AND (last_status_check_ts IS NULL                         │
│        OR last_status_check_ts < NOW() - 2 hours)           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Call Bland AI Batch Logs API (SYNC)                         │
│ File: af_code/shared/bland_ai_batch_monitor.py              │
│                                                             │
│ GET https://api.bland.ai/v2/batches/{batch_id}/logs         │
│ Headers: Authorization: Bearer <api_key>                    │
│                                                             │
│ Response:                                                   │
│ {                                                           │
│     "data": [                                               │
│         {                                                   │
│             "event_type": "complete",                       │
│             "payload": {                                    │
│                 "calls_successful": 850,                    │
│                 "calls_failed": 150,                        │
│                 "calls_total": 1000                         │
│             }                                               │
│         }                                                   │
│     ]                                                       │
│ }                                                           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Update Batch Completion Status                              │
│                                                             │
│ UPDATE engage360.outreach_batches                           │
│ SET batch_status = 'Completed',                             │
│     total_calls_completed = 850,                            │
│     total_calls_failed = 150,                               │
│     last_status_check_ts = SYSDATETIMEOFFSET()              │
│ WHERE vendor_batch_id = 'bland_batch_xyz789'                │
└─────────────────────────────────────────────────────────────┘

Runs every 30 minutes as safety net
Usually finds batches complete via webhooks already
```

---

## Batch Submission (SYNC)

### Code Location
**File:** `af_code/af_dtc_intro_call/services/blandai_service.py`

### Complete Submission Code

```python
class BlandAIService:
    """Service to handle Bland AI API operations"""

    def submit_batch(self, campaign_id: str, qualified_members: List[Dict]) -> str:
        """
        Complete batch submission workflow (SYNCHRONOUS)

        Steps:
        1. Create batch record in database
        2. Create attempt records for each member
        3. Build Bland AI payload
        4. Submit to Bland AI API (WAIT for response)
        5. Update batch with vendor_batch_id

        Returns:
            vendor_batch_id from Bland AI
        """
        try:
            # Step 1: Create batch in database
            batch_id = self.create_outreach_batch(campaign_id, len(qualified_members))
            logger.info(f"📦 Created batch: {batch_id}")

            # Step 2: Create attempt records
            self.create_outreach_attempts(qualified_members, batch_id)
            logger.info(f"📝 Created {len(qualified_members)} attempt records")

            # Step 3: Get campaign config and members with attempts
            config = self.get_campaign_config(campaign_id)
            members_with_attempts = self.get_members_with_attempts(batch_id)

            # Step 4: Build Bland AI payload
            payload = self.build_bland_payload(config, members_with_attempts, batch_id)
            logger.info(f"🏗️ Built payload with {len(payload['call_objects'])} calls")

            # Step 5: Get API key from Key Vault
            api_key = self.get_bland_api_key()

            # Step 6: SYNCHRONOUS API call (blocks until response)
            logger.info("🚀 Submitting batch to Bland AI...")
            response = self.call_bland_ai_api(payload, api_key)

            # Step 7: Extract vendor_batch_id from response
            vendor_batch_id = response.get('batch_id')
            if not vendor_batch_id:
                raise ValueError("No batch_id in Bland AI response")

            logger.info(f"✅ Bland AI accepted batch: {vendor_batch_id}")

            # Step 8: Update database with vendor_batch_id
            self.update_batch_with_vendor_id(batch_id, vendor_batch_id)

            return vendor_batch_id

        except Exception as e:
            logger.error(f"💥 Batch submission failed: {str(e)}")
            self.update_batch_failed(batch_id, str(e))
            raise

    def call_bland_ai_api(self, payload: Dict, api_key: str) -> Dict:
        """
        Make SYNCHRONOUS API call to Bland AI

        This is a BLOCKING operation - we wait for response
        Timeout: 30 seconds
        """
        # Get encrypted Twilio key
        encrypted_key = self.get_bland_encrypted_key()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "encrypted_key": encrypted_key  # For Twilio integration
        }

        # SYNCHRONOUS POST request (blocks until response or timeout)
        response = requests.post(
            "https://api.bland.ai/v1/batches",
            json=payload,
            headers=headers,
            timeout=30  # Wait max 30 seconds
        )

        # Raise exception if HTTP error (4xx, 5xx)
        response.raise_for_status()

        # Parse JSON response
        result = response.json()

        return result
```

### Payload Structure

```python
def build_bland_payload(self, config: Dict, members: List[Dict], batch_id: str) -> Dict:
    """
    Build Bland AI batch payload

    Structure:
    {
        "global": {  # Applied to all calls in batch
            "pathway_id": "...",  # AI agent conversation flow
            "voice": "maya",  # Voice to use
            "webhook": "https://...com/api/bland_ai_webhook",  # Callback URL
            "model": "enhanced",
            "temperature": 0.7,
            "max_duration": 600  # Max call length in seconds
        },
        "call_objects": [  # Individual calls
            {
                "phone_number": "+1234567890",
                "request_data": {  # Data passed to AI pathway
                    "first_name": "John",
                    "last_name": "Doe",
                    "language_pref": "English"
                },
                "metadata": {  # Data returned in webhook
                    "attempt_id": "uuid",
                    "member_id": "uuid",
                    "batch_id": "uuid"
                }
            }
        ]
    }
    """
    global_config = {
        "pathway_id": config.get("pathway_id"),
        "pathway_version": config.get("pathway_version"),
        "voice": config.get("voice"),
        "webhook": config.get("webhook"),  # CRITICAL: Where to send callbacks
        "model": config.get("model"),
        "max_duration": config.get("max_duration")
    }

    call_objects = []
    for member in members:
        call_obj = {
            "phone_number": member["primary_phone"],
            "request_data": {
                "first_name": member["first_name"],
                "last_name": member["last_name"],
                "language_pref": member["language_pref"]
            },
            "metadata": {
                "attempt_id": str(member["attempt_id"]),
                "member_id": str(member["member_id"]),
                "batch_id": batch_id,
                "campaign_id": str(member["campaign_id"])
            }
        }
        call_objects.append(call_obj)

    return {
        "global": global_config,
        "call_objects": call_objects
    }
```

---

## Batch Processing (ASYNC)

### What Happens at Bland AI

Once we submit the batch (synchronously), Bland AI:

1. **Validates** all phone numbers
2. **Queues** calls for processing
3. **Makes calls** using AI agents (this takes time!)
4. **Records** call outcomes
5. **Sends webhooks** for each call (asynchronously)

**Timeline:**
- First calls start within 1-5 minutes
- Batch of 1000 calls completes in 30 mins - 2 hours
- Depends on: answering rates, call duration, time of day

**We don't wait for this!** Our Azure Function finished in step 6 of Phase 1.

---

## Webhook Callbacks (ASYNC)

### Code Location
**File:** `functions/bland_ai_webhook.py`

### Webhook Handler Code

```python
import azure.functions as func
import logging
import json
from af_code.bland_ai_webhook.services.call_log_parser import CallLogParser
from af_code.bland_ai_webhook.services.database_service import DatabaseService

bland_ai_webhook_bp = func.Blueprint()

@bland_ai_webhook_bp.route(route="bland_ai_webhook", methods=["POST"])
def bland_ai_webhook_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint for Bland AI callbacks (ASYNC)

    Bland AI calls this endpoint for EACH completed call
    For a batch of 1000 calls, this runs 1000 times
    """
    try:
        # Parse incoming webhook data
        webhook_data = req.get_json()

        logger.info(f"📞 [WEBHOOK] Received callback for call: {webhook_data.get('call_id')}")

        # Extract metadata (contains our attempt_id, member_id, etc.)
        metadata = webhook_data.get('metadata', {})
        attempt_id = metadata.get('attempt_id')

        if not attempt_id:
            logger.error("❌ [WEBHOOK] No attempt_id in metadata")
            return func.HttpResponse("Missing attempt_id", status_code=400)

        # Parse call outcome
        parser = CallLogParser()
        call_result = parser.parse_call_log(webhook_data)

        # Determine disposition
        disposition = call_result.get('disposition', 'Unknown')

        # Update database
        db_service = DatabaseService()
        db_service.update_outreach_attempt(
            attempt_id=attempt_id,
            vendor_session_id=webhook_data.get('call_id'),
            disposition=disposition,
            call_duration=webhook_data.get('duration'),
            pathway_data=call_result.get('pathway_data')
        )

        logger.info(f"✅ [WEBHOOK] Updated attempt {attempt_id}: {disposition}")

        return func.HttpResponse("OK", status_code=200)

    except Exception as e:
        logger.error(f"💥 [WEBHOOK] Error processing webhook: {str(e)}")
        return func.HttpResponse("Error", status_code=500)
```

### Webhook Payload Example

```json
{
    "batch_id": "bland_batch_xyz789",
    "call_id": "call_abc123",
    "to": "+1234567890",
    "from": "+1987654321",
    "status": "completed",
    "answered": true,
    "duration": 180,
    "max_duration": 600,
    "error_message": null,
    "pathway_logs": [
        {
            "type": "greeting",
            "text": "Hello, this is calling from Medical Guardian...",
            "timestamp": "2025-10-17T12:00:00Z"
        },
        {
            "type": "response",
            "text": "Yes, I'd like to schedule an appointment",
            "timestamp": "2025-10-17T12:00:15Z"
        },
        {
            "type": "appointment_booked",
            "appointment_date": "2025-10-20",
            "timestamp": "2025-10-17T12:02:00Z"
        }
    ],
    "metadata": {
        "attempt_id": "550e8400-e29b-41d4-a716-446655440000",
        "member_id": "660e8400-e29b-41d4-a716-446655440001",
        "batch_id": "770e8400-e29b-41d4-a716-446655440002",
        "campaign_id": "880e8400-e29b-41d4-a716-446655440003"
    }
}
```

---

## Batch Reconciliation (SCHEDULED)

### Code Location
**File:** `functions/batch_completion_reconciler.py`
**File:** `af_code/shared/batch_sync_coordinator.py`

### Purpose
Safety net to catch:
- Missed webhooks (network issues)
- Incomplete batches (stuck calls)
- Final batch statistics

### Reconciliation Code

```python
class BatchSyncCoordinator:
    """Periodic batch reconciliation"""

    def execute_batch_reconciliation(self):
        """
        Find and reconcile stale batches
        Runs every 30 minutes
        """
        # Step 1: Find batches that haven't had recent updates
        stale_batches = self.get_stale_batches()

        for batch in stale_batches:
            # Step 2: Call Bland AI API for batch status
            batch_status = self.get_batch_status_from_bland(
                batch['vendor_batch_id']
            )

            # Step 3: Update database with final stats
            if batch_status['is_complete']:
                self.update_batch_completion(
                    batch_id=batch['batch_id'],
                    completed_count=batch_status['calls_successful'],
                    failed_count=batch_status['calls_failed']
                )
```

---

## Code Examples

### Example 1: Complete DTC Intro Call Flow

```python
# File: functions/af_dtc_intro_call.py

@dtc_intro_call_bp.timer_trigger(
    schedule="0 */30 * * * *",  # Every 30 minutes
    arg_name="timer",
    run_on_startup=False
)
def af_dtc_intro_call_timer(timer: func.TimerRequest) -> None:
    """DTC Intro Call Timer - Runs every 30 minutes"""

    try:
        # Step 1: Get qualified members
        dtc_service = DTCIntroCallService(db_service)
        qualified_members = dtc_service.get_qualified_members(
            campaign_id="dtc-intro-campaign-001",
            limit=1000
        )

        if not qualified_members:
            logger.info("No qualified members found")
            return

        logger.info(f"Found {len(qualified_members)} qualified members")

        # Step 2: Submit batch to Bland AI (SYNCHRONOUS)
        bland_service = BlandAIService(db_service)
        vendor_batch_id = bland_service.submit_batch(
            campaign_id="dtc-intro-campaign-001",
            qualified_members=qualified_members
        )

        logger.info(f"✅ Batch submitted: {vendor_batch_id}")
        logger.info(f"📞 {len(qualified_members)} calls queued")
        logger.info("🔔 Will receive webhooks as calls complete")

        # DONE! Azure Function execution ends here
        # Bland AI will make calls and send webhooks over next 1-2 hours

    except Exception as e:
        logger.error(f"💥 Error: {str(e)}")
```

### Example 2: Partner Campaign Batch Submission

```python
# File: functions/partner_campaign_scheduler.py

def _execute_partner_campaign_scheduler(request_id: str, start_time: datetime):
    """Partner campaign execution (currently disabled for batch submission)"""

    # Get qualified campaigns
    qualified_campaigns = campaign_qualifier.get_qualified_campaigns()

    for campaign in qualified_campaigns:
        # Get eligible members
        eligible_members = member_service.get_eligible_members(campaign)

        if not eligible_members:
            continue

        # Create batches (max 1000 per batch)
        batches = member_service.create_batches(eligible_members, batch_size=1000)

        for batch in batches:
            # NOTE: Currently skipped because async not supported in sync timer
            # TODO: Enable when async support added

            # FUTURE: Submit batch to Bland AI
            # vendor_batch_id = batch_orchestrator.submit_batch(campaign, batch)

            # FUTURE: Track batch submission
            # status_tracker.log_batch_submission(campaign, batch, vendor_batch_id)

            logger.info(f"⚠️ Batch submission skipped (async not supported)")
            logger.info(f"📊 {len(batch)} members ready for submission")
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     SYNCHRONOUS PHASE                            │
│                  (Azure Function Execution)                       │
│                                                                   │
│  Timer Trigger (Every 30 min)                                    │
│         │                                                         │
│         ▼                                                         │
│  Get Qualified Members                                           │
│         │                                                         │
│         ▼                                                         │
│  Create Database Records                                         │
│    • outreach_batches (batch_id, status='Pending')               │
│    • outreach_attempts (attempt_id, disposition='Pending')       │
│         │                                                         │
│         ▼                                                         │
│  Build Bland AI Payload                                          │
│    • global config                                               │
│    • call_objects[] (1000 calls)                                 │
│    • metadata (attempt_id, member_id)                            │
│         │                                                         │
│         ▼                                                         │
│  POST to Bland AI API ◄─────── BLOCKS HERE (30s timeout)         │
│         │                                                         │
│         ▼                                                         │
│  Response: { batch_id: "bland_xyz" }                             │
│         │                                                         │
│         ▼                                                         │
│  Update Database                                                 │
│    • vendor_batch_id = "bland_xyz"                               │
│    • batch_status = 'Submitted'                                  │
│                                                                   │
│  ✅ AZURE FUNCTION ENDS                                          │
│     Total time: ~5-10 seconds                                    │
└───────────────────────────────────────────────────────────────────┘

                          ↓  (Asynchronous boundary)

┌─────────────────────────────────────────────────────────────────┐
│                    ASYNCHRONOUS PHASE                            │
│                   (Bland AI Processing)                          │
│                                                                   │
│  Bland AI Processes Batch                                        │
│    • Validates 1000 phone numbers                                │
│    • Queues calls                                                │
│    • Makes calls (30 min - 2 hours)                              │
│         │                                                         │
│         ├────► Call 1 completes ──► Webhook ──┐                  │
│         ├────► Call 2 completes ──► Webhook ──┤                  │
│         ├────► Call 3 completes ──► Webhook ──┤                  │
│         │  ...                                 │                  │
│         └────► Call 1000 completes ► Webhook ──┘                  │
│                                                │                  │
│                                                ▼                  │
│                       POST /api/bland_ai_webhook                  │
│                                                │                  │
│                                                ▼                  │
│                       Parse Webhook Payload                       │
│                         • call_id                                 │
│                         • status                                  │
│                         • duration                                │
│                         • metadata.attempt_id                     │
│                                                │                  │
│                                                ▼                  │
│                       Update Database                             │
│                         • disposition = 'Completed'               │
│                         • vendor_session_id = call_id             │
│                         • call_duration                           │
│                         • pathway_data                            │
│                                                                   │
│  This runs 1000 times (once per call)                            │
│  Typically completes in 30 min - 2 hours                         │
└───────────────────────────────────────────────────────────────────┘

                          ↓  (Parallel safety net)

┌─────────────────────────────────────────────────────────────────┐
│                   RECONCILIATION PHASE                           │
│              (Scheduled Timer - Every 30 min)                     │
│                                                                   │
│  Timer Trigger (Every 30 min)                                    │
│         │                                                         │
│         ▼                                                         │
│  Find Stale Batches                                              │
│    • status IN ('Submitted', 'Pending')                          │
│    • last_status_check > 2 hours ago                             │
│         │                                                         │
│         ▼                                                         │
│  GET /v2/batches/{batch_id}/logs ◄─── BLOCKS (30s timeout)       │
│         │                                                         │
│         ▼                                                         │
│  Response: {                                                     │
│      calls_successful: 850,                                      │
│      calls_failed: 150                                           │
│  }                                                               │
│         │                                                         │
│         ▼                                                         │
│  Update Database                                                 │
│    • batch_status = 'Completed'                                  │
│    • total_calls_completed = 850                                 │
│    • total_calls_failed = 150                                    │
│                                                                   │
│  Catches any missed webhooks                                     │
└───────────────────────────────────────────────────────────────────┘
```

---

## Summary

### Key Points

1. **Batch Submission = SYNCHRONOUS**
   - We submit batch and wait for confirmation
   - Takes 5-10 seconds
   - Returns batch_id immediately

2. **Call Processing = ASYNCHRONOUS**
   - Bland AI makes calls in background
   - Takes 30 minutes to 2 hours
   - We don't wait for this

3. **Webhooks = ASYNCHRONOUS**
   - Bland AI sends webhook for each call
   - Real-time updates as calls complete
   - Runs 1000 times for batch of 1000

4. **Reconciliation = SCHEDULED SYNC**
   - Safety net for missed webhooks
   - Runs every 30 minutes
   - Checks batch completion status

### Architecture Benefits

- **Non-blocking**: Submit thousands of calls without waiting
- **Real-time**: Webhooks provide immediate updates
- **Resilient**: Reconciliation catches missed webhooks
- **Scalable**: Can submit multiple batches in parallel

---

**Document Version**: 1.0
**Last Updated**: 2025-10-17
**Author**: Claude Code Assistant
**Maintained By**: IOE Development Team
