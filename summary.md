# IOE Services Platform - Project Context Summary

**Generated**: 2025-10-20
**Analysis Tool**: Claude Code Primer
**Python Version**: 3.12
**Azure Functions Runtime**: v4

---

## Project Structure

Based on comprehensive analysis of the codebase, here's the complete project structure:

```
IOE-functions/
├── function_app.py                          # Main entry point - registers 7 Azure Functions
├── host.json                                # Azure Functions runtime configuration
├── requirements.txt                         # Python dependencies (15 packages)
├── local.settings.json                      # Local development environment config
│
├── functions/                               # 7 Azure Function trigger definitions
│   ├── dtc_file_processor.py               # Blob trigger for DTC wellness CSV files
│   ├── partner_file_processor.py           # Blob trigger for partner campaign CSVs
│   ├── dtc_intro_call_scheduler.py         # Timer (every 10 min) + HTTP trigger
│   ├── dtc_wellness_check_scheduler.py     # Timer trigger for wellness calls
│   ├── partner_campaign_scheduler.py       # Timer (every 30 min) + HTTP trigger
│   ├── bland_ai_webhook.py                 # HTTP webhook for Bland AI callbacks
│   └── batch_completion_reconciler.py      # Timer (every 5 min) for batch status sync
│
├── af_code/                                # Core business logic (62 Python files)
│   ├── af_dtc_logic.py                     # DTC campaign processing (115KB)
│   ├── af_partner_logic.py                 # Partner campaign validation (66KB)
│   │
│   ├── bland_ai_webhook/                   # Webhook processing module
│   │   ├── webhook_handler.py              # Main webhook orchestration
│   │   ├── models/                         # Pydantic data models
│   │   │   ├── mapped_call_data.py
│   │   │   ├── enrollment_update.py
│   │   │   ├── validation_result.py
│   │   │   └── error_enums.py
│   │   │
│   │   ├── services/                       # Business service layer (10 services)
│   │   │   ├── config_manager.py           # Azure Key Vault integration
│   │   │   ├── database_service.py         # pymssql connection management
│   │   │   ├── database_orchestrator.py    # Transaction coordination
│   │   │   ├── data_validator.py           # Input validation
│   │   │   ├── duplicate_detector.py       # Deduplication logic
│   │   │   ├── status_mapper.py            # Disposition mapping
│   │   │   ├── business_rules_engine.py    # Campaign-specific rules
│   │   │   ├── error_handler.py            # Error categorization
│   │   │   └── service_bus_handler.py      # Azure Service Bus messaging
│   │   │
│   │   └── utils/                          # Logging and configuration
│   │       ├── config.py
│   │       └── logging_config.py
│   │
│   ├── af_dtc_intro_call/                  # DTC intro call scheduling
│   │   ├── main_logic.py
│   │   ├── services/
│   │   └── utils/
│   │
│   ├── af_dtc_wellness_check/              # Wellness check call scheduling
│   ├── partner_campaign_scheduler/         # Partner campaign logic
│   │   └── CAMPAIGN_QUALIFICATION_LOGIC.md # 1300+ lines of timezone logic
│   │
│   └── shared/                             # Shared utilities
│       ├── bland_ai_client.py              # Unified Bland AI API client
│       ├── batch_sync_coordinator.py       # Batch reconciliation
│       ├── bland_ai_batch_monitor.py       # Batch status monitoring
│       └── timezone_utils.py               # TimezoneConverter utility
│
└── Documentation (16 .md files):
    ├── CLAUDE.md                           # Claude Code instructions (580 lines)
    ├── README.md                           # Project overview (812 lines)
    ├── ENGAGE360_TABLE_USAGE_REFERENCE.md  # Database schema (2,731 words)
    ├── PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md (7,108 words)
    ├── DTC_CALL_FLOW.md                    # DTC workflow (1,686 words)
    ├── WEBHOOK_TESTING_GUIDE.md            # Testing instructions
    ├── CSV_TESTING_GUIDE.md                # File processing tests
    ├── BATCH_CREATION_AND_NAVIGATION_FLOW.md
    ├── DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md
    └── af_code/BLAND_AI_BATCH_CALL_ARCHITECTURE.md
```

**Statistics**:
- 62 Python files
- 16 comprehensive documentation files
- Total codebase size: ~57MB (including dependencies)

---

## Project Purpose and Goals

### What is IOE?
**IOE** = **Intelligence Orchestration Engine** - Medical Guardian's healthcare automation platform

### Primary Purpose
A **HIPAA-compliant serverless healthcare automation system** that:

1. **Automates Member Outreach** - Schedules and manages AI-powered voice calls to healthcare members
2. **Processes Campaign Data** - Ingests and validates DTC wellness and partner campaign files
3. **Orchestrates AI Interactions** - Integrates with Bland AI for intelligent voice conversations
4. **Manages Call Outcomes** - Processes webhook callbacks and updates member enrollment status
5. **Maintains Compliance** - Ensures complete audit trails and PHI (Protected Health Information) security

### Business Context
- **Organization**: Medical Guardian (healthcare technology company)
- **Team**: AI-POD Data Science Team
- **Environment**: Production healthcare system processing PHI
- **Compliance**: HIPAA, SOC 2 Type II, Azure Security Standards
- **Deployment**: Azure Functions v4 (serverless microservices)

### Key Features
- 📁 **Automated File Processing** - DTC wellness and partner campaign file processing with validation
- 📞 **Smart Call Scheduling** - Automated intro call scheduling with timezone optimization
- 🤖 **AI Voice Integration** - Bland AI webhook processing for intelligent customer interactions
- 🛡️ **Enterprise Security** - Azure Key Vault integration and comprehensive data validation
- 📊 **Real-time Monitoring** - Complete observability with Azure Application Insights
- 🔄 **Resilient Processing** - Retry mechanisms and robust error handling
- 🏷️ **Business Traceability** - Comprehensive BusinessCaseID tracking for compliance

---

## 7 Independent Azure Functions

### 1. 📁 **DTC File Processor** (`functions/dtc_file_processor.py`)
- **Trigger**: Blob Storage Trigger
- **Container**: `fs-dtc/landing/`
- **Pattern**: `MedicalGuardian_DTCWellness_*_Delta.csv`
- **Purpose**: Process daily wellness campaign eligibility files
- **Workflow**:
  1. File detection in blob container
  2. Filename validation against naming convention
  3. CSV schema validation using Pandera
  4. Database updates with customer eligibility
  5. Processing reports and error logs
- **BusinessCaseID**: BC-109

### 2. 🤝 **Partner File Processor** (`functions/partner_file_processor.py`)
- **Trigger**: Blob Storage Trigger
- **Container**: `fs-partner/landing/`
- **Pattern**: `PartnerName_CampaignName_YYYYMMDD[_Suffix].csv`
- **Purpose**: Validate and ingest partner campaign files
- **Validation**: 4-table pattern with care gap validation:
  - `partner_file_processing_log` - File-level tracking
  - `partner_row_validation_results` - Row-level summary
  - `partner_validation_error_details_file` - File-level errors
  - `partner_validation_error_details_row` - Row-level field errors
- **Error Threshold**: 15% row errors allowed
- **BusinessCaseID**: BC-109

### 3. ⏰ **DTC Intro Call Scheduler** (`functions/dtc_intro_call_scheduler.py`)
- **Triggers**:
  - Timer: Every 10 minutes (`0 */10 * * * *`)
  - HTTP POST: `/api/create_dtc_intro_batch`
- **Purpose**: Schedule introduction calls for new wellness program members
- **Qualification Logic**: **One attempt per member per day** (simplified from previous 5-attempt logic)
- **Qualification Criteria**:
  - ✅ Campaign status = 'Active'
  - ✅ Member enrollment status = 'PENDING'
  - ✅ Valid timezone and preferred window
  - ✅ Current time within member's preferred window
  - ✅ Today is a valid call day for the member
  - ❌ NO attempt made today (any previous attempt blocks qualification)
- **Timezone Support**: Both `operating_tz` and `member_tz` modes
- **BusinessCaseID**: BC-105

### 4. 🏥 **DTC Wellness Check Scheduler** (`functions/dtc_wellness_check_scheduler.py`)
- **Trigger**: Timer trigger
- **Purpose**: Schedule ongoing wellness check calls for enrolled members
- **Frequency Protection**: Respects campaign frequency settings (e.g., 1 week between calls)
- **Disposition Tracking**: Excludes members with 'Completed' or 'Pending' dispositions
- **BusinessCaseID**: BC-105

### 5. 👥 **Partner Campaign Scheduler** (`functions/partner_campaign_scheduler.py`)
- **Triggers**:
  - Timer: Every 30 minutes (`0 */30 * * * *`)
  - HTTP POST endpoint
- **Purpose**: Schedule partner campaign outreach calls
- **Timezone Logic**: 1300+ lines of comprehensive qualification logic in `CAMPAIGN_QUALIFICATION_LOGIC.md`
- **Features**:
  - Member-wise frequency and retry logic based on disposition
  - Support for Pending disposition handling
  - All 18+ Bland AI global parameters
  - Encrypted_key header for Twilio integration
- **BusinessCaseID**: BC-105

### 6. 🤖 **Bland AI Webhook** (`functions/bland_ai_webhook.py`)
- **Trigger**: HTTP POST Webhook
- **Route**: `/api/bland-ai-webhook`
- **Authentication**: Function-level auth
- **Purpose**: Process real-time call completion data from Bland AI
- **Features**:
  - **Idempotent processing** - DuplicateDetector prevents duplicate processing
  - **Disposition mapping** - StatusMapper translates Bland AI dispositions
  - **Business rules engine** - Campaign-specific follow-up actions
  - **Service Bus integration** - Queue post-call analysis tasks
- **Services Initialized**:
  - ConfigManager, DatabaseService, DataValidator
  - DatabaseOrchestrator, DuplicateDetector, StatusMapper
  - BusinessRulesEngine, ErrorHandler, ServiceBusHandler
- **BusinessCaseID**: BC-101, BC-102

### 7. 🔄 **Batch Completion Reconciler** (`functions/batch_completion_reconciler.py`)
- **Trigger**: Timer (every 5 minutes)
- **Purpose**: Sync batch statuses with Bland AI API
- **Features**:
  - **Distributed locking** - Uses `system_locks` table to prevent concurrent runs
  - **Batch status updates** - Queries Bland AI API for batch completion
  - **Automatic cleanup** - Expires old locks
- **Lock Pattern**:
  1. Delete expired locks
  2. INSERT new lock (fails if concurrent execution)
  3. Process batches
  4. DELETE lock to release
- **BusinessCaseID**: BC-106

---

## Key Files and Their Purposes

### Core Application Files

| File | Purpose | Key Details |
|------|---------|-------------|
| `function_app.py` (80 lines) | Application bootstrap | Registers all 7 function blueprints with try/except error handling |
| `host.json` (15 lines) | Runtime configuration | Application Insights sampling, extension bundle v4 |
| `requirements.txt` (45 lines) | Dependencies | 15 packages: azure-functions, pandas, pymssql, pytz, tenacity, etc. |
| `local.settings.json` (8 lines) | Local dev config | ⚠️ Contains Service Bus connection string (should be in Key Vault) |
| `mypy.ini` | Type checking config | Python 3.12, basic type checking enabled |
| `.gitignore` (98 lines) | Version control | Excludes `.claude/`, `CLAUDE.md`, `local.settings.json`, cache files |

### Critical Services (Shared Infrastructure)

| Service | Location | Lines | Purpose |
|---------|----------|-------|---------|
| **ConfigManager** | `af_code/bland_ai_webhook/services/config_manager.py` | ~150 | Azure Key Vault integration, retrieves secrets (DB, Bland AI, Twilio) |
| **DatabaseService** | `af_code/bland_ai_webhook/services/database_service.py` | ~200 | **Sole authority** for SQL Server connections using pymssql |
| **BlandAIClient** | `af_code/shared/bland_ai_client.py` | ~300 | Unified Bland AI API client for all functions |
| **TimezoneConverter** | `af_code/shared/timezone_utils.py` | ~150 | Timezone normalization (EST/CST/MST/PST → pytz) |
| **DatabaseOrchestrator** | `af_code/bland_ai_webhook/services/database_orchestrator.py` | ~600 | Multi-table transaction coordination |
| **StatusMapper** | `af_code/bland_ai_webhook/services/status_mapper.py` | ~200 | Maps Bland AI dispositions to internal statuses |

### Business Logic Layers

| File | Size | Purpose |
|------|------|---------|
| `af_dtc_logic.py` | 115KB (~1,500 lines) | Complete DTC campaign processing logic |
| `af_partner_logic.py` | 66KB (~900 lines) | Partner file validation with 4-table error tracking |
| `webhook_handler.py` | ~600 lines | Bland AI webhook orchestration |
| `business_rules_engine.py` | ~300 lines | Campaign-specific business rules |
| `duplicate_detector.py` | ~100 lines | Duplicate call detection logic |
| `error_handler.py` | ~200 lines | Error categorization and handling |

---

## Database Architecture (engage360 Schema)

### Core Tables (23 actively used out of 65 total)

**Master Data**:
- `campaigns_enhanced` - Campaign configuration (Active/Inactive, timezone settings, frequency rules)
- `members` - Member/patient master table (10 references)
- `orgs` - Organization/partner reference data

**Campaign Enrollment**:
- `member_campaign_enrollments_enhanced` - Member-to-campaign junction with status (15 references)
  - Status values: PENDING, COMPLETED, FAILED, OPTOUT
- `member_enrollment_status_history` - Complete audit trail of status changes

**Outreach Tracking**:
- `outreach_batches` - Batch-level tracking (18 references)
  - Status progression: Pending → Submitted → Processing → Completed/Failed
- `outreach_attempts` - Individual call attempts per member (12 references)
  - Disposition values: Pending, Completed, Failed, NoAnswer, OptOut
- `bland_call_logs` - Complete Bland AI webhook audit trail (6 references)
  - Every webhook call logged for HIPAA compliance

**Partner Campaign Validation**:
- `partner_file_processing_log` - File-level tracking
- `partner_row_validation_results` - Row-level summary
- `partner_validation_error_details_file` - File-level errors
- `partner_validation_error_details_row` - Row-level field errors
- `care_gaps` - Reference table for care gap validation

**System**:
- `system_locks` - Distributed locking for timer trigger functions

### Key Database Patterns

#### 1. 3-Phase Batch Tracking
```python
# Phase 1: Create batch with 'Pending' status
INSERT INTO outreach_batches (batch_id, campaign_id, status)
VALUES (?, ?, 'Pending')

# Phase 2: Create attempt records with 'Pending' disposition
INSERT INTO outreach_attempts (attempt_id, enrollment_id, disposition)
VALUES (?, ?, 'Pending')

# Phase 3: Update batch with vendor_batch_id and 'Submitted' status
UPDATE outreach_batches
SET vendor_batch_id = ?, status = 'Submitted', submitted_at = SYSDATETIMEOFFSET()
WHERE batch_id = ?
```

#### 2. SQL Server Gotchas & Solutions

**Problem**: `ORDER BY items must appear in the select list if SELECT DISTINCT is specified`

**Solution**: Use `ROW_NUMBER() OVER (PARTITION BY)` instead:
```sql
-- ❌ WRONG
SELECT DISTINCT member_id
FROM ...
ORDER BY last_attempt_ts

-- ✅ CORRECT
WITH RankedMembers AS (
    SELECT
        member_id,
        ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY last_attempt_ts) as rn
    FROM ...
)
SELECT member_id FROM RankedMembers WHERE rn = 1
ORDER BY last_attempt_ts
```

**Problem**: pymssql doesn't auto-convert UUID objects

**Solution**: Always convert to string:
```python
# ❌ WRONG
params = [uuid.uuid4()]

# ✅ CORRECT
params = [str(uuid.uuid4())]
```

#### 3. Database Best Practices
- **Always use parameterized queries** - Never use string concatenation (SQL injection prevention)
- **Use `SYSDATETIMEOFFSET()`** - For timezone-aware timestamps
- **All transactions through DatabaseService** - Never create raw pymssql connections
- **Test queries first** - Use `execute_query()` before `execute_transaction()`
- **Add logging** - Include correlation IDs for traceability

---

## Important Dependencies

### Core Technologies
- **Runtime**: Azure Functions v4, Python 3.12
- **Database**: Azure SQL Server via pymssql (replaced pyodbc for better Linux support)
- **Storage**: Azure Blob Storage for file processing
- **Secrets**: Azure Key Vault for credentials
- **AI Integration**: Bland AI API for voice calls
- **Messaging**: Azure Service Bus for post-call analysis

### Key Python Packages (from requirements.txt)

| Package | Purpose | Critical Notes |
|---------|---------|----------------|
| `azure-functions` | Serverless runtime | ⚠️ Must NOT include `azure-functions-worker` (managed by platform) |
| `pandas` | DataFrame operations | CSV processing and data manipulation |
| `numpy` | Numerical operations | Used by pandas |
| `pymssql` | SQL Server driver | **Replaced pyodbc** for better Linux/Azure compatibility |
| `azure-identity` | Azure authentication | Managed identity support |
| `azure-keyvault-secrets` | Secret management | ConfigManager dependency for secure credentials |
| `azure-storage-blob` | Blob operations | File processing triggers |
| `azure-servicebus` | Messaging | Post-call analysis queue |
| `pandera` | DataFrame validation | CSV schema enforcement with type checking |
| `tenacity` | Retry logic | Transient error handling with exponential backoff |
| `pytz` | Timezone handling | US timezone support (ET, CT, MT, PT) |
| `requests` | HTTP client | Bland AI API synchronous calls |
| `aiohttp` | Async HTTP | Bland AI batch operations |

### Dependency Management
```bash
# Install dependencies
pip install -r requirements.txt

# Quality tools (not in requirements.txt, install separately)
pip install black ruff mypy pytest bandit
```

---

## Important Configuration Files

### 1. `host.json` - Azure Functions Runtime Configuration
```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```
- **Extension Bundle v4**: Provides bindings for blob, timer, and HTTP triggers
- **Application Insights**: Telemetry with sampling enabled
- **Request Exclusion**: Reduces telemetry volume by excluding HTTP request logs

### 2. Environment Variables (Required)

**In Azure Function App Configuration or `local.settings.json`**:
```json
{
  "IsEncrypted": false,
  "Values": {
    "KEY_VAULT_URL": "https://your-keyvault.vault.azure.net/",
    "DB_SECRET_NAME": "SqlConnectionStringIOE",
    "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;...",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://..."
  }
}
```

**Critical Environment Variables**:
| Variable | Purpose | Required | Notes |
|----------|---------|----------|-------|
| `KEY_VAULT_URL` | Azure Key Vault URL | ✅ Yes | All functions fail without this |
| `DB_SECRET_NAME` | Key Vault secret name | ✅ Yes | Default: `SqlConnectionStringIOE` |
| `AzureWebJobsStorage` | Blob storage connection | ✅ Yes | Required for blob triggers |
| `FUNCTIONS_WORKER_RUNTIME` | Runtime language | ✅ Yes | Must be `python` |
| `SERVICE_BUS_CONNECTION_STRING` | Service Bus | ⚠️ Optional | ⚠️ Should be in Key Vault, not config |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Telemetry | ⚠️ Optional | Monitoring and diagnostics |

### 3. Azure Key Vault Secrets (Retrieved via ConfigManager)

| Secret Name | Purpose | Used By |
|-------------|---------|---------|
| `SqlConnectionStringIOE` | SQL Server connection | All functions via DatabaseService |
| `BlandAIkey` | Bland AI API key | Schedulers, webhook |
| `Blandaitwilio` | Twilio encryption key | Partner campaign scheduler (`encrypted_key` header) |

**Access Pattern**:
```python
from af_code.bland_ai_webhook.services.config_manager import ConfigManager

config_manager = ConfigManager()
bland_ai_key = config_manager.get_config("BlandAIkey")
db_conn_string = config_manager.get_db_connection_string()
```

### 4. `mypy.ini` - Type Checking Configuration
```ini
[mypy]
python_version = 3.12
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False  # Lenient mode
```

### 5. `.gitignore` - Version Control Exclusions
**Correctly excludes**:
- ✅ `.claude/`, `CLAUDE.md` (Claude Code files)
- ✅ `local.settings.json` (secrets)
- ✅ `__pycache__/`, `*.pyc` (Python cache)
- ✅ `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/` (tool caches)
- ✅ `venv/`, `.venv/`, `env/` (virtual environments)
- ✅ `*.zip` (deployment packages)
- ✅ `.env`, `.env.local` (environment files)

---

## Critical Implementation Patterns

### 1. Database Connection Pattern (ALWAYS USE THIS)

**Never create raw pymssql connections. Always use DatabaseService.**

```python
from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService

# Initialize services
config_manager = ConfigManager()
db_service = DatabaseService(config_manager)

# Single query with parameters
query = "SELECT * FROM members WHERE member_id = ?"
params = [member_id]
results = db_service.execute_query(query, params, fetch_results=True)

# Transaction (atomic, auto-rollback on error)
queries = [
    ("INSERT INTO outreach_batches (batch_id, campaign_id) VALUES (?, ?)",
     (str(batch_id), str(campaign_id))),
    ("INSERT INTO outreach_attempts (attempt_id, enrollment_id) VALUES (?, ?)",
     (str(attempt_id), str(enrollment_id)))
]
db_service.execute_transaction(queries)
```

**Connection String Parsing**:
DatabaseService automatically parses Azure SQL connection strings to pymssql parameters:
- `Server=` → `server`
- `Database=` → `database`
- `User ID=` → `user`
- `Password=` → `password`

### 2. Timezone Handling

**Always use TimezoneConverter - never use raw pytz directly**

```python
from af_code.shared.timezone_utils import TimezoneConverter

# Convert any timezone format to pytz
campaign_tz = TimezoneConverter.to_pytz('EST')  # Returns America/New_York
campaign_tz = TimezoneConverter.to_pytz('Pacific')  # Returns America/Los_Angeles

# Get all US timezones for member_tz mode
us_timezones = TimezoneConverter.get_us_timezones_pytz()
# Returns: {
#   'Eastern': pytz.timezone('America/New_York'),
#   'Central': pytz.timezone('America/Chicago'),
#   'Mountain': pytz.timezone('America/Denver'),
#   'Pacific': pytz.timezone('America/Los_Angeles')
# }
```

**Timezone Modes** (via `campaigns_enhanced.timezone_flag`):
- **operating_tz**: Campaign runs in single timezone (e.g., all calls in EST)
- **member_tz**: Campaign respects individual member timezones (ET, CT, MT, PT)

**Always use timezone-aware datetime**:
```python
import pytz
from datetime import datetime

# ✅ CORRECT
now_utc = datetime.now(pytz.UTC)
campaign_time = datetime.now(campaign_tz)

# ❌ WRONG
now = datetime.now()  # Naive datetime
```

### 3. Bland AI Batch Submission

**Always use shared BlandAIClient - follows DTC pattern with 3 headers**

```python
from af_code.shared.bland_ai_client import BlandAIClient

client = BlandAIClient(config_manager)

# BatchRequest model requires:
batch_request = {
    "campaign_id": str(campaign_id),
    "calls": [
        {
            "phone_number": "+15551234567",
            "task": "Introduction call",
            "transfer_phone_number": "+15559876543"
        }
    ],
    "pathway_id": "pathway-123",
    "voice_id": "voice-456",
    "bland_parameters_global": {
        "max_duration": 12,
        "wait_for_greeting": True,
        "record": True,
        # ... 15+ additional optional parameters
    }
}

result = client.submit_batch_calls(batch_request)
# Returns: {"success": bool, "batch_id": str, "calls_submitted": int}
```

**3 Required Headers**:
1. `authorization` - Bland AI API key from Key Vault
2. `twilio_account_sid` - Twilio account identifier
3. `encrypted_key` - Twilio encryption key (partner campaigns only)

### 4. Disposition Mapping (Call Outcomes)

**StatusMapper translates Bland AI dispositions to internal statuses**

```python
from af_code.bland_ai_webhook.services.status_mapper import StatusMapper

status_mapper = StatusMapper()
internal_status = status_mapper.map_disposition(bland_ai_disposition)
```

**Mapping Rules**:

| Bland AI Disposition | Internal Status | Next Action | Description |
|---------------------|-----------------|-------------|-------------|
| `INTERESTED` | Completed | Follow_Up | Member expressed interest |
| `NOT_INTERESTED` | Completed | Close | Member declined |
| `CALL_BACK_SCHEDULED` | Completed | Scheduled | Callback scheduled |
| `FOLLOW_UP_REQUIRED` | Completed | Follow_Up | Needs additional follow-up |
| `OBJECTION_RAISED` | Completed | Follow_Up | Objection handling needed |
| `NEEDS_MORE_INFO` | Completed | Follow_Up | More information requested |
| `NOT_QUALIFIED` | Completed | Close | Member doesn't qualify |
| `TRANSFERRED` | Completed | Transferred | Call transferred to agent |
| `DO_NOT_CONTACT` | OptOut | Close | Member opted out (HIPAA critical) |
| `AGENT_ENDED_CALL` | NoAnswer | Retry | Agent ended call early |
| `CANCELED` | Failed | Retry | System canceled call |
| `FAILED` | Failed | Retry | Call failed technically |

### 5. Member Eligibility (Frequency Protection)

**One attempt per member per day** (simplified from previous 5-attempt logic)

```sql
-- Eligibility query excludes members with:
-- 1. Any disposition IN ('Completed', 'Pending') today
-- 2. Any 'Completed' attempt within frequency window

SELECT m.member_id
FROM members m
INNER JOIN member_campaign_enrollments_enhanced mce ON m.member_id = mce.member_id
WHERE mce.campaign_id = @campaign_id
  AND mce.status = 'PENDING'
  -- Exclude any attempt today
  AND NOT EXISTS (
      SELECT 1 FROM outreach_attempts oa
      WHERE oa.enrollment_id = mce.enrollment_id
        AND CAST(oa.created_at AS DATE) = CAST(SYSDATETIMEOFFSET() AS DATE)
  )
  -- Exclude completed attempts within frequency window
  AND NOT EXISTS (
      SELECT 1 FROM outreach_attempts oa
      WHERE oa.enrollment_id = mce.enrollment_id
        AND oa.disposition = 'Completed'
        AND oa.created_at >= DATEADD(week, -1, SYSDATETIMEOFFSET()) -- Example: 1 week frequency
  )
```

### 6. Idempotency in Webhook Processing

**Always check for duplicate webhooks - Bland AI may retry on timeout**

```python
from af_code.bland_ai_webhook.services.duplicate_detector import DuplicateDetector

detector = DuplicateDetector(db_service)

if detector.is_duplicate_call(call_id):
    logging.info(f"⚠️ Duplicate webhook detected for call_id: {call_id}")
    return func.HttpResponse("Duplicate call, already processed", status_code=200)

# Process webhook...
```

**Duplicate Detection Logic**:
- Checks `bland_call_logs` table for existing `call_id`
- Returns HTTP 200 for duplicates (prevents Bland AI retries)
- Maintains idempotency for HIPAA audit trail integrity

### 7. Phone Number Validation (E.164 Format)

**Requirement**: E.164 format with 11-15 digits (e.g., +15551234567)

```python
def validate_phone_number(phone: str) -> bool:
    """
    Validate phone number is E.164 format.
    Must start with '+' and have 11-15 total characters.
    """
    if not phone.startswith('+'):
        return False
    if len(phone) < 12 or len(phone) > 16:  # '+' + 11-15 digits
        return False
    return True

# Used in CSV file processing and batch submission
```

---

## Quality Gates & CI/CD

### GitHub Actions Workflow

**Located**: `.github/workflows/WORKFLOW_DOCUMENTATION.md`

**Deployment is AUTOMATICALLY BLOCKED if any check fails**:

```yaml
jobs:
  build:
    # Build Python package

  quality-checks:
    steps:
      - name: Code formatting
        run: black --check --line-length 100 af_code/

      - name: Linting
        run: ruff check af_code/

      - name: Type checking
        run: mypy af_code/

      - name: Security scan
        run: bandit -r af_code/

      - name: Unit tests
        run: pytest af_code/ --verbose

  deploy:
    needs: [build, quality-checks]  # ⚠️ Blocked if quality-checks fail
    steps:
      - name: Deploy to Azure Functions
        run: func azure functionapp publish IOE-function --python
```

### Manual Quality Checks (Before Commits)

**Run these locally before pushing**:
```bash
# Install quality tools
pip install black ruff mypy pytest bandit

# 1. Format code (PEP 8, line length 100)
black --line-length 100 af_code/

# 2. Lint code (check for errors)
ruff check af_code/

# 3. Type checking (static analysis)
mypy af_code/

# 4. Security scan (HIPAA compliance)
bandit -r af_code/

# 5. Run tests
pytest af_code/ --verbose
```

### Quality Gate Benefits
- 🛡️ **Zero defect deployments** - Only validated code reaches production
- 📊 **Quality metrics** - Comprehensive code quality visibility
- 🚀 **Automated enforcement** - No manual oversight needed
- 🔄 **Fast feedback** - Quality issues detected within minutes
- ✅ **HIPAA compliance** - Security vulnerabilities caught before deployment

---

## Compliance & Security (HIPAA-Compliant)

### HIPAA Requirements

**All PHI (Protected Health Information) must be**:
- ✅ **Encrypted at rest** - Azure SQL Database encryption, Blob Storage encryption
- ✅ **Encrypted in transit** - TLS 1.2+ for all communications
- ✅ **Complete audit trails** - `bland_call_logs`, `member_enrollment_status_history`
- ✅ **No PHI in logs** - Phone numbers and member names masked in debug output
- ✅ **Secure credential management** - Azure Key Vault only (never environment variables for secrets)

### Code Security Patterns

**Secrets Management**:
```python
# ❌ WRONG - Hardcoded secret
BLAND_AI_KEY = "sk-12345..."

# ✅ CORRECT - Use ConfigManager
config_manager = ConfigManager()
bland_ai_key = config_manager.get_config("BlandAIkey")
```

**SQL Injection Prevention**:
```python
# ❌ WRONG - String concatenation
query = f"SELECT * FROM members WHERE member_id = '{member_id}'"

# ✅ CORRECT - Parameterized query
query = "SELECT * FROM members WHERE member_id = ?"
params = [member_id]
results = db_service.execute_query(query, params, fetch_results=True)
```

**Input Validation**:
```python
from pydantic import BaseModel, Field

class WebhookData(BaseModel):
    call_id: str = Field(..., regex=r"^[a-zA-Z0-9\-]+$")
    member_id: str = Field(..., min_length=10, max_length=10)
    phone_number: str = Field(..., regex=r"^\+\d{11,15}$")
```

### Security Checklist

**Before Every Commit**:
- ✅ Run `bandit -r af_code/` (security scan)
- ✅ No hardcoded secrets (use ConfigManager)
- ✅ Validate all external inputs (webhook payloads, CSV files)
- ✅ Use prepared statements for SQL (parameterized queries)
- ✅ Phone numbers masked in logs: `phone[:3] + "***" + phone[-2:]`

**PHI Logging Rules**:
```python
# ❌ WRONG - PHI in logs
logging.info(f"Processing call for {member_name} at {phone_number}")

# ✅ CORRECT - No PHI in logs
logging.info(f"Processing call for member_id: {member_id}", extra={
    "correlation_id": correlation_id
})
```

---

## Architecture Highlights

### Serverless Microservices Pattern

Each of the 7 functions operates independently:

**Benefits**:
- **Independent scaling** - High webhook traffic doesn't affect file processing
- **Independent deployment** - Update one function without touching others
- **Fault isolation** - One function failure doesn't cascade to others
- **Cost optimization** - Pay only for actual execution time
- **Automatic retry** - Azure Functions handles transient failures

**Architecture Diagram**:
```
┌─────────────────────────────────────────────────────────┐
│          Azure Function App (IOE-function)              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
│  │ DTC File   │  │ Partner    │  │ DTC Intro  │      │
│  │ Processor  │  │ Processor  │  │ Scheduler  │      │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘      │
│         │                │                │            │
│  ┌──────┴─────┐  ┌──────┴─────┐  ┌──────┴─────┐      │
│  │ Wellness   │  │ Partner    │  │ Bland AI   │      │
│  │ Scheduler  │  │ Scheduler  │  │ Webhook    │      │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘      │
│         │                │                │            │
│  ┌──────┴──────────────────────────┬─────┘            │
│  │       Batch Reconciler          │                  │
│  └─────────────────────────────────┘                  │
│                                                         │
└────────────────┬────────────────────────────────────┬──┘
                 │                                    │
        ┌────────▼────────┐                  ┌────────▼────────┐
        │  Shared Services │                  │  Azure Services │
        │  - ConfigManager │                  │  - Key Vault    │
        │  - DatabaseSvc   │                  │  - SQL Database │
        │  - BlandAIClient │                  │  - Blob Storage │
        │  - TimezoneUtils │                  │  - Service Bus  │
        └─────────────────┘                  └─────────────────┘
```

### Service Layer Pattern

**Layered Architecture**:
```
┌─────────────────────────────────────────────────┐
│  Azure Function Trigger Layer                  │
│  (Blob, Timer, HTTP triggers)                   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│  Business Logic Layer (af_code/)                │
│  - Workflow orchestration                       │
│  - Business rules application                   │
│  - Data transformation                          │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│  Service Layer                                  │
│  - DatabaseService (data access)                │
│  - ConfigManager (secrets)                      │
│  - BlandAIClient (external API)                 │
│  - Validators, Mappers, Engines                 │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│  External Systems                               │
│  - Azure SQL Database (engage360 schema)        │
│  - Bland AI API (voice calls)                   │
│  - Azure Service Bus (messaging)                │
└─────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Single Responsibility** - Each service has one clear purpose
2. **Dependency Injection** - Services injected at function initialization
3. **Transaction Safety** - Database operations are atomic with auto-rollback
4. **Retry Logic** - Tenacity library for transient error handling
5. **Distributed Locking** - system_locks table prevents concurrent timer triggers
6. **Idempotency** - Webhook processing handles duplicates gracefully
7. **Audit Trail** - Complete logging for HIPAA compliance

---

## BusinessCaseID Traceability

Every module and function maps to specific business requirements for compliance tracking.

### Primary Business Cases

| **BusinessCaseID** | **Functional Area** | **Description** | **Components** |
|---|---|---|---|
| **BC-101** | Webhook Processing | Real-time Bland AI webhook handling, validation, and routing | `bland_ai_webhook/` module |
| **BC-102** | Disposition Mapping | Status translation and call outcome processing | `status_mapper.py`, disposition logic |
| **BC-103** | Database Operations | Atomic data operations, connection management, queries | `database_*.py` files |
| **BC-104** | Business Rules Engine | Enrollment logic, campaign-specific decision making | `business_rules_engine.py` |
| **BC-105** | Call Scheduling | Member qualification, time window management, batch creation | `af_dtc_intro_call/`, schedulers |
| **BC-106** | Bland AI Integration | API communication, batch processing, error handling | `blandai_service.py`, `bland_ai_client.py` |
| **BC-107** | Data Integrity | Duplicate detection, validation, data consistency | `duplicate_detector.py`, validators |
| **BC-108** | Configuration Management | Settings, secrets, environment-specific configs | `config_manager.py`, `config.py` |
| **BC-109** | File Processing | ETL pipelines, partner file validation, data transformation | File processors, `af_partner_logic.py` |
| **BC-110** | Time & Scheduling | Timezone handling, time windows, scheduling logic | `timezone_utils.py`, time helpers |

### Supporting Business Cases

| **BusinessCaseID** | **Area** | **Purpose** |
|---|---|---|
| **BC-201** | Error Handling | Structured exception management, logging, monitoring |
| **BC-202** | Data Models | Shared data structures, type definitions, validation |
| **BC-203** | Security & Auth | Key vault integration, secure configuration, PII handling |
| **BC-204** | Performance | Query optimization, caching, batch processing efficiency |
| **BC-205** | Testing & QA | Unit tests, integration tests, quality assurance |

### Implementation Example

```python
def map_webhook_to_internal_format(self, webhook_data: Dict[str, Any]) -> MappedCallData:
    """
    Transform Bland AI webhook data into standardized internal format.

    BusinessCaseID: BC-102

    Args:
        webhook_data: Complete webhook payload from Bland AI

    Returns:
        MappedCallData: Standardized call information ready for database storage

    Raises:
        ValidationError: If webhook data doesn't meet schema requirements
    """
    # Implementation...
```

---

## Development Workflow

### Local Development Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd IOE-functions

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install black ruff mypy pytest bandit  # Quality tools

# 4. Configure local settings (copy template)
cp local.settings.json.template local.settings.json
# Edit local.settings.json with your Azure credentials

# 5. Start Azure Functions locally
func start --python

# 6. Test specific endpoint
curl http://localhost:7071/api/bland-ai-webhook -X POST -d @test_webhook.json
```

### Testing Strategy

**Unit Tests**:
```bash
pytest af_code/ --verbose
pytest af_code/bland_ai_webhook/services/test_status_mapper.py -v
```

**Integration Tests**:
- **Webhook**: `WEBHOOK_TESTING_GUIDE.md`
- **File Processing**: `CSV_TESTING_GUIDE.md`

**Database Testing**:
```bash
# Test database connection
python -c "from af_code.bland_ai_webhook.services.config_manager import ConfigManager; \
           from af_code.bland_ai_webhook.services.database_service import DatabaseService; \
           cm = ConfigManager(); db = DatabaseService(cm); print('✅ DB Connected')"
```

### Deployment Process

```bash
# 1. Run quality checks
black --check --line-length 100 af_code/
ruff check af_code/
mypy af_code/
bandit -r af_code/
pytest af_code/ --verbose

# 2. Commit changes
git add .
git commit -m "feat: Add new disposition handling"

# 3. Push to main (triggers GitHub Actions)
git push origin main

# 4. GitHub Actions automatically:
#    - Runs quality checks
#    - Blocks deployment if checks fail
#    - Deploys to Azure if all checks pass

# 5. Verify deployment
curl https://ioe-function.azurewebsites.net/api/health
```

---

## Monitoring & Observability

### Application Insights Integration

**Structured Logging Pattern**:
```python
import logging
logger = logging.getLogger(__name__)

# Use emoji prefixes for visibility
logger.info(f"✅ [WEBHOOK] Successfully processed call_id: {call_id}")
logger.warning(f"⚠️ [SCHEDULER] Member excluded due to recent attempt")
logger.error(f"❌ [DATABASE] Query failed: {error}")
logger.critical(f"🚨 [CONFIG] Key Vault connection failed")

# Include correlation IDs
logger.info(f"Processing file: {filename}", extra={
    "correlation_id": correlation_id,
    "file_size": file_size,
    "processing_stage": "validation"
})
```

**Log Levels**:
- `INFO`: Normal operational events (file processed, call scheduled)
- `WARNING`: Recoverable errors (validation failures, member exclusions)
- `ERROR`: System errors requiring attention (database failures, API errors)
- `CRITICAL`: Service unavailability or data corruption

### Key Metrics to Monitor

**Function Performance**:
- Execution time per function
- Success rate (%)
- Error rate by category
- Cold start frequency

**Business Metrics**:
- Files processed per hour
- Call scheduling success rate
- Webhook processing latency
- Batch completion time

**Database Metrics**:
- Query execution time
- Connection pool usage
- Transaction failure rate

---

## Troubleshooting Guide

### Common Issues

**1. Database Connection Failures**
```
❌ [DB-SERVICE] CRITICAL: KEY_VAULT_URL environment variable is not set!
```
**Solution**: Set `KEY_VAULT_URL` in Azure Function App Configuration

**2. File Processing Skipped**
```
⚠️ File skipped due to invalid naming pattern: test_file.csv
```
**Solution**: Rename file to match pattern: `MedicalGuardian_DTCWellness_YYYYMMDD_Delta.csv`

**3. Webhook Duplicate Detected**
```
⚠️ Duplicate webhook detected for call_id: abc-123
```
**Solution**: This is expected behavior (idempotency). No action required.

**4. Member Not Qualified**
```
⚠️ Member excluded: already attempted today
```
**Solution**: Member can only receive one call per day. Wait until next day.

**5. Batch Status Not Updating**
```
❌ Failed to acquire lock: Another instance is running
```
**Solution**: Batch reconciler is already running. Wait for completion or check `system_locks` table.

---

## Support & Contact

**Development Team**: AI-POD Team - Data Science at Medical Guardian

**For Issues**:
- GitHub Issues for bugs/features
- Contact AI-POD Team for technical support
- Emergency: Medical Guardian IT Operations

**Response Times**:
- 🔴 **Critical Issues**: 2 hours
- 🟡 **High Priority**: 4 hours
- 🟢 **Standard Issues**: 24 hours
- 🔵 **Feature Requests**: 1 week

---

## Additional Resources

### Key Documentation Files
- `CLAUDE.md` - Claude Code development instructions (580 lines)
- `README.md` - Project overview and business context (812 lines)
- `ENGAGE360_TABLE_USAGE_REFERENCE.md` - Complete database schema (2,731 words)
- `PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md` - Partner workflows (7,108 words)
- `DTC_CALL_FLOW.md` - DTC intro call scheduling flow (1,686 words)
- `WEBHOOK_TESTING_GUIDE.md` - Bland AI webhook testing
- `CSV_TESTING_GUIDE.md` - File processing testing
- `BATCH_CREATION_AND_NAVIGATION_FLOW.md` - Batch creation and reconciliation
- `DTC_DATABASE_OPERATIONS_COMPLETE_FLOW.md` - Complete DTC database workflow
- `af_code/BLAND_AI_BATCH_CALL_ARCHITECTURE.md` - Bland AI batch architecture

### Useful Commands

```bash
# Check function registration
grep -r "@bp.function_name" functions/

# Count Python files
find . -name "*.py" | wc -l

# Find BusinessCaseID references
grep -r "BusinessCaseID:" af_code/

# View recent git commits
git log --oneline -10

# Check Azure Function App status
az functionapp show --name IOE-function --resource-group <rg>

# Tail logs in real-time
az functionapp logs tail --name IOE-function --resource-group <rg>
```

---

**Last Updated**: 2025-10-20
**Generated By**: Claude Code Primer
**Project**: IOE Services Platform
**Organization**: Medical Guardian - AI-POD Team

---

© 2024 Medical Guardian. All rights reserved.
**HIPAA Compliant** | **SOC 2 Type II** | **Azure Security Standards**
