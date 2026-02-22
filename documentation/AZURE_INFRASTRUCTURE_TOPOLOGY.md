# Azure Infrastructure Topology - IOE Services Platform

**Document Version**: 1.0
**Created**: 2025-12-11
**Project**: Intelligence Orchestration Engine (IOE) - Medical Guardian Healthcare Automation
**Compliance**: HIPAA-compliant production healthcare system
**Azure Region**: East US 2

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Infrastructure Topology Diagram](#infrastructure-topology-diagram)
3. [Security Architecture](#security-architecture)
4. [PHI Data Flow Architecture](#phi-data-flow-architecture)
5. [CI/CD Deployment Pipeline](#cicd-deployment-pipeline)
6. [Component Inventory](#component-inventory)
7. [Connection Matrix](#connection-matrix)
8. [Cost Breakdown](#cost-breakdown)
9. [Security & Compliance](#security--compliance)
10. [Deployment Configuration](#deployment-configuration)
11. [References](#references)

---

## Executive Summary

The IOE Services Platform leverages a **serverless-first, event-driven architecture** on Microsoft Azure to deliver HIPAA-compliant healthcare automation. The infrastructure spans **7 core Azure services** deployed in **East US 2** region, processing Protected Health Information (PHI) while maintaining complete audit trails, data security, and regulatory compliance.

### Quick Stats

| Metric | Value |
|--------|-------|
| **Azure Region** | East US 2 |
| **Total Azure Services** | 7 core services + Azure Identity |
| **Serverless Functions** | 9 independent functions |
| **Monthly Estimated Cost** | $500-$1,200 (production workload) |
| **Compliance Level** | HIPAA, SOC 2 Type II ready |
| **Runtime** | Python 3.12 on Azure Functions v4 |
| **Primary Database** | Azure SQL Database (ioe schema, 65 tables) |
| **Storage** | Azure Blob Storage (3 containers, Standard LRS) |
| **Deployment** | GitHub Actions CI/CD with quality gates |

### Architecture Principles

- **Serverless-First**: Consumption-based Azure Functions for cost efficiency
- **Security by Default**: Managed Identity for service-to-service authentication
- **Secret Management**: Centralized Azure Key Vault for all credentials
- **PHI Protection**: Encryption at rest (TDE, Storage encryption) and in transit (TLS 1.2+)
- **Observability**: Application Insights with structured logging
- **Event-Driven**: Blob triggers, timer triggers, HTTP webhooks
- **Cost-Optimized**: Pay-per-execution with automatic scaling

---

## Infrastructure Topology Diagram

### Azure Resource Architecture

```mermaid
graph TB
    subgraph "External Systems"
        CSV[CSV File Uploads<br/>DTC/Partner/Device Campaigns<br/>PHI: YES]
        BlandAI[Bland AI Platform<br/>api.bland.ai<br/>Cost: $$$<br/>PHI: YES]
        GitHub[GitHub Actions<br/>CI/CD Pipeline<br/>PHI: NO]
    end

    subgraph "Azure Region: East US 2"
        subgraph "Resource Group: IOE-Production"

            subgraph "Compute Layer"
                Functions[Azure Functions<br/>App: IOE-function<br/>Runtime: Python 3.12<br/>Plan: Consumption<br/>Cost: $$<br/>PHI: Memory Only]
            end

            subgraph "Data Layer"
                Blob[Azure Blob Storage<br/>Standard LRS<br/>Containers: 3<br/>Cost: $<br/>PHI: YES]
                SQL[(Azure SQL Database<br/>Database: ioe<br/>Schema: 65 tables<br/>Cost: $$<br/>PHI: YES)]
            end

            subgraph "Security & Identity Layer"
                KV[Azure Key Vault<br/>Standard Tier<br/>Secrets: 5<br/>Cost: $<br/>PHI: Credentials Only]
                Identity[Azure Managed Identity<br/>DefaultAzureCredential<br/>Cost: Free<br/>PHI: NO]
            end

            subgraph "Messaging Layer"
                ServiceBus[Azure Service Bus<br/>Namespace: ioe-postcall-analysis<br/>Queue: IOE-POSTCALL-ANALYSIS<br/>Tier: Standard<br/>Cost: $<br/>PHI: YES]
            end

            subgraph "Monitoring Layer"
                AppInsights[Application Insights<br/>Sampling: 20 items/sec<br/>Cost: $<br/>PHI: Custom Logs]
                LogAnalytics[Log Analytics Workspace<br/>Query Engine<br/>Cost: $<br/>PHI: Query Results]
            end
        end
    end

    CSV -->|HTTPS Upload| Blob
    Blob -->|Blob Created Event| Functions

    Functions -->|Managed Identity| Identity
    Identity -->|OAuth 2.0| KV
    Identity -->|Managed Identity| Blob

    Functions -->|TDS over TLS 1.2<br/>SQL Auth| SQL

    KV -->|Connection String| SQL
    KV -->|API Key + Encryption Key| BlandAI
    KV -->|Connection String| Blob
    KV -->|Connection String| ServiceBus

    Functions -->|HTTPS POST<br/>Bearer Token + encrypted_key| BlandAI
    BlandAI -->|Webhook HTTPS<br/>Call Results| Functions

    Functions -->|AMQP over TLS<br/>Async Messaging| ServiceBus

    Functions -.->|Telemetry<br/>HTTPS| AppInsights
    AppInsights -->|Aggregation| LogAnalytics

    GitHub -->|Deploy<br/>HTTPS + Publish Profile| Functions

    classDef azureCompute fill:#0078D4,stroke:#004578,color:#fff,stroke-width:2px
    classDef azureData fill:#50E6FF,stroke:#00537C,color:#000,stroke-width:2px
    classDef azureSecurity fill:#FFB900,stroke:#995700,color:#000,stroke-width:2px
    classDef azureMessaging fill:#8661C5,stroke:#4B3867,color:#fff,stroke-width:2px
    classDef azureMonitoring fill:#00A4EF,stroke:#005A9E,color:#fff,stroke-width:2px
    classDef external fill:#E5E5E5,stroke:#666,color:#000,stroke-width:2px

    class Functions azureCompute
    class Blob,SQL azureData
    class KV,Identity azureSecurity
    class ServiceBus azureMessaging
    class AppInsights,LogAnalytics azureMonitoring
    class CSV,BlandAI,GitHub external
```

### Legend

| Symbol | Meaning |
|--------|---------|
| **$** | Low cost ($0-50/month per service) |
| **$$** | Medium cost ($50-500/month per service) |
| **$$$** | High cost ($500+/month per service) |
| **PHI: YES** | Stores or processes Protected Health Information |
| **PHI: NO** | Does not handle PHI |
| **PHI: Memory Only** | Processes PHI in memory without persistent storage |
| **Solid Line** | Synchronous communication |
| **Dashed Line** | Asynchronous communication |

---

## Security Architecture

### Managed Identity and Secret Management Flow

```mermaid
graph TD
    subgraph "Azure Functions Runtime"
        F1[dtc_file_processor]
        F2[partner_file_processor]
        F3[dtc_intro_call_scheduler]
        F4[bland_ai_webhook]
        F5[partner_campaign_scheduler]
        F6[batch_completion_reconciler]
        F7[device_activation_scheduler]
        F8[dtc_wellness_check_scheduler]
        F9[device_activation_file_processor]
    end

    subgraph "Azure Identity Service"
        MI[Managed Identity<br/>DefaultAzureCredential<br/>Authentication: OAuth 2.0]
    end

    subgraph "Azure Key Vault"
        S1[SqlConnectionStringIOE<br/>Database Connection]
        S2[BlandAIkey<br/>API Bearer Token]
        S3[Blandaitwilio<br/>Twilio Encryption Key]
        S4[AzureStorageConnectionString<br/>Blob Storage Access]
        S5[IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT<br/>Service Bus Connection]
    end

    subgraph "Target Azure Services"
        SQL[(Azure SQL Database)]
        Blob[Azure Blob Storage]
        SB[Azure Service Bus]
    end

    subgraph "External API"
        Bland[Bland AI<br/>api.bland.ai]
    end

    F1 --> MI
    F2 --> MI
    F3 --> MI
    F4 --> MI
    F5 --> MI
    F6 --> MI
    F7 --> MI
    F8 --> MI
    F9 --> MI

    MI -->|HTTPS REST API<br/>Get Secret| S1
    MI -->|HTTPS REST API<br/>Get Secret| S2
    MI -->|HTTPS REST API<br/>Get Secret| S3
    MI -->|HTTPS REST API<br/>Get Secret| S4
    MI -->|HTTPS REST API<br/>Get Secret| S5

    S1 -->|TDS over TLS 1.2<br/>SQL Authentication| SQL
    S2 -->|HTTPS<br/>Authorization: Bearer| Bland
    S3 -->|HTTPS<br/>encrypted_key Header| Bland
    S4 -->|HTTPS<br/>Blob SDK| Blob
    S5 -->|AMQP over TLS<br/>Connection String| SB

    classDef functionClass fill:#0078D4,stroke:#004578,color:#fff
    classDef identityClass fill:#FFB900,stroke:#995700,color:#000
    classDef secretClass fill:#FFA500,stroke:#CC8400,color:#000
    classDef serviceClass fill:#50E6FF,stroke:#00537C,color:#000
    classDef externalClass fill:#E5E5E5,stroke:#666,color:#000

    class F1,F2,F3,F4,F5,F6,F7,F8,F9 functionClass
    class MI identityClass
    class S1,S2,S3,S4,S5 secretClass
    class SQL,Blob,SB serviceClass
    class Bland externalClass
```

### Security Highlights

- **No Credentials in Code**: All secrets retrieved from Key Vault at runtime
- **Managed Identity**: Zero credential management for Azure-to-Azure communication
- **Encryption at Rest**: TDE for SQL Database, Microsoft-managed keys for Blob Storage
- **Encryption in Transit**: TLS 1.2+ enforced on all connections
- **Secret Rotation**: Azure Key Vault supports secret versioning and rotation
- **Access Policies**: RBAC controls who can read secrets from Key Vault

---

## PHI Data Flow Architecture

### Protected Health Information Journey

```mermaid
graph LR
    subgraph "PHI Ingestion"
        CSV[CSV File Upload<br/>Member Data<br/>Phone: +1XXXXXXXXXX<br/>Name: First Last<br/>Language: eng/spa<br/>Care Gaps: IDs]
    end

    subgraph "PHI Storage (Azure)"
        Blob[Blob Storage<br/>fs-dtc/landing/<br/>fs-partner/landing/<br/>Encryption: AES-256]
        SQL[(SQL Database<br/>Tables: members,<br/>member_campaign_enrollments,<br/>outreach_attempts<br/>Encryption: TDE)]
    end

    subgraph "PHI Processing (Serverless)"
        FileProc[File Processors<br/>Validate & Upsert<br/>Memory: PHI<br/>Disk: None]
        Scheduler[Schedulers<br/>Query Eligible Members<br/>Memory: PHI<br/>Disk: None]
    end

    subgraph "PHI Transmission (External)"
        BlandAI[Bland AI<br/>Voice Call Platform<br/>Receives: Phone, Name,<br/>Language, Metadata<br/>Stores: Call Recordings]
    end

    subgraph "PHI Audit Trail"
        CallLogs[bland_call_logs<br/>Call ID, Phone,<br/>Disposition, Transcript]
        History[member_enrollment_status_history<br/>Status Changes, Timestamps]
        AppInsights[Application Insights<br/>Custom Logs<br/>WARNING: May contain PHI]
    end

    CSV -->|1. HTTPS Upload| Blob
    Blob -->|2. Blob Trigger| FileProc
    FileProc -->|3. INSERT/UPDATE<br/>TDS over TLS 1.2| SQL

    SQL -->|4. SELECT Eligible<br/>TDS over TLS 1.2| Scheduler
    Scheduler -->|5. POST Batch<br/>HTTPS + Bearer Token| BlandAI

    BlandAI -->|6. Webhook POST<br/>Call Results| FileProc
    FileProc -->|7. INSERT Audit<br/>TDS over TLS 1.2| CallLogs
    FileProc -->|8. INSERT History<br/>TDS over TLS 1.2| History

    FileProc -.->|9. Telemetry<br/>MASKED PHI| AppInsights

    style CSV fill:#FFE5E5,stroke:#CC0000,color:#000
    style Blob fill:#FFE5E5,stroke:#CC0000,color:#000
    style SQL fill:#FFE5E5,stroke:#CC0000,color:#000
    style FileProc fill:#FFF4E5,stroke:#FF9900,color:#000
    style Scheduler fill:#FFF4E5,stroke:#FF9900,color:#000
    style BlandAI fill:#FFE5E5,stroke:#CC0000,color:#000
    style CallLogs fill:#FFE5E5,stroke:#CC0000,color:#000
    style History fill:#FFE5E5,stroke:#CC0000,color:#000
    style AppInsights fill:#FFF9E5,stroke:#FFCC00,color:#000
```

### PHI Classification

| Component | PHI Elements | HIPAA Controls |
|-----------|--------------|----------------|
| **CSV Files** | Phone, Name, Care Gap IDs, Language | Deleted after processing |
| **Blob Storage** | Complete CSV contents | AES-256 encryption, SAS tokens |
| **SQL Database** | members.first_name, members.last_name, members.phone_number, members.gender | TDE encryption, SQL authentication |
| **Azure Functions** | Processes PHI in memory (not persisted) | No disk writes, secure memory |
| **Bland AI** | Phone, Name, Language, Call Recordings | BAA in place, external HIPAA compliance |
| **Service Bus** | Call analysis metadata (may contain member ID) | TLS encryption, 24-hour TTL |
| **Application Insights** | Custom logs may contain member IDs (PHI masked) | 90-day retention, RBAC access control |
| **bland_call_logs** | call_id, from_number, to_number, transcript | Complete audit trail, TDE encryption |

---

## CI/CD Deployment Pipeline

### GitHub Actions Workflow

```mermaid
graph TB
    subgraph "GitHub Repository"
        Code[Python Code<br/>function_app.py<br/>af_code/*<br/>functions/*]
        Deps[requirements.txt<br/>Azure SDK Dependencies]
    end

    subgraph "Build Stage"
        Checkout[Checkout Code<br/>actions/checkout@v4]
        SetupPython[Setup Python 3.12<br/>actions/setup-python@v5]
        InstallDeps[Install Dependencies<br/>pip install -r requirements.txt]
        ZipArtifact[Create Release Artifact<br/>release.zip]
    end

    subgraph "Quality Gates Stage"
        Black[Code Formatting<br/>black --check --line-length 100]
        Ruff[Linting<br/>ruff check af_code/]
        MyPy[Type Checking<br/>mypy af_code/]
        Bandit[Security Scan<br/>bandit -r af_code/]
        Pytest[Unit Tests<br/>pytest af_code/]
    end

    subgraph "Deploy Stage"
        Download[Download Artifact<br/>actions/download-artifact@v4]
        Unzip[Extract release.zip]
        Deploy[Deploy to Azure Functions<br/>Azure/functions-action@v1]
    end

    subgraph "Azure Functions"
        FunctionApp[IOE-function<br/>Production Slot<br/>East US 2]
    end

    Code --> Checkout
    Deps --> Checkout
    Checkout --> SetupPython
    SetupPython --> InstallDeps
    InstallDeps --> ZipArtifact

    ZipArtifact --> Black
    ZipArtifact --> Ruff
    ZipArtifact --> MyPy
    ZipArtifact --> Bandit
    ZipArtifact --> Pytest

    Black --> Download
    Ruff --> Download
    MyPy --> Download
    Bandit --> Download
    Pytest --> Download

    Download --> Unzip
    Unzip --> Deploy
    Deploy --> FunctionApp

    classDef buildClass fill:#4CAF50,stroke:#2E7D32,color:#fff
    classDef qualityClass fill:#FF9800,stroke:#E65100,color:#fff
    classDef deployClass fill:#2196F3,stroke:#0D47A1,color:#fff
    classDef azureClass fill:#0078D4,stroke:#004578,color:#fff

    class Checkout,SetupPython,InstallDeps,ZipArtifact buildClass
    class Black,Ruff,MyPy,Bandit,Pytest qualityClass
    class Download,Unzip,Deploy deployClass
    class FunctionApp azureClass
```

### Deployment Configuration

- **Trigger**: Push to `main` branch or manual workflow dispatch
- **Build Environment**: Ubuntu Latest, Python 3.12
- **Quality Gates**: All must pass (black, ruff, mypy, bandit, pytest)
- **Deployment Method**: Azure Functions publish profile (from GitHub secrets)
- **Deployment Slot**: Production (direct deployment)
- **Build Options**: `scm-do-build-during-deployment: true`, `enable-oryx-build: true`
- **Health Check**: Retries up to 5 times with 10-second intervals

---

## Component Inventory

### Detailed Azure Services

| Component | Azure Service | SKU/Tier | Region | Authentication | Protocol | PHI Classification | Cost Tier | Monthly Estimate |
|-----------|---------------|----------|--------|----------------|----------|-------------------|-----------|------------------|
| **IOE-function** | Azure Functions | Consumption Plan (Y1) | East US 2 | Managed Identity (Key Vault, Storage)<br/>Connection String (SQL)<br/>API Key (Bland AI) | HTTPS, TDS over TLS 1.2, AMQP over TLS | Processes PHI in memory (no persistent storage) | $$ | $200-600 |
| **Blob Storage** | Azure Storage Account | Standard LRS | East US 2 | Managed Identity (DefaultAzureCredential)<br/>SAS Tokens (file uploads) | HTTPS (Blob SDK) | Contains PHI (CSV files with member data) | $ | $10-30 |
| **SQL Database** | Azure SQL Database | Standard S2 (50 DTU) or higher | East US 2 | SQL Authentication (connection string from Key Vault) | TDS over TLS 1.2 (force encryption=True) | Stores PHI (members, phone, names, care gaps) | $$ | $200-500 |
| **Key Vault** | Azure Key Vault | Standard | East US 2 | Managed Identity (DefaultAzureCredential) | HTTPS REST API | Stores credentials for PHI systems | $ | $5-10 |
| **Service Bus** | Azure Service Bus | Standard | East US 2 | Connection String (RootManageSharedAccessKey) | AMQP over TLS | May contain PHI in messages (call analysis) | $ | $10-20 |
| **Application Insights** | Azure Monitor | Standard (pay-as-you-go) | East US 2 | Instrumentation Key | HTTPS (SDK telemetry) | Contains PHI in custom logs (masking required) | $ | $20-50 |
| **Managed Identity** | Azure Identity | N/A (included with Functions) | East US 2 | OAuth 2.0, OpenID Connect | HTTPS | No PHI (authentication only) | Free | $0 |

**Total Estimated Monthly Cost**: $500-$1,200 (varies by call volume, storage usage, and execution count)

### Azure Functions Inventory

| Function Name | Trigger Type | Schedule/Path | Purpose | BusinessCaseID | Code Location |
|---------------|--------------|---------------|---------|----------------|---------------|
| **dtc_file_processor** | Blob Trigger | `fs-dtc/landing/{name}` | Process DTC wellness CSV files | BC-101 | `functions/dtc_file_processor.py` |
| **partner_file_processor** | Blob Trigger | `fs-partner/landing/{name}` | Process partner campaign CSV files | BC-102 | `functions/partner_file_processor.py` |
| **device_activation_file_processor** | Blob Trigger | `fs-device-activation/landing/{name}` | Process device activation CSV files | BC-108 | `functions/device_activation_file_processor.py` |
| **dtc_intro_call_scheduler** | Timer + HTTP | Every 10 min + `/create_dtc_intro_batch` | Schedule DTC intro calls | BC-103 | `functions/dtc_intro_call_scheduler.py` |
| **dtc_wellness_check_scheduler** | Timer + HTTP | Every 10 min + `/create_dtc_wellness_batch` | Schedule DTC wellness check calls | BC-104 | `functions/dtc_wellness_check_scheduler.py` |
| **partner_campaign_scheduler** | Timer + HTTP | Every 30 min + `/partner_campaign_scheduler` | Schedule partner campaign calls | BC-105 | `functions/partner_campaign_scheduler.py` |
| **device_activation_scheduler** | Timer + HTTP | Timer + `/device_activation_scheduler` | Schedule device activation callbacks | BC-109 | `functions/device_activation_scheduler.py` |
| **bland_ai_webhook** | HTTP POST | `/bland-ai-webhook` | Process Bland AI call results (webhook receiver) | BC-106 | `functions/bland_ai_webhook.py` |
| **batch_completion_reconciler** | Timer + HTTP | Every 30 min + `/batch_completion_reconciler` | Reconcile batch statuses from attempts | BC-107 | `functions/batch_completion_reconciler.py` |

---

## Connection Matrix

### Service-to-Service Communication

| Source | Destination | Protocol | Authentication Method | Data Transmitted | Data Classification | Connection Type |
|--------|-------------|----------|----------------------|------------------|---------------------|-----------------|
| **CSV Upload** | Blob Storage | HTTPS | SAS Token or Managed Identity | Complete CSV file (member data) | PHI | Synchronous |
| **Blob Storage** | Azure Functions | Event Grid (Blob Trigger) | Managed Identity | Blob metadata and path | Non-PHI | Asynchronous (event) |
| **Azure Functions** | Key Vault | HTTPS REST | Managed Identity (DefaultAzureCredential) | Secret names (no data) | Non-PHI | Synchronous |
| **Key Vault** | Azure Functions | HTTPS REST | Managed Identity response | Connection strings, API keys | Credentials (sensitive) | Synchronous |
| **Azure Functions** | SQL Database | TDS over TLS 1.2 | SQL Authentication (connection string) | SQL queries (PHI in WHERE/INSERT) | PHI | Synchronous |
| **SQL Database** | Azure Functions | TDS over TLS 1.2 | SQL Authentication response | Query results (member data) | PHI | Synchronous |
| **Azure Functions** | Bland AI | HTTPS POST | Bearer Token + encrypted_key header | Batch requests (phone, name, metadata) | PHI | Synchronous |
| **Bland AI** | Azure Functions | HTTPS POST (Webhook) | Twilio signature validation | Call results (disposition, transcript) | PHI | Asynchronous (webhook) |
| **Azure Functions** | Service Bus | AMQP over TLS | Connection String (SharedAccessKey) | Call analysis messages (JSON) | May contain PHI | Asynchronous (fire & forget) |
| **Azure Functions** | Application Insights | HTTPS (SDK) | Instrumentation Key | Telemetry, logs, metrics | Custom logs may contain PHI | Asynchronous (telemetry) |
| **Application Insights** | Log Analytics | Internal Azure | N/A (Azure-managed) | Aggregated telemetry | Custom logs may contain PHI | Asynchronous |
| **GitHub Actions** | Azure Functions | HTTPS | Publish Profile (from GitHub secrets) | Deployment artifact (release.zip) | Non-PHI (code only) | Synchronous |

### External Integrations

| External System | Direction | Protocol | Authentication | Data Exchanged | PHI Classification |
|-----------------|-----------|----------|----------------|----------------|-------------------|
| **Bland AI (api.bland.ai)** | Outbound (batch submission) | HTTPS POST | Bearer Token + encrypted_key header | Member phone, name, language, care gap data | PHI |
| **Bland AI (webhook)** | Inbound (call results) | HTTPS POST | Twilio signature validation | Call ID, disposition, transcript, analysis | PHI |
| **Partner CSV Uploads** | Inbound | HTTPS (Blob upload) | SAS Token or Managed Identity | Complete member data (phone, name, care gaps) | PHI |
| **DTC CSV Uploads** | Inbound | HTTPS (Blob upload) | SAS Token or Managed Identity | Member wellness data (phone, checkin time, language) | PHI |

---

## Cost Breakdown

### Monthly Cost Estimates (Production Workload)

#### Azure Services Cost Summary

| Service | SKU/Tier | Cost Driver | Low Estimate | High Estimate | Notes |
|---------|----------|-------------|--------------|---------------|-------|
| **Azure Functions** | Consumption Plan | Execution time × executions | $200 | $600 | ~672 timer executions/day + blob triggers + HTTP calls |
| **Azure SQL Database** | Standard S2 (50 DTU) | Fixed tier + storage | $200 | $500 | Consider Serverless for cost optimization during off-hours |
| **Blob Storage** | Standard LRS | Storage + operations | $10 | $30 | CSV files deleted after processing (minimal retention) |
| **Key Vault** | Standard | Operations (secret retrievals) | $5 | $10 | ~10 secrets × retrieval frequency |
| **Service Bus** | Standard | Messages + operations | $10 | $20 | Async message queue for post-call analysis |
| **Application Insights** | Pay-as-you-go | Data ingestion volume | $20 | $50 | Telemetry from 9 functions × log verbosity |
| **Managed Identity** | Included | N/A | $0 | $0 | No additional cost |
| **Total (Azure Infrastructure)** | | | **$445** | **$1,210** | Excluding external services |

#### External Services Cost

| Service | Type | Cost Estimate | Notes |
|---------|------|---------------|-------|
| **Bland AI** | External SaaS | $500-2,000/month | Per-call pricing (~$0.10-0.50/min) × call volume |

#### Total Estimated Monthly Cost

- **Azure Infrastructure Only**: $445-$1,210/month
- **Including Bland AI**: $945-$3,210/month (varies significantly by call volume)

### Cost Optimization Recommendations

1. **Azure SQL Serverless**: Migrate from Standard S2 to Serverless tier with auto-pause
   - **Savings**: ~40% during off-hours (nights, weekends)
   - **Impact**: Database auto-pauses after 1 hour of inactivity
   - **Tradeoff**: 1-2 second cold start delay

2. **Application Insights Sampling**: Enable adaptive sampling to reduce telemetry volume
   - **Current**: 20 items/second max (configured in host.json)
   - **Recommendation**: Increase sampling percentage to 50-70%
   - **Savings**: ~30-50% reduction in Application Insights costs

3. **Blob Lifecycle Management**: Already implemented (delete CSV files after processing)
   - **Status**: Active (files moved to processed folder, then deleted)
   - **Savings**: Prevents long-term storage costs

4. **Reserved Capacity**: Consider 1-year or 3-year reserved instances for SQL Database
   - **Savings**: 30-50% discount on compute costs
   - **Requirement**: Stable workload with predictable usage

5. **Function Execution Optimization**: Review timer trigger intervals
   - **Current**: DTC schedulers run every 10 min, Partner/Batch every 30 min
   - **Recommendation**: Evaluate if 15-min intervals are acceptable for DTC
   - **Savings**: ~33% reduction in timer trigger executions

---

## Security & Compliance

### HIPAA Technical Safeguards

#### Access Control (164.312(a)(1))

| Control | Implementation | Azure Service | Status |
|---------|----------------|---------------|--------|
| **Unique User Identification** | Azure Active Directory (Entra ID) | Azure Identity | ✅ Implemented |
| **Automatic Logoff** | Session timeouts configured | Azure Functions | ✅ Implemented |
| **Encryption and Decryption** | TDE for SQL, AES-256 for Blob Storage | SQL Database, Blob Storage | ✅ Implemented |

#### Audit Controls (164.312(b))

| Control | Implementation | Azure Service | Status |
|---------|----------------|---------------|--------|
| **Audit Logs** | Application Insights custom logs | Application Insights | ✅ Implemented |
| **Database Audit** | SQL Extended Events (optional) | SQL Database | ⚠️ Recommended |
| **Storage Analytics** | Blob storage access logs | Blob Storage | ✅ Implemented |
| **Webhook Audit Trail** | bland_call_logs table (complete history) | SQL Database | ✅ Implemented |

#### Integrity (164.312(c)(1))

| Control | Implementation | Azure Service | Status |
|---------|----------------|---------------|--------|
| **Data Integrity** | Parameterized queries prevent SQL injection | SQL Database | ✅ Implemented |
| **Transaction Atomicity** | DatabaseService.execute_transaction() | SQL Database | ✅ Implemented |
| **Idempotency** | DuplicateDetector service for webhooks | SQL Database | ✅ Implemented |

#### Transmission Security (164.312(e)(1))

| Control | Implementation | Azure Service | Status |
|---------|----------------|---------------|--------|
| **Encryption in Transit** | TLS 1.2+ enforced on all connections | All services | ✅ Implemented |
| **SQL Connection Security** | force encryption=True in connection string | SQL Database | ✅ Implemented |
| **Blob Storage Security** | HTTPS required (secure transfer=True) | Blob Storage | ✅ Implemented |
| **Service Bus Security** | AMQP over TLS | Service Bus | ✅ Implemented |

### Business Associate Agreements (BAA)

| Vendor | BAA Status | Scope | Data Shared |
|--------|-----------|-------|-------------|
| **Microsoft Azure** | ✅ Signed | All Azure services (Functions, SQL, Blob, Key Vault, Service Bus, Application Insights) | PHI in SQL, Blob, Application Insights custom logs |
| **Bland AI** | ✅ Signed | AI voice call execution and recording storage | Member phone, name, language preference, call recordings |

### Network Security

| Component | Current State | Recommended Enhancement |
|-----------|---------------|------------------------|
| **Azure Functions** | Public endpoint with IP restrictions | ✅ Deploy in VNet with Private Endpoints |
| **SQL Database** | Public endpoint with firewall rules | ✅ Enable Private Endpoint (eliminate public access) |
| **Blob Storage** | Public endpoint with SAS tokens | ✅ Enable Private Endpoint for internal access |
| **Key Vault** | Public endpoint with access policies | ✅ Enable Private Endpoint |
| **Service Bus** | Public endpoint with shared access keys | ✅ Enable Private Endpoint |

---

## Deployment Configuration

### Environment Variables (Azure Function App Configuration)

| Variable | Source | Purpose | Example Value |
|----------|--------|---------|---------------|
| `FUNCTIONS_WORKER_RUNTIME` | App Setting | Specifies Python runtime | `python` |
| `KEY_VAULT_URL` | App Setting | Azure Key Vault endpoint | `https://your-keyvault.vault.azure.net/` |
| `DB_SECRET_NAME` | App Setting | Database connection string secret name | `SqlConnectionStringIOE` |
| `AzureWebJobsStorage` | App Setting | Storage account for Functions internal use | `DefaultEndpointsProtocol=https;AccountName=...` |
| `TIMEZONE` | App Setting (optional) | Deployment timezone (default: UTC) | `UTC` or `America/New_York` |

### Azure Key Vault Secrets

| Secret Name | Description | Used By | Format |
|-------------|-------------|---------|--------|
| `SqlConnectionStringIOE` | Azure SQL Database connection string | All functions needing database access | `Server=tcp:...;Database=ioe;User ID=...;Password=...;Encrypt=true` |
| `BlandAIkey` | Bland AI API authentication token | Schedulers (batch submission) | Bearer token string |
| `Blandaitwilio` | Twilio encryption key for Bland AI | Schedulers (batch submission) | Encryption key string |
| `AzureStorageConnectionString` | Blob storage connection string | File processors | `DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...` |
| `IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT` | Service Bus connection string | Webhook processor | `Endpoint=sb://ioe-postcall-analysis.servicebus.windows.net/;SharedAccessKeyName=...` |

### Function App Host Configuration (host.json)

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "maxTelemetryItemsPerSecond": 20,
        "excludedTypes": "Request"
      },
      "enableDependencyTracking": true,
      "enablePerformanceCountersCollection": true
    },
    "logLevel": {
      "default": "Information",
      "Function": "Information",
      "af_code.shared.bland_ai_client": "Information",
      "af_code.partner_campaign_scheduler": "Information"
    }
  },
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

**Key Configuration**:
- **Sampling**: 20 telemetry items/second max (cost optimization)
- **Dependency Tracking**: Enabled (tracks SQL, HTTP, Service Bus calls)
- **Performance Counters**: Enabled (CPU, memory, request metrics)
- **Extension Bundle**: v4 (Azure Functions v4 runtime)

---

## References

### Related Documentation

- **[AZURE_COMPONENTS_REFERENCE.md](./AZURE_COMPONENTS_REFERENCE.md)** - Detailed component analysis and code references
- **[IOE_AZURE_FUNCTIONS_COMPREHENSIVE_DOCUMENTATION.md](../IOE_AZURE_FUNCTIONS_COMPREHENSIVE_DOCUMENTATION.md)** - Complete function-level documentation with workflows
- **[IOE_TABLE_USAGE_REFERENCE.md](../IOE_TABLE_USAGE_REFERENCE.md)** - Database schema (65 tables, 23 actively used)
- **[PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md](../PARTNER_CAMPAIGN_COMPLETE_DOCUMENTATION.md)** - Partner campaign workflows and SQL queries
- **[DTC_CALL_FLOW.md](../DTC_CALL_FLOW.md)** - DTC intro call scheduling flow
- **[WEBHOOK_TESTING_GUIDE.md](../WEBHOOK_TESTING_GUIDE.md)** - Bland AI webhook integration testing
- **[CLAUDE.md](../CLAUDE.md)** - Development patterns, code quality gates, deployment procedures

### Code References

| File | Purpose | Lines of Interest |
|------|---------|-------------------|
| `function_app.py` | Function registration and environment validation | Lines 1-96 |
| `host.json` | Application Insights and extension bundle configuration | Lines 1-24 |
| `requirements.txt` | Azure SDK dependencies | Lines 5-19 |
| `.github/workflows/main_ioe-function.yml` | CI/CD pipeline with quality gates | Lines 1-77 |
| `af_code/bland_ai_webhook/services/config_manager.py` | Key Vault integration and secret management | Lines 1-131 |
| `af_code/bland_ai_webhook/services/database_service.py` | Database connection and transaction management | Lines 1-150+ |
| `local.settings.json` | Local development configuration (Service Bus) | Lines 1-8 |

### External Resources

- **[Azure Functions Python Developer Guide](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-python)**
- **[Azure SQL Database Security](https://learn.microsoft.com/en-us/azure/azure-sql/database/security-overview)**
- **[Azure Key Vault Best Practices](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices)**
- **[Azure Blob Storage Security](https://learn.microsoft.com/en-us/azure/storage/blobs/security-recommendations)**
- **[HIPAA Compliance on Azure](https://learn.microsoft.com/en-us/azure/compliance/offerings/offering-hipaa-us)**

---

**Document Maintained By**: AI-POD Team - Data Science at Medical Guardian
**For Questions**: Contact AI-POD Team or refer to `CLAUDE.md` for development guidelines
**Last Reviewed**: 2025-12-11
**Next Review**: Quarterly or after major infrastructure changes
