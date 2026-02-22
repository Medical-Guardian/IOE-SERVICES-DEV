# Device Activation - Testing Guide

**Date:** 2025-12-24
**Version:** 1.0
**BusinessCaseID:** BC-DA-001 through BC-DA-008
**Purpose:** Comprehensive testing strategies, test scenarios, and validation procedures for Device Activation system

---

## Table of Contents

1. [Testing Overview](#1-testing-overview)
2. [Test Environment Setup](#2-test-environment-setup)
3. [Unit Testing](#3-unit-testing)
4. [Integration Testing](#4-integration-testing)
5. [End-to-End Testing Scenarios](#5-end-to-end-testing-scenarios)
6. [Test Data Management](#6-test-data-management)
7. [Validation Checkpoints](#7-validation-checkpoints)
8. [Performance Testing](#8-performance-testing)
9. [Regression Testing](#9-regression-testing)
10. [Troubleshooting Test Failures](#10-troubleshooting-test-failures)

---

## 1. Testing Overview

### 1.1 Testing Scope

Device Activation testing covers:
- **File Processing:** 5-phase ETL pipeline (CSV → Database)
- **Scheduler:** Eligibility determination, batch creation, callback processing
- **Bland AI Integration:** Batch submission, webhook processing
- **Database Operations:** CRUD operations, transactions, data integrity
- **Business Logic:** Call frequency, business hours, 90-day window
- **Error Handling:** Validation failures, API errors, rollback scenarios

### 1.2 Testing Levels

| Level | Scope | Tools | Frequency |
|-------|-------|-------|-----------|
| Unit | Individual functions/methods | pytest | Every commit |
| Integration | Component interactions | pytest + Azure Functions Core Tools | Daily |
| End-to-End | Complete workflows | Manual + Postman | Before deployment |
| Performance | Load, throughput, latency | Azure Application Insights | Weekly |
| Regression | Existing functionality | Automated test suite | Before release |

### 1.3 Success Criteria

✅ **All tests pass** with 100% success rate
✅ **Code coverage** ≥ 80% for critical paths
✅ **Performance** meets SLAs (file processing <60s, scheduler <10min, webhook <1s)
✅ **Data integrity** maintained across all failure scenarios
✅ **Error handling** gracefully handles all edge cases

---

## 2. Test Environment Setup

### 2.1 Local Development Environment

**Prerequisites:**
```bash
# Python 3.12 with virtual environment
python3.12 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # pytest, black, ruff, mypy

# Azure Functions Core Tools
func --version  # Should be 4.x
```

**Environment Variables (local.settings.json):**
```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "KEY_VAULT_URL": "https://your-dev-keyvault.vault.azure.net/",
    "DB_SECRET_NAME": "SqlConnectionStringIOE-Dev",
    "PYTHON_ISOLATE_WORKER_DEPENDENCIES": "1"
  }
}
```

**Database Setup:**
```sql
-- Create test database (copy of production schema, no data)
CREATE DATABASE engage360_test;

-- Restore schema from production backup
USE engage360_test;
-- Run schema creation scripts from database/ folder

-- Create test data (see Section 6)
```

### 2.2 Azure Test Environment

**Resource Group:** `rg-ioe-test`

**Resources:**
- Azure Function App: `ioe-function-test`
- SQL Database: `engage360-test`
- Blob Storage: `stdeviceactivation` (containers: fs-ops-test [PRIMARY], fs-device-activation-test [LEGACY])
- Key Vault: `kv-ioe-test`
- Application Insights: `appinsights-ioe-test`

**Configuration:**
```bash
# Deploy to test environment
az login
az account set --subscription "Test Subscription"
func azure functionapp publish ioe-function-test --python
```

---

## 3. Unit Testing

### 3.1 Test Structure

```
af_code/
├── device_activation_scheduler/
│   ├── services/
│   │   ├── eligibility_service.py
│   │   ├── batch_orchestrator.py
│   │   ├── callback_scheduler.py
│   │   └── tests/
│   │       ├── test_eligibility_service.py
│   │       ├── test_batch_orchestrator.py
│   │       └── test_callback_scheduler.py
├── af_device_activation_logic.py
└── tests/
    ├── test_file_processing.py
    ├── test_validation.py
    └── test_business_logic.py
```

### 3.2 Unit Test Examples

**Test File Processing (Phase 1 - Extract):**

```python
# af_code/tests/test_file_processing.py

import pytest
import pandas as pd
from af_code.af_device_activation_logic import extract, get_device_activation_schema

class TestFileProcessing:
    """
    Unit tests for Device Activation file processing

    BusinessCaseID: BC-DA-002
    """

    def test_extract_valid_csv(self, sample_csv_blob):
        """Test successful CSV extraction with valid data"""
        # Arrange
        context = ProcessingContext(
            file_name="MedicalGuardian_DeviceActivation_20250115_Delta.csv",
            file_id="test-file-id-123",
            blob_path="fs-ops/landing/..."
        )

        # Act
        result = extract(context)

        # Assert
        assert result['success'] is True
        assert result['dataframe'] is not None
        assert len(result['dataframe']) > 0
        assert result['phase'] == 'Phase 1: Extract'

    def test_extract_missing_columns(self, invalid_csv_blob):
        """Test extraction fails with missing required columns"""
        # Arrange
        context = ProcessingContext(
            file_name="Invalid_File.csv",
            file_id="test-file-id-456",
            blob_path="fs-ops/landing/..."
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Missing required columns"):
            extract(context)

    def test_pandera_schema_validation(self):
        """Test Pandera schema validates required data types"""
        # Arrange
        schema = get_device_activation_schema()

        valid_df = pd.DataFrame({
            'member_id': ['M001'],
            'first_name': ['John'],
            'last_name': ['Doe'],
            'primary_phone': ['555-123-4567'],
            # ... all 23 columns
        })

        # Act
        result = schema.validate(valid_df)

        # Assert
        assert result is not None
        assert len(result) == 1

    def test_pandera_schema_rejects_invalid_types(self):
        """Test Pandera schema rejects invalid data types"""
        # Arrange
        schema = get_device_activation_schema()

        invalid_df = pd.DataFrame({
            'member_id': [123],  # Should be string, not int
            'first_name': ['John'],
            # ... other columns
        })

        # Act & Assert
        with pytest.raises(pa.errors.SchemaError):
            schema.validate(invalid_df)
```

**Test Eligibility Service:**

```python
# af_code/device_activation_scheduler/services/tests/test_eligibility_service.py

import pytest
from datetime import datetime, timedelta
import pytz
from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService

class TestEligibilityService:
    """
    Unit tests for Eligibility Service

    BusinessCaseID: BC-DA-003, BC-DA-006
    """

    @pytest.fixture
    def eligibility_service(self, mock_db_service):
        """Fixture: EligibilityService instance with mocked database"""
        return EligibilityService(mock_db_service)

    def test_call_1_eligibility_no_previous_attempts(self, eligibility_service, mock_enrollment):
        """Test Call 1 eligibility: No previous attempts, activation_start_date reached"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 1
        mock_enrollment['last_attempt_date'] = None
        mock_enrollment['activation_start_date'] = datetime.now(pytz.UTC).date()

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is True

    def test_call_2_eligibility_2_business_days(self, eligibility_service, mock_enrollment):
        """Test Call 2 eligibility: 2 BUSINESS days after Call 1 (excludes weekends/holidays)"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 2
        # Last attempt: 2 business days ago (e.g., last Monday if today is Wednesday)
        mock_enrollment['last_attempt_date'] = datetime.now(pytz.UTC) - timedelta(days=2)

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is True

    def test_call_2_not_eligible_before_2_business_days(self, eligibility_service, mock_enrollment):
        """Test Call 2 NOT eligible: Only 1 business day after Call 1"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 2
        # Last attempt: 1 business day ago (not enough time elapsed)
        mock_enrollment['last_attempt_date'] = datetime.now(pytz.UTC) - timedelta(days=1)

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is False

    def test_call_4_eligibility_5_business_days(self, eligibility_service, mock_enrollment):
        """Test Call 4 eligibility: 5 BUSINESS days after Call 3"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 4
        # Last attempt: 5 business days ago (e.g., last Monday if today is next Monday)
        mock_enrollment['last_attempt_date'] = datetime.now(pytz.UTC) - timedelta(days=7)  # 7 calendar days = ~5 business days

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is True

    def test_call_5_eligibility_within_90_day_window(self, eligibility_service, mock_enrollment):
        """Test Call 5 eligibility: Within 90-day window"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 5
        mock_enrollment['last_attempt_date'] = datetime.now(pytz.UTC) - timedelta(days=8)
        mock_enrollment['call_5_timestamp'] = datetime.now(pytz.UTC) - timedelta(days=30)

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is True

    def test_call_6_not_eligible_after_90_day_window(self, eligibility_service, mock_enrollment):
        """Test Call 6 NOT eligible: 90-day window expired"""
        # Arrange
        mock_enrollment['call_attempt_number'] = 6
        mock_enrollment['last_attempt_date'] = datetime.now(pytz.UTC) - timedelta(days=8)
        mock_enrollment['call_5_timestamp'] = datetime.now(pytz.UTC) - timedelta(days=95)

        # Act
        is_eligible = eligibility_service._check_call_eligibility(mock_enrollment)

        # Assert
        assert is_eligible is False

    def test_business_hours_validation_both_timezones(self, eligibility_service, mock_campaign):
        """Test business hours validation requires both campaign AND member hours"""
        # Arrange
        member = {
            'member_id': 'M001',
            'timezone': 'America/Chicago',  # Central (1 hour behind Eastern)
            'member_current_time': '14:00:00'  # 2 PM Central
        }

        campaign = {
            'operating_tz': 'America/New_York',  # Eastern
            'operating_start_time': '09:00:00',
            'operating_end_time': '17:00:00',
            'timezone_flag': 'member_tz'
        }

        # Simulate current time: 3 PM EST (2 PM CST)
        # Campaign hours: PASS (3 PM EST is within 9 AM - 5 PM EST)
        # Member hours: PASS (2 PM CST is within 9 AM - 5 PM CST)

        # Act
        is_valid = eligibility_service._filter_by_business_hours([member], campaign)

        # Assert
        assert len(is_valid) == 1  # Member passed both checks

    def test_business_hours_validation_member_after_hours(self, eligibility_service, mock_campaign):
        """Test business hours validation FAILS if member is after hours"""
        # Arrange
        member = {
            'member_id': 'M001',
            'timezone': 'America/Los_Angeles',  # Pacific (3 hours behind Eastern)
            'member_current_time': '18:00:00'  # 6 PM Pacific (AFTER 5 PM)
        }

        campaign = {
            'operating_tz': 'America/New_York',
            'operating_start_time': '09:00:00',
            'operating_end_time': '17:00:00',
            'timezone_flag': 'member_tz'
        }

        # Simulate current time: 9 PM EST (6 PM PST)
        # Campaign hours: FAIL (9 PM EST is AFTER 5 PM EST)
        # Member hours: FAIL (6 PM PST is AFTER 5 PM PST)

        # Act
        is_valid = eligibility_service._filter_by_business_hours([member], campaign)

        # Assert
        assert len(is_valid) == 0  # Member failed business hours check
```

**Test Batch Orchestrator (3-Phase Tracking):**

```python
# af_code/device_activation_scheduler/services/tests/test_batch_orchestrator.py

import pytest
import uuid
from af_code.device_activation_scheduler.services.batch_orchestrator import BatchOrchestrator

class TestBatchOrchestrator:
    """
    Unit tests for Batch Orchestrator

    BusinessCaseID: BC-DA-004, BC-DA-006
    """

    @pytest.fixture
    def batch_orchestrator(self, mock_db_service, mock_config_manager):
        """Fixture: BatchOrchestrator instance with mocked dependencies"""
        return BatchOrchestrator(mock_db_service, mock_config_manager)

    def test_create_outreach_batch_phase_1(self, batch_orchestrator):
        """Test Phase 1: Create batch record with status='Pending'"""
        # Arrange
        campaign_id = str(uuid.uuid4())
        batch_size = 50

        # Act
        batch_id = batch_orchestrator._create_outreach_batch(campaign_id, batch_size)

        # Assert
        assert batch_id is not None
        assert isinstance(batch_id, str)

        # Verify database INSERT was called
        mock_db_service.execute_query.assert_called_once()
        call_args = mock_db_service.execute_query.call_args
        assert 'Pending' in str(call_args)

    def test_create_outreach_attempts_phase_2(self, batch_orchestrator, sample_members):
        """Test Phase 2: Create attempt records with disposition='Pending'"""
        # Arrange
        batch_id = str(uuid.uuid4())
        members = sample_members[:10]  # 10 members

        # Act
        attempt_ids = batch_orchestrator._create_outreach_attempts(batch_id, members)

        # Assert
        assert len(attempt_ids) == 10

        # Verify transaction executed (10 INSERTs in one transaction)
        mock_db_service.execute_transaction.assert_called_once()
        queries = mock_db_service.execute_transaction.call_args[0][0]
        assert len(queries) == 10

    def test_update_batch_with_vendor_id_phase_3(self, batch_orchestrator):
        """Test Phase 3: Update batch with vendor_batch_id and status='Submitted'"""
        # Arrange
        batch_id = str(uuid.uuid4())
        vendor_batch_id = "bland-batch-xyz-123"

        # Act
        batch_orchestrator._update_batch_with_vendor_id(batch_id, vendor_batch_id)

        # Assert
        mock_db_service.execute_query.assert_called_once()
        call_args = mock_db_service.execute_query.call_args
        assert vendor_batch_id in str(call_args)
        assert 'Submitted' in str(call_args)

    def test_batch_splitting_max_100_members(self, batch_orchestrator, sample_members):
        """Test batch splitting: Batches process 20 members per scheduler run"""
        # Arrange
        members = sample_members[:250]  # 250 members should create 3 batches

        # Act
        batches = batch_orchestrator._split_into_batches(members, max_size=100)

        # Assert
        assert len(batches) == 3
        assert len(batches[0]) == 100
        assert len(batches[1]) == 100
        assert len(batches[2]) == 50

    def test_call_5_timestamp_update(self, batch_orchestrator, sample_members):
        """Test Call 5 timestamp: Only set when call_attempt_number = 5"""
        # Arrange
        members_call_5 = [
            {**m, 'call_attempt_number': 5}
            for m in sample_members[:5]
        ]
        batch_id = str(uuid.uuid4())

        # Act
        batch_orchestrator._update_call_5_enrollments(batch_id, members_call_5)

        # Assert
        # Verify UPDATE query includes call_5_timestamp and campaign_end_date
        mock_db_service.execute_query.assert_called()
        call_args = str(mock_db_service.execute_query.call_args)
        assert 'call_5_timestamp' in call_args
        assert 'campaign_end_date' in call_args
        assert 'DATEADD(DAY, 90' in call_args
```

**Run Unit Tests:**

```bash
# Run all unit tests
pytest af_code/tests/ -v

# Run specific test file
pytest af_code/tests/test_file_processing.py -v

# Run with coverage report
pytest af_code/tests/ --cov=af_code --cov-report=html

# Run only tests matching pattern
pytest af_code/tests/ -k "test_call_5" -v
```

---

## 4. Integration Testing

### 4.1 File Processing Integration Test

**Test Scenario:** Upload CSV → File Processor Function → Database Validation

**Steps:**

1. **Prepare Test CSV:**

```csv
member_id,first_name,last_name,primary_phone,email,dob,timezone,language_pref,address_street,address_city,address_state,address_zip,member_brand,salesforce_account_number,device_id,device_name,brand,device_phone_number,is_device_callable,fall_detection,powersaver_mode,delivery_date,campaign_id
M001,John,Doe,555-123-4567,john.doe@example.com,1950-01-01,Eastern,EN,123 Main St,Boston,MA,02101,Medical Guardian,SF12345,D001,Mini Guardian,Medical Guardian,555-111-1111,Yes,Yes,No,2025-01-13,campaign-uuid-here
M002,Jane,Smith,555-987-6543,jane.smith@example.com,1955-05-15,Central,ES,456 Oak Ave,Chicago,IL,60601,Medical Guardian,SF67890,D002,Home Guardian,Medical Guardian,555-222-2222,Yes,No,Yes,2025-01-14,campaign-uuid-here
```

2. **Upload to Blob Storage:**

```bash
# Using Azure CLI
az storage blob upload \
  --account-name stdeviceactivation \
  --container-name fs-ops/landing \
  --name "MedicalGuardian_DeviceActivation_20250115_Delta.csv" \
  --file test_data.csv
```

3. **Monitor Function Execution:**

```bash
# Watch function logs (local)
func start --python

# Watch Azure logs
az functionapp log tail --name ioe-function-test --resource-group rg-ioe-test
```

4. **Validate Database:**

```sql
-- Check staging table
SELECT COUNT(*) AS staged_rows
FROM engage360_stg.stg_device_activation_delta
WHERE file_id = 'expected-file-id'
  AND processing_status = 'Completed';

-- Expected: 2 rows

-- Check members table
SELECT * FROM engage360.members
WHERE member_id IN ('M001', 'M002');

-- Expected: 2 rows with cleaned data

-- Check enrollments
SELECT * FROM engage360.member_campaign_enrollments_enhanced
WHERE member_id IN ('M001', 'M002');

-- Expected: 2 enrollments with status='ENROLLED', activation_start_date calculated

-- Check file processing log
SELECT * FROM engage360.file_processing_log
WHERE file_name = 'MedicalGuardian_DeviceActivation_20250115_Delta.csv';

-- Expected: 1 row with status='Completed'
```

5. **Validate Blob Movement:**

```bash
# Check file moved to processed/ folder
az storage blob list \
  --account-name stdeviceactivation \
  --container-name fs-ops/processed \
  --prefix "MedicalGuardian_DeviceActivation_20250115"
```

**Expected Results:**
- ✅ File processed successfully (processing_status='Completed')
- ✅ 2 rows in staging table
- ✅ 2 members in members table with proper case names
- ✅ 2 devices in member_devices table
- ✅ 2 enrollments with activation_start_date = delivery_date + 2 business days
- ✅ File moved to processed/ folder

### 4.2 Scheduler Integration Test

**Test Scenario:** Timer Trigger → Eligibility Query → Batch Creation → Bland AI Submission

**Steps:**

1. **Setup Test Data:**

```sql
-- Insert test member eligible for Call 1
INSERT INTO engage360.member_campaign_enrollments_enhanced (
    enrollment_id,
    member_id,
    campaign_id,
    current_status,
    activation_start_date,
    created_at,
    updated_at
)
VALUES (
    NEWID(),
    'M001',
    'device-activation-campaign-id',
    'ENROLLED',
    CAST(GETDATE() AS DATE),  -- Today (eligible for Call 1)
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

2. **Trigger Scheduler (Manual HTTP Trigger):**

```bash
# Local testing
curl -X POST http://localhost:7071/api/device_activation_scheduler

# Azure testing
curl -X POST https://ioe-function-test.azurewebsites.net/api/device_activation_scheduler
```

3. **Monitor Execution:**

```bash
# Check function logs for:
# - "✅ Found X eligible members"
# - "✅ Phase 1: Created batch"
# - "✅ Phase 2: Created X attempt records"
# - "✅ Submitted batch to Bland AI"
# - "✅ Phase 3: Updated vendor_batch_id"
```

4. **Validate Database:**

```sql
-- Check batch created
SELECT * FROM engage360.outreach_batches
WHERE batch_status = 'Submitted'
  AND created_at > DATEADD(MINUTE, -5, SYSDATETIMEOFFSET())
ORDER BY created_at DESC;

-- Expected: 1 batch with status='Submitted', vendor_batch_id populated

-- Check attempts created
SELECT * FROM engage360.outreach_attempts
WHERE batch_id = 'batch-id-from-above'
  AND disposition = 'Pending';

-- Expected: 1 attempt for member M001
```

5. **Validate Bland AI (Staging Environment):**

```bash
# Check Bland AI dashboard or API for batch
curl -X GET https://api.bland.ai/v1/batches/{vendor_batch_id} \
  -H "authorization: Bearer $BLAND_AI_KEY"

# Expected: Batch exists with status='processing' or 'completed'
```

**Expected Results:**
- ✅ 1 eligible member found
- ✅ 1 batch created with status='Pending' → 'Submitted'
- ✅ 1 attempt created with disposition='Pending'
- ✅ vendor_batch_id stored in outreach_batches
- ✅ Bland AI received batch (verify via API or dashboard)

### 4.3 Webhook Integration Test

**Test Scenario:** Bland AI Webhook → Webhook Function → Database Updates

**Steps:**

1. **Prepare Webhook Payload:**

```json
{
  "call_id": "test-call-id-12345",
  "batch_id": "vendor-batch-id-from-previous-test",
  "to": "+15551234567",
  "from": "+15559876543",
  "call_length": 180,
  "recording_url": "https://bland.ai/recordings/test-call-12345.mp3",
  "disposition": "INTERESTED",
  "transcript": "Member: Hello? Agent: Hi John, this is Medical Guardian calling to help you activate your device. Member: Oh yes, I already activated it yesterday! Agent: That's wonderful! Is it working properly? Member: Yes, everything is working great. Agent: Excellent! Have a great day.",
  "analysis": {
    "summary": "Member activated device successfully",
    "sentiment": "positive"
  },
  "metadata": {
    "member_id": "M001",
    "enrollment_id": "enrollment-id-from-previous-test",
    "campaign_id": "device-activation-campaign-id",
    "campaign_type": "DeviceActivation",
    "batch_id": "batch-id-from-previous-test",
    "attempt_id": "attempt-id-from-previous-test",
    "call_attempt_number": "1",
    "salesforce_account_number": "SF12345",
    "email": "john.doe@example.com",
    "address_city": "Boston",
    "address_state": "MA",
    "dob": "1950-01-01",
    "member_brand": "Medical Guardian"
  },
  "completed_at": "2025-01-15T14:45:30Z"
}
```

2. **Send Webhook POST:**

```bash
# Local testing
curl -X POST http://localhost:7071/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -d @webhook_payload.json

# Azure testing
curl -X POST https://ioe-function-test.azurewebsites.net/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-webhook-api-key" \
  -d @webhook_payload.json
```

3. **Validate Response:**

```json
{
  "status": "success",
  "message": "Webhook processed",
  "call_id": "test-call-id-12345"
}
```

4. **Validate Database Updates:**

```sql
-- Check attempt updated
SELECT disposition, completed_at, call_length, recording_url
FROM engage360.outreach_attempts
WHERE attempt_id = 'attempt-id-from-payload';

-- Expected: disposition='Completed', completed_at populated, call_length=180

-- Check call log created
SELECT * FROM engage360.bland_call_logs
WHERE call_id = 'test-call-id-12345';

-- Expected: 1 row with complete webhook payload in metadata

-- Check duplicate detection (send webhook again)
-- Expected: 200 OK but no duplicate database insert
```

5. **Test Duplicate Detection:**

```bash
# Send same webhook payload again
curl -X POST http://localhost:7071/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -d @webhook_payload.json

# Expected: 200 OK response
# Database should still have only 1 row in bland_call_logs
```

**Expected Results:**
- ✅ Webhook processed successfully (200 OK)
- ✅ Attempt disposition updated to 'Completed'
- ✅ Call log inserted with full transcript and metadata
- ✅ Duplicate webhook returns 200 OK but skips processing

---

## 5. End-to-End Testing Scenarios

### 5.1 Scenario 1: New Member Enrollment → Call 1 → Success

**Narrative:** Member receives device, file processed, eligible for Call 1, call made, member activated device

**Steps:**

1. Upload CSV with new member (delivery_date = today - 2 business days)
2. Wait for file processing (30-60 seconds)
3. Validate enrollment created with activation_start_date = today
4. Wait for scheduler run (up to 15 minutes)
5. Validate batch created and submitted to Bland AI
6. Send webhook with disposition='INTERESTED'
7. Validate attempt marked 'Completed', enrollment remains 'ENROLLED'

**Validation SQL:**

```sql
-- Step 2: Check enrollment
SELECT * FROM engage360.member_campaign_enrollments_enhanced
WHERE member_id = 'TEST-M001'
  AND current_status = 'ENROLLED'
  AND activation_start_date = CAST(GETDATE() AS DATE);

-- Step 5: Check batch
SELECT * FROM engage360.outreach_batches
WHERE batch_status = 'Submitted'
  AND created_at > DATEADD(MINUTE, -20, SYSDATETIMEOFFSET());

-- Step 7: Check attempt
SELECT * FROM engage360.outreach_attempts
WHERE enrollment_id = (SELECT enrollment_id FROM engage360.member_campaign_enrollments_enhanced WHERE member_id = 'TEST-M001')
  AND disposition = 'Completed';
```

**Expected Timeline:**
- T+0: CSV uploaded
- T+60s: File processing complete, enrollment created
- T+15m: Scheduler runs, batch created, Bland AI submission
- T+20m: Webhook received, attempt marked 'Completed'

### 5.2 Scenario 2: Call 1-4 Sequence with NoAnswer

**Narrative:** Member doesn't answer first 4 calls, transitions to Call 5+ logic

**Steps:**

1. **Day 1 (Monday):** Call 1 made, webhook disposition='NO_ANSWER'
2. **Day 3 (Wed, +2 BUSINESS days):** Call 2 made, webhook disposition='NO_ANSWER'
3. **Day 5 (Fri, +2 BUSINESS days):** Call 3 made, webhook disposition='NO_ANSWER'
4. **Day 12 (Fri, +5 BUSINESS days):** Call 4 made, webhook disposition='NO_ANSWER'
5. **Day 19 (Fri, +7 CALENDAR days):** Call 5 made, webhook disposition='INTERESTED', call_5_timestamp set
6. Validate campaign_end_date = call_5_timestamp + 90 CALENDAR days

**Validation SQL:**

```sql
-- After Call 4
SELECT COUNT(*) AS attempt_count
FROM engage360.outreach_attempts
WHERE enrollment_id = 'test-enrollment-id'
  AND disposition = 'NoAnswer';
-- Expected: 4

-- After Call 5
SELECT call_5_timestamp, campaign_end_date
FROM engage360.member_campaign_enrollments_enhanced
WHERE enrollment_id = 'test-enrollment-id';
-- Expected: call_5_timestamp populated, campaign_end_date = call_5_timestamp + 90 days

-- Validate 90-day window calculation
SELECT
    call_5_timestamp,
    campaign_end_date,
    DATEDIFF(DAY, call_5_timestamp, campaign_end_date) AS days_diff
FROM engage360.member_campaign_enrollments_enhanced
WHERE enrollment_id = 'test-enrollment-id';
-- Expected: days_diff = 90
```

### 5.3 Scenario 3: Callback Request → Reschedule → Success

**Narrative:** Member requests callback, initially outside business hours, rescheduled, then successful

**Steps:**

1. Send webhook with disposition='CALL_BACK_SCHEDULED', scheduled_callback_time = today 6:00 PM (after hours)
2. Validate callback created with status='Pending'
3. Wait for scheduler run (up to 15 minutes after 6:00 PM)
4. Validate callback rescheduled to next business day 9:00 AM, attempt_count = 1
5. Wait for scheduler run next day at 9:00 AM
6. Validate callback submitted to Bland AI, status='Completed'

**Validation SQL:**

```sql
-- Step 2: Check callback created
SELECT * FROM engage360.outreach_callback_queue
WHERE enrollment_id = 'test-enrollment-id'
  AND status = 'Pending';

-- Step 4: Check callback rescheduled
SELECT scheduled_callback_time, attempt_count, last_rescheduled_at
FROM engage360.outreach_callback_queue
WHERE enrollment_id = 'test-enrollment-id';
-- Expected: scheduled_callback_time = next business day 9 AM, attempt_count = 1

-- Step 6: Check callback completed
SELECT status, completed_at
FROM engage360.outreach_callback_queue
WHERE enrollment_id = 'test-enrollment-id';
-- Expected: status='Completed'
```

### 5.4 Scenario 4: Member Opt-Out

**Narrative:** Member requests DO_NOT_CONTACT, enrollment status updated, no more calls

**Steps:**

1. Send webhook with disposition='DO_NOT_CONTACT'
2. Validate attempt disposition='OptedOut'
3. Validate enrollment status updated to 'OPTED_OUT'
4. Validate status history logged
5. Wait for next scheduler run
6. Validate member NOT included in eligible members query

**Validation SQL:**

```sql
-- Step 3: Check enrollment status
SELECT current_status, updated_at
FROM engage360.member_campaign_enrollments_enhanced
WHERE enrollment_id = 'test-enrollment-id';
-- Expected: current_status='OPTED_OUT'

-- Step 4: Check status history
SELECT previous_status, new_status, change_reason
FROM engage360.member_enrollment_status_history
WHERE enrollment_id = 'test-enrollment-id'
ORDER BY changed_at DESC;
-- Expected: previous_status='ENROLLED', new_status='OPTED_OUT', change_reason contains 'DO_NOT_CONTACT'

-- Step 6: Run eligibility query manually
-- Member with enrollment_id='test-enrollment-id' should NOT appear in results
```

---

## 6. Test Data Management

### 6.1 Test Member Data

**Create Test Members:**

```sql
-- Test Member 1: Call 1 eligible today
INSERT INTO engage360.members (member_id, first_name, last_name, primary_phone, email, timezone, created_at, updated_at)
VALUES ('TEST-M001', 'Test', 'Member1', '+15551111111', 'test1@example.com', 'America/New_York', SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());

INSERT INTO engage360.member_devices (device_id, member_id, device_name, brand, is_device_callable, fall_detection, powersaver_mode, created_at, updated_at)
VALUES ('TEST-D001', 'TEST-M001', 'Mini Guardian', 'Medical Guardian', 1, 1, 0, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());

INSERT INTO engage360.member_campaign_enrollments_enhanced (enrollment_id, member_id, campaign_id, current_status, activation_start_date, created_at, updated_at)
VALUES (
    'TEST-E001',
    'TEST-M001',
    'device-activation-campaign-id',
    'ENROLLED',
    CAST(GETDATE() AS DATE),  -- Today (eligible for Call 1)
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);

-- Test Member 2: Call 5 eligible (has 4 previous attempts, 7+ days ago)
INSERT INTO engage360.members (member_id, first_name, last_name, primary_phone, email, timezone, created_at, updated_at)
VALUES ('TEST-M002', 'Test', 'Member2', '+15552222222', 'test2@example.com', 'America/Chicago', SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());

INSERT INTO engage360.member_devices (device_id, member_id, device_name, brand, is_device_callable, fall_detection, powersaver_mode, created_at, updated_at)
VALUES ('TEST-D002', 'TEST-M002', 'Home Guardian', 'Medical Guardian', 1, 0, 1, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());

INSERT INTO engage360.member_campaign_enrollments_enhanced (enrollment_id, member_id, campaign_id, current_status, activation_start_date, call_5_timestamp, campaign_end_date, created_at, updated_at)
VALUES (
    'TEST-E002',
    'TEST-M002',
    'device-activation-campaign-id',
    'ENROLLED',
    CAST(DATEADD(DAY, -30, GETDATE()) AS DATE),
    NULL,  -- Will be set when Call 5 created
    NULL,
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);

-- Create 4 previous attempts for TEST-M002
DECLARE @i INT = 1;
WHILE @i <= 4
BEGIN
    INSERT INTO engage360.outreach_attempts (attempt_id, enrollment_id, batch_id, disposition, attempt_ts, created_at, updated_at)
    VALUES (
        NEWID(),
        'TEST-E002',
        NEWID(),  -- Dummy batch_id
        'NoAnswer',
        DATEADD(DAY, -30 + (@i * 2), SYSDATETIMEOFFSET()),  -- Spread over 8 days, 30 days ago
        SYSDATETIMEOFFSET(),
        SYSDATETIMEOFFSET()
    );
    SET @i = @i + 1;
END
```

### 6.2 Test CSV Files

**Minimal Test CSV (test_minimal.csv):**

```csv
member_id,first_name,last_name,primary_phone,email,dob,timezone,language_pref,address_street,address_city,address_state,address_zip,member_brand,salesforce_account_number,device_id,device_name,brand,device_phone_number,is_device_callable,fall_detection,powersaver_mode,delivery_date,campaign_id
TEST-M003,Alice,Johnson,555-333-3333,alice@example.com,1960-06-15,Eastern,EN,789 Elm St,New York,NY,10001,Medical Guardian,SF11111,TEST-D003,Mini Guardian,Medical Guardian,555-333-3330,Yes,Yes,No,2025-01-13,campaign-uuid
```

**Error Test CSV (test_errors.csv) - 50% invalid rows:**

```csv
member_id,first_name,last_name,primary_phone,email,dob,timezone,language_pref,address_street,address_city,address_state,address_zip,member_brand,salesforce_account_number,device_id,device_name,brand,device_phone_number,is_device_callable,fall_detection,powersaver_mode,delivery_date,campaign_id
VALID001,Bob,Smith,555-444-4444,bob@example.com,1965-03-20,Central,EN,123 Main,Dallas,TX,75001,Medical Guardian,SF22222,DEV001,Home Guardian,Medical Guardian,555-444-4440,Yes,No,Yes,2025-01-14,campaign-uuid
INVALID001,Carol,Davis,INVALID_PHONE,carol@example.com,1970-08-10,INVALID_TZ,EN,456 Oak,Miami,FL,33101,Medical Guardian,SF33333,DEV002,Mini Guardian,Medical Guardian,555-555-5550,Yes,Yes,No,2025-01-15,campaign-uuid
VALID002,David,Wilson,555-666-6666,david@example.com,1955-12-05,Pacific,EN,789 Pine,Seattle,WA,98101,Medical Guardian,SF44444,DEV003,Home Guardian,Medical Guardian,555-666-6660,Yes,No,No,2025-01-16,campaign-uuid
INVALID002,Eve,Taylor,555-777-7777,INVALID_EMAIL,1980-04-25,Mountain,EN,321 Birch,Denver,CO,80201,Medical Guardian,SF55555,DEV004,Mini Guardian,Medical Guardian,555-777-7770,Yes,Yes,Yes,INVALID_DATE,campaign-uuid
```

**Expected:** File rejected (50% error rate exceeds 50% validation threshold)

### 6.3 Cleanup Test Data

```sql
-- Delete test members and cascading data
DELETE FROM engage360.member_campaign_enrollments_enhanced WHERE member_id LIKE 'TEST-%';
DELETE FROM engage360.member_devices WHERE member_id LIKE 'TEST-%';
DELETE FROM engage360.members WHERE member_id LIKE 'TEST-%';

-- Delete test batches
DELETE FROM engage360.outreach_batches WHERE batch_name LIKE '%Test%';

-- Delete test staging data
DELETE FROM engage360_stg.stg_device_activation_delta WHERE file_id LIKE 'TEST-%';

-- Delete test call logs
DELETE FROM engage360.bland_call_logs WHERE call_id LIKE 'test-%';
```

---

## 7. Validation Checkpoints

### 7.1 File Processing Checkpoints

| Checkpoint | Validation Query | Expected Result |
|------------|------------------|-----------------|
| CSV uploaded | `SELECT * FROM sys.dm_filestream_non_transacted_segments` | File visible in blob storage |
| Staging INSERT | `SELECT COUNT(*) FROM stg_device_activation_delta WHERE file_id = ?` | Row count matches CSV rows |
| Validation pass | `SELECT COUNT(*) FROM stg_device_activation_delta WHERE validation_status = 'Valid'` | ≥50% of rows valid |
| Members MERGE | `SELECT * FROM members WHERE member_id = ?` | Member exists with cleaned data |
| Enrollments INSERT | `SELECT * FROM member_campaign_enrollments_enhanced WHERE member_id = ?` | Enrollment exists, status='ENROLLED' |
| activation_start_date | `SELECT activation_start_date, delivery_date FROM ... WHERE member_id = ?` | activation_start_date = delivery_date + 2 business days |
| Blob movement | Check processed/ folder | File moved to processed/ |

### 7.2 Scheduler Checkpoints

| Checkpoint | Validation Query | Expected Result |
|------------|------------------|-----------------|
| Eligibility query | Run eligibility query manually | Returns expected members |
| Business hours | Check member_current_time in query | All members within business hours |
| Batch created (Phase 1) | `SELECT * FROM outreach_batches WHERE batch_status = 'Pending'` | Batch exists |
| Attempts created (Phase 2) | `SELECT COUNT(*) FROM outreach_attempts WHERE batch_id = ?` | Count = batch_size |
| Bland AI submission | Check Bland AI dashboard | Batch exists in Bland AI |
| Batch updated (Phase 3) | `SELECT vendor_batch_id FROM outreach_batches WHERE batch_id = ?` | vendor_batch_id populated |
| Call 5 timestamp | `SELECT call_5_timestamp FROM ... WHERE enrollment_id = ?` | Timestamp set for Call 5 only |

### 7.3 Webhook Checkpoints

| Checkpoint | Validation Query | Expected Result |
|------------|------------------|-----------------|
| Webhook received | Check function logs | "Webhook received for call_id: ..." |
| Duplicate detection | `SELECT COUNT(*) FROM bland_call_logs WHERE call_id = ?` | 0 (new) or 1 (duplicate) |
| Attempt updated | `SELECT disposition FROM outreach_attempts WHERE attempt_id = ?` | Disposition matches webhook |
| Enrollment updated | `SELECT current_status FROM ... WHERE enrollment_id = ?` | Status = 'OPTED_OUT' (if DO_NOT_CONTACT) |
| Callback created | `SELECT * FROM outreach_callback_queue WHERE enrollment_id = ?` | Callback exists (if CALL_BACK_SCHEDULED) |
| Call log created | `SELECT * FROM bland_call_logs WHERE call_id = ?` | Log exists with full payload |

---

## 8. Performance Testing

### 8.1 File Processing Performance

**Test:** Process CSV with 1000 rows

**Steps:**
1. Create CSV with 1000 valid rows
2. Upload to blob storage
3. Measure time from upload to file moved to processed/

**Expected Performance:**
- Total time: <60 seconds
- Phase 1 (Extract): <5 seconds
- Phase 2 (Staging): <20 seconds (20ms per row)
- Phase 3 (Validation): <10 seconds
- Phase 4 (Transform): <20 seconds
- Phase 5 (Audit): <5 seconds

**Validation:**

```sql
-- Check processing duration
SELECT
    file_name,
    rows_total,
    duration_seconds,
    rows_total / duration_seconds AS rows_per_second
FROM engage360.file_processing_log
WHERE file_id = ?;

-- Expected: rows_per_second ≥ 16 (1000 rows / 60 seconds)
```

### 8.2 Scheduler Performance

**Test:** Scheduler with 1000 eligible members

**Steps:**
1. Create 1000 test enrollments eligible for Call 1
2. Trigger scheduler manually
3. Measure time from trigger to last batch submitted

**Expected Performance:**
- Eligibility query: <5 seconds
- Business hours filtering: <1 second
- Batch creation (10 batches of 100): <30 seconds (3 seconds per batch)
- Total: <40 seconds

**Validation:**

```bash
# Check Application Insights for scheduler execution duration
az monitor app-insights metrics show \
  --app appinsights-ioe-test \
  --metric "requests/duration" \
  --filter "name eq 'device_activation_scheduler'"

# Expected: avg duration <40 seconds
```

### 8.3 Webhook Performance

**Test:** Process 100 webhooks concurrently

**Steps:**
1. Send 100 webhook POST requests simultaneously (use load testing tool)
2. Measure response time

**Expected Performance:**
- P50 (median): <500ms
- P95: <1000ms
- P99: <2000ms

**Load Testing Script (Apache Bench):**

```bash
# Create 100 copies of webhook payload in files webhook_001.json through webhook_100.json
# Each with unique call_id

# Run concurrent requests
ab -n 100 -c 10 -p webhook_payload.json -T application/json \
   https://ioe-function-test.azurewebsites.net/api/bland_ai_webhook

# Expected: Requests per second ≥ 50
```

---

## 9. Regression Testing

### 9.1 Regression Test Suite

**Run before every release:**

```bash
# Full regression test suite
pytest af_code/tests/ --regression -v

# Includes:
# - All unit tests (3.x)
# - All integration tests (4.x)
# - Critical end-to-end scenarios (5.1, 5.2, 5.4)
# - Performance benchmarks (8.x)
```

### 9.2 Critical Regression Scenarios

| Scenario | Description | Test File |
|----------|-------------|-----------|
| CSV validation | Pandera schema accepts valid CSV, rejects invalid | `test_file_processing.py::test_pandera_validation` |
| Call frequency | Call 2 not eligible before 2 business days | `test_eligibility_service.py::test_call_2_frequency` |
| 90-day window | Call 6 not eligible after 90 days | `test_eligibility_service.py::test_call_6_after_window` |
| Business hours | Member excluded if outside business hours | `test_eligibility_service.py::test_business_hours` |
| 3-phase tracking | Batch rollback if Bland AI fails | `test_batch_orchestrator.py::test_rollback_on_error` |
| Callback timeout | Callback timeout after 24h OR 3 attempts | `test_callback_scheduler.py::test_timeout` |
| Opt-out | Enrollment status updated to OPTED_OUT | `test_webhook_processing.py::test_opt_out` |

---

## 10. Troubleshooting Test Failures

### 10.1 File Processing Failures

**Symptom:** File not processed, remains in landing/ folder

**Debug Steps:**

1. **Check function logs:**
```bash
func start --python  # Local
# OR
az functionapp log tail --name ioe-function-test  # Azure

# Look for errors in logs
```

2. **Check blob trigger:**
```sql
-- Verify blob trigger fired
SELECT * FROM sys.dm_exec_requests WHERE command LIKE '%blob%';
```

3. **Check staging table:**
```sql
-- Check if any rows inserted
SELECT * FROM engage360_stg.stg_device_activation_delta
WHERE file_id = 'expected-file-id';

-- If 0 rows: Phase 1 or Phase 2 failed
-- Check logs for Pandera validation errors
```

4. **Check validation errors:**
```sql
-- Check validation errors
SELECT validation_error, COUNT(*) AS error_count
FROM engage360_stg.stg_device_activation_delta
WHERE file_id = 'expected-file-id'
  AND validation_status = 'Invalid'
GROUP BY validation_error;
```

**Common Issues:**

| Error | Cause | Solution |
|-------|-------|----------|
| "Missing required columns" | CSV missing columns | Add missing columns to CSV |
| "Pandera SchemaError" | Invalid data types | Fix data types in CSV |
| "Error threshold exceeded" | >10% staging errors | Review error_count in logs, fix data |
| "Validation threshold exceeded" | >50% validation errors | Review validation_error in staging table |

### 10.2 Scheduler Failures

**Symptom:** No batches created, members not called

**Debug Steps:**

1. **Check eligibility query:**
```sql
-- Run eligibility query manually
-- (Copy from eligibility_service.py)
-- Check if any members returned
```

2. **Check business hours:**
```sql
-- Verify current time vs operating hours
SELECT
    SYSDATETIMEOFFSET() AS current_time_utc,
    CONVERT(TIME, SYSDATETIMEOFFSET() AT TIME ZONE 'America/New_York') AS current_time_est;

-- Compare to campaign operating hours (9 AM - 5 PM EST)
```

3. **Check batch creation:**
```sql
-- Check for failed batches
SELECT * FROM engage360.outreach_batches
WHERE batch_status = 'Failed'
  AND created_at > DATEADD(HOUR, -1, SYSDATETIMEOFFSET());
```

**Common Issues:**

| Error | Cause | Solution |
|-------|-------|----------|
| "No eligible members" | All members outside business hours | Wait for business hours or adjust test data |
| "Bland AI submission failed" | API key invalid | Check KEY_VAULT_URL and BlandAIkey secret |
| "Phase 2 transaction failed" | Database connection error | Check DB_SECRET_NAME and connection string |

### 10.3 Webhook Failures

**Symptom:** Webhook returns error, database not updated

**Debug Steps:**

1. **Check webhook payload:**
```bash
# Validate JSON structure
cat webhook_payload.json | jq .

# Ensure required fields present: call_id, metadata.attempt_id, disposition
```

2. **Check duplicate detection:**
```sql
-- Check if call_id already processed
SELECT * FROM engage360.bland_call_logs
WHERE call_id = 'call-id-from-payload';

-- If exists: Webhook is duplicate (expected behavior)
```

3. **Check database transaction:**
```bash
# Check function logs for transaction errors
# Look for "Transaction failed" or "Rollback"
```

**Common Issues:**

| Error | Cause | Solution |
|-------|-------|----------|
| "Missing required field" | Webhook payload incomplete | Verify metadata contains all 13 fields |
| "Duplicate call_id" | Bland AI retried webhook | Expected behavior, returns 200 OK |
| "Transaction failed" | Database constraint violation | Check foreign key constraints (enrollment_id, attempt_id exist) |

---

## Summary

This testing guide provides comprehensive strategies for validating Device Activation functionality:

1. **Unit Testing:** Individual function/method tests with mocked dependencies
2. **Integration Testing:** Component interaction tests (file processor → database, scheduler → Bland AI)
3. **End-to-End Testing:** Complete workflow scenarios (enrollment → calls → outcomes)
4. **Test Data Management:** Scripts to create, validate, and cleanup test data
5. **Validation Checkpoints:** SQL queries to verify correctness at each step
6. **Performance Testing:** Load and throughput benchmarks
7. **Regression Testing:** Automated suite for pre-release validation
8. **Troubleshooting:** Debug steps for common failure scenarios

**Test Coverage Goals:**
- Unit tests: 80%+ code coverage
- Integration tests: All critical paths
- End-to-end tests: All user scenarios
- Performance tests: Meet SLA requirements

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md) - System design
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md) - SQL queries
- [Deployment Guide](DEVICE_ACTIVATION_DEPLOYMENT_GUIDE.md) - Deployment procedures
- [Troubleshooting Guide](DEVICE_ACTIVATION_TROUBLESHOOTING.md) - Production debugging

---

**End of Document**
