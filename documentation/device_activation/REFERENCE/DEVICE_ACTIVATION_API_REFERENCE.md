# Device Activation API Reference

**Version:** 1.0
**Last Updated:** 2026-01-23
**BusinessCaseID:** BC-DA-001 (Core Orchestration), BC-DA-007 (Campaign Closure)
**Purpose:** Complete API reference for Device Activation HTTP endpoints, timer triggers, and blob triggers

---

## Table of Contents

1. [HTTP Endpoints](#http-endpoints)
   - [Create Device Activation Batch (Manual Trigger)](#1-create-device-activation-batch-manual-trigger)
   - [Device Activation Campaign Closure](#2-device-activation-campaign-closure)
2. [Timer Triggers (Automated)](#timer-triggers-automated)
   - [Device Activation Scheduler](#1-device-activation-scheduler)
   - [Campaign Closure Scheduler](#2-campaign-closure-scheduler)
3. [Blob Triggers (Automated)](#blob-triggers-automated)
   - [Operations Device Activation File Processor](#1-operations-device-activation-file-processor)
4. [Response Codes](#response-codes)
5. [Error Handling](#error-handling)
6. [Monitoring](#monitoring)
7. [Related Documentation](#related-documentation)

---

## HTTP Endpoints

### 1. Create Device Activation Batch (Manual Trigger)

**Endpoint**: `POST /api/create_device_activation_batch`

**Purpose**: Manually trigger Device Activation batch creation outside scheduled runs. Useful for testing, ad-hoc processing, or recovery after system downtime.

**Authentication**: Function key required (set in Azure Function App configuration)

**Request Headers**:
```http
Content-Type: application/json
x-functions-key: YOUR_FUNCTION_KEY
```

**Request Body**:
```json
{
  "force": false  // Optional: bypass some validation checks (default: false)
}
```

**Response (200 OK)**:
```json
{
  "success": true,
  "message": "Device Activation batches created successfully",
  "total_eligible": 25,
  "batches_created": 2,
  "calls_submitted": 20,
  "timestamp": "2026-01-23T14:30:00Z",
  "request_id": "da-manual-20260123-143000"
}
```

**Response (500 Error)**:
```json
{
  "success": false,
  "error": "An internal server error occurred",
  "details": "Error details here",
  "request_id": "da-manual-20260123-143000"
}
```

**Example cURL**:
```bash
# Basic manual trigger
curl -X POST "https://ioe-function.azurewebsites.net/api/create_device_activation_batch" \
  -H "Content-Type: application/json" \
  -H "x-functions-key: YOUR_FUNCTION_KEY" \
  -d '{"force": false}'

# Force mode (bypass some validations)
curl -X POST "https://ioe-function.azurewebsites.net/api/create_device_activation_batch" \
  -H "Content-Type: application/json" \
  -H "x-functions-key: YOUR_FUNCTION_KEY" \
  -d '{"force": true}'
```

**Use Cases**:
- Testing batch creation logic in dev/staging environments
- Manual recovery after system downtime
- Ad-hoc batch creation for urgent member outreach
- Validation of eligibility query changes

**Important Notes**:
- Does NOT bypass business hours validation (calls only scheduled during business hours)
- Respects 20 members per run limit (same as timer trigger)
- Checks for concurrent runs (distributed locking)
- Logs all manual triggers to Application Insights

---

### 2. Device Activation Campaign Closure

**Endpoint**: `GET /api/device_activation_campaign_closure`
**Endpoint**: `POST /api/device_activation_campaign_closure`

**Purpose**: Manually trigger 90-day campaign window closure check. Auto-unenrolls members whose campaign_end_date has expired.

**Authentication**: Function key required

**Request Headers**:
```http
x-functions-key: YOUR_FUNCTION_KEY
```

**Request**: No body required (both GET and POST supported)

**Response (200 OK)**:
```json
{
  "success": true,
  "request_id": "da-closure-http-20260123-143000",
  "timestamp": "2026-01-23T14:30:00Z",
  "result": {
    "enrollments_closed": 15,
    "campaigns_affected": [
      "Device Activation - Medicaid",
      "Device Activation - DTC/MA"
    ],
    "members_unenrolled": 15,
    "execution_duration_seconds": 2.45
  }
}
```

**Response (200 OK - No Eligible Members)**:
```json
{
  "success": true,
  "request_id": "da-closure-http-20260123-143000",
  "timestamp": "2026-01-23T14:30:00Z",
  "result": {
    "enrollments_closed": 0,
    "campaigns_affected": [],
    "members_unenrolled": 0,
    "execution_duration_seconds": 0.23
  }
}
```

**Response (409 Conflict - Lock Active)**:
```json
{
  "success": false,
  "error": "Campaign closure already running",
  "details": "Distributed lock is active. Another campaign closure process is in progress.",
  "request_id": "da-closure-http-20260123-143000"
}
```

**Response (500 Error)**:
```json
{
  "success": false,
  "error": "An internal server error occurred",
  "details": "Error details here",
  "request_id": "da-closure-http-20260123-143000"
}
```

**Example cURL**:
```bash
# GET request
curl -X GET "https://ioe-function.azurewebsites.net/api/device_activation_campaign_closure" \
  -H "x-functions-key: YOUR_FUNCTION_KEY"

# POST request (equivalent)
curl -X POST "https://ioe-function.azurewebsites.net/api/device_activation_campaign_closure" \
  -H "x-functions-key: YOUR_FUNCTION_KEY"
```

**Use Cases**:
- Testing campaign closure logic in dev/staging environments
- Manual closure trigger after database maintenance
- Immediate closure after updating campaign_end_date values
- Validation of 90-day window calculations

**Important Notes**:
- Uses distributed locking (`system_locks` table) to prevent concurrent execution
- Returns 409 Conflict if another closure process is running
- Updates enrollment status to 'UNENROLLED' for expired members
- Logs status change to `member_enrollment_status_history` table
- Automatically called by hourly timer trigger (no manual intervention needed)

---

## Timer Triggers (Automated)

### 1. Device Activation Scheduler

**Function Name**: `timer_device_activation`

**Schedule**: `0 */15 * * * *` (Every 15 minutes at :00, :15, :30, :45)

**Purpose**: Automatically check for eligible members and create Device Activation call batches.

**Execution Flow**:
1. Check distributed lock (prevent concurrent runs)
2. Query eligible members (business hours, frequency rules, enrollment status)
3. Create batch with up to 20 members
4. Submit batch to Bland AI
5. Update database (batch, attempts, timestamps)
6. Release lock

**No Manual Invocation Needed** - Runs automatically every 15 minutes

**Monitoring Query** (Application Insights):
```kusto
traces
| where message contains "DEVICE ACTIVATION SCHEDULER"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 15m)
| render timechart
```

**Expected Frequency**: 96 runs per day (24 hours × 4 runs/hour)

**Daily Capacity**: ~1,920 members/day (20 members/run × 96 runs/day)

---

### 2. Campaign Closure Scheduler

**Function Name**: `timer_device_activation_campaign_closure`

**Schedule**: `0 0 * * * *` (Every hour at :00 minutes)

**Purpose**: Automatically unenroll members whose 90-day campaign window has expired.

**Execution Flow**:
1. Acquire distributed lock (`system_locks` table)
2. Query enrollments where `campaign_end_date < SYSDATETIMEOFFSET()`
3. Update enrollment status to 'UNENROLLED'
4. Log status change to `member_enrollment_status_history`
5. Release lock

**No Manual Invocation Needed** - Runs automatically every hour

**Monitoring Query** (Application Insights):
```kusto
traces
| where message contains "DA-CLOSURE"
| where timestamp > ago(24h)
| project timestamp, message
| order by timestamp desc
```

**Expected Frequency**: 24 runs per day (once per hour)

---

## Blob Triggers (Automated)

### 1. Operations Device Activation File Processor

**Function Name**: `operations_device_activation_file_processor`

**Trigger**: Blob created in `fs-ops/landing/` container

**Filename Patterns**:
- `MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv`
- `MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv`

**Purpose**: Process CSV files uploaded to blob storage, validate data, and create member enrollments.

**Execution Flow**:
1. Detect blob upload (trigger fires)
2. Validate filename pattern
3. Extract CSV data (27 required columns)
4. Validate and cleanse data (phone, email, address, timezone, etc.)
5. Load to staging table (`ioe_stg.stg_device_activation_delta`)
6. Transform and MERGE to core tables (members, member_devices, enrollments)
7. Move blob to processed/ folder
8. Log results to `file_processing_log`

**Upload Example** (Azure CLI):
```bash
# Medicaid campaign
az storage blob upload \
  --account-name ioestore \
  --container-name fs-ops \
  --name "landing/MedicalGuardian_DeviceActivationMedicaid_20260123_DELTA.csv" \
  --file ./medicaid_members.csv \
  --auth-mode key

# DTC/MA campaign
az storage blob upload \
  --account-name ioestore \
  --container-name fs-ops \
  --name "landing/MedicalGuardian_DeviceActivationDTCMA_20260123_DELTA.csv" \
  --file ./dtcma_members.csv \
  --auth-mode key
```

**Upload Example** (Azure Portal):
1. Navigate to Storage Account: `ioestore`
2. Go to Containers → `fs-ops`
3. Click "Upload"
4. Select file with correct naming pattern
5. Ensure blob path starts with `landing/`
6. Click "Upload"

**Hardcoded Campaign IDs**:

| Campaign Name | Campaign ID | Filename Pattern |
|---------------|-------------|------------------|
| Device Activation - Medicaid | `0F69659B-491B-40E2-88C3-ABC7D87385B2` | `MedicalGuardian_DeviceActivationMedicaid_*` |
| Device Activation - DTC/MA | `BA865458-60F9-4EBB-9FB5-D195B532CF5A` | `MedicalGuardian_DeviceActivationDTCMA_*` |

**Important Notes**:
- **PRIMARY Processor**: Uses `fs-ops/landing` container
- **LEGACY Processor**: `device_activation_file_processor` uses `fs-device-activation/landing` (backup only)
- Risk: Uploading to wrong container may cause duplicate processing
- File validation includes: 27 columns, phone format (E.164), timezone (IANA), address (5 parts)
- Failed rows logged to validation error tables for troubleshooting

---

## Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Request processed successfully |
| 400 | Bad Request | Check request body format and parameters |
| 401 | Unauthorized | Verify function key in `x-functions-key` header |
| 404 | Not Found | Check endpoint URL and function name |
| 409 | Conflict | Distributed lock active (campaign closure already running) |
| 500 | Internal Error | Check Application Insights logs for details |

---

## Error Handling

All endpoints return consistent error format:

```json
{
  "success": false,
  "error": "Error message here",
  "details": "Additional context or stack trace",
  "request_id": "da-manual-20260123-143000"
}
```

### Common Errors

**1. "No eligible members found"**
- **Type**: Informational (not an error)
- **Meaning**: No members meet eligibility criteria (business hours, frequency, status)
- **Action**: Normal behavior, no action needed

**2. "Duplicate processing detected"**
- **Type**: Warning
- **Meaning**: Webhook received duplicate call_id
- **Action**: System handles automatically (idempotent)

**3. "Campaign not found"**
- **Type**: Error
- **Meaning**: campaign_id does not exist in database
- **Action**: Verify hardcoded campaign IDs, check `campaigns_enhanced` table

**4. "Distributed lock active"**
- **Type**: Conflict (409)
- **Meaning**: Campaign closure already running (another process holds lock)
- **Action**: Wait for current process to complete (max 5 minutes)

**5. "Database connection timeout"**
- **Type**: Error (500)
- **Meaning**: Transient SQL Server issue
- **Action**: System retries 3 times with exponential backoff, then fails

---

## Monitoring

### Application Insights Queries

**1. Scheduler Execution Frequency**
```kusto
traces
| where message contains "DEVICE ACTIVATION SCHEDULER"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 15m)
| render timechart
```

**Expected**: 4 runs per hour (every 15 minutes)

---

**2. Campaign Closure Executions**
```kusto
traces
| where message contains "DA-CLOSURE"
| where timestamp > ago(24h)
| project timestamp, message
| order by timestamp desc
```

**Expected**: 24 runs per day (every hour)

---

**3. API Endpoint Calls**
```kusto
requests
| where url contains "create_device_activation_batch"
| where timestamp > ago(7d)
| summarize count() by resultCode, bin(timestamp, 1d)
| render barchart
```

**Expected**: Varies (manual triggers only)

---

**4. Blob Trigger Processing**
```kusto
traces
| where message contains "BLOB TRIGGER: operations_device_activation_file_processor"
| where timestamp > ago(7d)
| project timestamp, message
| order by timestamp desc
```

**Expected**: Varies based on file upload frequency

---

**5. Batch Submission Success Rate**
```kusto
traces
| where message contains "Bland AI batch submission"
| where timestamp > ago(24h)
| summarize
    Total = count(),
    Success = countif(message contains "success"),
    Failed = countif(message contains "failed")
| extend SuccessRate = (Success * 100.0) / Total
```

**Target**: >95% success rate

---

### Key Metrics

| Metric | Value | Frequency |
|--------|-------|-----------|
| Scheduler runs | 96/day | Every 15 minutes |
| Campaign closure runs | 24/day | Every hour |
| Batch size | 20 members per run | Per scheduler execution |
| Max daily capacity | 1,920 members/day | 20 × 96 runs |
| File processing | Varies | On blob upload |
| 90-day window | activation_start_date + 90 days | Set at enrollment |

---

### Health Checks

**1. Scheduler Health**
```kusto
// Alert if scheduler hasn't run in 30 minutes
traces
| where message contains "DEVICE ACTIVATION SCHEDULER"
| where timestamp > ago(30m)
| summarize count()
```

**Expected**: >= 2 (at least 2 runs in last 30 minutes)

**Alert**: If count < 1, scheduler may be down

---

**2. Campaign Closure Health**
```kusto
// Alert if campaign closure hasn't run in 90 minutes
traces
| where message contains "DA-CLOSURE"
| where timestamp > ago(90m)
| summarize count()
```

**Expected**: >= 1 (at least 1 run in last 90 minutes)

**Alert**: If count < 1, campaign closure may be down

---

**3. Database Connection Health**
```kusto
traces
| where message contains "Database connection"
| where message contains "error" or message contains "timeout"
| where timestamp > ago(1h)
```

**Expected**: 0 errors

**Alert**: If count > 0, investigate database connectivity

---

## Related Documentation

- **Architecture**: [DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md)
- **Deployment**: [DEVICE_ACTIVATION_DEPLOYMENT_GUIDE.md](../GUIDES/DEVICE_ACTIVATION_DEPLOYMENT_GUIDE.md)
- **Troubleshooting**: [DEVICE_ACTIVATION_TROUBLESHOOTING.md](../GUIDES/DEVICE_ACTIVATION_TROUBLESHOOTING.md)
- **BusinessCaseIDs**: [DEVICE_ACTIVATION_BUSINESSCASEID_MAPPING.md](./DEVICE_ACTIVATION_BUSINESSCASEID_MAPPING.md)
- **Call Flow**: [OPERATIONS_DEVICE_ACTIVATION_CALL_FLOW.md](../../../OPERATIONS_DEVICE_ACTIVATION_CALL_FLOW.md)
- **CSV Reference**: [DEVICE_ACTIVATION_CSV_REFERENCE.md](../../../documentation/DEVICE_ACTIVATION_CSV_REFERENCE.md)

---

**Document Status:** ✅ Complete
**Last Reviewed:** 2026-01-23
**Next Review:** 2026-04-23
**BusinessCaseID:** BC-DA-001 (Core Orchestration), BC-DA-007 (Campaign Closure)
