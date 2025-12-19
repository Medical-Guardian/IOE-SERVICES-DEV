# Implementation Plan: Device Activation CSV File Ingestion & Validation System

## Overview
Create a complete ETL pipeline for Device Activation campaign CSV files following DTC and Partner campaign patterns. The system will process member/device data from SFTP, validate against business rules, cleanse data, and merge into core database tables.

---

## Current State

**✅ COMPLETED:**
1. `DEVICE_ACTIVATION_DATA_SPECIFICATION.md` - Complete data spec (24 CSV fields)
2. `IOE_Device_Activation_System_Specification.md` - Workflow documentation
3. `DEVICE_ACTIVATION_CSV_REFERENCE.md` - Comprehensive CSV file format reference with validation rules
4. `SAMPLE_DEVICE_ACTIVATION.csv` - Sample CSV file with 10 test records
5. `af_code/shared/business_hours_utils.py` - Holiday + dual-timezone validation
6. Exploration of DTC/Partner ingestion patterns (3 agents completed)
7. **Existing database tables ready** (members, member_devices, member_campaign_enrollments_enhanced, staging)
6. **`af_code/af_device_activation_logic.py`** - Core processing logic (1,247 lines)
   - All 5 ETL phases implemented (Extract → Load → Validate → Transform → Audit)
   - 13 validation functions (phone, email, device status, delivery date, customer type, etc.)
   - Business day calculations using `business_hours_utils.add_business_days()`
   - MERGE statements for members and member_devices tables
   - 90-day campaign lifecycle with activation_start_date calculation
7. **`functions/device_activation_file_processor.py`** - Azure Function blob trigger (91 lines)
   - Blob trigger for `fs-device-activation/landing/{name}`
   - Filename validation: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`
   - Registered in `function_app.py` with error handling
8. **`tests/test_device_activation_logic.py`** - Comprehensive unit tests (628 lines)
   - Phone number validation tests (10 test cases)
   - Email validation tests (6 test cases)
   - Timezone validation tests (8 test cases)
   - Device status validation tests (14 test cases)
   - Delivery date validation tests (8 test cases)
   - Customer type validation tests (6 test cases)
   - Business day calculation tests (2 test cases)
   - Row-level validation tests (2 test cases)
   - Data model tests (4 test cases)

**❌ TODO (Integration & Deployment):**
1. Campaign setup: Create `device_activation` campaign in `engage360.campaigns_enhanced`
2. Blob storage setup: Create `fs-device-activation` container with folders (landing/, staging/, processed/, error/)
3. Integration testing with sample CSV file
4. Production deployment verification

**Note:** Database schema already exists - this is a **new requirement with new data**. No migrations needed.

---

## Implementation Phases

### **Phase 1: Core Processing Logic (PRIORITY 1)**

#### **File:** `af_code/af_device_activation_logic.py`
**Pattern:** Follow `af_code/af_dtc_logic.py` (2900 lines)
**Size estimate:** ~2500 lines

**Structure (5-phase ETL):**

```python
# Phase 1: Extract
def extract(file_path, context) -> Tuple[pd.DataFrame, ProcessingResult]:
    """
    - Download CSV from blob storage (landing/ folder)
    - Parse CSV into DataFrame
    - Add metadata columns (file_batch_id, row_number, timestamps)
    - Pandera schema validation (structural)
    - Move file to staging/ folder
    """

# Phase 2: Load to Staging
def load_to_staging(df, context) -> ProcessingResult:
    """
    - Call validate_and_cleanse_data_before_insert()
    - Check error threshold (10% default)
    - Filter to VALIDATED rows
    - Bulk INSERT into stg_device_activation_delta
    """

# Phase 3: Validate Data (SQL-based cleansing)
def validate_data(context) -> ProcessingResult:
    """
    - UPDATE staging with SQL cleansing functions
    - Lookup org_id from partner_name
    - Apply fn_standardize_phone, fn_proper_case
    - Convert dates, booleans
    - Mark as VALIDATED
    """

# Phase 4: Transform & Load Core Tables
def transform_and_load_core(context) -> ProcessingResult:
    """
    - Get device_activation campaign_id
    - Check for duplicates
    - MERGE INTO members (use salesforce_account_id + salesforce_account_number)
    - MERGE INTO member_devices (add brand, delivery_date, status fields)
    - INSERT INTO member_campaign_enrollments_enhanced
      • Calculate activation_start_date = delivery_date + 2 business days
      • Calculate campaign_end_date = activation_start_date + 90 days
      • Set customer_type (DTC or MS)
    - Mark staging as PROCESSED
    """

# Phase 5: Audit & Log
def audit_and_log(context) -> ProcessingResult:
    """
    - UPDATE file_processing_log
    - INSERT processing_step_log
    - Move file to processed/ folder
    """
```

---

**Key Validation Functions:**

```python
def validate_and_cleanse_data_before_insert(df, context):
    """
    Row-by-row validation (600+ lines)

    Validations:
    1. Partner name = "Medical Guardian"
    2. Salesforce IDs (both account_id and account_number)
    3. Phone numbers → E.164 format
    4. Names → Proper case
    5. Timezone → IANA format (America/New_York)
    6. Language → ISO 639 → EN/ES/Other
    7. DOB → DATE type
    8. Email → Valid format
    9. Device UDI → Required, non-empty
    10. Device status → Constrained values
    11. Delivery date → Not in future
    12. Customer type → DTC or MS
    13. is_device_callable → Y/N boolean

    Returns: DataFrame with validation_status, error_message
    """

def validate_device_status_fields(row):
    """
    Validate fall_detection_status and battery_status

    Valid fall_detection_status:
    - Active, Inactive, Not Applicable, Unknown

    Valid battery_status:
    - Good, Low, Critical, Charging, Unknown
    """

def calculate_activation_dates(delivery_date):
    """
    Calculate campaign dates using business_hours_utils

    activation_start_date = add_business_days(delivery_date, 2)
    campaign_end_date = activation_start_date + timedelta(days=90)

    Uses: business_hours_utils.add_business_days()
    - Skips weekends
    - Skips federal holidays
    """
```

---

### **Phase 2: Azure Function Blob Trigger**

#### **File:** `functions/device_activation_file_processor.py`
**Pattern:** Follow `functions/dtc_file_processor.py`
**Size:** ~80 lines

```python
import azure.functions as func
import logging
from af_code.af_device_activation_logic import process_device_activation_file_complete

app = func.FunctionApp()

@app.blob_trigger(
    arg_name="myblob",
    path="fs-device-activation/landing/{name}",
    connection="AzureWebJobsStorage"
)
def ProcessDeviceActivationBlob(myblob: func.InputStream):
    """
    Azure Function blob trigger for Device Activation CSV files

    Trigger path: fs-device-activation/landing/
    Expected filename: MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv
    """
    filename = myblob.name.split('/')[-1]

    # Validate filename pattern
    if not (filename.startswith("MedicalGuardian_DeviceActivation_")
            and filename.endswith("_Delta.csv")):
        logging.warning(f"⚠️ File skipped due to invalid naming: {filename}")
        return

    logging.info(f"📄 Processing Device Activation file: {filename}")

    # Process file
    success, message, details = process_device_activation_file_complete(
        file_path=myblob.name,
        connection_string=None,  # Retrieved from Key Vault
        uploaded_by_user="AzureFunction",
        error_threshold_pct=10.0,
        log_level="INFO"
    )

    if success:
        logging.info(f"✅ {message}")
    else:
        logging.error(f"❌ {message}")
```

---

### **Phase 3: Key Differences from DTC**

| Aspect | DTC Wellness | Device Activation |
|--------|-------------|-------------------|
| **CSV Fields** | 28 fields | 24 fields |
| **Caregiver** | Required (5 fields) | ❌ Not needed |
| **checkin_time** | Required (AM/PM/EV) | ❌ Not needed |
| **salesforce_account_id** | Not used | ✅ Required (NEW) |
| **Device Status** | Not tracked | ✅ fall_detection, battery (NEW) |
| **Delivery Date** | Not tracked | ✅ Required (for Day 2 calc) |
| **Customer Type** | Not in CSV | ✅ DTC/MS (affects workflow) |
| **Campaign** | 2 campaigns (intro + wellness) | 1 campaign (device_activation) |
| **Blob Container** | fs-dtc | fs-device-activation |
| **Filename Pattern** | DTCWellness | DeviceActivation |

---

### **Phase 4: Database Operations (MERGE Patterns)**

#### **MERGE INTO members**
**Match key:** `org_id + salesforce_account_number`

```sql
MERGE engage360.members AS tgt
USING (
    SELECT
        stg.org_id,
        stg.salesforce_account_id,      -- NEW FIELD
        stg.salesforce_account_number,
        stg.first_name_clean AS first_name,
        stg.primary_phone_clean AS primary_phone,
        stg.service_address AS address_street,  -- Different from DTC
        stg.dob AS dob
    FROM engage360_stg.stg_device_activation_delta stg
    WHERE stg.file_batch_id = %s AND stg.processing_status = 'TRANSFORMING'
) AS src
ON (tgt.org_id = src.org_id AND tgt.salesforce_account_number = src.salesforce_account_number)
WHEN MATCHED THEN
    UPDATE SET
        salesforce_account_id = ISNULL(src.salesforce_account_id, tgt.salesforce_account_id),
        first_name = ISNULL(src.first_name, tgt.first_name),
        updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (member_id, org_id, salesforce_account_id, salesforce_account_number, ...)
    VALUES (NEWID(), src.org_id, src.salesforce_account_id, src.salesforce_account_number, ...);
```

---

#### **MERGE INTO member_devices**
**Match key:** `device_id = device_udi`

```sql
MERGE engage360.member_devices AS tgt
USING (
    SELECT DISTINCT
        stg.device_udi,
        m.member_id,
        stg.device_phone_clean AS device_phone_number,
        stg.is_device_callable_clean AS is_device_callable,
        stg.device_name,
        stg.brand,                          -- NEW
        stg.delivery_date,                  -- NEW
        stg.fall_detection_status,          -- NEW
        stg.battery_status                  -- NEW
    FROM engage360_stg.stg_device_activation_delta stg
    JOIN engage360.members m
        ON m.org_id = stg.org_id
        AND m.salesforce_account_number = stg.salesforce_account_number
    WHERE stg.file_batch_id = %s
      AND stg.processing_status = 'TRANSFORMING'
      AND stg.device_udi IS NOT NULL
) AS src
ON tgt.device_id = src.device_udi
WHEN MATCHED THEN
    UPDATE SET
        brand = ISNULL(src.brand, tgt.brand),
        delivery_date = ISNULL(src.delivery_date, tgt.delivery_date),
        fall_detection_status = ISNULL(src.fall_detection_status, tgt.fall_detection_status),
        battery_status = ISNULL(src.battery_status, tgt.battery_status),
        updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (device_id, member_id, device_name, brand, delivery_date,
            fall_detection_status, battery_status, created_ts)
    VALUES (src.device_udi, src.member_id, src.device_name, src.brand,
            src.delivery_date, src.fall_detection_status, src.battery_status,
            SYSDATETIMEOFFSET());
```

---

#### **INSERT INTO member_campaign_enrollments_enhanced**
**New pattern:** Calculate activation dates using business_hours_utils

```python
# In Python code before SQL INSERT
from af_code.shared.business_hours_utils import add_business_days
from datetime import datetime, timedelta

# Calculate dates
activation_start_date = add_business_days(delivery_date, 2)  # Day 2
campaign_end_date = activation_start_date + timedelta(days=90)  # 90-day limit

# SQL INSERT
insert_enrollment_sql = """
INSERT INTO engage360.member_campaign_enrollments_enhanced
(enrollment_id, member_id, campaign_id, enrollment_ts, current_status,
 activation_start_date, campaign_end_date, customer_type, device_activated)
SELECT
    NEWID(),
    m.member_id,
    %s AS campaign_id,  -- device_activation campaign
    SYSDATETIMEOFFSET(),
    'ENROLLED',
    %s AS activation_start_date,
    %s AS campaign_end_date,
    stg.customer_type,
    0 AS device_activated
FROM engage360_stg.stg_device_activation_delta stg
JOIN engage360.members m ...
WHERE stg.enrollment_status = 'ENROLL'
"""
```

---

### **Phase 5: Testing Strategy**

#### **Unit Tests**
**File:** `tests/test_device_activation_logic.py`

```python
class TestDeviceActivationValidation:
    def test_phone_number_e164_conversion()
    def test_device_status_validation()
    def test_activation_date_calculation()
    def test_customer_type_validation()
    def test_salesforce_account_id_validation()

class TestDeviceActivationETL:
    def test_extract_csv_to_dataframe()
    def test_load_to_staging_with_validation()
    def test_merge_members_with_new_account_id()
    def test_merge_devices_with_status_fields()
    def test_enrollment_with_activation_dates()
```

---

### **Phase 6: Integration Points**

1. **Campaign Setup Required:**
   - Create `device_activation` campaign in `engage360.campaigns_enhanced`
   - Status: 'Active'
   - Type: 'Device Activation'

2. **Blob Storage Container:**
   - Create `fs-device-activation` container
   - Folders: `landing/`, `staging/`, `processed/`, `error/`

3. **File Processing Log:**
   - Use existing `engage360_stg.file_processing_log` table
   - Set `workflow_type = 'DEVICE_ACTIVATION'`

4. **Business Hours Integration:**
   - Use `business_hours_utils.add_business_days()` for activation_start_date
   - Integrate with call scheduler (future phase)

---

## Files to Create

### **Core Logic (1 file):**
1. `af_code/af_device_activation_logic.py` (~2500 lines)
   - 5-phase ETL: Extract → Load → Validate → Transform → Audit
   - Row-by-row validation (13 validation rules)
   - MERGE statements for members, member_devices, member_campaign_enrollments_enhanced
   - Business day calculation for activation dates

### **Azure Function (1 file):**
2. `functions/device_activation_file_processor.py` (~80 lines)
   - Blob trigger for `fs-device-activation/landing/{name}`
   - Filename validation: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`

### **Tests (1 file):**
3. `tests/test_device_activation_logic.py` (~500 lines)
   - Unit tests for validation logic
   - Integration tests for ETL workflow

### **Registration:**
4. `function_app.py` - Register new function blueprint

---

## Implementation Order

1. ✅ **Research** - DTC/Partner patterns (COMPLETED - 2025-12-07)
2. ✅ **Specification** - Data spec and business hours utility (COMPLETED - 2025-12-07)
3. ✅ **Phase 1** - Core processing logic (af_device_activation_logic.py) - **COMPLETED - 2025-12-07**
   - 1,247 lines implementing complete 5-phase ETL pipeline
   - All validation functions implemented
   - Business day calculations integrated
4. ✅ **Phase 2** - Azure Function trigger (device_activation_file_processor.py) - **COMPLETED - 2025-12-07**
   - 91 lines with blob trigger and filename validation
   - Registered in function_app.py
5. ✅ **Phase 3** - Unit tests (test_device_activation_logic.py) - **COMPLETED - 2025-12-07**
   - 628 lines with 60+ test cases
   - Covers all validation functions and data models
6. ⏳ **Phase 4** - Integration testing with sample CSV
   - Create sample CSV file
   - Test end-to-end processing
   - Verify database MERGE operations
7. 🔜 **Phase 5** - Production deployment
   - Campaign setup
   - Blob storage container creation
   - Azure deployment verification

---

## Key Patterns to Follow (from DTC)

1. **Staging Table Pattern:**
   - 4 column groups: Metadata, Raw CSV, Clean, Processing
   - `processing_status` state machine: PENDING → VALIDATING → VALIDATED → TRANSFORMING → PROCESSED

2. **Validation Strategy:**
   - Pandera schema (structure)
   - Python row-level (business rules)
   - SQL cleansing (database lookups)
   - 10% error threshold

3. **MERGE Pattern:**
   - Match on natural keys
   - UPDATE: `ISNULL(src.field, tgt.field)` (preserve existing)
   - INSERT: `NEWID()` for UUIDs

4. **Transaction Management:**
   - Single atomic transaction for Transform & Load
   - Rollback on any error

5. **Error Handling:**
   - File-level: Move to error/ folder
   - Row-level: Store in staging
   - Master log tracking

---

## Success Criteria

✅ CSV file processing completes end-to-end (Extract → Load → Validate → Transform → Audit)
✅ Members table populated with salesforce_account_id (using existing schema)
✅ Devices table populated with brand, delivery_date, status fields (using existing columns)
✅ Enrollments table has activation_start_date calculated correctly using business_hours_utils
✅ Business day calculation excludes weekends and federal holidays
✅ Error threshold enforcement (10% default)
✅ File movement: landing → staging → processed
✅ Audit trail in file_processing_log
✅ Unit tests pass with 95%+ coverage
✅ Integration test: Sample CSV → Members enrolled → Ready for scheduler

---

**READY FOR IMPLEMENTATION**
