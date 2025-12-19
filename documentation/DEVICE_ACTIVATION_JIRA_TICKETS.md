# Device Activation System - JIRA Tickets Plan

## Overview
This document contains detailed JIRA tickets for implementing the Device Activation System (Grace AI Agent) for Medical Guardian. The system automates outreach to customers who have received their MGMini device but haven't activated it.

**Campaign Flow**: File ingestion → Call sequence (Days 2, 4, 6, 11, then weekly) → Device activation → 90-day lifecycle

**Organized by Component**:
1. Database Schema & Migrations
2. File Processor (CSV Ingestion)
3. Scheduler (Call Orchestration)
4. Business Logic (Hours, Holidays, Callbacks)
5. Webhook Integration
6. Testing & Quality Assurance

---

## COMPONENT 1: DATABASE SCHEMA & MIGRATIONS

### Story 1.1: Create Device Activation Staging Table Schema

**Description:**
Create the staging table `engage360_stg.stg_device_activation_delta` to receive CSV file data from SFTP/blob storage. This table follows the established IOE pattern for file processing with metadata tracking, raw CSV columns, and cleaned columns for validation.

**Acceptance Criteria:**
- [ ] Table created with 50+ columns covering all CSV fields from specification
- [ ] Metadata columns include: file_batch_id, source_filename, row_number_in_file, processing_status, error_message
- [ ] Raw CSV columns match DEVICE_ACTIVATION_DATA_SPECIFICATION.md exactly
- [ ] Clean columns (_clean suffix) for validated data: first_name_clean, last_name_clean, primary_phone_clean, timezone_clean
- [ ] Processing timestamp columns: cleansing_started_ts, cleansing_completed_ts, enrollment_started_ts, enrollment_completed_ts
- [ ] Tracking columns: member_id_processed, enrollment_id_processed
- [ ] Primary key on (file_batch_id, row_number_in_file)

**Technical Implementation Notes:**
- **File**: `database/create_device_activation_staging.sql`
- **Schema**: `engage360_stg`
- **Table name**: `stg_device_activation_delta`
- **Pattern reference**: See `database/partner_validation_tables.sql` for similar staging structure
- **Data types**:
  - UUIDs: `UNIQUEIDENTIFIER`
  - Dates: `DATE` for dob, delivery_date
  - Timestamps: `DATETIMEOFFSET` for all _ts columns
  - Booleans: `BIT` for is_device_callable_clean
  - Strings: `NVARCHAR` with appropriate lengths

**CSV Fields to Include (from specification):**
- Identity: salesforce_account_id, salesforce_account_number, member_first_name, member_last_name
- Contact: member_phone_number, member_email
- Address: service_address, city, state, zip
- Demographics: dob, customer_timezone, language_pref
- Device: device_udi, device_name, brand, device_phone_number, is_device_callable, delivery_date
- Device Status: fall_detection_status, battery_status
- Campaign: partner_name, customer_type, enrollment_status

**Dependencies:**
- None (foundational table)

**Testing Requirements:**
- [ ] Table creates without errors in Azure SQL Database
- [ ] All indexes created successfully
- [ ] INSERT test record succeeds with all columns
- [ ] UPDATE test record processing_status succeeds
- [ ] Query performance acceptable (<100ms for file_batch_id filter)

---

**Sub-task 1.1.1: Define Metadata Columns**

**Description**: Create metadata columns for file tracking and processing status management

**Details**:
```sql
-- Metadata columns
file_batch_id UNIQUEIDENTIFIER NOT NULL,
source_filename NVARCHAR(255),
row_number_in_file INT,
load_timestamp DATETIMEOFFSET,
file_load_date DATE,
processing_status NVARCHAR(50),  -- PENDING, VALIDATING, VALIDATED, VALIDATION_ERROR, PROCESSED
error_message NVARCHAR(MAX),
file_size_bytes BIGINT,
total_rows_in_file INT,
uploaded_by_user NVARCHAR(100),

-- Processing timestamps
cleansing_started_ts DATETIMEOFFSET,
cleansing_completed_ts DATETIMEOFFSET,
enrollment_started_ts DATETIMEOFFSET,
enrollment_completed_ts DATETIMEOFFSET,

-- Tracking
member_id_processed UNIQUEIDENTIFIER,
enrollment_id_processed UNIQUEIDENTIFIER,
```

**Acceptance**: All metadata fields defined with correct data types

---

**Sub-task 1.1.2: Define Raw CSV Columns**

**Description**: Create columns matching CSV file structure exactly as received

**Details**: All 24 fields from CSV header (see DEVICE_ACTIVATION_DATA_SPECIFICATION.md line 223):
- salesforce_account_id NVARCHAR(50) NOT NULL
- salesforce_account_number NVARCHAR(50) NOT NULL
- member_first_name NVARCHAR(100)
- member_last_name NVARCHAR(100)
- member_phone_number NVARCHAR(20)
- member_email NVARCHAR(255)
- service_address NVARCHAR(255)
- city NVARCHAR(100)
- state NVARCHAR(2)
- zip NVARCHAR(10)
- dob NVARCHAR(50)  -- Raw as string, parse later
- customer_timezone NVARCHAR(50)
- language_pref NVARCHAR(10)
- device_udi NVARCHAR(100) NOT NULL
- device_name NVARCHAR(100)
- brand NVARCHAR(100)
- device_phone_number NVARCHAR(20)
- is_device_callable NVARCHAR(10)  -- Raw as string (Y/N/TRUE/FALSE)
- delivery_date NVARCHAR(50)  -- Raw as string
- fall_detection_status NVARCHAR(50)
- battery_status NVARCHAR(50)
- partner_name NVARCHAR(100)
- customer_type NVARCHAR(10)
- enrollment_status NVARCHAR(20)

**Acceptance**: All CSV columns defined as NVARCHAR for raw ingestion

---

**Sub-task 1.1.3: Define Clean Columns for Validated Data**

**Description**: Create _clean suffix columns for validated/transformed versions of key fields

**Details**:
```sql
-- Clean columns (validated/transformed versions)
first_name_clean NVARCHAR(100),
last_name_clean NVARCHAR(100),
primary_phone_clean NVARCHAR(20),  -- E.164 format
device_phone_clean NVARCHAR(20),   -- E.164 format
email_clean NVARCHAR(255),
dob_clean DATE,
delivery_date_clean DATE,
timezone_clean NVARCHAR(50),       -- IANA format
language_pref_clean NVARCHAR(10),  -- EN/ES/Other
is_device_callable_clean BIT,      -- 0/1
state_clean NVARCHAR(2),           -- Validated US state
org_id UNIQUEIDENTIFIER,           -- Looked up from orgs table
```

**Acceptance**: All clean columns defined with appropriate business data types

---

**Sub-task 1.1.4: Add Primary Key and Indexes**

**Description**: Add primary key constraint and indexes for performance

**Details**:
```sql
PRIMARY KEY (file_batch_id, row_number_in_file),

-- Indexes for common queries
CREATE INDEX idx_staging_status ON engage360_stg.stg_device_activation_delta(processing_status);
CREATE INDEX idx_staging_batch ON engage360_stg.stg_device_activation_delta(file_batch_id);
CREATE INDEX idx_staging_member ON engage360_stg.stg_device_activation_delta(member_id_processed) WHERE member_id_processed IS NOT NULL;
```

**Acceptance**: Primary key and 3 indexes created successfully

---

### Story 1.2: Enhance member_devices Table for Device Activation

**Description:**
Add new columns to `engage360.member_devices` table to track device-specific information needed for activation campaign: delivery date, activation date, fall detection status, battery status, brand, and last signal received timestamp.

**Acceptance Criteria:**
- [ ] Migration script adds 6 new columns to member_devices table
- [ ] All new columns are nullable (existing devices won't have this data)
- [ ] Activation_date is auto-set when device sends signal
- [ ] Migration runs without locking member_devices for extended period
- [ ] Rollback script provided for safe deployment

**Technical Implementation Notes:**
- **File**: `database/add_device_activation_columns_migration.sql`
- **Table**: `engage360.member_devices`
- **New columns**:
  ```sql
  ALTER TABLE engage360.member_devices ADD
      brand NVARCHAR(100),                           -- Device brand (e.g., "Medical Guardian")
      delivery_date DATE,                            -- Date device was delivered
      activation_date DATE,                          -- Set when device first activates
      fall_detection_status NVARCHAR(50),            -- Active/Inactive/Not Applicable/Unknown
      battery_status NVARCHAR(50),                   -- Good/Low/Critical/Charging/Unknown
      last_signal_received_ts DATETIMEOFFSET;        -- Last time device sent signal
  ```

**Dependencies:**
- Story 1.1 (understand data model)

**Testing Requirements:**
- [ ] Migration runs successfully in dev environment
- [ ] Existing member_devices records unaffected (NULL values for new columns)
- [ ] INSERT new device with activation fields succeeds
- [ ] UPDATE existing device with activation fields succeeds
- [ ] Rollback script restores original schema

---

**Sub-task 1.2.1: Write ALTER TABLE Migration Script**

**Description**: Create migration script to add 6 device activation columns

**Acceptance**: Script adds brand, delivery_date, activation_date, fall_detection_status, battery_status, last_signal_received_ts

---

**Sub-task 1.2.2: Write Rollback Script**

**Description**: Create rollback script to remove columns if deployment fails

**Acceptance**: Script safely drops 6 columns without data loss for other fields

---

**Sub-task 1.2.3: Test Migration in Dev Environment**

**Description**: Execute migration on dev database and validate

**Acceptance**: Migration completes in <10 seconds, no table locks, existing data intact

---

### Story 1.3: Enhance member_campaign_enrollments_enhanced for Device Activation Lifecycle

**Description:**
Add columns to track device activation campaign lifecycle: activation_start_date (delivery_date + 2 business days), campaign_end_date (start + 90 days), customer_type (DTC/MS), device_activated flag, and activation_confirmed_ts timestamp.

**Acceptance Criteria:**
- [ ] Migration adds 5 new columns to member_campaign_enrollments_enhanced
- [ ] activation_start_date calculation logic documented (delivery_date + 2 business days)
- [ ] campaign_end_date calculation logic documented (activation_start_date + 90 days)
- [ ] customer_type constraint enforces 'DTC' or 'MS' values only
- [ ] device_activated defaults to 0 (FALSE)

**Technical Implementation Notes:**
- **File**: `database/add_activation_lifecycle_columns_migration.sql`
- **Table**: `engage360.member_campaign_enrollments_enhanced`
- **New columns**:
  ```sql
  ALTER TABLE engage360.member_campaign_enrollments_enhanced ADD
      activation_start_date DATE,                    -- delivery_date + 2 business days
      campaign_end_date DATE,                        -- activation_start_date + 90 days
      customer_type NVARCHAR(10),                    -- DTC or MS
      device_activated BIT DEFAULT 0,                -- TRUE when device sends signal
      activation_confirmed_ts DATETIMEOFFSET;        -- When activation confirmed

  ALTER TABLE engage360.member_campaign_enrollments_enhanced ADD
      CONSTRAINT CK_enrollment_customer_type CHECK (customer_type IN ('DTC', 'MS'));
  ```

**Dependencies:**
- Story 1.1, 1.2

**Testing Requirements:**
- [ ] Migration runs successfully
- [ ] customer_type constraint rejects invalid values ('OTHER', 'test', NULL if NOT NULL)
- [ ] device_activated defaults to 0 for new enrollments
- [ ] activation_start_date can be calculated from delivery_date
- [ ] campaign_end_date correctly calculates 90 days from start

---

**Sub-task 1.3.1: Add Lifecycle Date Columns**

**Description**: Add activation_start_date and campaign_end_date columns

**Acceptance**: Both DATE columns added, nullable, no defaults

---

**Sub-task 1.3.2: Add Device Activation Tracking Columns**

**Description**: Add device_activated BIT and activation_confirmed_ts columns

**Acceptance**: device_activated defaults to 0, activation_confirmed_ts nullable DATETIMEOFFSET

---

**Sub-task 1.3.3: Add Customer Type Column with Constraint**

**Description**: Add customer_type with CHECK constraint for DTC/MS values

**Acceptance**: Column added, constraint enforces only 'DTC' or 'MS' values

---

### Story 1.4: Enhance outreach_attempts for Call Sequence Tracking

**Description:**
Add columns to `engage360.outreach_attempts` to track device activation-specific call context: call_sequence_number (1, 2, 3, 4...), callback_type (scheduled/unboxing/charging), and device_status_at_call (unboxed/charged/testing).

**Acceptance Criteria:**
- [ ] Migration adds 3 new columns to outreach_attempts
- [ ] call_sequence_number tracks which attempt in sequence (Call 1, Call 2, etc.)
- [ ] callback_type distinguishes callback reasons
- [ ] device_status_at_call tracks device readiness at time of call

**Technical Implementation Notes:**
- **File**: `database/add_call_sequence_tracking_migration.sql`
- **Table**: `engage360.outreach_attempts`
- **New columns**:
  ```sql
  ALTER TABLE engage360.outreach_attempts ADD
      call_sequence_number INT,                      -- 1, 2, 3, 4, 5... (Call 1, Call 2, etc.)
      callback_type NVARCHAR(50),                    -- 'scheduled', 'unboxing', 'charging', NULL
      device_status_at_call NVARCHAR(50);            -- 'unboxed', 'charged', 'testing', NULL
  ```

**Dependencies:**
- Story 1.3

**Testing Requirements:**
- [ ] Migration runs successfully
- [ ] call_sequence_number increments correctly for same enrollment
- [ ] callback_type accepts valid values and NULL
- [ ] device_status_at_call stores device state properly

---

**Sub-task 1.4.1: Add call_sequence_number Column**

**Description**: Track which call attempt in the sequence (1-15+)

**Acceptance**: INT column added, nullable, no constraint

---

**Sub-task 1.4.2: Add callback_type Column**

**Description**: Track callback reason (scheduled/unboxing/charging)

**Acceptance**: NVARCHAR(50) column added, nullable

---

**Sub-task 1.4.3: Add device_status_at_call Column**

**Description**: Track device readiness state during call

**Acceptance**: NVARCHAR(50) column added, nullable

---

### Story 1.5: Create device_activation_campaign Master Record

**Description:**
Insert master campaign record into `engage360.campaigns_enhanced` for the Device Activation campaign with campaign_id, name, description, type='Device_Activation', and default configuration.

**Acceptance Criteria:**
- [ ] Campaign record created with specific UUID
- [ ] Campaign name: "Device Activation - Grace AI Agent"
- [ ] campaign_type set to 'Device_Activation'
- [ ] status set to 'active'
- [ ] timezone_flag set to 'member_tz' (respect member timezones)
- [ ] Operating hours: 9 AM - 5 PM (dual-timezone validation)
- [ ] call_days_of_week: 'Monday,Tuesday,Wednesday,Thursday,Friday'

**Technical Implementation Notes:**
- **File**: `database/insert_device_activation_campaign.sql`
- **Table**: `engage360.campaigns_enhanced`
- **Campaign record**:
  ```sql
  INSERT INTO engage360.campaigns_enhanced (
      campaign_id,
      org_id,  -- Medical Guardian org_id
      name,
      description,
      campaign_type,
      status,
      start_ts,
      end_ts,
      timezone_flag,
      operating_tz,
      operating_start_time,
      operating_end_time,
      call_days_of_week,
      created_ts
  ) VALUES (
      '12345678-ABCD-EFGH-IJKL-MNOPQRSTUVWX',  -- Replace with actual UUID
      (SELECT org_id FROM engage360.orgs WHERE org_name = 'Medical Guardian'),
      'Device Activation - Grace AI Agent',
      'Automated outreach to help customers activate MGMini devices when no signal detected within 5 days of delivery',
      'Device_Activation',
      'active',
      '2025-01-01',
      '2099-12-31',  -- Far future end date
      'member_tz',
      'America/New_York',  -- Medical Guardian EST timezone
      '09:00:00',
      '17:00:00',
      'Monday,Tuesday,Wednesday,Thursday,Friday',
      SYSDATETIMEOFFSET()
  );
  ```

**Dependencies:**
- Stories 1.1-1.4 (schema ready)

**Testing Requirements:**
- [ ] Campaign record inserts successfully
- [ ] campaign_id is unique
- [ ] org_id resolves correctly from orgs table
- [ ] Query campaign by campaign_type='Device_Activation' returns record
- [ ] timezone_flag='member_tz' respected by campaign qualifier

---

**Sub-task 1.5.1: Generate Campaign UUID**

**Description**: Generate and document campaign UUID for device activation

**Acceptance**: UUID generated using `uuid.uuid4()` or SQL Server `NEWID()`, documented in specification

---

**Sub-task 1.5.2: Write INSERT Campaign Script**

**Description**: Create SQL script to insert device_activation_campaign record

**Acceptance**: Script inserts 1 campaign record with all required fields

---

**Sub-task 1.5.3: Create Campaign Call Config Record**

**Description**: Insert corresponding record in campaign_call_configs_enhanced with Bland AI parameters

**Acceptance**: Config record links to campaign_id with pathway_id, voice_id, webhook_url

---

### Story 1.6: Create Callback Queue Table

**Description:**
Create new table `engage360.device_activation_callback_queue` to manage scheduled callbacks for members who need time to prepare (unbox/charge device) or requested specific callback time.

**Acceptance Criteria:**
- [ ] Table created with callback_id (PK), enrollment_id (FK), callback_type, scheduled_time
- [ ] Tracks attempt_count (max 3 attempts per callback)
- [ ] Tracks callback_status (PENDING, IN_PROGRESS, COMPLETED, FAILED, EXPIRED)
- [ ] Includes created_ts and expires_at (24-hour expiration)
- [ ] Foreign key to member_campaign_enrollments_enhanced

**Technical Implementation Notes:**
- **File**: `database/create_callback_queue_table.sql`
- **Schema**: `engage360`
- **Table**: `device_activation_callback_queue`
- **Structure**:
  ```sql
  CREATE TABLE engage360.device_activation_callback_queue (
      callback_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
      enrollment_id UNIQUEIDENTIFIER NOT NULL,
      member_id UNIQUEIDENTIFIER NOT NULL,
      callback_type NVARCHAR(50) NOT NULL,  -- 'scheduled', 'unboxing', 'charging'
      scheduled_time DATETIMEOFFSET NOT NULL,
      attempt_count INT DEFAULT 0,
      max_attempts INT DEFAULT 3,
      callback_status NVARCHAR(50) DEFAULT 'PENDING',  -- PENDING, IN_PROGRESS, COMPLETED, FAILED, EXPIRED
      created_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),
      expires_at DATETIMEOFFSET NOT NULL,  -- created_ts + 24 hours
      last_attempt_ts DATETIMEOFFSET,
      completion_ts DATETIMEOFFSET,
      notes NVARCHAR(MAX),

      CONSTRAINT FK_callback_enrollment FOREIGN KEY (enrollment_id)
          REFERENCES engage360.member_campaign_enrollments_enhanced(enrollment_id),
      CONSTRAINT FK_callback_member FOREIGN KEY (member_id)
          REFERENCES engage360.members(member_id),
      CONSTRAINT CK_callback_type CHECK (callback_type IN ('scheduled', 'unboxing', 'charging')),
      CONSTRAINT CK_callback_status CHECK (callback_status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'EXPIRED'))
  );

  CREATE INDEX idx_callback_status ON engage360.device_activation_callback_queue(callback_status, scheduled_time);
  CREATE INDEX idx_callback_enrollment ON engage360.device_activation_callback_queue(enrollment_id);
  ```

**Dependencies:**
- Story 1.3 (enrollment table enhanced)

**Testing Requirements:**
- [ ] Table creates successfully with all constraints
- [ ] Foreign keys enforce referential integrity
- [ ] CHECK constraints reject invalid callback_type and callback_status
- [ ] Indexes created for query performance
- [ ] INSERT test callback record succeeds
- [ ] UPDATE callback_status succeeds
- [ ] Query pending callbacks by scheduled_time returns correct results

---

**Sub-task 1.6.1: Define Callback Queue Schema**

**Description**: Create table structure for callback queue management

**Acceptance**: All columns, constraints, and defaults defined

---

**Sub-task 1.6.2: Add Foreign Key Constraints**

**Description**: Link callback queue to enrollments and members tables

**Acceptance**: FK constraints created, cascading behavior defined

---

**Sub-task 1.6.3: Create Performance Indexes**

**Description**: Add indexes for callback queue queries

**Acceptance**: Indexes on callback_status+scheduled_time and enrollment_id created

---

---

## COMPONENT 2: FILE PROCESSOR (CSV INGESTION)

### Story 2.1: Create Device Activation File Processor Azure Function

**Description:**
Create blob-triggered Azure Function `device_activation_file_processor` to process CSV files from SFTP location `/device-activation/landing/` with pattern `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`.

**Acceptance Criteria:**
- [ ] Azure Function Blueprint created in `functions/device_activation_file_processor.py`
- [ ] Blob trigger configured for path `fs-device-activation/landing/{name}`
- [ ] Filename validation against pattern: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`
- [ ] Delegates processing to `af_code.af_device_activation_logic.process_device_activation_file_complete()`
- [ ] Returns ProcessingResult with success/failure status
- [ ] Registered in `function_app.py` with error handling

**Technical Implementation Notes:**
- **File**: `functions/device_activation_file_processor.py`
- **Pattern reference**: `functions/partner_file_processor.py` (lines 1-40)
- **Blob path**: `fs-device-activation/landing/{name}`
- **Container**: `fs-device-activation` (new Azure Storage container)
- **Filename regex**: `^MedicalGuardian_DeviceActivation_(\d{8})_Delta\.csv$`
- **Blueprint pattern**:
  ```python
  import azure.functions as func
  import logging
  from af_code.af_device_activation_logic import process_device_activation_file_complete

  bp = func.Blueprint()

  @bp.function_name(name="ProcessDeviceActivationBlob")
  @bp.blob_trigger(arg_name="myblob", path="fs-device-activation/landing/{name}",
                   connection="AzureWebJobsStorage")
  def process_device_activation_blob(myblob: func.InputStream) -> None:
      filename = myblob.name.split("/")[-1]
      logger.info(f"📁 [DEVICE-ACTIVATION] Processing file: {filename}")

      # Validate filename pattern
      if not _validate_filename(filename):
          logger.error(f"❌ Invalid filename pattern: {filename}")
          return

      # Delegate to business logic
      success, message, result = process_device_activation_file_complete(
          filename=filename,
          uploaded_by_user="system_automated",
          blob_client=None  # Will fetch from storage
      )

      if success:
          logger.info(f"✅ [DEVICE-ACTIVATION] {message}")
      else:
          logger.error(f"❌ [DEVICE-ACTIVATION] {message}")
  ```

**Dependencies:**
- Story 1.1 (staging table created)
- Story 2.2 (business logic module)

**Testing Requirements:**
- [ ] Function deploys to Azure without errors
- [ ] Blob trigger activates when CSV uploaded
- [ ] Invalid filename rejected immediately
- [ ] Valid filename delegates to business logic
- [ ] Logs appear in Application Insights
- [ ] Blob moved to processed folder after successful processing

---

**Sub-task 2.1.1: Create Blueprint Module**

**Description**: Create `functions/device_activation_file_processor.py` with Blueprint structure

**Acceptance**: File created with imports, Blueprint instance, function decorator

---

**Sub-task 2.1.2: Implement Filename Validation**

**Description**: Add regex validation for filename pattern

**Acceptance**: Function `_validate_filename()` returns True/False, extracts date component

---

**Sub-task 2.1.3: Implement Blob Trigger Handler**

**Description**: Add blob trigger function that delegates to business logic

**Acceptance**: Function receives blob, validates, delegates to `process_device_activation_file_complete()`

---

**Sub-task 2.1.4: Register in function_app.py**

**Description**: Import and register blueprint in main function app

**Acceptance**:
```python
try:
    from functions.device_activation_file_processor import bp as device_activation_bp
    logger.info("✅ Successfully imported Device Activation File Processor blueprint")
    app.register_blueprint(device_activation_bp)
    logger.info("✅ Successfully registered Device Activation File Processor blueprint")
except Exception as e:
    logger.error(f"❌ Failed to register Device Activation File Processor: {str(e)}")
```

---

### Story 2.2: Create Device Activation Business Logic Module

**Description:**
Create comprehensive business logic module `af_code/af_device_activation_logic.py` implementing ETL pattern for device activation CSV files: Extract (blob → DataFrame), Transform (validate/cleanse), Load (staging table), Process (core tables).

**Acceptance Criteria:**
- [ ] Module created with all processing functions
- [ ] ProcessingConfig dataclass for configuration management
- [ ] ProcessingResult dataclass for return values
- [ ] ProcessingContext dataclass for shared state
- [ ] DatabaseManager class for connection handling with retry logic
- [ ] Main entry point: `process_device_activation_file_complete()`
- [ ] Follows partner campaign pattern (modular validators)
- [ ] Error threshold: 10% (same as DTC)
- [ ] Processing timeout: 600 seconds (10 minutes)

**Technical Implementation Notes:**
- **File**: `af_code/af_device_activation_logic.py`
- **Pattern reference**:
  - `af_code/af_dtc_logic.py` for ETL structure
  - `af_code/af_partner_logic.py` for validator classes
- **Key classes**:
  ```python
  @dataclass
  class ProcessingConfig:
      connection_string: str
      staging_table: str = "engage360_stg.stg_device_activation_delta"
      error_threshold_pct: float = 10.0
      max_retries: int = 3
      retry_delay_seconds: int = 5
      timeout_seconds: int = 600
      expected_filename_pattern: str = r"^MedicalGuardian_DeviceActivation_(\d{8})_Delta\.csv$"

  @dataclass
  class ProcessingResult:
      success: bool
      message: str
      records_processed: int = 0
      records_succeeded: int = 0
      records_failed: int = 0
      duration_seconds: float = 0.0
      error_details: Optional[str] = None
  ```

**Processing Functions**:
1. `extract_csv_to_dataframe()` - Download blob, parse CSV
2. `load_to_staging()` - Bulk insert to staging table
3. `validate_and_cleanse_data()` - Row-level validation
4. `transform_and_load_core_tables()` - MERGE into members, devices, enrollments
5. `process_device_activation_file_complete()` - Main orchestrator

**Dependencies:**
- Story 1.1 (staging table)
- Story 2.1 (function trigger)

**Testing Requirements:**
- [ ] Unit tests for each processing function
- [ ] Integration test with sample CSV file
- [ ] Error threshold triggers correctly (>10% errors)
- [ ] Database retry logic handles transient failures
- [ ] ProcessingResult contains accurate metrics
- [ ] Timeout enforced at 600 seconds

---

**Sub-task 2.2.1: Create Module Structure with Dataclasses**

**Description**: Create file with imports, dataclasses, and module structure

**Acceptance**: ProcessingConfig, ProcessingResult, ProcessingContext dataclasses defined

---

**Sub-task 2.2.2: Implement DatabaseManager Class**

**Description**: Connection handling with Azure Key Vault and retry logic

**Acceptance**: Class handles secret vs connection string, implements retry with exponential backoff

---

**Sub-task 2.2.3: Implement Extract Function**

**Description**: Download blob and parse CSV into pandas DataFrame

**Acceptance**: Function returns DataFrame with metadata columns added

---

**Sub-task 2.2.4: Implement Load to Staging Function**

**Description**: Bulk insert validated records to staging table

**Acceptance**: Function uses `executemany()` for performance, handles errors gracefully

---

**Sub-task 2.2.5: Implement Main Orchestrator Function**

**Description**: Coordinate all processing steps with timing and error handling

**Acceptance**: Function process_device_activation_file_complete() orchestrates ETL, returns ProcessingResult

---

### Story 2.3: Create Device Activation Data Validators

**Description:**
Create modular validator classes for device activation CSV data following partner campaign pattern: FileNameValidator, ColumnValidator, DataCleanerAndValidator, DeviceValidator.

**Acceptance Criteria:**
- [ ] FileNameValidator validates filename pattern and extracts date
- [ ] ColumnValidator checks required vs provided columns
- [ ] DataCleanerAndValidator performs row-level validation and cleansing
- [ ] DeviceValidator validates device-specific fields (UDI, brand, battery status)
- [ ] ValidationError dataclass for structured error reporting
- [ ] ValidationSeverity levels: ERROR, WARNING, INFO

**Technical Implementation Notes:**
- **File**: `af_code/af_device_activation_logic.py` (within main module)
- **Pattern reference**: `af_code/af_partner_logic.py` lines 200-600 (validator classes)
- **Classes**:
  ```python
  @dataclass
  class ValidationError:
      category: str          # e.g., "FileName", "Format", "Device"
      error_type: str        # Specific error within category
      message: str           # Human-readable description
      severity: str          # ERROR, WARNING, or INFO
      field: Optional[str]
      error_value: Optional[str]
      expected_value: Optional[str]
      row_number: Optional[int]

  class FileNameValidator:
      """Validates filename pattern and extracts metadata"""
      @staticmethod
      def validate(filename: str) -> Tuple[bool, List[ValidationError], Dict]:
          # Returns (is_valid, errors, extracted_metadata)

  class ColumnValidator:
      """Validates CSV header structure"""
      REQUIRED_COLUMNS = [
          'salesforce_account_id', 'salesforce_account_number',
          'member_first_name', 'member_last_name', 'member_phone_number',
          'service_address', 'city', 'state', 'zip', 'dob',
          'customer_timezone', 'device_udi', 'device_name', 'brand',
          'delivery_date', 'fall_detection_status', 'battery_status',
          'partner_name', 'customer_type', 'enrollment_status'
      ]

      @staticmethod
      def validate(df_columns: List[str]) -> Tuple[bool, List[ValidationError]]:
          # Returns (is_valid, errors)

  class DataCleanerAndValidator:
      """Row-level validation and cleansing"""
      def validate_and_clean_row(self, row: pd.Series, row_num: int) -> Tuple[pd.Series, List[ValidationError]]:
          # Returns (cleaned_row, errors)

  class DeviceValidator:
      """Device-specific field validation"""
      VALID_FALL_DETECTION = ['Active', 'Inactive', 'Not Applicable', 'Unknown']
      VALID_BATTERY_STATUS = ['Good', 'Low', 'Critical', 'Charging', 'Unknown']

      @staticmethod
      def validate_device_fields(row: pd.Series) -> List[ValidationError]:
          # Returns errors
  ```

**Validation Rules**:
- **Phone numbers**: E.164 format, 11-15 digits
- **Dates**: YYYY-MM-DD format, delivery_date not in future
- **Timezone**: Valid IANA timezone or US abbreviations
- **State**: Valid 2-letter US state code
- **Email**: Standard email format (optional field)
- **Boolean**: Y/N/YES/NO/TRUE/FALSE/1/0
- **Enums**: fall_detection_status, battery_status, customer_type, enrollment_status

**Dependencies:**
- Story 2.2 (main module structure)
- Shared utilities: `af_code/shared/language_mapper.py`, `timezone_utils.py`

**Testing Requirements:**
- [ ] Unit tests for each validator class
- [ ] FileNameValidator accepts valid filenames, rejects invalid
- [ ] ColumnValidator detects missing required columns
- [ ] DataCleanerAndValidator cleanses phone numbers to E.164
- [ ] DeviceValidator enforces enum values
- [ ] Error messages are descriptive and actionable

---

**Sub-task 2.3.1: Create ValidationError and Severity Classes**

**Description**: Define error data structures

**Acceptance**: ValidationError dataclass and ValidationSeverity enum created

---

**Sub-task 2.3.2: Implement FileNameValidator**

**Description**: Validate filename pattern and extract date

**Acceptance**: Validator accepts correct pattern, extracts YYYYMMDD, rejects invalid

---

**Sub-task 2.3.3: Implement ColumnValidator**

**Description**: Check CSV headers against required/optional columns

**Acceptance**: Validator detects missing mandatory columns, unexpected columns

---

**Sub-task 2.3.4: Implement DataCleanerAndValidator**

**Description**: Row-level validation with field-specific logic

**Acceptance**: Validates and cleanses phone, date, name, timezone, state, email fields

---

**Sub-task 2.3.5: Implement DeviceValidator**

**Description**: Device-specific field validation

**Acceptance**: Validates device_udi, brand, fall_detection_status, battery_status, is_device_callable

---

### Story 2.4: Implement Core Table MERGE Logic

**Description:**
Implement SQL MERGE logic to upsert data from staging table into core tables: `engage360.members`, `engage360.member_devices`, `engage360.member_campaign_enrollments_enhanced`. Handle new enrollments, updates to existing members, and device linking.

**Acceptance Criteria:**
- [ ] MERGE into members table (UPSERT on salesforce_account_id + org_id)
- [ ] MERGE into member_devices table (UPSERT on device_udi)
- [ ] INSERT into member_campaign_enrollments_enhanced (new enrollments only)
- [ ] Calculate activation_start_date (delivery_date + 2 business days)
- [ ] Calculate campaign_end_date (activation_start_date + 90 days)
- [ ] Handle ENROLL, UPDATE, UNENROLL enrollment_status values
- [ ] Transaction atomicity (all or nothing)

**Technical Implementation Notes:**
- **File**: `af_code/af_device_activation_logic.py` (function: `transform_and_load_core_tables()`)
- **Pattern reference**: `af_code/af_dtc_logic.py` lines 900-1200 (MERGE logic)
- **Business day calculation**: Use `af_code/shared/business_hours_utils.py`
- **Key MERGE queries**:

  **1. MERGE members**:
  ```sql
  MERGE engage360.members AS target
  USING engage360_stg.stg_device_activation_delta AS source
  ON target.salesforce_account_id = source.salesforce_account_id
      AND target.org_id = source.org_id
  WHEN MATCHED THEN
      UPDATE SET
          first_name = source.first_name_clean,
          last_name = source.last_name_clean,
          primary_phone = source.primary_phone_clean,
          email = source.email_clean,
          dob = source.dob_clean,
          timezone = source.timezone_clean,
          language_pref = source.language_pref_clean,
          address_street = source.service_address,
          address_city = source.city,
          address_state = source.state_clean,
          address_zip = source.zip,
          updated_ts = SYSDATETIMEOFFSET()
  WHEN NOT MATCHED BY TARGET THEN
      INSERT (member_id, org_id, salesforce_account_id, salesforce_account_number,
              first_name, last_name, primary_phone, email, dob, timezone, language_pref,
              address_street, address_city, address_state, address_zip, created_ts)
      VALUES (NEWID(), source.org_id, source.salesforce_account_id, source.salesforce_account_number,
              source.first_name_clean, source.last_name_clean, source.primary_phone_clean,
              source.email_clean, source.dob_clean, source.timezone_clean, source.language_pref_clean,
              source.service_address, source.city, source.state_clean, source.zip,
              SYSDATETIMEOFFSET());
  ```

  **2. MERGE member_devices**:
  ```sql
  MERGE engage360.member_devices AS target
  USING (
      SELECT s.device_udi, m.member_id, s.device_phone_clean, s.is_device_callable_clean,
             s.device_name, s.brand, s.delivery_date_clean,
             s.fall_detection_status, s.battery_status
      FROM engage360_stg.stg_device_activation_delta s
      JOIN engage360.members m ON s.salesforce_account_id = m.salesforce_account_id
  ) AS source
  ON target.device_id = source.device_udi
  WHEN MATCHED THEN
      UPDATE SET
          member_id = source.member_id,
          device_phone_number = source.device_phone_clean,
          is_device_callable = source.is_device_callable_clean,
          brand = source.brand,
          delivery_date = source.delivery_date_clean,
          fall_detection_status = source.fall_detection_status,
          battery_status = source.battery_status,
          updated_ts = SYSDATETIMEOFFSET()
  WHEN NOT MATCHED BY TARGET THEN
      INSERT (device_id, member_id, device_phone_number, is_device_callable,
              device_name, brand, delivery_date, fall_detection_status, battery_status, created_ts)
      VALUES (source.device_udi, source.member_id, source.device_phone_clean, source.is_device_callable_clean,
              source.device_name, source.brand, source.delivery_date_clean,
              source.fall_detection_status, source.battery_status, SYSDATETIMEOFFSET());
  ```

  **3. INSERT enrollments** (ENROLL only):
  ```sql
  INSERT INTO engage360.member_campaign_enrollments_enhanced (
      enrollment_id, member_id, campaign_id, enrollment_ts, current_status,
      activation_start_date, campaign_end_date, customer_type
  )
  SELECT
      NEWID(),
      m.member_id,
      @device_activation_campaign_id,  -- From Story 1.5
      SYSDATETIMEOFFSET(),
      'ENROLLED',
      dbo.add_business_days(s.delivery_date_clean, 2) AS activation_start_date,
      DATEADD(DAY, 90, dbo.add_business_days(s.delivery_date_clean, 2)) AS campaign_end_date,
      s.customer_type
  FROM engage360_stg.stg_device_activation_delta s
  JOIN engage360.members m ON s.salesforce_account_id = m.salesforce_account_id
  WHERE s.enrollment_status = 'ENROLL'
      AND s.processing_status = 'VALIDATED'
      AND NOT EXISTS (
          SELECT 1 FROM engage360.member_campaign_enrollments_enhanced e
          WHERE e.member_id = m.member_id AND e.campaign_id = @device_activation_campaign_id
      );
  ```

**Dependencies:**
- Story 1.1-1.5 (all database schema)
- Story 2.2 (business logic module)
- Story 2.3 (validators)
- Story 4.1 (business_hours_utils for add_business_days function)

**Testing Requirements:**
- [ ] New member INSERTS correctly
- [ ] Existing member UPDATES correctly
- [ ] Device MERGE links to correct member
- [ ] Enrollment INSERT creates with correct dates
- [ ] activation_start_date = delivery_date + 2 business days (excluding weekends/holidays)
- [ ] campaign_end_date = activation_start_date + 90 days
- [ ] UNENROLL status removes member from campaign
- [ ] Transaction rollback on any failure

---

**Sub-task 2.4.1: Implement Members MERGE Query**

**Description**: UPSERT members table from staging

**Acceptance**: Query handles INSERT and UPDATE paths, uses salesforce_account_id as business key

---

**Sub-task 2.4.2: Implement Devices MERGE Query**

**Description**: UPSERT member_devices table from staging

**Acceptance**: Query handles INSERT and UPDATE, links device to member via device_udi

---

**Sub-task 2.4.3: Implement Enrollments INSERT Query**

**Description**: Create enrollments for ENROLL status

**Acceptance**: Query creates enrollment with activation dates calculated, prevents duplicates

---

**Sub-task 2.4.4: Implement Date Calculation Logic**

**Description**: Calculate activation_start_date and campaign_end_date

**Acceptance**: Uses business_hours_utils.add_business_days(), excludes weekends and federal holidays

---

**Sub-task 2.4.5: Wrap in Transaction**

**Description**: Execute all 3 MERGE/INSERT queries in single transaction

**Acceptance**: Uses DatabaseService.execute_transaction(), atomic commit/rollback

---

---

## COMPONENT 3: SCHEDULER (CALL ORCHESTRATION)

### Story 3.1: Create Device Activation Scheduler Azure Function

**Description:**
Create timer-triggered Azure Function `device_activation_scheduler` to orchestrate call sequence for device activation campaign. Runs every 30 minutes to identify members ready for Call 1, Call 2, Call 3, Call 4, or weekly calls, respecting business hours and callback queue priority.

**Acceptance Criteria:**
- [ ] Timer trigger: every 30 minutes (cron: `0 */30 * * * *`)
- [ ] HTTP trigger endpoint for manual execution
- [ ] Queries device_activation_campaign for qualified members
- [ ] Respects callback queue priority (callbacks before scheduled calls)
- [ ] Enforces business hours (Mon-Fri, 9 AM-5 PM dual-timezone)
- [ ] Enforces federal holidays exclusion
- [ ] Rate limiting: Max 80 members per execution
- [ ] Delegates batch creation to BatchOrchestrator

**Technical Implementation Notes:**
- **File**: `functions/device_activation_scheduler.py`
- **Pattern reference**: `functions/partner_campaign_scheduler.py`
- **Timer schedule**: `0 */30 * * * *` (every 30 min at minute 0)
- **Blueprint structure**:
  ```python
  import azure.functions as func
  import logging
  from af_code.device_activation_scheduler.orchestrator import DeviceActivationOrchestrator

  bp = func.Blueprint()

  @bp.function_name(name="DeviceActivationScheduler")
  @bp.timer_trigger(schedule="0 */30 * * * *", arg_name="timer", run_on_startup=False)
  def timer_trigger(timer: func.TimerRequest) -> None:
      logger.info("⏰ [DEVICE-ACTIVATION-SCHEDULER] Timer trigger fired")
      _execute_scheduler()

  @bp.function_name(name="DeviceActivationSchedulerHTTP")
  @bp.route(route="device_activation_scheduler", methods=["GET", "POST"])
  def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
      logger.info("🌐 [DEVICE-ACTIVATION-SCHEDULER] HTTP trigger fired")
      result = _execute_scheduler()
      return func.HttpResponse(json.dumps(result), mimetype="application/json")

  def _execute_scheduler():
      orchestrator = DeviceActivationOrchestrator()
      return orchestrator.execute()
  ```

**Execution Logic**:
1. Check callback queue for pending callbacks (priority processing)
2. Query members eligible for Call 1 (activation_start_date <= today, no attempts yet)
3. Query members eligible for Call 2 (Call 1 + 2 business days, no answer)
4. Query members eligible for Call 3 (Call 2 + 2 business days, no answer)
5. Query members eligible for Call 4+ (weekly cadence until Day 90)
6. Apply business hours and timezone filtering
7. Rate limit to 80 members total
8. Submit batch to Bland AI

**Dependencies:**
- Story 1.5 (campaign record)
- Story 1.6 (callback queue table)
- Story 3.2 (orchestrator module)

**Testing Requirements:**
- [ ] Timer trigger fires every 30 minutes
- [ ] HTTP endpoint responds with execution result
- [ ] Callback queue processed before scheduled calls
- [ ] Business hours enforced (no calls on weekends/holidays/outside 9-5)
- [ ] Rate limiting enforced (max 80 members)
- [ ] Logs appear in Application Insights with emoji prefixes

---

**Sub-task 3.1.1: Create Blueprint Module**

**Description**: Create functions/device_activation_scheduler.py with timer and HTTP triggers

**Acceptance**: Both triggers defined, delegate to shared _execute_scheduler() function

---

**Sub-task 3.1.2: Implement Timer Trigger**

**Description**: Add timer trigger with 30-minute schedule

**Acceptance**: Timer fires every 30 minutes, logs execution, calls orchestrator

---

**Sub-task 3.1.3: Implement HTTP Trigger**

**Description**: Add manual HTTP endpoint for on-demand execution

**Acceptance**: HTTP GET/POST triggers scheduler, returns JSON result

---

**Sub-task 3.1.4: Register in function_app.py**

**Description**: Import and register device activation scheduler blueprint

**Acceptance**: Blueprint registered with error handling, logs in Application Insights

---

### Story 3.2: Create Device Activation Orchestrator Module

**Description:**
Create orchestrator module `af_code/device_activation_scheduler/orchestrator.py` to coordinate member eligibility queries, callback queue processing, call sequence determination, and batch submission for device activation campaign.

**Acceptance Criteria:**
- [ ] DeviceActivationOrchestrator class with execute() method
- [ ] Callback queue processor (checks pending callbacks first)
- [ ] Call sequence determiner (which call: 1, 2, 3, 4, weekly)
- [ ] Member eligibility service integration
- [ ] BatchOrchestrator integration for Bland AI submission
- [ ] Business hours validation integration
- [ ] Comprehensive logging with emoji prefixes

**Technical Implementation Notes:**
- **File**: `af_code/device_activation_scheduler/orchestrator.py`
- **Pattern reference**: `af_code/partner_campaign_scheduler/` (modular service architecture)
- **Key classes**:
  ```python
  class DeviceActivationOrchestrator:
      def __init__(self):
          self.config_manager = ConfigManager()
          self.db_service = DatabaseService(self.config_manager)
          self.callback_processor = CallbackQueueProcessor(self.db_service)
          self.eligibility_service = MemberEligibilityService(self.db_service)
          self.call_sequencer = CallSequencer(self.db_service)
          self.batch_orchestrator = BatchOrchestrator(self.db_service, self.config_manager)
          self.business_hours_validator = BusinessHoursValidator()

      def execute(self) -> Dict:
          """Main orchestration flow"""
          logger.info("🚀 [DA-ORCHESTRATOR] Starting device activation scheduler execution")

          # Phase 1: Process callback queue (priority)
          callback_members = self.callback_processor.get_pending_callbacks()
          logger.info(f"📞 [DA-ORCHESTRATOR] Found {len(callback_members)} pending callbacks")

          # Phase 2: Get scheduled call members
          scheduled_members = self._get_scheduled_call_members()
          logger.info(f"📅 [DA-ORCHESTRATOR] Found {len(scheduled_members)} scheduled call members")

          # Phase 3: Combine and prioritize (callbacks first)
          all_members = callback_members + scheduled_members
          eligible_members = self._apply_business_hours_filter(all_members)

          # Phase 4: Rate limit
          members_to_call = eligible_members[:80]

          # Phase 5: Submit batch
          if members_to_call:
              batch_result = self.batch_orchestrator.submit_batch(members_to_call)
              return batch_result
          else:
              return {"success": True, "message": "No eligible members at this time"}

      def _get_scheduled_call_members(self) -> List[EligibleMember]:
          """Query members for Call 1, 2, 3, 4, weekly"""
          call_1_members = self.eligibility_service.get_call_1_eligible()
          call_2_members = self.eligibility_service.get_call_2_eligible()
          call_3_members = self.eligibility_service.get_call_3_eligible()
          call_4_weekly_members = self.eligibility_service.get_call_4_weekly_eligible()

          return call_1_members + call_2_members + call_3_members + call_4_weekly_members
  ```

**Callback Queue Priority**:
- Callbacks processed before scheduled calls
- Max 3 attempts per callback within 24 hours
- Expired callbacks (>24 hours) moved back to main sequence

**Dependencies:**
- Story 3.1 (scheduler function)
- Story 3.3 (eligibility service)
- Story 3.4 (batch orchestrator)
- Story 4.1 (business hours utils)

**Testing Requirements:**
- [ ] Unit tests for orchestrator methods
- [ ] Callback queue processed first
- [ ] Call sequence members queried correctly
- [ ] Business hours filter applied
- [ ] Rate limiting enforced
- [ ] Batch submission success/failure handling

---

**Sub-task 3.2.1: Create Orchestrator Class Structure**

**Description**: Define DeviceActivationOrchestrator class with dependencies

**Acceptance**: Class initialized with all service dependencies injected

---

**Sub-task 3.2.2: Implement execute() Main Flow**

**Description**: Coordinate all orchestration phases

**Acceptance**: Method executes 5 phases: callbacks, scheduled, filter, rate limit, submit

---

**Sub-task 3.2.3: Implement Callback Priority Logic**

**Description**: Process callback queue before scheduled calls

**Acceptance**: Callbacks added to members list first, prioritized in batch submission

---

**Sub-task 3.2.4: Implement Business Hours Filter**

**Description**: Filter members to only those callable right now

**Acceptance**: Uses BusinessHoursValidator to enforce Mon-Fri 9-5 dual-timezone

---

### Story 3.3: Create Member Eligibility Service for Call Sequences

**Description:**
Create `MemberEligibilityService` to query eligible members for each call sequence (Call 1, 2, 3, 4, weekly) with complex SQL using CTEs for frequency protection, same-day blocking, business day calculations, and timezone-aware filtering.

**Acceptance Criteria:**
- [ ] Separate methods for each call type: `get_call_1_eligible()`, `get_call_2_eligible()`, etc.
- [ ] Call 1: activation_start_date <= today, no attempts yet
- [ ] Call 2: Last attempt 2 business days ago, disposition != Completed
- [ ] Call 3: Last attempt 2 business days ago (from Call 2)
- [ ] Call 4+: Last attempt 7 calendar days ago (weekly cadence)
- [ ] All calls: Same-day blocking (one attempt per member per day)
- [ ] All calls: Excludes members with device_activated = 1
- [ ] All calls: Excludes members past campaign_end_date (90 days)
- [ ] Returns List[EligibleMember] with demographics and call context

**Technical Implementation Notes:**
- **File**: `af_code/device_activation_scheduler/services/member_eligibility.py`
- **Pattern reference**: `af_code/partner_campaign_scheduler/services/member_eligibility.py` (6-CTE pattern)
- **SQL Pattern** (for Call 2 example):
  ```sql
  WITH LastAttempts AS (
      SELECT
          oa.enrollment_id,
          oa.attempt_id,
          oa.attempt_ts,
          oa.disposition,
          oa.call_sequence_number,
          ROW_NUMBER() OVER (PARTITION BY oa.enrollment_id ORDER BY oa.attempt_ts DESC) as rn
      FROM engage360.outreach_attempts oa
      WHERE oa.call_sequence_number = 1  -- Only Call 1 attempts
  ),
  TodayAttempts AS (
      SELECT DISTINCT enrollment_id
      FROM engage360.outreach_attempts
      WHERE CAST(attempt_ts AT TIME ZONE 'UTC' AS DATE) = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'UTC' AS DATE)
  ),
  EligibleForCall2 AS (
      SELECT
          m.member_id,
          mce.enrollment_id,
          m.first_name,
          m.last_name,
          m.primary_phone,
          m.timezone,
          mce.activation_start_date,
          mce.campaign_end_date,
          mce.customer_type,
          la.attempt_ts AS last_attempt_ts,
          dbo.add_business_days(CAST(la.attempt_ts AS DATE), 2) AS next_eligible_date
      FROM engage360.member_campaign_enrollments_enhanced mce
      JOIN engage360.members m ON mce.member_id = m.member_id
      JOIN LastAttempts la ON mce.enrollment_id = la.enrollment_id AND la.rn = 1
      WHERE mce.campaign_id = @device_activation_campaign_id
          AND mce.current_status = 'ENROLLED'
          AND mce.device_activated = 0
          AND CAST(SYSDATETIMEOFFSET() AS DATE) <= mce.campaign_end_date
          AND la.disposition IN ('NoAnswer', 'Failed', 'Pending')  -- Not Completed or OptOut
          AND dbo.add_business_days(CAST(la.attempt_ts AS DATE), 2) <= CAST(SYSDATETIMEOFFSET() AS DATE)
          AND NOT EXISTS (SELECT 1 FROM TodayAttempts ta WHERE ta.enrollment_id = mce.enrollment_id)
  )
  SELECT * FROM EligibleForCall2;
  ```

**EligibleMember Data Model**:
```python
@dataclass
class EligibleMember:
    member_id: str
    enrollment_id: str
    first_name: str
    last_name: str
    primary_phone: str
    device_phone: Optional[str]
    is_device_callable: bool
    timezone: str
    customer_type: str  # DTC or MS
    call_sequence_number: int  # 1, 2, 3, 4, 5...
    activation_start_date: date
    campaign_end_date: date
    last_attempt_ts: Optional[datetime]
    device_udi: str
    device_status: Dict  # fall_detection, battery_status
```

**Dependencies:**
- Story 1.3 (enrollment table with activation dates)
- Story 1.4 (outreach_attempts with call_sequence_number)
- Story 3.2 (orchestrator)
- Story 4.1 (business_hours_utils for add_business_days SQL function)

**Testing Requirements:**
- [ ] Call 1 query returns only members with no attempts
- [ ] Call 2 query returns only Call 1 members after 2 business days
- [ ] Call 3 query returns only Call 2 members after 2 business days
- [ ] Call 4+ query returns members after 7 calendar days (weekly)
- [ ] Same-day blocking prevents duplicate calls
- [ ] Members past campaign_end_date excluded
- [ ] device_activated=1 members excluded
- [ ] Query performance <5 seconds for 10,000+ enrollments

---

**Sub-task 3.3.1: Create MemberEligibilityService Class**

**Description**: Define service class with database dependency

**Acceptance**: Class initialized with DatabaseService, exposes 4 eligibility methods

---

**Sub-task 3.3.2: Implement get_call_1_eligible() Query**

**Description**: Query members ready for first call (activation_start_date <= today)

**Acceptance**: Returns members with no attempts yet, within campaign dates, device not activated

---

**Sub-task 3.3.3: Implement get_call_2_eligible() Query**

**Description**: Query members ready for second call (2 business days after Call 1)

**Acceptance**: Uses add_business_days(), excludes Completed/OptOut, enforces same-day blocking

---

**Sub-task 3.3.4: Implement get_call_3_eligible() Query**

**Description**: Query members ready for third call (2 business days after Call 2)

**Acceptance**: Same pattern as Call 2, filters call_sequence_number=2

---

**Sub-task 3.3.5: Implement get_call_4_weekly_eligible() Query**

**Description**: Query members ready for weekly calls (7 days cadence until Day 90)

**Acceptance**: Uses calendar days (DATEADD), continues until campaign_end_date

---

### Story 3.4: Create Batch Orchestrator for Device Activation

**Description:**
Create `BatchOrchestrator` service to coordinate 3-phase batch submission: create batch record, create attempt records, submit to Bland AI, update with vendor_batch_id. Follows partner campaign pattern with device activation-specific request_data fields.

**Acceptance Criteria:**
- [ ] 3-phase synchronous submission pattern
- [ ] Phase 1: INSERT outreach_batches (status='Pending')
- [ ] Phase 2: INSERT outreach_attempts (disposition='Pending', call_sequence_number)
- [ ] Phase 3: Submit to Bland AI and UPDATE batch (status='Submitted', vendor_batch_id)
- [ ] request_data includes device-specific fields (device_udi, delivery_date, fall_detection, battery_status)
- [ ] metadata includes attempt_id, call_sequence_number, callback_type
- [ ] Phone number E.164 validation
- [ ] Error handling with rollback

**Technical Implementation Notes:**
- **File**: `af_code/device_activation_scheduler/services/batch_orchestrator.py`
- **Pattern reference**: `af_code/partner_campaign_scheduler/services/batch_orchestrator.py`
- **Key methods**:
  ```python
  class BatchOrchestrator:
      def submit_batch(self, members: List[EligibleMember]) -> Dict:
          """Submit batch to Bland AI with 3-phase database tracking"""
          batch_id = uuid.uuid4()

          # Phase 1: Create batch record
          self._create_batch_record(batch_id, len(members))

          # Phase 2: Create attempt records
          attempt_map = self._create_attempt_records(batch_id, members)

          # Phase 3: Build and submit Bland AI request
          batch_request = self._build_bland_request(members, attempt_map)
          bland_result = self.bland_client.submit_batch_calls(batch_request)

          if bland_result["success"]:
              self._update_batch_with_vendor_id(batch_id, bland_result["batch_id"])
              return {"success": True, "batch_id": str(batch_id), "members": len(members)}
          else:
              self._mark_batch_failed(batch_id, bland_result["error"])
              return {"success": False, "error": bland_result["error"]}
  ```

**Bland AI Request Format for Device Activation**:
```python
{
    "campaign_id": "device-activation-campaign-uuid",
    "calls": [
        {
            "to": "+15551234567",  # E.164 validated
            "request_data": {
                # DTC-style demographics
                "first_name": "John",
                "last_name": "Doe",
                "language_pref": "en",
                "service_address": "123 Main St",
                "city": "Boston",
                "state": "MA",
                "zip_code": "02101",
                "primary_phone": "+15551234567",
                "dob": "1980-05-15",

                # Device activation specific
                "device_udi": "MGM-12345-2025",
                "device_name": "MGMini",
                "brand": "Medical Guardian",
                "delivery_date": "2025-01-06",
                "fall_detection_status": "Active",
                "battery_status": "Good",
                "customer_type": "DTC"
            },
            "metadata": {
                "attempt_id": "uuid",
                "batch_id": "uuid",
                "campaign_id": "device-activation-uuid",
                "member_id": "uuid",
                "enrollment_id": "uuid",
                "called_number": "+15551234567",
                "channel": "phone",
                "pathway_id": "device-activation-pathway",
                "voice_id": "grace-voice-id",
                "language_pref": "en",
                "campaign_type": "Device_Activation",
                "call_sequence_number": 1,  # 1, 2, 3, 4...
                "callback_type": None,  # or 'scheduled', 'unboxing', 'charging'
                "member_timezone": "America/New_York"
            }
        }
    ],
    "pathway_id": "device-activation-pathway",
    "voice_id": "grace-voice-id",
    "bland_parameters_global": {...}  # From campaign_call_configs_enhanced
}
```

**Dependencies:**
- Story 3.3 (eligibility service)
- Story 1.4 (outreach_attempts with device activation columns)
- Shared: `af_code/shared/bland_ai_client.py`

**Testing Requirements:**
- [ ] Phase 1 creates batch with Pending status
- [ ] Phase 2 creates N attempt records with correct call_sequence_number
- [ ] Phase 3 submits to Bland AI successfully
- [ ] vendor_batch_id stored after successful submission
- [ ] Batch marked Failed if Bland AI rejects
- [ ] Transaction rollback on any failure
- [ ] request_data includes all device-specific fields
- [ ] metadata includes call_sequence_number and callback_type

---

**Sub-task 3.4.1: Create BatchOrchestrator Class**

**Description**: Define class with dependencies (DatabaseService, BlandAIClient)

**Acceptance**: Class initialized, submit_batch() method skeleton created

---

**Sub-task 3.4.2: Implement Phase 1 - Create Batch Record**

**Description**: INSERT into outreach_batches with Pending status

**Acceptance**: Single INSERT query, batch_id generated client-side, status='Pending'

---

**Sub-task 3.4.3: Implement Phase 2 - Create Attempt Records**

**Description**: INSERT N attempt records for each member

**Acceptance**: Bulk INSERT with executemany(), maps attempt_id to enrollment_id, sets call_sequence_number

---

**Sub-task 3.4.4: Implement Phase 3 - Build Bland AI Request**

**Description**: Construct BatchRequest with device activation-specific fields

**Acceptance**: request_data includes device fields, metadata includes call sequence and callback type

---

**Sub-task 3.4.5: Implement Phase 3 - Submit and Update Batch**

**Description**: Call BlandAIClient, update batch with vendor_batch_id

**Acceptance**: Updates batch status to 'Submitted', stores vendor_batch_id, handles errors

---

---

## COMPONENT 4: BUSINESS LOGIC (HOURS, HOLIDAYS, CALLBACKS)

### Story 4.1: Enhance Business Hours Validator for Device Activation

**Description:**
Enhance existing `BusinessHoursValidator` in `af_code/shared/business_hours_utils.py` to support device activation requirements: add_business_days SQL function, federal holiday calendar for 2025+, and dual-timezone validation (MG hours + member hours).

**Acceptance Criteria:**
- [ ] add_business_days() function calculates N business days forward excluding weekends and federal holidays
- [ ] Federal holiday calendar includes all 10 US federal holidays with observed dates
- [ ] is_business_day() checks weekday and holiday calendar
- [ ] can_make_call() validates both MG business hours (EST) and member timezone hours
- [ ] get_next_valid_call_time() finds next valid window respecting both timezones

**Technical Implementation Notes:**
- **File**: `af_code/shared/business_hours_utils.py`
- **Pattern reference**: Existing file may exist, enhance if present, create if not
- **Federal holidays** (using `holidays` library):
  ```python
  import holidays

  class BusinessHoursValidator:
      def __init__(self):
          self.us_holidays = holidays.US(observed=True, years=range(2025, 2030))
          self.mg_timezone = pytz.timezone('America/New_York')
          self.business_start_hour = 9
          self.business_end_hour = 17

      def is_business_day(self, dt: datetime) -> bool:
          """Check if date is a weekday and not a federal holiday"""
          if dt.weekday() >= 5:  # Saturday=5, Sunday=6
              return False
          if dt.date() in self.us_holidays:
              return False
          return True

      def add_business_days(self, start_date: date, num_days: int) -> date:
          """Add N business days to start_date, skipping weekends and holidays"""
          current_date = start_date
          days_added = 0

          while days_added < num_days:
              current_date += timedelta(days=1)
              if self.is_business_day(datetime.combine(current_date, datetime.min.time())):
                  days_added += 1

          return current_date

      def can_make_call(self, call_time: datetime, member_timezone: str) -> bool:
          """Validate call time within business hours for BOTH MG and member timezone"""
          # Check MG business hours (EST)
          mg_time = call_time.astimezone(self.mg_timezone)
          if not (self.business_start_hour <= mg_time.hour < self.business_end_hour):
              return False

          # Check member business hours
          member_tz = pytz.timezone(member_timezone)
          member_time = call_time.astimezone(member_tz)
          if not (self.business_start_hour <= member_time.hour < self.business_end_hour):
              return False

          # Check business day
          if not self.is_business_day(mg_time):
              return False

          return True
  ```

**SQL Function for add_business_days**:
```sql
CREATE FUNCTION dbo.add_business_days (@start_date DATE, @num_days INT)
RETURNS DATE
AS
BEGIN
    DECLARE @current_date DATE = @start_date;
    DECLARE @days_added INT = 0;

    WHILE @days_added < @num_days
    BEGIN
        SET @current_date = DATEADD(DAY, 1, @current_date);

        -- Check if weekday (Mon-Fri)
        IF DATEPART(WEEKDAY, @current_date) NOT IN (1, 7)  -- 1=Sunday, 7=Saturday
        BEGIN
            -- Check if not a federal holiday (use separate holiday table)
            IF NOT EXISTS (
                SELECT 1 FROM engage360.federal_holidays
                WHERE holiday_date = @current_date
            )
            BEGIN
                SET @days_added = @days_added + 1;
            END
        END
    END

    RETURN @current_date;
END
```

**Dependencies:**
- Story 1.3, 1.4 (database schema uses this function)
- Story 3.3 (eligibility queries use this function)

**Testing Requirements:**
- [ ] add_business_days(2025-01-01, 2) returns 2025-01-03 (skipping weekends)
- [ ] add_business_days(2025-12-23, 2) returns 2025-12-27 (skipping Christmas Dec 25)
- [ ] is_business_day() returns False for weekends
- [ ] is_business_day() returns False for federal holidays
- [ ] can_make_call() enforces dual-timezone validation
- [ ] can_make_call() rejects calls on holidays
- [ ] get_next_valid_call_time() finds next valid window

---

**Sub-task 4.1.1: Implement add_business_days() Python Function**

**Description**: Calculate N business days forward excluding weekends and holidays

**Acceptance**: Function handles weekends, federal holidays, returns correct date

---

**Sub-task 4.1.2: Create SQL add_business_days() Function**

**Description**: SQL function for use in database queries

**Acceptance**: Function deployed to SQL Server, returns correct dates, used in eligibility queries

---

**Sub-task 4.1.3: Create Federal Holidays Reference Table**

**Description**: Create engage360.federal_holidays table with 2025-2030 dates

**Acceptance**: Table populated with all 10 federal holidays, includes observed dates

---

**Sub-task 4.1.4: Implement Dual-Timezone Validation**

**Description**: Enhance can_make_call() to check both MG and member timezones

**Acceptance**: Function validates both EST and member timezone are in business hours

---

**Sub-task 4.1.5: Add Unit Tests**

**Description**: Comprehensive tests for business hours logic

**Acceptance**: Tests cover weekends, holidays, DST transitions, edge cases

---

### Story 4.2: Create Callback Queue Processor

**Description:**
Create `CallbackQueueProcessor` service to manage device activation callback queue: query pending callbacks, validate scheduled time, attempt callback execution, update attempt count, mark expired callbacks (>24 hours).

**Acceptance Criteria:**
- [ ] get_pending_callbacks() returns callbacks with scheduled_time <= now, not expired
- [ ] increment_attempt_count() updates attempt_count after each try
- [ ] mark_completed() sets callback_status='COMPLETED', completion_ts
- [ ] mark_failed() sets callback_status='FAILED' after 3 attempts
- [ ] mark_expired() sets callback_status='EXPIRED' for callbacks >24 hours old
- [ ] Expired callbacks trigger member return to main call sequence

**Technical Implementation Notes:**
- **File**: `af_code/device_activation_scheduler/services/callback_queue_processor.py`
- **Pattern**: New service, follows eligibility service pattern
- **Key methods**:
  ```python
  class CallbackQueueProcessor:
      def __init__(self, db_service: DatabaseService):
          self.db_service = db_service

      def get_pending_callbacks(self) -> List[CallbackMember]:
          """Query callbacks ready to execute"""
          query = """
          SELECT
              cq.callback_id,
              cq.enrollment_id,
              cq.member_id,
              cq.callback_type,
              cq.scheduled_time,
              cq.attempt_count,
              cq.max_attempts,
              m.first_name,
              m.last_name,
              m.primary_phone,
              m.timezone,
              mce.call_sequence_number
          FROM engage360.device_activation_callback_queue cq
          JOIN engage360.members m ON cq.member_id = m.member_id
          JOIN engage360.member_campaign_enrollments_enhanced mce ON cq.enrollment_id = mce.enrollment_id
          WHERE cq.callback_status = 'PENDING'
              AND cq.scheduled_time <= SYSDATETIMEOFFSET()
              AND cq.expires_at > SYSDATETIMEOFFSET()
              AND cq.attempt_count < cq.max_attempts
          ORDER BY cq.scheduled_time ASC;
          """
          return self.db_service.execute_query(query, fetch_results=True)

      def increment_attempt_count(self, callback_id: str):
          """Increment attempt count after each callback try"""
          query = """
          UPDATE engage360.device_activation_callback_queue
          SET attempt_count = attempt_count + 1,
              last_attempt_ts = SYSDATETIMEOFFSET()
          WHERE callback_id = %s;
          """
          self.db_service.execute_query(query, params=(callback_id,))

      def mark_expired_callbacks(self):
          """Mark callbacks older than 24 hours as expired"""
          query = """
          UPDATE engage360.device_activation_callback_queue
          SET callback_status = 'EXPIRED',
              completion_ts = SYSDATETIMEOFFSET()
          WHERE callback_status = 'PENDING'
              AND expires_at <= SYSDATETIMEOFFSET();
          """
          self.db_service.execute_query(query)
  ```

**Callback Queue Logic**:
1. Query pending callbacks scheduled for now
2. Filter expired (>24 hours)
3. Return to orchestrator for batch submission
4. After batch submission, increment attempt_count
5. If 3 attempts reached OR expired, mark accordingly

**Dependencies:**
- Story 1.6 (callback queue table)
- Story 3.2 (orchestrator integration)

**Testing Requirements:**
- [ ] get_pending_callbacks() returns only non-expired, scheduled callbacks
- [ ] increment_attempt_count() updates correctly
- [ ] mark_expired_callbacks() finds callbacks older than 24 hours
- [ ] Callback status transitions: PENDING → IN_PROGRESS → COMPLETED/FAILED/EXPIRED
- [ ] Attempt count increments correctly (0 → 1 → 2 → 3)

---

**Sub-task 4.2.1: Create CallbackQueueProcessor Class**

**Description**: Define service class with database dependency

**Acceptance**: Class initialized with DatabaseService, exposes callback management methods

---

**Sub-task 4.2.2: Implement get_pending_callbacks() Query**

**Description**: Query callbacks ready for execution

**Acceptance**: Returns callbacks with scheduled_time <= now, not expired, attempts < max

---

**Sub-task 4.2.3: Implement Attempt Count Management**

**Description**: Methods to increment attempts and mark status

**Acceptance**: increment_attempt_count(), mark_completed(), mark_failed() methods work

---

**Sub-task 4.2.4: Implement Expiration Logic**

**Description**: Mark callbacks older than 24 hours as expired

**Acceptance**: mark_expired_callbacks() updates status, sets completion_ts

---

**Sub-task 4.2.5: Add Unit Tests**

**Description**: Test callback queue processing logic

**Acceptance**: Tests cover pending queries, attempt counting, expiration

---

### Story 4.3: Create Call Sequencer Service

**Description:**
Create `CallSequencer` service to determine which call sequence number should be used for each member (Call 1, 2, 3, 4, or weekly call N) based on attempt history and business day calculations.

**Acceptance Criteria:**
- [ ] determine_sequence_number() calculates correct call number (1-15+)
- [ ] get_next_call_date() calculates when next call should occur
- [ ] Handles Call 1-3: 2 business days apart
- [ ] Handles Call 4+: 7 calendar days apart (weekly)
- [ ] Respects 90-day hard stop (campaign_end_date)

**Technical Implementation Notes:**
- **File**: `af_code/device_activation_scheduler/services/call_sequencer.py`
- **Pattern**: New service, business logic encapsulation
- **Key methods**:
  ```python
  class CallSequencer:
      def __init__(self, db_service: DatabaseService):
          self.db_service = db_service
          self.business_hours_validator = BusinessHoursValidator()

      def determine_sequence_number(self, enrollment_id: str) -> int:
          """Determine which call sequence number this should be"""
          query = """
          SELECT MAX(call_sequence_number) AS last_sequence
          FROM engage360.outreach_attempts
          WHERE enrollment_id = %s;
          """
          result = self.db_service.execute_query(query, params=(enrollment_id,), fetch_results=True)

          if not result or result[0]['last_sequence'] is None:
              return 1  # First call
          else:
              return result[0]['last_sequence'] + 1

      def get_next_call_date(self, last_attempt_date: date, sequence_number: int) -> date:
          """Calculate when next call should occur based on sequence"""
          if sequence_number in [2, 3]:
              # Call 2 and 3: 2 business days apart
              return self.business_hours_validator.add_business_days(last_attempt_date, 2)
          elif sequence_number == 4:
              # Call 4: 5 business days after Call 3
              return self.business_hours_validator.add_business_days(last_attempt_date, 5)
          else:
              # Call 5+: 7 calendar days apart (weekly)
              return last_attempt_date + timedelta(days=7)

      def is_past_campaign_end(self, campaign_end_date: date) -> bool:
          """Check if campaign has exceeded 90-day window"""
          return datetime.now(pytz.UTC).date() > campaign_end_date
  ```

**Call Sequence Rules**:
- **Call 1**: activation_start_date (delivery_date + 2 business days)
- **Call 2**: Call 1 date + 2 business days
- **Call 3**: Call 2 date + 2 business days
- **Call 4**: Call 3 date + 5 business days
- **Call 5+**: Previous call + 7 calendar days (weekly)
- **Hard stop**: campaign_end_date (activation_start_date + 90 days)

**Dependencies:**
- Story 4.1 (business hours validator)
- Story 3.3 (eligibility service uses this)

**Testing Requirements:**
- [ ] determine_sequence_number() returns 1 for no attempts
- [ ] determine_sequence_number() returns N+1 for N attempts
- [ ] get_next_call_date() calculates 2 business days for Call 2/3
- [ ] get_next_call_date() calculates 5 business days for Call 4
- [ ] get_next_call_date() calculates 7 calendar days for Call 5+
- [ ] is_past_campaign_end() correctly identifies expired campaigns

---

**Sub-task 4.3.1: Create CallSequencer Class**

**Description**: Define service class with database and business hours dependencies

**Acceptance**: Class initialized, exposes sequence determination methods

---

**Sub-task 4.3.2: Implement determine_sequence_number() Method**

**Description**: Query attempt history and calculate next sequence number

**Acceptance**: Returns correct number (1 for no attempts, N+1 for N attempts)

---

**Sub-task 4.3.3: Implement get_next_call_date() Method**

**Description**: Calculate next call date based on sequence rules

**Acceptance**: Handles 2 business days (Call 2/3), 5 business days (Call 4), 7 calendar days (Call 5+)

---

**Sub-task 4.3.4: Implement Campaign End Detection**

**Description**: Check if campaign has exceeded 90-day window

**Acceptance**: is_past_campaign_end() returns True if past campaign_end_date

---

**Sub-task 4.3.5: Add Unit Tests**

**Description**: Test call sequencing logic

**Acceptance**: Tests cover all sequence numbers, date calculations, edge cases

---

---

## COMPONENT 5: WEBHOOK INTEGRATION

### Story 5.1: Enhance Webhook Handler for Device Activation Dispositions

**Description:**
Enhance existing `WebhookHandler` to recognize device activation campaign type and handle device-specific dispositions: DEVICE_ACTIVATED, UNBOXING_NEEDED, CHARGING_NEEDED, CALLBACK_REQUESTED, MEMBER_NOT_AVAILABLE.

**Acceptance Criteria:**
- [ ] Detects campaign_type='Device_Activation' from metadata
- [ ] Routes device activation webhooks to DeviceActivationWebhookProcessor
- [ ] Existing DTC/Partner/Wellness webhook handling unchanged
- [ ] Logs device activation webhook processing with emoji prefix `🎯 [DA-WEBHOOK]`

**Technical Implementation Notes:**
- **File**: `af_code/bland_ai_webhook/webhook_handler.py`
- **Pattern**: Enhance existing handler with campaign type detection
- **Code enhancement**:
  ```python
  def process_webhook(self, webhook_data: Dict) -> Dict:
      """Enhanced to route device activation webhooks"""
      campaign_type = webhook_data.get("metadata", {}).get("campaign_type")

      if campaign_type == "Device_Activation":
          logger.info("🎯 [DA-WEBHOOK] Device activation webhook detected")
          processor = DeviceActivationWebhookProcessor(
              db_service=self.db_service,
              config_manager=self.config_manager
          )
          return processor.process(webhook_data)
      elif campaign_type == "Partner":
          # Existing partner logic
      elif campaign_type == "DTC_Intro":
          # Existing DTC intro logic
      # ... etc
  ```

**Dependencies:**
- Story 5.2 (device activation webhook processor)
- Existing webhook handler

**Testing Requirements:**
- [ ] campaign_type='Device_Activation' routes to correct processor
- [ ] Existing campaign types still route correctly
- [ ] Logs appear with correct emoji prefix
- [ ] Webhook returns 200 for successful device activation processing

---

**Sub-task 5.1.1: Add Campaign Type Detection**

**Description**: Detect campaign_type from webhook metadata

**Acceptance**: Code checks metadata.campaign_type, logs campaign type

---

**Sub-task 5.1.2: Route to Device Activation Processor**

**Description**: Instantiate and call DeviceActivationWebhookProcessor

**Acceptance**: If campaign_type='Device_Activation', delegates to new processor

---

**Sub-task 5.1.3: Maintain Backward Compatibility**

**Description**: Ensure existing webhook handling unchanged

**Acceptance**: Partner, DTC, Wellness webhooks still process correctly

---

### Story 5.2: Create Device Activation Webhook Processor

**Description:**
Create `DeviceActivationWebhookProcessor` to handle device activation-specific webhook processing: map dispositions to actions, update outreach_attempts, update enrollment status, handle callback queue creation, update device_activated flag.

**Acceptance Criteria:**
- [ ] Maps device activation dispositions to internal statuses
- [ ] DEVICE_ACTIVATED → Sets device_activated=1, activation_confirmed_ts
- [ ] UNBOXING_NEEDED → Creates callback in queue with callback_type='unboxing', scheduled_time=+2 hours
- [ ] CHARGING_NEEDED → Creates callback in queue with callback_type='charging', scheduled_time=+2 hours
- [ ] CALLBACK_REQUESTED → Creates callback in queue with callback_type='scheduled', member-specified time
- [ ] MEMBER_NOT_AVAILABLE → Creates callback with member-specified time
- [ ] Updates outreach_attempts with call_sequence_number from metadata
- [ ] Atomic transaction (all or nothing)

**Technical Implementation Notes:**
- **File**: `af_code/bland_ai_webhook/processors/device_activation_processor.py`
- **Pattern**: Similar to existing webhook processors
- **Disposition mapping**:
  ```python
  DEVICE_ACTIVATION_DISPOSITION_MAP = {
      ("completed", "DEVICE_ACTIVATED"): {
          "disposition": "Completed",
          "next_action": "Close",
          "update_enrollment": True,
          "new_status": "COMPLETED",
          "set_device_activated": True
      },
      ("completed", "UNBOXING_NEEDED"): {
          "disposition": "Pending",
          "next_action": "Callback",
          "create_callback": True,
          "callback_type": "unboxing",
          "callback_delay_hours": 2
      },
      ("completed", "CHARGING_NEEDED"): {
          "disposition": "Pending",
          "next_action": "Callback",
          "create_callback": True,
          "callback_type": "charging",
          "callback_delay_hours": 2
      },
      ("completed", "CALLBACK_REQUESTED"): {
          "disposition": "Pending",
          "next_action": "Scheduled",
          "create_callback": True,
          "callback_type": "scheduled",
          "use_member_preferred_time": True
      },
      ("completed", "MEMBER_NOT_AVAILABLE"): {
          "disposition": "NoAnswer",
          "next_action": "Retry",
          "create_callback": True,
          "callback_type": "scheduled"
      },
      ("completed", "NOT_INTERESTED"): {
          "disposition": "Completed",
          "next_action": "Close",
          "update_enrollment": True,
          "new_status": "COMPLETED"
      },
      ("completed", "DO_NOT_CONTACT"): {
          "disposition": "OptOut",
          "next_action": "Close",
          "update_enrollment": True,
          "new_status": "OPTED_OUT"
      },
      ("failed", None): {
          "disposition": "Failed",
          "next_action": "Retry"
      },
      ("no-answer", None): {
          "disposition": "NoAnswer",
          "next_action": "Retry"
      }
  }
  ```

**Transaction Statements**:
1. INSERT bland_call_logs (audit trail)
2. INSERT bland_raw_response (full webhook JSON)
3. UPDATE outreach_attempts (disposition, call_sequence_number, device_status_at_call)
4. UPDATE member_campaign_enrollments_enhanced (if device activated or opt-out)
5. UPDATE member_devices (if device activated: activation_date, last_signal_received_ts)
6. INSERT device_activation_callback_queue (if callback needed)

**Dependencies:**
- Story 5.1 (webhook handler routing)
- Story 1.6 (callback queue table)
- Story 1.2 (device activation columns in member_devices)
- Story 1.3 (device_activated column in enrollments)

**Testing Requirements:**
- [ ] DEVICE_ACTIVATED disposition sets device_activated=1
- [ ] UNBOXING_NEEDED creates callback with type='unboxing'
- [ ] CHARGING_NEEDED creates callback with type='charging'
- [ ] CALLBACK_REQUESTED creates callback with member's preferred time
- [ ] DO_NOT_CONTACT sets enrollment status to 'OPTED_OUT'
- [ ] All updates in single atomic transaction
- [ ] Rollback on any failure
- [ ] Webhook logs to bland_call_logs and bland_raw_response

---

**Sub-task 5.2.1: Create DeviceActivationWebhookProcessor Class**

**Description**: Define processor class with dependencies

**Acceptance**: Class initialized with DatabaseService and ConfigManager

---

**Sub-task 5.2.2: Implement Disposition Mapping**

**Description**: Map Bland AI webhook statuses to internal actions

**Acceptance**: DEVICE_ACTIVATION_DISPOSITION_MAP handles all device activation scenarios

---

**Sub-task 5.2.3: Implement Device Activation Logic**

**Description**: Update device_activated flag and activation_confirmed_ts

**Acceptance**: When disposition=DEVICE_ACTIVATED, updates enrollments and devices tables

---

**Sub-task 5.2.4: Implement Callback Queue Creation**

**Description**: Insert callback records for UNBOXING/CHARGING/CALLBACK_REQUESTED

**Acceptance**: Creates callback with correct type, scheduled_time, expires_at (24 hours)

---

**Sub-task 5.2.5: Implement Atomic Transaction**

**Description**: Wrap all 6 database operations in single transaction

**Acceptance**: Uses execute_transaction(), commits all or rolls back all

---

### Story 5.3: Create 90-Day Campaign Termination Job

**Description:**
Create scheduled job (Azure Function timer trigger) to identify device activation campaigns that have reached 90-day limit (campaign_end_date), update enrollment status to 'TERMINATED', flag MS customers for manual follow-up, and send final status to Salesforce.

**Acceptance Criteria:**
- [ ] Timer trigger runs daily (cron: `0 0 9 * * *` - 9 AM daily)
- [ ] Queries enrollments where campaign_end_date < today AND current_status='ENROLLED'
- [ ] Updates status to 'TERMINATED' for campaigns past 90 days
- [ ] For MS customers: Flags for human sales/support follow-up
- [ ] For DTC customers: No further action (process ends)
- [ ] Logs termination count with emoji prefix `🔚 [DA-TERMINATION]`
- [ ] Sends termination status to Salesforce (future integration point)

**Technical Implementation Notes:**
- **File**: `functions/device_activation_termination_job.py`
- **Pattern**: Simple timer trigger similar to batch reconciler
- **Timer schedule**: `0 0 9 * * *` (9 AM UTC daily)
- **Blueprint structure**:
  ```python
  import azure.functions as func
  import logging
  from af_code.device_activation_scheduler.services.termination_service import TerminationService

  bp = func.Blueprint()

  @bp.function_name(name="DeviceActivationTermination")
  @bp.timer_trigger(schedule="0 0 9 * * *", arg_name="timer", run_on_startup=False)
  def termination_job(timer: func.TimerRequest) -> None:
      logger.info("🔚 [DA-TERMINATION] Starting 90-day termination check")

      termination_service = TerminationService()
      result = termination_service.process_terminations()

      logger.info(f"🔚 [DA-TERMINATION] Processed {result['terminated_count']} campaigns")
      logger.info(f"🔚 [DA-TERMINATION] MS flagged: {result['ms_flagged_count']}, DTC ended: {result['dtc_ended_count']}")
  ```

**Termination Query**:
```sql
WITH ExpiredCampaigns AS (
    SELECT
        mce.enrollment_id,
        mce.member_id,
        mce.campaign_id,
        mce.activation_start_date,
        mce.campaign_end_date,
        mce.customer_type,
        mce.device_activated,
        m.salesforce_account_id
    FROM engage360.member_campaign_enrollments_enhanced mce
    JOIN engage360.members m ON mce.member_id = m.member_id
    WHERE mce.campaign_id = @device_activation_campaign_id
        AND mce.current_status = 'ENROLLED'
        AND CAST(SYSDATETIMEOFFSET() AS DATE) > mce.campaign_end_date
)
UPDATE engage360.member_campaign_enrollments_enhanced
SET current_status = 'TERMINATED',
    updated_ts = SYSDATETIMEOFFSET()
WHERE enrollment_id IN (SELECT enrollment_id FROM ExpiredCampaigns);

-- Flag MS customers for follow-up
INSERT INTO engage360.ms_customer_follow_up_queue (
    member_id, salesforce_account_id, campaign_id, reason, created_ts
)
SELECT
    member_id, salesforce_account_id, campaign_id,
    'Device activation campaign ended - 90 days reached without activation',
    SYSDATETIMEOFFSET()
FROM ExpiredCampaigns
WHERE customer_type = 'MS';
```

**Dependencies:**
- Story 1.3 (enrollments with campaign_end_date and customer_type)
- Story 3.2 (campaign orchestration)

**Testing Requirements:**
- [ ] Timer trigger fires daily at 9 AM
- [ ] Queries only campaigns past campaign_end_date
- [ ] Updates status to 'TERMINATED'
- [ ] MS customers flagged in follow-up queue
- [ ] DTC customers no further action
- [ ] Logs accurate count of terminated campaigns
- [ ] Idempotent (running multiple times doesn't duplicate)

---

**Sub-task 5.3.1: Create Timer Trigger Blueprint**

**Description**: Create functions/device_activation_termination_job.py

**Acceptance**: Timer trigger defined, runs daily at 9 AM

---

**Sub-task 5.3.2: Create TerminationService Class**

**Description**: Service to identify and process expired campaigns

**Acceptance**: Class queries campaigns past campaign_end_date, updates status

---

**Sub-task 5.3.3: Implement MS Customer Flagging**

**Description**: Flag MS customers for manual follow-up

**Acceptance**: Inserts records into ms_customer_follow_up_queue for MS customers

---

**Sub-task 5.3.4: Implement Salesforce Integration (Placeholder)**

**Description**: Add placeholder for Salesforce status update

**Acceptance**: TODO comment for future Salesforce API integration

---

**Sub-task 5.3.5: Add Unit Tests**

**Description**: Test termination logic

**Acceptance**: Tests verify correct campaigns terminated, MS flagging works

---

---

## COMPONENT 6: TESTING & QUALITY ASSURANCE

### Story 6.1: Create Unit Tests for Device Activation Validators

**Description:**
Create comprehensive unit tests for all validator classes: FileNameValidator, ColumnValidator, DataCleanerAndValidator, DeviceValidator using pytest framework.

**Acceptance Criteria:**
- [ ] Test file created: `tests/test_device_activation_validators.py`
- [ ] FileNameValidator tests: valid patterns, invalid patterns, date extraction
- [ ] ColumnValidator tests: missing required columns, unexpected columns
- [ ] DataCleanerAndValidator tests: phone cleansing, date parsing, timezone validation
- [ ] DeviceValidator tests: enum validation, UDI format, boolean parsing
- [ ] Code coverage >= 90% for validator modules
- [ ] All tests pass with pytest

**Technical Implementation Notes:**
- **File**: `tests/test_device_activation_validators.py`
- **Pattern reference**: Existing test files (if any), pytest best practices
- **Test structure**:
  ```python
  import pytest
  from af_code.af_device_activation_logic import (
      FileNameValidator, ColumnValidator, DataCleanerAndValidator, DeviceValidator
  )

  class TestFileNameValidator:
      def test_valid_filename(self):
          filename = "MedicalGuardian_DeviceActivation_20250115_Delta.csv"
          is_valid, errors, metadata = FileNameValidator.validate(filename)
          assert is_valid is True
          assert metadata['date'] == '20250115'

      def test_invalid_filename_pattern(self):
          filename = "InvalidFile_20250115.csv"
          is_valid, errors, metadata = FileNameValidator.validate(filename)
          assert is_valid is False
          assert len(errors) > 0

      # ... more tests

  class TestColumnValidator:
      def test_all_required_columns_present(self):
          columns = ['salesforce_account_id', 'salesforce_account_number', ...]
          is_valid, errors = ColumnValidator.validate(columns)
          assert is_valid is True

      def test_missing_required_column(self):
          columns = ['salesforce_account_id']  # Missing others
          is_valid, errors = ColumnValidator.validate(columns)
          assert is_valid is False

      # ... more tests
  ```

**Dependencies:**
- Story 2.3 (validators implemented)

**Testing Requirements:**
- [ ] All tests pass in local environment
- [ ] All tests pass in CI/CD pipeline
- [ ] Code coverage report generated
- [ ] No test failures or warnings

---

**Sub-task 6.1.1: Create Test File Structure**

**Description**: Create tests/test_device_activation_validators.py with pytest setup

**Acceptance**: File created with imports, test classes defined

---

**Sub-task 6.1.2: Write FileNameValidator Tests**

**Description**: Test valid/invalid filenames, date extraction

**Acceptance**: 5+ test cases covering valid, invalid, edge cases

---

**Sub-task 6.1.3: Write ColumnValidator Tests**

**Description**: Test required columns, optional columns, unexpected columns

**Acceptance**: 5+ test cases covering all column scenarios

---

**Sub-task 6.1.4: Write DataCleanerAndValidator Tests**

**Description**: Test row-level validation and cleansing

**Acceptance**: 10+ test cases covering phone, date, name, timezone, state validation

---

**Sub-task 6.1.5: Write DeviceValidator Tests**

**Description**: Test device-specific field validation

**Acceptance**: 5+ test cases covering device_udi, fall_detection, battery_status, boolean parsing

---

### Story 6.2: Create Integration Tests for File Processing End-to-End

**Description:**
Create integration test that uploads sample CSV file, triggers file processor, validates staging table insertion, verifies core table MERGE, and confirms enrollment creation.

**Acceptance Criteria:**
- [ ] Test file created: `tests/integration/test_device_activation_file_processing.py`
- [ ] Sample CSV file: `tests/fixtures/sample_device_activation.csv`
- [ ] Test uploads CSV to blob storage (test container)
- [ ] Validates blob trigger fires
- [ ] Checks staging table for processed records
- [ ] Checks members, member_devices, enrollments tables updated
- [ ] Validates activation_start_date calculated correctly
- [ ] Cleans up test data after execution

**Technical Implementation Notes:**
- **File**: `tests/integration/test_device_activation_file_processing.py`
- **Fixtures**: `tests/fixtures/sample_device_activation.csv`
- **Test structure**:
  ```python
  import pytest
  from azure.storage.blob import BlobServiceClient
  from af_code.af_device_activation_logic import process_device_activation_file_complete

  @pytest.fixture
  def sample_csv_file():
      return "tests/fixtures/sample_device_activation.csv"

  @pytest.fixture
  def test_db_connection():
      # Return test database connection
      pass

  def test_end_to_end_file_processing(sample_csv_file, test_db_connection):
      # 1. Upload CSV to test blob storage
      # 2. Call process_device_activation_file_complete()
      # 3. Verify staging table has records
      # 4. Verify members table updated
      # 5. Verify devices table updated
      # 6. Verify enrollments created
      # 7. Verify activation_start_date calculated
      # 8. Clean up test data
      pass
  ```

**Sample CSV Content** (3 test members):
```csv
salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,member_phone_number,member_email,service_address,city,state,zip,dob,customer_timezone,language_pref,device_udi,device_name,brand,device_phone_number,is_device_callable,delivery_date,fall_detection_status,battery_status,partner_name,customer_type,enrollment_status
SF-TEST-001,ACC-TEST-001,John,Doe,+15551234567,john@test.com,123 Test St,Boston,MA,02101,1950-01-15,America/New_York,EN,TEST-UDI-001,MGMini,Medical Guardian,+15551234568,Y,2025-01-06,Active,Good,Medical Guardian,DTC,ENROLL
SF-TEST-002,ACC-TEST-002,Jane,Smith,+15559876543,jane@test.com,456 Test Ave,Los Angeles,CA,90001,1955-03-20,America/Los_Angeles,ES,TEST-UDI-002,MGMini,Medical Guardian,,N,2025-01-05,Inactive,Low,Medical Guardian,MS,ENROLL
SF-TEST-003,ACC-TEST-003,Bob,Johnson,+15556543210,bob@test.com,789 Test Blvd,Chicago,IL,60601,1948-07-10,America/Chicago,EN,TEST-UDI-003,MGMini,Medical Guardian,+15556543211,Y,2025-01-04,Active,Unknown,Medical Guardian,DTC,UPDATE
```

**Dependencies:**
- Story 2.1, 2.2, 2.4 (file processing implemented)
- Test database environment

**Testing Requirements:**
- [ ] Test passes in local environment
- [ ] Test passes in CI/CD with test database
- [ ] Test data cleaned up (no orphaned records)
- [ ] All assertions pass
- [ ] Test completes within 60 seconds

---

**Sub-task 6.2.1: Create Sample CSV Fixture**

**Description**: Create tests/fixtures/sample_device_activation.csv with 3 test members

**Acceptance**: CSV file with valid data matching specification

---

**Sub-task 6.2.2: Create Integration Test Structure**

**Description**: Set up pytest fixtures for blob storage and database

**Acceptance**: Fixtures provide test blob client and test database connection

---

**Sub-task 6.2.3: Implement End-to-End Test**

**Description**: Test full file processing workflow

**Acceptance**: Test uploads CSV, processes, validates results, cleans up

---

**Sub-task 6.2.4: Add Database Assertions**

**Description**: Verify staging and core tables updated correctly

**Acceptance**: Assertions check record counts, field values, activation dates

---

**Sub-task 6.2.5: Implement Cleanup Logic**

**Description**: Delete test data after test completes

**Acceptance**: Test data removed from staging and core tables

---

### Story 6.3: Create Integration Tests for Scheduler and Batch Submission

**Description:**
Create integration test for device activation scheduler: seed test enrollments, execute scheduler, validate batch creation, verify Bland AI submission (mocked), check outreach_attempts created.

**Acceptance Criteria:**
- [ ] Test file created: `tests/integration/test_device_activation_scheduler.py`
- [ ] Seeds 5 test enrollments in different call sequence states
- [ ] Executes DeviceActivationOrchestrator.execute()
- [ ] Validates batch record created in outreach_batches
- [ ] Validates attempt records created in outreach_attempts
- [ ] Mocks Bland AI client to avoid actual API calls
- [ ] Verifies call_sequence_number set correctly
- [ ] Cleans up test data

**Technical Implementation Notes:**
- **File**: `tests/integration/test_device_activation_scheduler.py`
- **Pattern**: Integration test with mocked external dependencies
- **Test structure**:
  ```python
  import pytest
  from unittest.mock import patch, MagicMock
  from af_code.device_activation_scheduler.orchestrator import DeviceActivationOrchestrator

  @pytest.fixture
  def test_enrollments(test_db_connection):
      # Seed 5 test enrollments:
      # 1. Ready for Call 1 (activation_start_date = today)
      # 2. Ready for Call 2 (last attempt 2 business days ago, Call 1)
      # 3. Ready for Call 3 (last attempt 2 business days ago, Call 2)
      # 4. Ready for weekly (last attempt 7 days ago, Call 4)
      # 5. Callback pending (in callback queue)
      pass

  @patch('af_code.shared.bland_ai_client.BlandAIClient.submit_batch_calls')
  def test_scheduler_execution(mock_bland_submit, test_enrollments, test_db_connection):
      # Mock Bland AI response
      mock_bland_submit.return_value = {
          "success": True,
          "batch_id": "test-batch-id-123",
          "calls_submitted": 5
      }

      # Execute scheduler
      orchestrator = DeviceActivationOrchestrator()
      result = orchestrator.execute()

      # Assertions
      assert result["success"] is True
      assert result["members"] == 5

      # Verify batch created
      # Verify attempts created with correct call_sequence_number
      # Verify Bland AI called with correct payload

      # Cleanup
      pass
  ```

**Dependencies:**
- Story 3.2, 3.3, 3.4 (scheduler implemented)
- Story 6.2 (test database setup pattern)

**Testing Requirements:**
- [ ] Test passes with mocked Bland AI client
- [ ] All 5 test enrollments processed
- [ ] Batch and attempts created correctly
- [ ] call_sequence_number values: 1, 2, 3, 5, callback
- [ ] Test data cleaned up
- [ ] Test completes within 30 seconds

---

**Sub-task 6.3.1: Create Test Enrollment Fixtures**

**Description**: Seed 5 test enrollments in different call states

**Acceptance**: Fixtures create members, devices, enrollments, attempts for each scenario

---

**Sub-task 6.3.2: Mock Bland AI Client**

**Description**: Use unittest.mock to mock BlandAIClient.submit_batch_calls

**Acceptance**: Mock returns success response, test doesn't call real API

---

**Sub-task 6.3.3: Implement Scheduler Execution Test**

**Description**: Execute orchestrator and validate results

**Acceptance**: Test calls execute(), verifies batch creation, attempts creation

---

**Sub-task 6.3.4: Add Batch and Attempt Assertions**

**Description**: Verify database records created correctly

**Acceptance**: Assertions check outreach_batches and outreach_attempts tables

---

**Sub-task 6.3.5: Implement Cleanup Logic**

**Description**: Delete all test data after test

**Acceptance**: Test members, enrollments, batches, attempts removed

---

### Story 6.4: Create Integration Tests for Webhook Processing

**Description:**
Create integration test for device activation webhook processing: mock webhook payload, process through DeviceActivationWebhookProcessor, verify database updates, validate callback queue creation for UNBOXING_NEEDED.

**Acceptance Criteria:**
- [ ] Test file created: `tests/integration/test_device_activation_webhook.py`
- [ ] Test payloads for each disposition: DEVICE_ACTIVATED, UNBOXING_NEEDED, CHARGING_NEEDED, etc.
- [ ] Processes webhook through DeviceActivationWebhookProcessor
- [ ] Validates outreach_attempts updated
- [ ] Validates device_activated flag set (for DEVICE_ACTIVATED)
- [ ] Validates callback queue record created (for UNBOXING_NEEDED)
- [ ] Validates enrollment status updated (for DO_NOT_CONTACT)
- [ ] Cleans up test data

**Technical Implementation Notes:**
- **File**: `tests/integration/test_device_activation_webhook.py`
- **Test structure**:
  ```python
  import pytest
  from af_code.bland_ai_webhook.processors.device_activation_processor import DeviceActivationWebhookProcessor

  @pytest.fixture
  def webhook_payload_device_activated():
      return {
          "call_id": "test-call-123",
          "status": "completed",
          "from": "+15551111111",
          "to": "+15551234567",
          "disposition_tag": "DEVICE_ACTIVATED",
          "metadata": {
              "attempt_id": "test-attempt-uuid",
              "enrollment_id": "test-enrollment-uuid",
              "member_id": "test-member-uuid",
              "campaign_type": "Device_Activation",
              "call_sequence_number": 1
          }
      }

  def test_device_activated_webhook(webhook_payload_device_activated, test_db_connection):
      # Seed test enrollment with device_activated=0
      # Process webhook
      processor = DeviceActivationWebhookProcessor(db_service, config_manager)
      result = processor.process(webhook_payload_device_activated)

      # Verify device_activated = 1
      # Verify activation_confirmed_ts set
      # Verify outreach_attempts updated
      # Verify bland_call_logs created

      # Cleanup
      pass

  def test_unboxing_needed_webhook(webhook_payload_unboxing, test_db_connection):
      # Process webhook with UNBOXING_NEEDED disposition
      # Verify callback queue record created
      # Verify callback_type = 'unboxing'
      # Verify scheduled_time = now + 2 hours
      # Cleanup
      pass
  ```

**Test Dispositions**:
1. DEVICE_ACTIVATED
2. UNBOXING_NEEDED
3. CHARGING_NEEDED
4. CALLBACK_REQUESTED
5. MEMBER_NOT_AVAILABLE
6. NOT_INTERESTED
7. DO_NOT_CONTACT

**Dependencies:**
- Story 5.2 (webhook processor implemented)
- Story 6.2 (test database pattern)

**Testing Requirements:**
- [ ] All 7 disposition tests pass
- [ ] Database updates verified for each disposition
- [ ] Callback queue creation tested
- [ ] device_activated flag update tested
- [ ] Test data cleaned up
- [ ] All tests complete within 60 seconds total

---

**Sub-task 6.4.1: Create Webhook Payload Fixtures**

**Description**: Create pytest fixtures for each disposition type

**Acceptance**: 7 fixtures defined, each with complete webhook payload

---

**Sub-task 6.4.2: Implement DEVICE_ACTIVATED Test**

**Description**: Test device activation webhook processing

**Acceptance**: Verifies device_activated=1, activation_confirmed_ts set, status updated

---

**Sub-task 6.4.3: Implement UNBOXING_NEEDED Test**

**Description**: Test callback queue creation for unboxing

**Acceptance**: Verifies callback record created with type='unboxing', scheduled_time=+2 hours

---

**Sub-task 6.4.4: Implement CHARGING_NEEDED Test**

**Description**: Test callback queue creation for charging

**Acceptance**: Verifies callback record created with type='charging', scheduled_time=+2 hours

---

**Sub-task 6.4.5: Implement DO_NOT_CONTACT Test**

**Description**: Test opt-out enrollment status update

**Acceptance**: Verifies enrollment status='OPTED_OUT', disposition='OptOut'

---

### Story 6.5: Create Performance and Load Tests

**Description:**
Create performance tests to validate device activation system handles expected load: 1000 members per day (file processing), 80 members per scheduler execution (batch submission), 200 webhooks per hour (webhook processing).

**Acceptance Criteria:**
- [ ] Load test file created: `tests/performance/test_device_activation_load.py`
- [ ] File processing: 1000-row CSV completes within 10 minutes
- [ ] Scheduler execution: 80 members processed within 2 minutes
- [ ] Webhook processing: 200 webhooks processed within 5 minutes
- [ ] Database queries remain performant (<5 seconds per query)
- [ ] Memory usage stays within acceptable limits (< 2 GB)

**Technical Implementation Notes:**
- **File**: `tests/performance/test_device_activation_load.py`
- **Tools**: pytest-benchmark, locust, or custom timing code
- **Test structure**:
  ```python
  import pytest
  from time import time

  def test_file_processing_1000_members(benchmark):
      # Generate 1000-row CSV
      # Measure time to process
      start = time()
      result = process_device_activation_file_complete(...)
      duration = time() - start

      assert duration < 600  # 10 minutes
      assert result.records_processed == 1000

  def test_scheduler_80_members(benchmark):
      # Seed 80 eligible members
      # Measure time to execute scheduler
      start = time()
      orchestrator.execute()
      duration = time() - start

      assert duration < 120  # 2 minutes

  def test_webhook_processing_200_webhooks(benchmark):
      # Generate 200 webhook payloads
      # Measure time to process all
      start = time()
      for webhook in webhooks:
          processor.process(webhook)
      duration = time() - start

      assert duration < 300  # 5 minutes
  ```

**Dependencies:**
- All previous stories (full system implemented)
- Performance testing environment

**Testing Requirements:**
- [ ] Tests pass in performance environment (not dev)
- [ ] Timing assertions met
- [ ] No memory leaks detected
- [ ] Database connection pooling validated
- [ ] Results documented for baseline

---

**Sub-task 6.5.1: Create Large CSV Generator**

**Description**: Generate 1000-row CSV for load testing

**Acceptance**: Script creates valid CSV with 1000 unique test members

---

**Sub-task 6.5.2: Implement File Processing Load Test**

**Description**: Measure file processing performance

**Acceptance**: 1000 members processed within 10 minutes

---

**Sub-task 6.5.3: Implement Scheduler Load Test**

**Description**: Measure scheduler performance with 80 members

**Acceptance**: 80 members processed within 2 minutes

---

**Sub-task 6.5.4: Implement Webhook Load Test**

**Description**: Measure webhook processing throughput

**Acceptance**: 200 webhooks processed within 5 minutes

---

**Sub-task 6.5.5: Document Performance Baselines**

**Description**: Record timing results for future comparison

**Acceptance**: Performance report created with benchmarks

---

---

## Summary

**Total Stories**: 25 stories across 6 components
**Total Sub-tasks**: 125+ sub-tasks
**Estimated Complexity**: Large (3-6 months for 2-3 developers)

**Critical Path**:
1. Database Schema (Component 1) - Must complete first
2. File Processor (Component 2) - Depends on schema
3. Business Logic (Component 4) - Parallel with scheduler
4. Scheduler (Component 3) - Depends on business logic
5. Webhook Integration (Component 5) - Parallel with scheduler
6. Testing (Component 6) - Throughout implementation

**Dependencies Graph**:
```
Component 1 (Database) → Component 2 (File Processor)
                       → Component 4 (Business Logic) → Component 3 (Scheduler)
                                                      → Component 5 (Webhook)
Component 6 (Testing) - Parallel with all components
```

---

**Next Steps After Planning**:
1. Review and refine JIRA tickets with team
2. Assign story points and priorities
3. Create sprints (recommend 2-week sprints)
4. Start with Component 1 (Database Schema) in Sprint 1
5. Parallel track Component 2 and 4 in Sprint 2-3
6. Integration work Component 3 and 5 in Sprint 4-5
7. Testing and refinement Sprint 6+
