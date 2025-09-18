# 🚀 IOE Azure Functions Platform

> **Intelligent Operations Engine** - Enterprise-grade Azure Functions for automated healthcare campaign processing, call management, and AI-powered customer interactions at Medical Guardian.

[![Deploy Status](https://github.com/zubairashfaque/IOE-function/workflows/Deploy%20Python%20Azure%20Function/badge.svg)](https://github.com/zubairashfaque/IOE-function/actions)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Azure Functions](https://img.shields.io/badge/Azure-Functions-0078d4.svg)](https://azure.microsoft.com/en-us/services/functions/)
[![Medical Guardian](https://img.shields.io/badge/Medical-Guardian-red.svg)](https://medicalguardian.com)

---

## 🏢 Development Team

**Created by**: Zubair Ashfaque - Tech Lead, Data Science Team  
**Team**: AI-POD at Medical Guardian  
**Contact**: For bugs, issues, or technical support, please email: [zubair.ashfaque@medicalguardian.com](mailto:zubair.ashfaque@medicalguardian.com)

---

## 📖 Overview

The **IOE (Intelligent Operations Engine) Azure Functions Platform** is a comprehensive serverless solution designed to automate and optimize healthcare customer engagement workflows at Medical Guardian. This enterprise-grade platform processes DTC (Direct-to-Consumer) wellness campaigns, partner campaign files, manages intro call scheduling, and integrates with Bland AI for intelligent voice interactions.

### 🎯 Key Features

- **📁 Automated File Processing** - DTC wellness and partner campaign file processing with validation
- **📞 Smart Call Scheduling** - Automated intro call scheduling with timezone optimization
- **🤖 AI Voice Integration** - Bland AI webhook processing for intelligent customer interactions
- **🛡️ Enterprise Security** - Azure Key Vault integration and comprehensive data validation
- **📊 Real-time Monitoring** - Complete observability with Azure Application Insights
- **🔄 Resilient Processing** - Retry mechanisms and robust error handling
- **📈 Campaign Analytics** - Advanced analytics for campaign performance tracking

---

## 🏗️ Project Structure

```
📦 IOE-Functions/
├── 📄 function_app.py                    # Main application entry point and blueprint registration
├── 📄 host.json                         # Azure Functions host configuration
├── 📄 requirements.txt                  # Python dependencies and packages
├── 📄 local.settings.json               # Local development environment settings
│
├── 🎯 functions/                        # Azure Function triggers and entry points
│   ├── dtc_file_processor.py           # Blob trigger for DTC wellness file processing
│   ├── partner_file_processor.py       # Blob trigger for partner campaign files
│   ├── dtc_intro_call_scheduler.py     # Timer/HTTP triggers for call scheduling
│   └── bland_ai_webhook.py             # HTTP trigger for Bland AI webhook processing
│
├── 🧠 af_code/                         # Core application logic and business rules
│   ├── af_dtc_logic.py                 # DTC campaign processing business logic
│   ├── af_partner_logic.py             # Partner campaign processing logic
│   │
│   ├── 🤖 bland_ai_webhook/            # Bland AI integration module
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
│   └── 📞 af_dtc_intro_call/           # DTC intro call management
│       ├── services/                   # Call scheduling services
│       └── utils/                      # Call management utilities
│
└── 📁 __pycache__/                     # Python bytecode cache
    └── [Compiled Python files]
```

---

## 🎯 Business Use Cases & Workflows

### 1. 📋 DTC Wellness Campaign Processing

**Business Context**: Process daily wellness campaign files containing customer eligibility data for Medical Guardian's direct-to-consumer wellness programs.

**Workflow**:
1. **File Detection**: Monitor `fs-dtc/landing/` blob container for new files
2. **Validation**: Enforce naming convention `MedicalGuardian_DTCWellness_*_Delta.csv`
3. **Data Processing**: Parse CSV files with customer wellness data
4. **Database Updates**: Insert/update customer eligibility records
5. **Reporting**: Generate processing reports and error logs

**Triggers**:
- **Type**: Blob Storage Trigger
- **Container**: `fs-dtc/landing/`
- **Pattern**: `MedicalGuardian_DTCWellness_*_Delta.csv`
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

### 4. 🤖 Bland AI Voice Integration

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
| `function_app.py` | **Application Bootstrap** | Registers all function blueprints and initializes the Azure Functions app |
| `host.json` | **Runtime Configuration** | Timeout settings, logging levels, and performance tuning |
| `requirements.txt` | **Dependency Management** | Python packages for Azure, database, AI, and validation |
| `local.settings.json` | **Development Config** | Local environment variables and connection strings |

### Function Triggers

| File | Trigger Type | Business Purpose |
|------|--------------|------------------|
| `dtc_file_processor.py` | **Blob Storage** | Processes DTC wellness campaign files for customer eligibility |
| `partner_file_processor.py` | **Blob Storage** | Handles partner campaign file ingestion and validation |
| `dtc_intro_call_scheduler.py` | **Timer/HTTP** | Schedules intro calls for new wellness program participants |
| `bland_ai_webhook.py` | **HTTP Webhook** | Processes real-time AI voice interaction data |

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

- **Python 3.11+**
- **Azure Functions Core Tools v4**
- **Azure CLI**
- **Azure Subscription** with appropriate permissions
- **SQL Server Database** access
- **Azure Storage Account**

### 🔧 Local Development Setup

1. **Clone Repository**
   ```bash
   git clone https://github.com/zubairashfaque/IOE-function.git
   cd IOE-function
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

- **Azure Function App** (Python 3.11, Consumption or Premium plan)
- **Azure Storage Account** (Standard performance, blob storage)
- **Azure SQL Database** (Standard tier minimum)
- **Azure Key Vault** (Standard tier)
- **Azure Service Bus** (Standard tier for webhooks)
- **Application Insights** (for monitoring and diagnostics)

---

## 🛠️ Technology Stack

| Layer | Technologies | Purpose |
|-------|-------------|---------|
| **Runtime** | Azure Functions, Python 3.11 | Serverless compute platform |
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
- **Function Performance** - Execution time and success rate tracking

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
- **Error Rate Tracking** - Error percentage by function and category

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

### Automated Deployment

GitHub Actions workflow for continuous deployment:

```yaml
name: Deploy IOE Azure Functions
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Deploy to Azure
        run: func azure functionapp publish IOE-function-app
```

### Manual Deployment

```bash
# Login to Azure
az login

# Deploy function app
func azure functionapp publish IOE-function-app --python

# Verify deployment
curl https://ioe-function-app.azurewebsites.net/api/health
```

### Environment Promotion

1. **Development** → `dev-ioe-function-app`
2. **Staging** → `staging-ioe-function-app`  
3. **Production** → `ioe-function-app`

---

## 🎯 Sample Configurations

### DTC File Processing Configuration

```python
# File naming validation
VALID_DTC_PATTERN = r"MedicalGuardian_DTCWellness_\d{8}_Delta\.csv"

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
📧 **Primary Contact**: [zubair.ashfaque@medicalguardian.com](mailto:zubair.ashfaque@medicalguardian.com)  
🏢 **Team**: AI-POD Data Science Team at Medical Guardian  
📋 **Issues**: [GitHub Issues](https://github.com/zubairashfaque/IOE-function/issues)  
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

**🏥 Developed with ❤️ by Zubair Ashfaque & AI-POD Team at Medical Guardian**

*Enhancing healthcare through intelligent automation and data-driven insights*

---

[![Medical Guardian](https://img.shields.io/badge/Powered%20by-Medical%20Guardian-red.svg)](https://medicalguardian.com)
[![Azure](https://img.shields.io/badge/Deployed%20on-Azure-blue.svg)](https://azure.microsoft.com)
[![Python](https://img.shields.io/badge/Built%20with-Python-green.svg)](https://python.org)

</div>