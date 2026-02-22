# 🚀 IOE Services Platform

> **Intelligence Orchestration Engine** - Enterprise-grade IOE Services for automated healthcare campaign processing, device activation campaign processing, call management, and AI-powered customer interactions at Medical Guardian.

**Platform Architecture**: Each IOE Service runs as an individual Azure Function within the IOE Services platform, providing scalable and independent microservices for healthcare automation.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Code Quality](https://img.shields.io/badge/code%20quality-protected-green.svg)](https://github.com/Medical-Guardian/IOE-services/actions)
[![IOE Services](https://img.shields.io/badge/IOE-Services-0078d4.svg)](https://azure.microsoft.com/en-us/services/functions/)
[![Medical Guardian](https://img.shields.io/badge/Medical-Guardian-red.svg)](https://medicalguardian.com)

---

## 🏢 Development Team

**Created by**: AI-POD Team - Data Science Team  
**Team**: AI-POD at Medical Guardian  
**Contact**: For bugs, issues, or technical support, please contact the AI-POD Team at Medical Guardian

---

## 📖 Overview

The **IOE (Intelligence Orchestration Engine) Services Platform** is a comprehensive serverless solution designed to automate and optimize healthcare customer engagement workflows at Medical Guardian. This enterprise-grade platform consists of multiple intelligent services that process DTC (Direct-to-Consumer) wellness campaigns, partner campaign files, device activation campaigns, manage intro call scheduling, and integrate with Bland AI for intelligent voice interactions.

**What is IOE?**  
IOE stands for **Intelligence Orchestration Engine** - a smart system that coordinates and manages different healthcare processes automatically. Think of it as a digital conductor that orchestrates various healthcare services to work together seamlessly.

**How IOE Services Work**:  
Each IOE Service runs as an independent Azure Function within the IOE Services platform. This means:
- Each service can scale independently based on demand
- Services can be updated without affecting others
- Each service has its own trigger mechanism (file uploads, timers, webhooks)
- All services work together as part of the larger IOE ecosystem

### 🎯 Key Features

- **📁 Automated File Processing** - DTC wellness, partner campaign, and device activation file processing with validation
- **📞 Smart Call Scheduling** - Automated intro call and device activation call scheduling with timezone optimization
- **📱 Device Activation Management** - 90-day campaign windows with business hours validation and call frequency rules
- **🤖 AI Voice Integration** - Bland AI webhook processing for intelligent customer interactions
- **🛡️ Enterprise Security** - Azure Key Vault integration and comprehensive data validation
- **📊 Real-time Monitoring** - Complete observability with Azure Application Insights
- **🔄 Resilient Processing** - Retry mechanisms and robust error handling
- **📈 Campaign Analytics** - Advanced analytics for campaign performance tracking
- **🏷️ Business Traceability** - Comprehensive BusinessCaseID tracking for compliance
- **🛡️ Quality Gates** - Automated code quality validation with CI/CD pipeline protection

---

## 🏗️ Project Structure

```
📦 IOE-Services/
├── 📄 function_app.py                    # Main application entry point and IOE service registration
├── 📄 host.json                         # IOE Services host configuration
├── 📄 requirements.txt                  # Python dependencies and packages
├── 📄 local.settings.json               # Local development environment settings
│
├── 🎯 functions/                        # Azure Function triggers and entry points
│   ├── dtc_file_processor.py           # File Processing Service - monitors and processes DTC wellness files
│   ├── partner_file_processor.py       # Partner Integration Service - handles partner campaign files
│   ├── dtc_intro_call_scheduler.py     # Call Scheduling Service - manages intro call scheduling
│   ├── bland_ai_webhook.py             # AI Integration Service - processes Bland AI webhook data
│   ├── device_activation_scheduler.py                    # Device Activation Scheduler - schedules device activation calls
│   ├── operations_device_activation_file_processor.py    # Operations Device Activation File Processor - processes device activation enrollment files
│   └── device_activation_campaign_closure.py             # Device Activation Campaign Closure - auto-unenrolls members after 90 days
│
├── 🧠 af_code/                         # Core application logic and business rules
│   ├── af_dtc_logic.py                 # DTC campaign processing business logic
│   ├── af_partner_logic.py             # Partner campaign processing logic
│   ├── af_device_activation_logic.py                     # Device Activation campaign processing logic
│   │
│   ├── 📱 device_activation_scheduler/                   # Device Activation scheduling module
│   │   └── services/
│   │       ├── eligibility_service.py  # Member qualification and frequency rules
│   │       ├── batch_orchestrator.py   # Batch creation and Bland AI submission
│   │       ├── campaign_qualifier.py   # Campaign and member qualification logic
│   │       └── callback_scheduler.py   # Callback scheduling logic
│   │
│   ├── 🤖 bland_ai_webhook/            # Bland AI integration module (shared across all campaigns)
│   │   ├── webhook_handler.py          # Main webhook request processor
│   │   ├── models/                     # Data models and validation schemas
│   │   │   ├── mapped_call_data.py     # Call data mapping models
│   │   │   ├── enrollment_update.py    # Customer enrollment update models
│   │   │   ├── validation_result.py    # Validation result schemas
│   │   │   ├── update_result.py        # Database update result models
│   │   │   └── error_enums.py          # Error categorization enums
│   │   │
│   │   ├── services/                   # Business service layer
│   │   │   ├── config_manager.py       # Configuration and environment management
│   │   │   ├── database_service.py     # Database connectivity and operations
│   │   │   ├── database_orchestrator.py # Database transaction orchestration
│   │   │   ├── data_validator.py       # Input data validation service
│   │   │   ├── duplicate_detector.py   # Duplicate call detection logic
│   │   │   ├── status_mapper.py        # Call status mapping service
│   │   │   ├── business_rules_engine.py # Business rules validation
│   │   │   ├── error_handler.py        # Error processing and categorization
│   │   │   └── service_bus_handler.py  # Service Bus message processing
│   │   │
│   │   └── utils/                      # Shared utilities and helpers
│   │       ├── config.py               # Configuration constants and settings
│   │       └── logging_config.py       # Structured logging configuration
│   │
│   ├── 📞 af_dtc_intro_call/           # DTC intro call management
│   │   ├── services/                   # Call scheduling services
│   │   └── utils/                      # Call management utilities
│   │
│   └── 🔧 shared/                      # Shared utilities across all campaigns
│       ├── bland_ai_client.py          # Shared Bland AI API client
│       ├── business_hours_utils.py     # Business hours validation (Device Activation)
│       ├── custom_holidays.py          # US federal holidays (Device Activation)
│       ├── filename_validators.py      # Filename pattern validation (Device Activation)
│       ├── language_mapper.py          # Language code conversion utility
│       ├── phone_utils.py              # Phone number validation and standardization
│       └── timezone_utils.py           # Timezone conversion and validation
│
└── 📁 __pycache__/                     # Python bytecode cache
    └── [Compiled Python files]
```

---

## 🏷️ BusinessCaseID Traceability Framework

The IOE platform implements comprehensive business case traceability to ensure every service maps to specific business requirements and compliance standards. Each module and service includes BusinessCaseID tags for complete audit trails.

### Primary Business Cases

| **BusinessCaseID** | **Functional Area** | **Description** | **Components** |
|---|---|---|---|
| **BC-101** | Webhook Processing | Real-time Bland AI webhook handling, validation, and routing | `bland_ai_webhook/` module |
| **BC-102** | Webhook Processing (Shared) | Status translation and call outcome processing (DTC, Partner, Device Activation) | `status_mapper.py`, disposition logic |
| **BC-103** | Database Operations | Atomic data operations, connection management, queries | `database_*.py` files |
| **BC-104** | Business Rules Engine | Enrollment logic, campaign-specific decision making | `business_rules_engine.py` |
| **BC-105** | DTC Call Scheduling | Member qualification, time window management, batch creation | `af_dtc_intro_call/` module |
| **BC-106** | Bland AI Integration | API communication, batch processing, error handling | `blandai_service.py` |
| **BC-107** | Data Integrity | Duplicate detection, validation, data consistency | `duplicate_detector.py` |
| **BC-108** | Configuration Management | Settings, secrets, environment-specific configs | `config_manager.py`, `config.py` |
| **BC-109** | File Processing | ETL pipelines, partner file validation, data transformation | `dtc_file_processor.py`, partner logic |
| **BC-110** | Time & Scheduling | Timezone handling, time windows, scheduling logic | `time_window_helper.py` |
| **BC-DA-001** | Device Activation Orchestration | Core scheduling and batch creation for device activation calls | `device_activation_scheduler/` module |
| **BC-DA-002** | Device Activation File Processing | CSV file processing, validation, ETL pipeline for device activation | `operations_device_activation_file_processor.py` |
| **BC-DA-003** | Business Hours Validation | Dual-timezone business hours and holiday calculations | `business_hours_utils.py`, `custom_holidays.py` |
| **BC-DA-004** | Batch Orchestration | Batch creation, Bland AI submission, 3-phase tracking | `batch_orchestrator.py` |
| **BC-DA-005** | Eligibility & Frequency Logic | Member qualification, frequency rules, same-day blocking | `eligibility_service.py` |
| **BC-DA-006** | Call Frequency & Sequencing | Call 1-4 business day logic, Call 5+ weekly scheduling | `eligibility_service.py` |
| **BC-DA-007** | Campaign Closure | 90-day auto-unenrollment, distributed locking | `device_activation_campaign_closure.py` |
| **BC-DA-008** | Operations File Processor | Hardcoded campaign ID routing, operations container | `operations_device_activation_file_processor.py` |

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
    """
```

---

## 🔧 IOE Services Overview

The IOE platform consists of seven main intelligent services. Each service runs as an independent Azure Function within the IOE Services platform, with different triggers and purposes:

### 1. 📁 **File Processing Service** (`dtc_file_processor.py`)
**What it does**: Automatically processes customer wellness data files
**How it works**: Watches for new CSV files containing customer information
**Azure Function Trigger**: Blob Storage Trigger
**Example**: When a file named `medical_guardian_dtc_wellness_20260202.csv` is uploaded:
- ✅ Validates the file format and naming convention
- ✅ Checks customer data quality and phone number formats (E.164 with 11-15 digits)
- ✅ Updates the database with new customer information
- ✅ Sends notifications if there are any errors

### 2. 🤝 **Partner Integration Service** (`partner_file_processor.py`)
**What it does**: Handles campaign files from business partners  
**How it works**: Processes files from external partners and converts them to our format  
**Azure Function Trigger**: Blob Storage Trigger  
**Example**: When a partner uploads their customer list:
- ✅ Verifies the partner's permissions and credentials
- ✅ Converts their data format to IOE standards
- ✅ Creates new marketing campaigns in the system
- ✅ Notifies campaign managers of new partner data

### 3. ⏰ **Call Scheduling Service** (`dtc_intro_call_scheduler.py`)
**What it does**: Automatically schedules introduction calls with customers  
**How it works**: Runs on a schedule to find customers ready for calls  
**Azure Function Trigger**: Timer Trigger (every 30 minutes) + HTTP Trigger (manual)  
**Example**: Every 30 minutes during business hours:
- ✅ Finds customers who need intro calls (one attempt per day)
- ✅ Checks their time zones and call preferences
- ✅ Matches them with available wellness agents
- ✅ Schedules the calls and sends reminders

### 4. 🤖 **AI Integration Service** (`bland_ai_webhook.py`)
**What it does**: Processes real-time data from AI voice calls
**How it works**: Receives instant updates when AI calls complete
**Azure Function Trigger**: HTTP Webhook Trigger (real-time)
**Example**: When an AI voice call finishes:
- ✅ Receives the call results instantly via webhook
- ✅ Updates customer status based on call outcome
- ✅ Triggers follow-up actions (like scheduling callbacks)
- ✅ Records conversation summaries and disposition codes

### 5. 📱 **Device Activation Services**

The Device Activation campaign system consists of three specialized Azure Functions that work together to manage the 90-day device activation campaign lifecycle:

#### 5a. Device Activation Scheduler (`device_activation_scheduler.py`)
**What it does**: Automatically schedules device activation calls for new members
**How it works**: Runs every 15 minutes to find eligible members
**Azure Function Trigger**: Timer Trigger (every 15 minutes) + HTTP Trigger (manual)
**Example**: Every 15 minutes:
- ✅ Finds members eligible for device activation calls
- ✅ Checks business hours (9 AM - 5 PM EST + member timezone)
- ✅ Creates batches of up to 20 members
- ✅ Submits to Bland AI for automated calls
- ✅ Tracks call frequency (Calls 1-4: business days, Call 5+: weekly)

#### 5b. Operations Device Activation File Processor (`operations_device_activation_file_processor.py`)
**What it does**: Processes device activation enrollment files from operations
**How it works**: Watches for CSV files with device and member information
**Azure Function Trigger**: Blob Storage Trigger
**Example**: When file uploaded to fs-ops/landing:
- ✅ Validates filename pattern (MedicalGuardian_DeviceActivation{Medicaid|DTCMA}_YYYYMMDD_DELTA.csv)
- ✅ Processes 27 required columns (member, device, campaign data)
- ✅ Creates/updates member and device records
- ✅ Enrolls members in Device Activation campaigns
- ✅ Routes to hardcoded campaign IDs (Medicaid, DTC/MA)

#### 5c. Device Activation Campaign Closure (`device_activation_campaign_closure.py`)
**What it does**: Automatically closes 90-day device activation campaigns
**How it works**: Runs hourly to unenroll members past 90-day window
**Azure Function Trigger**: Timer Trigger (hourly) + HTTP Trigger (manual)
**Example**: Every hour:
- ✅ Finds enrollments where campaign_end_date expired
- ✅ Updates status to 'UNENROLLED'
- ✅ Logs status change to history table
- ✅ Uses distributed locking to prevent concurrent runs

---

## 🎯 Detailed Business Use Cases & Workflows

### 1. 📋 DTC Wellness Campaign Processing

**Business Context**: Process daily wellness campaign files containing customer eligibility data for Medical Guardian's direct-to-consumer wellness programs.

**Workflow**:
1. **File Detection**: Monitor `fs-dtc/landing/` blob container for new files
2. **Validation**: Enforce naming convention `medical_guardian_dtc_wellness_YYYYMMDD.csv`
3. **Data Processing**: Parse CSV files with customer wellness data
4. **Database Updates**: Insert/update customer eligibility records
5. **Reporting**: Generate processing reports and error logs

**Triggers**:
- **Type**: Blob Storage Trigger
- **Container**: `fs-dtc/landing/`
- **Pattern**: `medical_guardian_dtc_wellness_YYYYMMDD.csv`
- **Connection**: `AzureWebJobsStorage`

**Validations**:
- File naming convention compliance
- CSV structure validation using Pandera schemas
- Customer data integrity checks
- Duplicate record prevention

### 2. 🤝 Partner Campaign File Processing

**Business Context**: Process partner-generated campaign files for co-marketing initiatives and referral programs.

**Workflow**:
1. **File Ingestion**: Automatic detection of partner campaign files
2. **Partner Validation**: Verify partner credentials and permissions
3. **Data Transformation**: Convert partner formats to internal schemas
4. **Campaign Setup**: Initialize campaign tracking and metrics
5. **Notification**: Alert campaign managers of new partner campaigns

**Triggers**:
- **Type**: Blob Storage Trigger
- **Container**: Partner-specific containers
- **Pattern**: Configurable based on partner requirements

**Validations**:
- Partner authentication and authorization
- Campaign data completeness checks
- Budget and compliance validations
- Conflict detection with existing campaigns

### 3. 📞 DTC Intro Call Scheduling Engine

**Business Context**: Automatically schedule and manage introduction calls for new DTC wellness program participants.

**Workflow**:
1. **Customer Eligibility**: Identify customers ready for intro calls
2. **Timezone Optimization**: Calculate optimal call times based on customer location
3. **Agent Availability**: Match customers with available wellness agents
4. **Call Scheduling**: Create calendar appointments and notifications
5. **Reminder System**: Send automated reminders to customers and agents

**Triggers**:
- **Type**: Timer Trigger (scheduled execution)
- **Schedule**: Configurable CRON expressions
- **Manual**: HTTP trigger for on-demand scheduling

**Validations**:
- Customer consent verification
- Business hours compliance
- Agent capacity management
- Timezone accuracy validation

**Enhanced Qualification Logic (BC-105)**:
The call scheduling engine has been updated with simplified member qualification:

**Previous Logic**: Members could receive up to 5 failed call attempts per day
**New Logic**: **One call attempt per member per day** regardless of outcome

**Qualification Criteria (DTC Campaigns)**:
- ✅ Campaign status = 'Active'
- ✅ Member enrollment status = 'PENDING'
- ✅ Valid timezone and preferred window
- ✅ Current time within member's preferred window
- ✅ Today is a valid call day for the member
- ❌ **NO attempt made today** (any previous attempt blocks qualification)

**Partner Campaign Same-Day Retry Policy**:
Partner campaigns enforce the same "one attempt per day" policy:
- ❌ **Blocks ALL dispositions** from same-day retry: Completed, Pending, Failed, NoAnswer
- ✅ Members can be retried **next day** (or after frequency window for Completed)
- This reduces member call fatigue and improves experience

**Benefits**:
- **Improved member experience** - No repeated calls on same day
- **Simplified logic** - Easier to understand and maintain
- **Resource optimization** - Better distribution across member base

### 4. 📱 Device Activation Campaign Processing

**Business Context**: Automatically schedule and manage device activation calls for Medical Guardian members who received new medical alert devices. The system makes scheduled calls over a 90-day window to help members activate their devices and ensure they understand device features.

**Workflow**:
1. **File Ingestion**: Monitor `fs-ops/landing/` for device activation CSV files
2. **Validation**: Enforce strict naming patterns for Medicaid and DTC/MA campaigns
3. **Enrollment Creation**: Create member enrollments with 90-day campaign window
4. **Scheduler Execution**: Every 15 minutes, find eligible members
5. **Batch Creation**: Create batches of up to 20 members per run
6. **Call Submission**: Submit batches to Bland AI for automated calls
7. **Webhook Processing**: Update member status based on call outcomes
8. **Campaign Closure**: Hourly check for expired 90-day windows

**Triggers**:
- **File Processor**: Blob Storage Trigger
  - **Container**: `fs-ops/landing/`
  - **Pattern**: `MedicalGuardian_DeviceActivation{Medicaid|DTCMA}_YYYYMMDD_DELTA.csv`
  - **Connection**: `AzureWebJobsStorage`
- **Scheduler**: Timer Trigger (every 15 minutes) + HTTP (manual)
  - **Schedule**: `0 */15 * * * *` (every 15 minutes)
  - **HTTP**: `/api/create_device_activation_batch`
- **Campaign Closure**: Timer Trigger (hourly) + HTTP (manual)
  - **Schedule**: `0 0 * * * *` (every hour)
  - **HTTP**: `/api/device_activation_campaign_closure`

**Validations**:
- Filename pattern matching (Medicaid vs DTC/MA)
- 27 required CSV columns
- Phone number format (E.164, 11 digits)
- Timezone validation (IANA format, supports 13 US timezones)
- Address validation (5-part address)
- Device UDI validation (5-50 alphanumeric characters)
- Campaign ID routing (hardcoded UUIDs)

**Call Frequency Rules**:
- **Call 1**: activation_start_date (delivery_date + 2 business days)
- **Call 2-3**: 2 business days after previous call
- **Call 4**: 5 business days after Call 3
- **Call 5+**: 7 calendar days (weekly), business days only
- **Same-Day Blocking**: One attempt per member per day
- **90-Day Window**: From activation_start_date to campaign_end_date

**Business Hours Validation**:
- **Medical Guardian Hours**: 9 AM - 5 PM EST
- **Member Hours**: 9 AM - 5 PM in member's timezone
- **Dual Validation**: Both MG and member must be within hours
- **Excludes**: Weekends, US federal holidays (6 business-critical holidays)

**Campaign Closure Logic**:
- **Trigger**: campaign_end_date < current time
- **Action**: Update enrollment status to 'UNENROLLED'
- **Frequency**: Hourly check via timer trigger
- **Distributed Locking**: Prevents concurrent execution
- **History Tracking**: Logs all status changes

**Hardcoded Campaign IDs**:
1. **Device Activation - Medicaid**
   - Campaign ID: `0F69659B-491B-40E2-88C3-ABC7D87385B2`
   - Filename: `MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv`
2. **Device Activation - DTC/MA**
   - Campaign ID: `BA865458-60F9-4EBB-9FB5-D195B532CF5A`
   - Filename: `MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv`

### 5. 🤖 Bland AI Voice Integration

**Business Context**: Process real-time webhook data from Bland AI voice interactions to update customer records and trigger follow-up actions.

**Workflow**:
1. **Webhook Reception**: Receive real-time call data from Bland AI
2. **Data Mapping**: Transform Bland AI data to internal customer models
3. **Duplicate Detection**: Prevent duplicate call processing
4. **Status Updates**: Update customer enrollment and interaction status
5. **Business Rules**: Apply complex business logic for next-best-actions
6. **Service Bus**: Queue follow-up actions for downstream processing

**Triggers**:
- **Type**: HTTP Trigger (webhook endpoint)
- **Method**: POST
- **Authentication**: API key validation
- **Content-Type**: application/json

**Validations**:
- Webhook signature verification
- Request payload schema validation
- Customer ID verification
- Call status consistency checks
- Business rules compliance

**Enhanced Disposition Mapping (BC-102)**:
The platform now supports comprehensive disposition tag mapping for granular call outcome tracking:

**Engagement Dispositions**:
- `INTERESTED` → Completed + Follow_Up
- `NOT_INTERESTED` → Completed + Close
- `FOLLOW_UP_REQUIRED` → Completed + Follow_Up
- `CALL_BACK_SCHEDULED` → Completed + Scheduled
- `OBJECTION_RAISED` → Completed + Follow_Up
- `NEEDS_MORE_INFO` → Completed + Follow_Up

**Administrative Dispositions**:
- `NOT_QUALIFIED` → Completed + Close
- `TRANSFERRED` → Completed + Transferred
- `DO_NOT_CONTACT` → OptOut + Close
- `AGENT_ENDED_CALL` → NoAnswer + Retry

**System Dispositions**:
- `CANCELED` → Failed + Retry
- `FAILED` → Failed + Retry

---

## 🛡️ Validation Framework

### Data Validation Pipeline

1. **Schema Validation**
   - Pydantic models for type safety
   - Pandera DataFrames for CSV validation
   - JSON schema validation for API requests

2. **Business Rule Validation**
   - Customer eligibility checks
   - Campaign budget validations
   - Agent availability verification
   - Timezone and scheduling constraints

3. **Security Validation**
   - Input sanitization
   - SQL injection prevention
   - Authentication token verification
   - Rate limiting and throttling

4. **Data Integrity Checks**
   - Duplicate detection algorithms
   - Referential integrity validation
   - Data consistency verification
   - Audit trail maintenance

---

## 🔧 Triggers & Event Processing

### Blob Storage Triggers

```python
@bp.blob_trigger(
    arg_name="myblob",
    path="fs-dtc/landing/{name}",
    connection="AzureWebJobsStorage"
)
```

**Configuration**:
- **Polling Interval**: 10 seconds
- **Batch Size**: 1 (sequential processing)
- **Retry Policy**: Exponential backoff (3 attempts)

### Timer Triggers

```python
@bp.timer_trigger(
    schedule="0 */30 * * * *",  # Every 30 minutes
    arg_name="timer"
)
```

**Scheduling Options**:
- **Intro Calls**: Every 30 minutes during business hours
- **Campaign Processing**: Daily at 2 AM EST
- **Health Checks**: Every 5 minutes

### HTTP Triggers

```python
@bp.route(
    route="webhook/bland-ai",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION
)
```

**Security Features**:
- Function-level authentication
- API key validation
- Request size limits (10MB)
- Rate limiting (100 req/min)

---

## 📊 File Descriptions

### Core Application Files

| File | Purpose | Functionality |
|------|---------|---------------|
| `function_app.py` | **Application Bootstrap** | Registers all IOE service blueprints and initializes the Azure Functions app |
| `host.json` | **Runtime Configuration** | Timeout settings, logging levels, and performance tuning |
| `requirements.txt` | **Dependency Management** | Python packages for Azure, database, AI, and validation |
| `local.settings.json` | **Development Config** | Local environment variables and connection strings |

### IOE Services Summary

| IOE Service | Azure Function Trigger | Business Purpose |
|-------------|------------------------|------------------|
| `dtc_file_processor.py` | **Blob Storage Trigger** | Processes DTC wellness campaign files for customer eligibility |
| `partner_file_processor.py` | **Blob Storage Trigger** | Handles partner campaign file ingestion and validation |
| `dtc_intro_call_scheduler.py` | **Timer + HTTP Trigger** | Schedules intro calls for new wellness program participants |
| `bland_ai_webhook.py` | **HTTP Webhook Trigger** | Processes real-time AI voice interaction data (shared across campaigns) |
| `device_activation_scheduler.py` | **Timer + HTTP Trigger** | Schedules device activation calls, creates batches every 15 minutes |
| `operations_device_activation_file_processor.py` | **Blob Storage Trigger** | Processes device activation enrollment files from operations |
| `device_activation_campaign_closure.py` | **Timer + HTTP Trigger** | Auto-unenrolls members after 90-day campaign window expires |

### Business Logic Layer

| Component | Domain | Responsibility |
|-----------|--------|----------------|
| `af_dtc_logic.py` | **DTC Campaigns** | Core business logic for wellness campaign processing |
| `af_partner_logic.py` | **Partner Integration** | Partner campaign validation and processing logic |
| `webhook_handler.py` | **AI Integration** | Bland AI webhook data processing orchestration |

### Service Layer

| Service | Function | Integration |
|---------|----------|-------------|
| `database_service.py` | **Data Persistence** | SQL Server connectivity with connection pooling |
| `config_manager.py` | **Configuration** | Azure Key Vault integration and environment management |
| `data_validator.py` | **Validation** | Input validation using Pydantic and business rules |
| `duplicate_detector.py` | **Data Quality** | Advanced duplicate detection algorithms |
| `business_rules_engine.py` | **Business Logic** | Complex business rule evaluation and enforcement |
| `error_handler.py` | **Error Management** | Categorized error handling and recovery strategies |

---

## 🚀 Quick Start Guide

### Prerequisites

- **Python 3.12+**
- **Azure Functions Core Tools v4**
- **Azure CLI**
- **Azure Subscription** with appropriate permissions
- **SQL Server Database** access
- **Azure Storage Account**

### 🔧 Local Development Setup

1. **Clone Repository**
   ```bash
   git clone https://github.com/Medical-Guardian/IOE-services.git
   cd IOE-services
   ```

2. **Setup Python Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Local Settings**
   ```json
   {
     "IsEncrypted": false,
     "Values": {
       "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;...",
       "FUNCTIONS_WORKER_RUNTIME": "python",
       "SQL_CONNECTION_STRING": "Server=your-server;Database=IOE;...",
       "KEYVAULT_URL": "https://your-keyvault.vault.azure.net/",
       "BLAND_AI_API_KEY": "your-bland-ai-key"
     }
   }
   ```

4. **Start Local Development**
   ```bash
   func start --python
   ```

---

## ⚙️ Configuration Management

### Environment Variables

| Variable | Purpose | Example | Required |
|----------|---------|---------|----------|
| `SQL_CONNECTION_STRING` | Database connectivity | `Server=...;Database=IOE;...` | ✅ |
| `AzureWebJobsStorage` | Blob storage connection | `DefaultEndpointsProtocol=https;...` | ✅ |
| `KEYVAULT_URL` | Azure Key Vault URL | `https://ioe-kv.vault.azure.net/` | ✅ |
| `BLAND_AI_API_KEY` | Bland AI authentication | `sk-...` | ✅ |
| `SERVICE_BUS_CONNECTION` | Service Bus messaging | `Endpoint=sb://...` | ⚠️ |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Telemetry | `InstrumentationKey=...` | ⚠️ |

### Azure Resource Requirements

- **Azure Function App** (Python 3.12, Consumption or Premium plan) - hosts all IOE Services
- **Azure Storage Account** (Standard performance, blob storage)
- **Azure SQL Database** (Standard tier minimum)
- **Azure Key Vault** (Standard tier)
- **Azure Service Bus** (Standard tier for webhooks)
- **Application Insights** (for monitoring and diagnostics)

---

## 🛠️ Technology Stack

| Layer | Technologies | Purpose |
|-------|-------------|---------|
| **Runtime** | Azure Functions, Python 3.12 | Serverless IOE Services platform |
| **Data Processing** | Pandas, NumPy, Pandera | File processing and validation |
| **Database** | Azure SQL, PyMSSQL | Data persistence and querying |
| **Security** | Azure Key Vault, Azure Identity | Secure credential management |
| **Storage** | Azure Blob Storage | File storage and processing |
| **AI Integration** | Bland AI API, Requests | Voice AI webhook processing |
| **Validation** | Pydantic, JSON Schema | Data validation and type safety |
| **Reliability** | Tenacity | Retry logic and resilience |
| **Monitoring** | Application Insights | Observability and diagnostics |

---

## 📈 Monitoring & Observability

### Health Monitoring

The platform includes comprehensive health monitoring capabilities:

- **Database Connectivity** - Real-time database health checks
- **Storage Account Status** - Blob storage accessibility validation
- **External API Health** - Bland AI service availability
- **IOE Service Performance** - Execution time and success rate tracking

### Logging Strategy

**Structured Logging** with correlation IDs:
```python
logging.info(f"🟢 Processing file: {filename}", extra={
    "correlation_id": correlation_id,
    "file_size": file_size,
    "processing_stage": "validation"
})
```

**Log Levels**:
- `INFO`: Normal operational events
- `WARNING`: Recoverable errors and validation failures
- `ERROR`: System errors requiring attention
- `CRITICAL`: Service unavailability or data corruption

### Performance Metrics

- **File Processing Rate** - Files processed per hour
- **Call Scheduling Success** - Percentage of successful call schedules
- **Webhook Response Time** - Bland AI webhook processing latency
- **Database Query Performance** - Average query execution time
- **Error Rate Tracking** - Error percentage by IOE service and category

---

## 🔐 Security & Compliance

### Data Protection

- **Encryption at Rest** - All data encrypted in Azure SQL and Blob Storage
- **Encryption in Transit** - TLS 1.2+ for all communications
- **Key Management** - Azure Key Vault for credential storage
- **Access Control** - Azure AD integration with RBAC

### Healthcare Compliance

- **HIPAA Compliance** - PHI handling and audit trails
- **Data Retention** - Automated data lifecycle management
- **Access Logging** - Complete audit trail for all data access
- **Data Minimization** - Process only necessary customer data

### Input Validation & Security

```python
# Example validation pipeline
@validator('customer_id')
def validate_customer_id(cls, v):
    if not isinstance(v, str) or len(v) != 10:
        raise ValueError('Invalid customer ID format')
    return v
```

---

## 🚀 Deployment & CI/CD

### Automated Deployment with Quality Gates

Enhanced GitHub Actions workflow with comprehensive quality validation for IOE Services:

```yaml
name: Build and deploy Python project to Azure Function App - IOE Services

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Create deployment package
        run: zip release.zip ./* -r

  quality-checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install quality tools
        run: |
          pip install black ruff mypy pytest pytest-cov bandit
          pip install -r requirements.txt
      - name: Run quality validation
        run: |
          black --check --line-length 100 .    # Code formatting
          ruff check af_code/                  # Linting
          mypy af_code/                        # Type checking
          bandit -r af_code/                   # Security scan
          pytest af_code/ --verbose            # Unit tests

  deploy:
    runs-on: ubuntu-latest
    needs: [build, quality-checks]  # Deployment blocked if quality fails
    steps:
      - name: Deploy to Azure Functions
        uses: Azure/functions-action@v1
        with:
          app-name: 'IOE-function'
          package: './release.zip'
```

### Quality Gate Protection

**Deployment Protection**: IOE Services deployment is **automatically blocked** if:
- ❌ Code formatting doesn't meet PEP 8 standards (black)
- ❌ Linting issues detected (ruff)
- ❌ Type safety violations found (mypy)
- ❌ Security vulnerabilities identified (bandit)
- ❌ Unit tests fail or coverage below threshold (pytest)

**Benefits**:
- 🛡️ **Zero defect deployments** - Only validated code reaches production
- 📊 **Quality metrics** - Comprehensive code quality visibility
- 🚀 **Automated enforcement** - No manual quality gate oversight needed
- 🔄 **Fast feedback** - Quality issues detected within minutes of push

### Manual Deployment

```bash
# Login to Azure
az login

# Deploy IOE services
func azure functionapp publish IOE-services-app --python

# Verify deployment
curl https://ioe-services-app.azurewebsites.net/api/health
```

### Environment Promotion

1. **Development** → `dev-ioe-services-app`
2. **Staging** → `staging-ioe-services-app`  
3. **Production** → `ioe-services-app`

---

## 🎯 Sample Configurations

### DTC File Processing Configuration

```python
# File naming validation
VALID_DTC_PATTERN = r"medical_guardian_dtc_wellness_\d{8}\.csv"

# CSV schema validation
DTC_SCHEMA = pa.DataFrameSchema({
    "customer_id": pa.Column(pa.String, checks=pa.Check.str_length(10, 10)),
    "enrollment_date": pa.Column(pa.DateTime),
    "wellness_tier": pa.Column(pa.String, checks=pa.Check.isin(["Basic", "Premium", "Elite"])),
    "contact_preference": pa.Column(pa.String, checks=pa.Check.isin(["Phone", "Email", "SMS"]))
})
```

### Bland AI Webhook Validation

```python
# Webhook payload validation
class BlandAIWebhookData(BaseModel):
    call_id: str = Field(..., regex=r"^[a-zA-Z0-9\-]+$")
    customer_id: str = Field(..., min_length=10, max_length=10)
    call_status: CallStatus
    call_duration: Optional[int] = Field(None, ge=0, le=3600)
    call_timestamp: datetime
    conversation_summary: Optional[str] = Field(None, max_length=1000)
```

### Timer Trigger Configuration

```python
# Business hours call scheduling
BUSINESS_HOURS = {
    "start_time": "09:00",
    "end_time": "17:00",
    "timezone": "America/New_York",
    "excluded_days": ["Saturday", "Sunday"]
}

# Scheduling cron expressions
SCHEDULES = {
    "intro_calls": "0 */30 9-17 * * 1-5",  # Every 30 min, business hours
    "campaign_processing": "0 0 2 * * *",   # Daily at 2 AM
    "health_checks": "0 */5 * * * *"        # Every 5 minutes
}
```

---

## 🐛 Support & Troubleshooting

### Common Issues

1. **File Processing Failures**
   - Check file naming convention compliance
   - Validate CSV schema against expected format
   - Verify blob storage connectivity

2. **Database Connection Issues**
   - Validate SQL connection string in Key Vault
   - Check network connectivity and firewall rules
   - Verify database user permissions

3. **Webhook Processing Errors**
   - Validate Bland AI API key configuration
   - Check webhook payload format
   - Verify business rules engine configuration

### Support Channels

**Technical Support**:
📧 **Primary Contact**: AI-POD Team at Medical Guardian  
🏢 **Team**: AI-POD Data Science Team at Medical Guardian  
📋 **Issues**: [GitHub Issues](https://github.com/Medical-Guardian/IOE-services/issues)  
📞 **Emergency**: Contact Medical Guardian IT Operations

**Response Times**:
- 🔴 **Critical Issues**: 2 hours
- 🟡 **High Priority**: 4 hours  
- 🟢 **Standard Issues**: 24 hours
- 🔵 **Feature Requests**: 1 week

---

## 📄 License & Compliance

This project is proprietary software owned by Medical Guardian.  
© 2024 Medical Guardian. All rights reserved.

**Compliance Standards**:
- HIPAA (Health Insurance Portability and Accountability Act)
- SOC 2 Type II (Service Organization Control)
- Azure Security Standards
- Medical Device Data Systems (MDDS) Guidelines

---

<div align="center">

**🏥 Developed with ❤️ by AI-POD Team at Medical Guardian**

*Enhancing healthcare through intelligent automation and data-driven insights*

---

[![Medical Guardian](https://img.shields.io/badge/Powered%20by-Medical%20Guardian-red.svg)](https://medicalguardian.com)
[![Azure](https://img.shields.io/badge/Deployed%20on-Azure-blue.svg)](https://azure.microsoft.com)
[![Python](https://img.shields.io/badge/Built%20with-Python-green.svg)](https://python.org)

</div>