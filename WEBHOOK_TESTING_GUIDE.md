# Bland AI Webhook Testing Guide

## Overview
This guide provides comprehensive testing scenarios for the **Bland AI Webhook** processing system, including disposition mappings, duplicate detection, and database integration.

## Table of Contents
1. [Webhook Endpoint Testing](#webhook-endpoint-testing)
2. [Disposition Mapping Scenarios](#disposition-mapping-scenarios)
3. [Duplicate Detection Testing](#duplicate-detection-testing)
4. [Error Handling Scenarios](#error-handling-scenarios)
5. [Business Rules Testing](#business-rules-testing)
6. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

---

## Webhook Endpoint Testing

### Base Configuration
- **Endpoint URL**: `https://your-function-app.azurewebsites.net/api/bland-ai-webhook`
- **Method**: POST
- **Content-Type**: `application/json`
- **Authentication**: Function key required

### Test Tools Setup

#### Using cURL
```bash
# Set your function app details
FUNCTION_URL="https://your-function-app.azurewebsites.net/api/bland-ai-webhook"
FUNCTION_KEY="your-function-key"

# Test command template
curl -X POST "$FUNCTION_URL?code=$FUNCTION_KEY" \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

#### Using Postman
1. **Method**: POST
2. **URL**: `https://your-function-app.azurewebsites.net/api/bland-ai-webhook?code=your-function-key`
3. **Headers**: `Content-Type: application/json`
4. **Body**: Raw JSON payload

---

## Disposition Mapping Scenarios

### Scenario 1: Successful Call with Interest
**Test Payload**:
```json
{
  "call_id": "call_12345_interest",
  "status": "completed",
  "to": "+15551234567",
  "metadata": {
    "attempt_id": "attempt_67890",
    "phone_number": "+15551234567",
    "member_id": "MBR_12345"
  },
  "disposition_tag": "INTERESTED",
  "call_length": 180,
  "recording_url": "https://recordings.blandai.com/call_12345.mp3",
  "summary": "Customer expressed strong interest in wellness monitoring services",
  "transcript": "Hello, this is John from Medical Guardian...",
  "analysis": {
    "sentiment": "positive",
    "keywords": ["interested", "sign up", "wellness"]
  }
}
```

**Expected Logs - Success Path**:
```
[2024-12-26 14:00:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:00:01] 🔍 [DATA-VALIDATOR] Starting webhook payload validation
[2024-12-26 14:00:01] ✅ [DATA-VALIDATOR] Validation succeeded
[2024-12-26 14:00:02] 🔍 [DUPLICATE-DETECTOR] Checking for duplicate call_id: call_12345_interest
[2024-12-26 14:00:02] ✅ [DUPLICATE-DETECTOR] No duplicate found for call_id: call_12345_interest. Proceeding.
[2024-12-26 14:00:03] 🔄 [STATUS-MAPPER] Processing webhook data for call_id: call_12345_interest
[2024-12-26 14:00:03] ✅ [STATUS-MAPPER] Successfully mapped status 'completed' + disposition 'INTERESTED'
[2024-12-26 14:00:03] 📋 [STATUS-MAPPER] Mapped to: disposition=Completed, next_action=Follow_Up, contact_made=true
[2024-12-26 14:00:04] 🔍 [BUSINESS-RULES] Evaluating business rules for mapped data
[2024-12-26 14:00:04] ✅ [BUSINESS-RULES] All business rules passed
[2024-12-26 14:00:05] 💾 [DB-ORCHESTRATOR] Starting database transaction
[2024-12-26 14:00:05] 📝 [DB-ORCHESTRATOR] Inserting call log record
[2024-12-26 14:00:06] 🎯 [DB-ORCHESTRATOR] Updating member engagement status
[2024-12-26 14:00:06] ✅ [DB-ORCHESTRATOR] Database transaction completed successfully
[2024-12-26 14:00:07] 📤 [SERVICE-BUS] Sending follow-up message to service bus
[2024-12-26 14:00:07] ✅ [SERVICE-BUS] Message sent successfully
[2024-12-26 14:00:08] ✅ Webhook processed successfully for call_id: call_12345_interest
```

**Expected HTTP Response**:
```json
{
  "success": true,
  "message": "Webhook processed successfully",
  "call_id": "call_12345_interest",
  "disposition": "Completed",
  "next_action": "Follow_Up",
  "processing_time_ms": 7543
}
```

**Expected Database Changes**:
- New record in `ioe.bland_call_logs`
- Updated `ioe.member_campaign_enrollments_enhanced` (if member found)
- Service bus message queued for follow-up

---

### Scenario 2: Opt-Out Request
**Test Payload**:
```json
{
  "call_id": "call_12346_optout",
  "status": "completed", 
  "to": "+15559876543",
  "metadata": {
    "attempt_id": "attempt_67891",
    "phone_number": "+15559876543"
  },
  "disposition_tag": "DO_NOT_CONTACT",
  "call_length": 45,
  "summary": "Customer requested to be removed from all future calls",
  "transcript": "Please remove me from your calling list..."
}
```

**Expected Logs - Opt-Out Processing**:
```
[2024-12-26 14:05:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:05:01] ✅ [DATA-VALIDATOR] Validation succeeded
[2024-12-26 14:05:02] ✅ [DUPLICATE-DETECTOR] No duplicate found for call_id: call_12346_optout. Proceeding.
[2024-12-26 14:05:03] 🔄 [STATUS-MAPPER] Processing webhook data for call_id: call_12346_optout
[2024-12-26 14:05:03] ⚠️ [STATUS-MAPPER] Opt-out request detected: DO_NOT_CONTACT
[2024-12-26 14:05:03] ✅ [STATUS-MAPPER] Successfully mapped to: disposition=OptOut, next_action=Close, contact_made=true
[2024-12-26 14:05:04] 🚫 [BUSINESS-RULES] Opt-out processing initiated for phone: +15559876543
[2024-12-26 14:05:05] 💾 [DB-ORCHESTRATOR] Starting opt-out database transaction
[2024-12-26 14:05:05] 🚫 [DB-ORCHESTRATOR] Updating member opt-out status
[2024-12-26 14:05:06] 📝 [DB-ORCHESTRATOR] Recording opt-out in compliance log
[2024-12-26 14:05:06] ✅ [DB-ORCHESTRATOR] Opt-out transaction completed successfully
[2024-12-26 14:05:07] 📤 [SERVICE-BUS] Sending opt-out notification to compliance system
[2024-12-26 14:05:07] ✅ Opt-out webhook processed successfully for call_id: call_12346_optout
```

**Expected Database Changes**:
- New record in `ioe.bland_call_logs` with `opt_out_requested = 1`
- Member status updated to opt-out in relevant tables
- Compliance audit trail created

---

### Scenario 3: Failed Call - No Answer
**Test Payload**:
```json
{
  "call_id": "call_12347_noanswer",
  "status": "completed",
  "to": "+15551119999", 
  "metadata": {
    "attempt_id": "attempt_67892"
  },
  "disposition_tag": "NO_ANSWER",
  "call_length": 0,
  "summary": "Call went to voicemail, no answer"
}
```

**Expected Logs - No Answer Processing**:
```
[2024-12-26 14:10:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:10:01] ✅ [DATA-VALIDATOR] Validation succeeded
[2024-12-26 14:10:02] ✅ [DUPLICATE-DETECTOR] No duplicate found for call_id: call_12347_noanswer. Proceeding.
[2024-12-26 14:10:03] 🔄 [STATUS-MAPPER] Processing webhook data for call_id: call_12347_noanswer
[2024-12-26 14:10:03] ✅ [STATUS-MAPPER] Successfully mapped to: disposition=NoAnswer, next_action=Retry, contact_made=false
[2024-12-26 14:10:04] 🔄 [BUSINESS-RULES] Evaluating retry logic for failed call
[2024-12-26 14:10:04] ✅ [BUSINESS-RULES] Retry approved - under maximum attempt limit
[2024-12-26 14:10:05] 💾 [DB-ORCHESTRATOR] Recording failed attempt
[2024-12-26 14:10:05] 📅 [DB-ORCHESTRATOR] Scheduling retry attempt
[2024-12-26 14:10:06] ✅ [DB-ORCHESTRATOR] Failed call transaction completed
[2024-12-26 14:10:07] 📤 [SERVICE-BUS] Scheduling retry message
[2024-12-26 14:10:07] ✅ No-answer webhook processed successfully for call_id: call_12347_noanswer
```

---

## Duplicate Detection Testing

### Scenario 4: Duplicate Call ID
**Test Setup**: Send the same payload twice

**First Request** (Success):
```json
{
  "call_id": "call_duplicate_test_123",
  "status": "completed",
  "to": "+15551234567",
  "metadata": {
    "attempt_id": "attempt_first"
  },
  "disposition_tag": "COMPLETED_ACTION"
}
```

**Expected Logs - First Request**:
```
[2024-12-26 14:15:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:15:02] ✅ [DUPLICATE-DETECTOR] No duplicate found for call_id: call_duplicate_test_123. Proceeding.
[2024-12-26 14:15:05] ✅ Webhook processed successfully for call_id: call_duplicate_test_123
```

**Second Request** (Duplicate):
Same JSON payload sent again

**Expected Logs - Second Request**:
```
[2024-12-26 14:16:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:16:02] 🔍 [DUPLICATE-DETECTOR] Checking for duplicate call_id: call_duplicate_test_123
[2024-12-26 14:16:02] 🚨 [DUPLICATE-DETECTOR] Duplicate detected. Call ID 'call_duplicate_test_123' already exists in the database.
[2024-12-26 14:16:02] ⚠️ Duplicate webhook ignored for call_id: call_duplicate_test_123
```

**Expected HTTP Response**:
```json
{
  "success": false,
  "message": "Duplicate call_id detected - webhook ignored",
  "call_id": "call_duplicate_test_123",
  "error_code": "DUPLICATE_CALL_ID"
}
```

---

## Error Handling Scenarios

### Scenario 5: Invalid Payload Structure
**Test Payload** (Missing required fields):
```json
{
  "call_id": "call_invalid_123",
  "status": "completed"
  // Missing 'to' and 'metadata' fields
}
```

**Expected Logs - Validation Error**:
```
[2024-12-26 14:20:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:20:01] 🔍 [DATA-VALIDATOR] Starting webhook payload validation
[2024-12-26 14:20:01] ❌ [DATA-VALIDATOR] Validation failed
[2024-12-26 14:20:01] ❌ [DATA-VALIDATOR] Validation errors: ["Missing required fields: to, metadata"]
[2024-12-26 14:20:02] 💥 [ERROR-HANDLER] Logging validation error to database
[2024-12-26 14:20:02] ❌ Webhook validation failed for call_id: call_invalid_123
```

**Expected HTTP Response**:
```json
{
  "success": false,
  "message": "Webhook validation failed",
  "errors": ["Missing required fields: to, metadata"],
  "call_id": "call_invalid_123",
  "error_code": "VALIDATION_FAILED"
}
```

---

### Scenario 6: Database Connection Failure
**Test Setup**: Simulate database connection issues

**Expected Logs - Database Error**:
```
[2024-12-26 14:25:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:25:03] ✅ [STATUS-MAPPER] Successfully mapped webhook data
[2024-12-26 14:25:04] 💾 [DB-ORCHESTRATOR] Starting database transaction
[2024-12-26 14:25:05] 💥 [DB-SERVICE] Database error: Login timeout expired
[2024-12-26 14:25:05] 🔄 [DB-ORCHESTRATOR] Retrying database operation (attempt 1/3)
[2024-12-26 14:25:07] 💥 [DB-SERVICE] Database error: Login timeout expired  
[2024-12-26 14:25:07] 🔄 [DB-ORCHESTRATOR] Retrying database operation (attempt 2/3)
[2024-12-26 14:25:09] 💥 [DB-SERVICE] Database error: Login timeout expired
[2024-12-26 14:25:09] ❌ [DB-ORCHESTRATOR] All retry attempts failed
[2024-12-26 14:25:10] 📧 [ERROR-HANDLER] Sending database error notification
[2024-12-26 14:25:10] ❌ Webhook processing failed due to database error
```

**Expected HTTP Response**:
```json
{
  "success": false,
  "message": "Database operation failed after retries",
  "call_id": "call_12348_dberror",
  "error_code": "DATABASE_ERROR",
  "retry_suggested": true
}
```

---

### Scenario 7: Unknown Disposition Tag
**Test Payload**:
```json
{
  "call_id": "call_unknown_disposition",
  "status": "completed",
  "to": "+15551234567",
  "metadata": {
    "attempt_id": "attempt_unknown"
  },
  "disposition_tag": "UNKNOWN_DISPOSITION_TAG"
}
```

**Expected Logs - Fallback Mapping**:
```
[2024-12-26 14:30:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:30:02] ✅ [DUPLICATE-DETECTOR] No duplicate found. Proceeding.
[2024-12-26 14:30:03] 🔄 [STATUS-MAPPER] Processing webhook data for call_id: call_unknown_disposition
[2024-12-26 14:30:03] ⚠️ [STATUS-MAPPER] Unknown disposition 'UNKNOWN_DISPOSITION_TAG', expected one of completed, failed, in-progress, cancelled
[2024-12-26 14:30:03] 🔄 [STATUS-MAPPER] Applying fallback mapping for unknown disposition
[2024-12-26 14:30:03] ✅ [STATUS-MAPPER] Fallback mapping applied: disposition=Failed, next_action=Escalate, contact_made=false
[2024-12-26 14:30:04] 💾 [DB-ORCHESTRATOR] Recording with fallback disposition
[2024-12-26 14:30:05] ✅ Webhook processed with fallback mapping for call_id: call_unknown_disposition
```

---

## Business Rules Testing

### Scenario 8: Service Bus Integration
**Test Payload**:
```json
{
  "call_id": "call_servicebus_test",
  "status": "completed",
  "to": "+15551234567",
  "metadata": {
    "attempt_id": "attempt_sb_test",
    "member_id": "MBR_SERVICEBUS_TEST"
  },
  "disposition_tag": "FOLLOW_UP_REQUIRED",
  "priority": "high"
}
```

**Expected Logs - Service Bus Processing**:
```
[2024-12-26 14:35:01] 🚀 Bland AI Webhook received a request.
[2024-12-26 14:35:03] ✅ [STATUS-MAPPER] Successfully mapped to: disposition=Completed, next_action=Follow_Up, contact_made=true
[2024-12-26 14:35:05] ✅ [DB-ORCHESTRATOR] Database transaction completed successfully
[2024-12-26 14:35:06] 📤 [SERVICE-BUS] Preparing follow-up message for service bus
[2024-12-26 14:35:06] 📋 [SERVICE-BUS] Message content: {"member_id":"MBR_SERVICEBUS_TEST","action":"follow_up","priority":"high","call_id":"call_servicebus_test"}
[2024-12-26 14:35:07] ✅ [SERVICE-BUS] Message sent successfully to queue: follow-up-actions
[2024-12-26 14:35:07] 📊 [SERVICE-BUS] Message ID: msg_sb_20241226143507
[2024-12-26 14:35:08] ✅ Webhook processed with service bus integration for call_id: call_servicebus_test
```

---

## Monitoring and Troubleshooting

### Application Insights Queries

#### Webhook Success Rate
```kql
requests
| where name contains "bland-ai-webhook"
| where timestamp > ago(1h)
| summarize 
    TotalRequests = count(),
    SuccessfulRequests = countif(success == true),
    FailedRequests = countif(success == false)
| extend SuccessRate = round(SuccessfulRequests * 100.0 / TotalRequests, 2)
```

#### Error Analysis
```kql
traces
| where message contains "ERROR-HANDLER" or severityLevel >= 3
| where timestamp > ago(1h)
| project timestamp, message, severityLevel
| order by timestamp desc
```

#### Disposition Mapping Statistics
```kql
traces
| where message contains "STATUS-MAPPER" and message contains "Successfully mapped"
| where timestamp > ago(24h)
| extend disposition = extract("disposition=([^,]+)", 1, message)
| summarize count() by disposition
| order by count_ desc
```

#### Duplicate Detection Metrics
```kql
traces
| where message contains "DUPLICATE-DETECTOR"
| where timestamp > ago(1h)
| extend isDuplicate = message contains "Duplicate detected"
| summarize 
    TotalChecks = count(),
    DuplicatesFound = countif(isDuplicate),
    UniqueCallsProcessed = countif(not(isDuplicate))
```

### Database Verification Queries

#### Recent Call Logs
```sql
SELECT TOP 20
    call_id,
    phone_number,
    disposition,
    next_action,
    contact_made,
    opt_out_requested,
    created_ts
FROM ioe.bland_call_logs
ORDER BY created_ts DESC;
```

#### Disposition Distribution
```sql
SELECT 
    disposition,
    next_action,
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM ioe.bland_call_logs
WHERE created_ts >= DATEADD(day, -1, GETUTCDATE())
GROUP BY disposition, next_action
ORDER BY count DESC;
```

#### Opt-Out Tracking
```sql
SELECT 
    phone_number,
    call_id,
    disposition,
    created_ts
FROM ioe.bland_call_logs
WHERE opt_out_requested = 1
    AND created_ts >= DATEADD(day, -7, GETUTCDATE())
ORDER BY created_ts DESC;
```

### Performance Benchmarks

#### Expected Response Times
- **Simple webhook** (validation + mapping): 100-300ms
- **Database operations**: 200-500ms
- **Service bus integration**: 300-700ms
- **Total end-to-end**: 500-1500ms

#### Throughput Expectations
- **Concurrent requests**: Up to 10 simultaneous
- **Requests per minute**: 200-500 
- **Daily volume**: Up to 50,000 webhooks

### Common Error Patterns and Solutions

#### Error 1: Validation Failures
**Pattern**: `❌ [DATA-VALIDATOR] Validation failed`
**Common Causes**:
- Missing required fields (`call_id`, `status`, `to`, `metadata`)
- Invalid phone number format
- Empty metadata object

**Solution**: Verify payload structure matches expected schema

#### Error 2: Database Timeouts  
**Pattern**: `💥 [DB-SERVICE] Database error: Login timeout expired`
**Common Causes**:
- Database server overload
- Network connectivity issues
- Connection pool exhaustion

**Solution**: Check database health and connection string

#### Error 3: Service Bus Failures
**Pattern**: `❌ [SERVICE-BUS] Failed to send message`
**Common Causes**:
- Service bus queue full
- Authentication issues
- Network connectivity

**Solution**: Verify service bus configuration and capacity

### Load Testing Script

```bash
#!/bin/bash
# Webhook Load Testing Script

WEBHOOK_URL="https://your-function-app.azurewebsites.net/api/bland-ai-webhook?code=your-key"
CONCURRENT_REQUESTS=5
TOTAL_REQUESTS=100

echo "🚀 Starting webhook load test..."
echo "URL: $WEBHOOK_URL"
echo "Concurrent: $CONCURRENT_REQUESTS"
echo "Total: $TOTAL_REQUESTS"

# Create test payload
cat > test_payload.json << 'EOF'
{
  "call_id": "load_test_TIMESTAMP_RANDOM",
  "status": "completed",
  "to": "+15551234567",
  "metadata": {
    "attempt_id": "attempt_TIMESTAMP_RANDOM"
  },
  "disposition_tag": "INTERESTED",
  "call_length": 120
}
EOF

# Run load test
for i in $(seq 1 $TOTAL_REQUESTS); do
    # Generate unique call_id
    TIMESTAMP=$(date +%s)
    RANDOM_ID=$(shuf -i 1000-9999 -n 1)
    UNIQUE_CALL_ID="load_test_${TIMESTAMP}_${RANDOM_ID}"
    
    # Update payload with unique ID
    sed "s/load_test_TIMESTAMP_RANDOM/$UNIQUE_CALL_ID/g" test_payload.json > "payload_$i.json"
    
    # Send request in background
    (
        curl -s -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d @"payload_$i.json" \
            -w "Request $i: %{http_code} - %{time_total}s\n"
        rm "payload_$i.json"
    ) &
    
    # Limit concurrent requests
    if (( i % CONCURRENT_REQUESTS == 0 )); then
        wait
    fi
done

wait
rm test_payload.json
echo "✅ Load test completed"
```

This comprehensive webhook testing guide provides detailed scenarios, expected logs, troubleshooting steps, and monitoring queries to ensure your Bland AI webhook integration is working correctly across all scenarios.