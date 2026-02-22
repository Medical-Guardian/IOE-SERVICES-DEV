# Device Activation - Deployment Guide

**Date:** 2025-12-24
**Version:** 1.0
**BusinessCaseIDs:** BC-DA-001 through BC-DA-008
**Target Environments:** Development, Test, Production

---

## Table of Contents

1. [Deployment Overview](#1-deployment-overview)
2. [Prerequisites](#2-prerequisites)
3. [Environment Configuration](#3-environment-configuration)
4. [Database Schema Deployment](#4-database-schema-deployment)
5. [Function App Deployment](#5-function-app-deployment)
6. [Blob Storage Configuration](#6-blob-storage-configuration)
7. [Key Vault Configuration](#7-key-vault-configuration)
8. [Bland AI Configuration](#8-bland-ai-configuration)
9. [Post-Deployment Validation](#9-post-deployment-validation)
10. [Rollback Procedures](#10-rollback-procedures)
11. [Monitoring Setup](#11-monitoring-setup)
12. [Deployment Checklist](#12-deployment-checklist)

---

## 1. Deployment Overview

### 1.1 Deployment Architecture

The Device Activation system consists of:

- **4 Azure Functions** (part of IOE-functions app):
  - `device_activation_file_processor` (Blob trigger - LEGACY)
  - `operations_device_activation_file_processor` (Blob trigger - PRIMARY)
  - `device_activation_scheduler` (Timer trigger: 15 min)
  - `device_activation_campaign_closure` (Timer trigger: hourly)
- **Azure SQL Database** (engage360 schema):
  - 8 core tables
  - 1 staging table (engage360_stg.stg_device_activation_delta)
- **Azure Blob Storage**:
  - fs-device-activation container (landing, processed, error folders)
  - fs-ops container (landing, processed, error folders)
- **Azure Key Vault**:
  - SqlConnectionStringIOE secret
  - BlandAIkey secret
  - Blandaitwilio secret (encrypted_key header)
- **Bland AI API** (External):
  - Batch submission endpoint
  - Webhook callback URL

### 1.2 Deployment Environments

| Environment | Function App | Database | Key Vault | Purpose |
|-------------|--------------|----------|-----------|---------|
| **Local** | localhost:7071 | Dev DB | Dev KV | Development testing |
| **Development** | ioe-functions-dev | engage360-dev | kv-ioe-dev | Integration testing |
| **Test** | ioe-functions-test | engage360-test | kv-ioe-test | UAT and regression |
| **Production** | ioe-function | engage360-prod | kv-ioe-prod | Live member calls |

### 1.3 Deployment Flow

```
Code Changes → Local Testing → Dev Deployment → Test Deployment → Production Deployment
                    ↓              ↓                  ↓                    ↓
                Unit Tests    Integration Tests   UAT Testing      Production Release
```

---

## 2. Prerequisites

### 2.1 Required Software

**Local Development:**
```bash
# Python 3.12 (exact version required by Azure Functions v4)
python --version  # Should output: Python 3.12.x

# Azure Functions Core Tools (v4)
func --version  # Should output: 4.x.x

# Azure CLI
az --version  # Should output: 2.x.x or higher

# Git (for version control)
git --version
```

**Installation Commands:**

```bash
# Install Python 3.12 (Ubuntu/Debian)
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# Install Azure Functions Core Tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Verify installations
python3.12 --version
func --version
az --version
```

### 2.2 Azure Permissions

**Required Azure RBAC Roles:**

- **Function App Deployment:**
  - `Contributor` role on Resource Group
  - `Website Contributor` role on Function App
- **Database Deployment:**
  - `db_owner` role on engage360 database
  - `db_owner` role on engage360_stg schema
- **Key Vault Access:**
  - `Key Vault Secrets Officer` role (create/update secrets)
  - `Key Vault Secrets User` role (read secrets)
- **Blob Storage Access:**
  - `Storage Blob Data Contributor` role

**Verify Permissions:**

```bash
# Check your Azure account
az account show

# List Function Apps you have access to
az functionapp list --query "[].{name:name, resourceGroup:resourceGroup}" -o table

# Verify Key Vault access
az keyvault secret list --vault-name kv-ioe-prod --query "[].name" -o table
```

### 2.3 Local Environment Setup

**Clone Repository:**

```bash
# Clone the IOE-functions repository
git clone https://github.com/your-org/IOE-functions.git
cd IOE-functions

# Create Python virtual environment
python3.12 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install development dependencies (testing, linting)
pip install black ruff mypy pytest bandit
```

**Configure Local Settings:**

Create `local.settings.json` (NOT committed to Git):

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "KEY_VAULT_URL": "https://kv-ioe-dev.vault.azure.net/",
    "DB_SECRET_NAME": "SqlConnectionStringIOE",
    "PYTHON_ENABLE_WORKER_EXTENSIONS": "1",
    "PYTHON_ISOLATE_WORKER_DEPENDENCIES": "1"
  },
  "ConnectionStrings": {}
}
```

**Test Local Function App:**

```bash
# Start Azure Functions locally
func start --python

# Expected output:
# Functions:
#   device_activation_file_processor: blobTrigger
#   device_activation_scheduler: timerTrigger, httpTrigger
#   operations_device_activation_file_processor: blobTrigger
#   ... (other functions)
#
# Host started
# Http Functions:
#   device_activation_scheduler: [GET,POST] http://localhost:7071/api/device_activation_scheduler
```

---

## 3. Environment Configuration

### 3.1 Function App Settings (Azure Portal)

**Navigate to:** Azure Portal → Function App → Configuration → Application Settings

**Required Settings:**

| Setting Name | Value | Description |
|--------------|-------|-------------|
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Required for Python functions |
| `PYTHON_VERSION` | `3.12` | Exact Python version |
| `AzureWebJobsStorage` | `<connection-string>` | Storage account for function state |
| `KEY_VAULT_URL` | `https://kv-ioe-{env}.vault.azure.net/` | Key Vault URL |
| `DB_SECRET_NAME` | `SqlConnectionStringIOE` | Database secret name in KV |
| `WEBSITE_ENABLE_SYNC_UPDATE_SITE` | `true` | Enable deployment sync |
| `WEBSITE_RUN_FROM_PACKAGE` | `1` | Run from deployment package |
| `PYTHON_ENABLE_WORKER_EXTENSIONS` | `1` | Enable Python worker extensions |
| `PYTHON_ISOLATE_WORKER_DEPENDENCIES` | `1` | Isolate Python dependencies |

**Azure CLI Command (Set All Settings):**

```bash
# Set Function App settings
az functionapp config appsettings set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --settings \
    FUNCTIONS_WORKER_RUNTIME=python \
    PYTHON_VERSION=3.12 \
    KEY_VAULT_URL=https://kv-ioe-prod.vault.azure.net/ \
    DB_SECRET_NAME=SqlConnectionStringIOE \
    WEBSITE_ENABLE_SYNC_UPDATE_SITE=true \
    WEBSITE_RUN_FROM_PACKAGE=1 \
    PYTHON_ENABLE_WORKER_EXTENSIONS=1 \
    PYTHON_ISOLATE_WORKER_DEPENDENCIES=1
```

### 3.2 Function App Identity (Managed Identity)

**Enable System-Assigned Managed Identity:**

```bash
# Enable managed identity for Function App
az functionapp identity assign \
  --name ioe-function \
  --resource-group rg-ioe-prod

# Capture the Principal ID (will be needed for Key Vault access)
PRINCIPAL_ID=$(az functionapp identity show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query principalId -o tsv)

echo "Principal ID: $PRINCIPAL_ID"
```

**Grant Managed Identity Access to Key Vault:**

```bash
# Grant "Key Vault Secrets User" role
az keyvault set-policy \
  --name kv-ioe-prod \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list
```

**Verify Key Vault Access:**

```bash
# Test secret retrieval (should succeed)
az functionapp config appsettings list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?name=='KEY_VAULT_URL'].value" -o tsv
```

### 3.3 Connection Strings

**Storage Account Connection String:**

```bash
# Get storage account connection string
az storage account show-connection-string \
  --name stioefstorage \
  --resource-group rg-ioe-prod \
  --query connectionString -o tsv

# Set as AzureWebJobsStorage setting
az functionapp config appsettings set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --settings AzureWebJobsStorage="<connection-string-from-above>"
```

**Database Connection String (Stored in Key Vault):**

```bash
# Database connection string format (stored as secret):
# Server=tcp:sql-ioe-prod.database.windows.net,1433;Database=engage360;User ID=ioe_user;Password=<strong-password>;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;

# Set/Update in Key Vault
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --value "Server=tcp:sql-ioe-prod.database.windows.net,1433;Database=engage360;User ID=ioe_user;Password=<password>;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
```

---

## 4. Database Schema Deployment

### 4.1 Pre-Deployment Checklist

**Before deploying database changes:**

1. ✅ Backup production database
2. ✅ Review SQL migration scripts for syntax errors
3. ✅ Test migration scripts on dev/test databases first
4. ✅ Verify all table dependencies exist
5. ✅ Check for breaking changes (column renames, data type changes)

### 4.2 Database Backup

**Production Backup (Before ANY Schema Changes):**

```bash
# Create on-demand backup
az sql db create \
  --resource-group rg-ioe-prod \
  --server sql-ioe-prod \
  --name engage360 \
  --backup-storage-redundancy Local

# Verify backup exists
az sql db list-backups \
  --resource-group rg-ioe-prod \
  --server sql-ioe-prod \
  --database engage360
```

**Alternative: SQL Server Management Studio (SSMS):**

```sql
-- Manual backup script
BACKUP DATABASE [engage360]
TO DISK = N'/var/opt/mssql/backup/engage360_pre_deployment_2025-12-24.bak'
WITH FORMAT, INIT, COMPRESSION,
  NAME = N'engage360-Pre-Deployment-Full',
  STATS = 10;
GO
```

### 4.3 Deploy Staging Table

**Staging Table: `engage360_stg.stg_device_activation_delta`**

**Script:** `database/create_stg_device_activation_delta_table.sql`

**Deployment Steps:**

```bash
# Connect to Azure SQL Database
sqlcmd -S sql-ioe-prod.database.windows.net -d engage360 -U ioe_user -P <password> -i database/create_stg_device_activation_delta_table.sql

# Or use Azure CLI with AAD authentication
az sql query \
  --server sql-ioe-prod \
  --database engage360 \
  --auth-type ADPassword \
  --file database/create_stg_device_activation_delta_table.sql
```

**Verify Table Creation:**

```sql
-- Verify staging table exists
SELECT TABLE_SCHEMA, TABLE_NAME, CREATE_DATE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta';

-- Expected result:
-- TABLE_SCHEMA      | TABLE_NAME                       | CREATE_DATE
-- engage360_stg     | stg_device_activation_delta      | 2025-12-24 10:30:00
```

### 4.4 Deploy Core Tables (If Not Exist)

**Core tables required for Device Activation:**

1. `engage360.members` (Master member table)
2. `engage360.member_devices` (Device information)
3. `engage360.campaigns_enhanced` (Campaign configuration)
4. `engage360.campaign_call_configs_enhanced` (Bland AI config)
5. `engage360.member_campaign_enrollments_enhanced` (Enrollment tracking)
6. `engage360.outreach_batches` (Batch tracking)
7. `engage360.outreach_attempts` (Call attempt tracking)
8. `engage360.outreach_callback_queue` (Callback queue)
9. `engage360.bland_call_logs` (Webhook audit trail)

**Check if tables exist:**

```sql
-- Check core tables
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME IN (
    'members',
    'member_devices',
    'campaigns_enhanced',
    'campaign_call_configs_enhanced',
    'member_campaign_enrollments_enhanced',
    'outreach_batches',
    'outreach_attempts',
    'outreach_callback_queue',
    'bland_call_logs'
  )
ORDER BY TABLE_NAME;
```

**If tables missing:** Contact database administrator or deploy from schema scripts in `database/Context Engage360 schema.txt`

### 4.5 Schema Migrations (Recent Changes)

**Migration #1: Fix Staging Table Schema (2025-12-23)**

**File:** `database/fix_device_activation_staging_table_schema.sql`

**Purpose:** Fix column name mismatches (battery_status → powersaver_mode)

```bash
# Deploy migration
sqlcmd -S sql-ioe-prod.database.windows.net -d engage360 -U ioe_user -P <password> -i database/fix_device_activation_staging_table_schema.sql
```

**Migration #2: Rename Battery Status Column (2025-12-23)**

**File:** `database/rename_battery_status_to_powersaver_mode.sql`

**Purpose:** Align naming with updated CSV specification

```bash
# Deploy migration
sqlcmd -S sql-ioe-prod.database.windows.net -d engage360 -U ioe_user -P <password> -i database/rename_battery_status_to_powersaver_mode.sql
```

**Verify Migrations Applied:**

```sql
-- Check staging table columns
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME LIKE '%powersaver%';

-- Expected result:
-- COLUMN_NAME          | DATA_TYPE | CHARACTER_MAXIMUM_LENGTH | IS_NULLABLE
-- powersaver_mode      | varchar   | 50                       | YES
-- powersaver_mode_clean| varchar   | 50                       | YES
```

### 4.6 Create Indexes (Performance Optimization)

**Critical indexes for Device Activation queries:**

```sql
-- Index 1: Enrollment eligibility (used in eligibility_service.py)
CREATE NONCLUSTERED INDEX IX_enrollments_eligibility
ON engage360.member_campaign_enrollments_enhanced (
    current_status,
    activation_start_date,
    call_5_timestamp
)
INCLUDE (enrollment_id, member_id, campaign_id, campaign_end_date);

-- Index 2: Outreach attempts (frequency protection)
CREATE NONCLUSTERED INDEX IX_attempts_enrollment_ts
ON engage360.outreach_attempts (
    enrollment_id,
    attempt_ts DESC
)
INCLUDE (disposition);

-- Index 3: Callback queue (scheduler query)
CREATE NONCLUSTERED INDEX IX_callbacks_pending
ON engage360.outreach_callback_queue (
    status,
    scheduled_callback_time
)
INCLUDE (enrollment_id, attempt_count, created_at);

-- Index 4: Batch status (reconciler query)
CREATE NONCLUSTERED INDEX IX_batches_status
ON engage360.outreach_batches (
    batch_status,
    created_at DESC
)
INCLUDE (batch_id, campaign_id, vendor_batch_id);
```

**Verify Indexes Created:**

```sql
-- Check indexes on key tables
SELECT
    t.name AS TableName,
    i.name AS IndexName,
    i.type_desc AS IndexType
FROM sys.indexes i
INNER JOIN sys.tables t ON i.object_id = t.object_id
WHERE t.name IN (
    'member_campaign_enrollments_enhanced',
    'outreach_attempts',
    'outreach_callback_queue',
    'outreach_batches'
)
ORDER BY t.name, i.name;
```

---

## 5. Function App Deployment

### 5.1 Pre-Deployment Code Quality Checks

**CRITICAL: Run all quality checks before deployment**

```bash
# Activate virtual environment
source venv/bin/activate

# 1. Code Formatting (PEP 8)
black --line-length 100 --check af_code/
# If issues found: black --line-length 100 af_code/

# 2. Linting
ruff check af_code/
# Fix issues manually or: ruff check --fix af_code/

# 3. Type Checking
mypy af_code/

# 4. Security Scan
bandit -r af_code/ -ll

# 5. Run Tests
pytest af_code/ --verbose --cov=af_code

# All checks MUST pass before proceeding
```

**Expected Output (All Passing):**

```
✅ black: All files formatted correctly
✅ ruff: No linting issues
✅ mypy: No type errors
✅ bandit: No security issues (or only low severity)
✅ pytest: All tests passed (100% or near 100% coverage)
```

### 5.2 Deployment Method 1: Azure CLI (Recommended)

**Step 1: Build Deployment Package**

```bash
# Ensure you're in the project root
cd /home/zubair-ashfaque/MG-IOE/Azure\ Function/Azure_function_Deployment/IOE-functions

# Clean previous builds
rm -rf .python_packages/
rm -f function_app.zip

# Azure Functions will handle package installation
# No need to manually create .python_packages
```

**Step 2: Deploy to Azure**

```bash
# Login to Azure
az login

# Set default subscription (if multiple subscriptions)
az account set --subscription "Your-Subscription-Name"

# Deploy to Development
az functionapp deployment source config-zip \
  --resource-group rg-ioe-dev \
  --name ioe-functions-dev \
  --src . \
  --build-remote true \
  --verbose

# Deploy to Production
az functionapp deployment source config-zip \
  --resource-group rg-ioe-prod \
  --name ioe-function \
  --src . \
  --build-remote true \
  --verbose
```

**Step 3: Monitor Deployment**

```bash
# Watch deployment logs in real-time
az functionapp log tail \
  --name ioe-function \
  --resource-group rg-ioe-prod
```

**Expected Deployment Output:**

```
Getting scm site credentials for zip deployment
Starting zip deployment. This operation can take a while to complete ...
Deployment endpoint responded with status code 202
Remote build in progress, please check status at https://ioe-function.scm.azurewebsites.net/api/deployments/latest
Remote build succeeded!
Deployment successful. deployer = ms-azuretools-vscode deploymentPath = Functions App ZipDeploy. Extract zip. Remote build.
✅ Successfully registered Device Activation File Processor blueprint
✅ Successfully registered Operations Device Activation File Processor blueprint
✅ Successfully registered Device Activation Scheduler blueprint
```

### 5.3 Deployment Method 2: VS Code (Alternative)

**Prerequisites:**
- Install [Azure Functions VS Code Extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azurefunctions)

**Steps:**

1. Open VS Code in project folder
2. Click **Azure icon** in left sidebar
3. Expand **Function App** section
4. Right-click **ioe-function** → **Deploy to Function App**
5. Confirm deployment prompt
6. Wait for deployment to complete (watch OUTPUT panel)

**Verify Deployment:**

```
OUTPUT (Azure Functions)
---------------------
12:30:00 PM: Starting deployment...
12:30:15 PM: Uploading content...
12:31:00 PM: Running remote build...
12:32:30 PM: Deployment successful
12:32:31 PM: Functions:
  - device_activation_file_processor
  - device_activation_scheduler
  - device_activation_campaign_closure
  - operations_device_activation_file_processor
```

### 5.4 Deployment Method 3: GitHub Actions CI/CD (Automated)

**GitHub Actions Workflow:** `.github/workflows/deploy-azure-functions.yml`

**Trigger:** Push to `main` branch

**Workflow Steps:**

1. Checkout code
2. Setup Python 3.12
3. Install dependencies
4. Run quality checks (black, ruff, mypy, bandit, pytest)
5. Build deployment package
6. Deploy to Azure Functions
7. Verify deployment

**Deployment Status:**

- Check: GitHub → Actions → Latest workflow run
- Expected: ✅ All checks passed, deployment successful

**Rollback (if deployment fails):**

```bash
# View recent deployments
az functionapp deployment list \
  --name ioe-function \
  --resource-group rg-ioe-prod

# Rollback to previous deployment
az functionapp deployment source sync \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --deployment-id <previous-deployment-id>
```

### 5.5 Verify Functions Registered

**After deployment, verify all Device Activation functions are registered:**

```bash
# List all functions in Function App
az functionapp function list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[].{Name:name, TriggerType:config.bindings[0].type}" -o table

# Expected output (Device Activation functions):
# Name                                          TriggerType
# --------------------------------------------  -------------
# device_activation_file_processor              blobTrigger
# device_activation_scheduler                   timerTrigger
# device_activation_campaign_closure            timerTrigger
# operations_device_activation_file_processor   blobTrigger
```

**Check Function App Logs:**

```bash
# Tail logs to see function registration messages
az functionapp log tail \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  | grep "Device Activation"

# Expected output:
# ✅ Successfully registered Device Activation File Processor blueprint
# ✅ Successfully registered Device Activation Scheduler blueprint
# ✅ Successfully registered Operations Device Activation File Processor blueprint
```

---

## 6. Blob Storage Configuration

### 6.1 Create Containers

**⚠️ WARNING: Dual Blob Processors Active**

Both processors are registered:
1. **operations_device_activation_file_processor** (PRIMARY) - `fs-ops/landing/`
2. **device_activation_file_processor** (LEGACY) - `fs-device-activation/landing/` (backup only)

**Risk:** Duplicate processing if files uploaded to wrong container. Always use PRIMARY processor (`fs-ops`).

---

**Required containers for Device Activation:**

1. **fs-ops** (PRIMARY - Operations campaigns: Medicaid, DTC/MA)
   - Folders: `landing/`, `processed/`, `error/`
   - **Hardcoded Campaign IDs:**
     - **Medicaid:** `0F69659B-491B-40E2-88C3-ABC7D87385B2`
     - **DTC/MA:** `BA865458-60F9-4EBB-9FB5-D195B532CF5A`
   - **Filename Patterns:**
     - `MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv`
     - `MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv`

2. **fs-device-activation** (LEGACY - Generic Device Activation files)
   - Folders: `landing/`, `processed/`, `error/`
   - **Status:** LEGACY - Use `fs-ops` instead
   - **Filename Pattern:** `MedicalGuardian_DeviceActivation_*.csv`

**Azure CLI Commands:**

```bash
# Create fs-device-activation container
az storage container create \
  --name fs-device-activation \
  --account-name stioefstorage \
  --auth-mode login

# Create subdirectories (virtual folders)
az storage blob directory create \
  --container-name fs-device-activation \
  --directory-path landing \
  --account-name stioefstorage

az storage blob directory create \
  --container-name fs-device-activation \
  --directory-path processed \
  --account-name stioefstorage

az storage blob directory create \
  --container-name fs-device-activation \
  --directory-path error \
  --account-name stioefstorage

# Create fs-ops container
az storage container create \
  --name fs-ops \
  --account-name stioefstorage \
  --auth-mode login

# Create subdirectories
az storage blob directory create \
  --container-name fs-ops \
  --directory-path landing \
  --account-name stioefstorage

az storage blob directory create \
  --container-name fs-ops \
  --directory-path processed \
  --account-name stioefstorage

az storage blob directory create \
  --container-name fs-ops \
  --directory-path error \
  --account-name stioefstorage
```

**Verify Containers Created:**

```bash
# List containers
az storage container list \
  --account-name stioefstorage \
  --auth-mode login \
  --query "[?name=='fs-device-activation' || name=='fs-ops'].{Name:name, PublicAccess:properties.publicAccess}" -o table

# Expected output:
# Name                   PublicAccess
# ---------------------  -------------
# fs-device-activation   None
# fs-ops                 None
```

### 6.2 Configure Blob Triggers

**Blob triggers are configured in function code:**

**File 1:** `functions/device_activation_file_processor.py`

```python
@device_activation_file_processor_bp.blob_trigger(
    arg_name="myblob",
    path="fs-device-activation/landing/{name}",  # Watch landing/ folder
    connection="AzureWebJobsStorage"
)
def device_activation_file_processor(myblob: func.InputStream) -> None:
    # Triggers when CSV uploaded to fs-device-activation/landing/
    ...
```

**File 2:** `functions/operations_device_activation_file_processor.py`

```python
@operations_device_activation_file_processor_bp.blob_trigger(
    arg_name="myblob",
    path="fs-ops/landing/{name}",  # Watch landing/ folder
    connection="AzureWebJobsStorage"
)
def operations_device_activation_file_processor(myblob: func.InputStream) -> None:
    # Triggers when CSV uploaded to fs-ops/landing/
    ...
```

**No additional configuration needed** - triggers activate automatically after deployment.

### 6.3 Set Blob Retention Policy

**Configure lifecycle management to auto-delete old blobs:**

```json
{
  "rules": [
    {
      "enabled": true,
      "name": "delete-old-processed-files",
      "type": "Lifecycle",
      "definition": {
        "actions": {
          "baseBlob": {
            "delete": {
              "daysAfterModificationGreaterThan": 90
            }
          }
        },
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": [
            "fs-device-activation/processed/",
            "fs-device-activation/error/",
            "fs-ops/processed/",
            "fs-ops/error/"
          ]
        }
      }
    }
  ]
}
```

**Apply Lifecycle Policy:**

```bash
# Save JSON above to file: lifecycle-policy.json

# Apply policy
az storage account management-policy create \
  --account-name stioefstorage \
  --policy @lifecycle-policy.json \
  --resource-group rg-ioe-prod
```

---

## 7. Key Vault Configuration

### 7.1 Required Secrets

**Device Activation requires 3 Key Vault secrets:**

| Secret Name | Purpose | Format |
|-------------|---------|--------|
| `SqlConnectionStringIOE` | Azure SQL connection string | Server=tcp:...;Database=engage360;... |
| `BlandAIkey` | Bland AI API key (authorization header) | sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx |
| `Blandaitwilio` | Bland AI encrypted_key header | your-twilio-encryption-key |

### 7.2 Set/Update Secrets

**SQL Connection String:**

```bash
# Format:
# Server=tcp:<server>.database.windows.net,1433;Database=engage360;User ID=<user>;Password=<password>;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;

# Set secret
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --value "Server=tcp:sql-ioe-prod.database.windows.net,1433;Database=engage360;User ID=ioe_user;Password=<strong-password>;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;"
```

**Bland AI API Key:**

```bash
# Obtain from Bland AI dashboard: https://app.bland.ai/settings/api-keys
# Format: sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Set secret
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name BlandAIkey \
  --value "sk_your_bland_ai_api_key_here"
```

**Bland AI Twilio Encryption Key:**

```bash
# Obtain from Bland AI dashboard: https://app.bland.ai/settings/integrations
# This is used for encrypted_key header (3-header authentication)

# Set secret
az keyvault secret set \
  --vault-name kv-ioe-prod \
  --name Blandaitwilio \
  --value "your_twilio_encryption_key_here"
```

### 7.3 Verify Secrets

**List all secrets in Key Vault:**

```bash
az keyvault secret list \
  --vault-name kv-ioe-prod \
  --query "[].{Name:name, Enabled:attributes.enabled}" -o table

# Expected output:
# Name                        Enabled
# --------------------------  --------
# SqlConnectionStringIOE      True
# BlandAIkey                  True
# Blandaitwilio               True
```

**Test Secret Retrieval:**

```bash
# Retrieve SQL connection string (masked)
az keyvault secret show \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --query "value" -o tsv | sed 's/Password=[^;]*/Password=***MASKED***/'

# Expected output (with password masked):
# Server=tcp:sql-ioe-prod.database.windows.net,1433;Database=engage360;User ID=ioe_user;Password=***MASKED***;Encrypt=True;...
```

### 7.4 Grant Function App Access (Managed Identity)

**Already completed in Section 3.2, but verify:**

```bash
# Check Key Vault access policies
az keyvault show \
  --name kv-ioe-prod \
  --query "properties.accessPolicies[?objectId=='<function-app-principal-id>'].permissions.secrets" -o table

# Expected output:
# Secrets
# ----------
# ['get', 'list']
```

**If access missing:**

```bash
# Get Function App Principal ID
PRINCIPAL_ID=$(az functionapp identity show \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query principalId -o tsv)

# Grant access
az keyvault set-policy \
  --name kv-ioe-prod \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list
```

---

## 8. Bland AI Configuration

### 8.1 Pathway Configuration

**Pathway:** Conversational script that defines call flow

**Setup Steps:**

1. **Login to Bland AI:** https://app.bland.ai/
2. **Navigate to:** Pathways → Create New Pathway
3. **Pathway Name:** "Device Activation - Medical Guardian"
4. **Configure Conversation Flow:**

   ```
   Introduction:
     "Hello [first_name], this is [agent_name] from Medical Guardian. We're calling to help you activate your [device_name] device."

   Question 1: Device Activation Status
     "Have you already activated your device?"
     - Yes → "Great! Is it working properly?" → Mark INTERESTED → End
     - No → Proceed to Question 2

   Question 2: Activation Assistance
     "Would you like help activating your device now?"
     - Yes → "Let me transfer you to our activation specialist." → Mark INTERESTED → Transfer
     - No → Proceed to Question 3

   Question 3: Callback Request
     "Would you like us to call you back at a better time?"
     - Yes → "What time works best for you?" → Mark CALL_BACK_SCHEDULED → End
     - No → "Okay, feel free to call us at 1-800-XXX-XXXX if you need help." → Mark NOT_INTERESTED → End

   Opt-Out Handling:
     If member says "do not call" or "remove from list":
       → Mark DO_NOT_CONTACT → End call immediately
   ```

5. **Save Pathway** and note the `pathway_id` (e.g., `pathway_abc123`)

### 8.2 Voice Configuration

**Voice:** AI voice used for calls

**Setup Steps:**

1. **Navigate to:** Bland AI → Voices → Browse Voices
2. **Select Voice:** Choose professional, clear voice (e.g., "Sarah - Professional Female")
3. **Test Voice:** Preview with sample script
4. **Note Voice ID:** (e.g., `voice_xyz789`)

### 8.3 Store Configuration in Database

**Device Activation campaign configuration:**

```sql
-- Update campaign_call_configs_enhanced with Bland AI settings
UPDATE engage360.campaign_call_configs_enhanced
SET
    pathway_id = 'pathway_abc123',  -- From Pathway setup
    voice_id = 'voice_xyz789',      -- From Voice setup
    bland_parameters_global = '{
        "record": true,
        "wait_for_greeting": true,
        "voicemail_message": "Hello, this is Medical Guardian calling about your device activation. Please call us back at 1-800-XXX-XXXX.",
        "max_duration": 600,
        "answered_by_enabled": true,
        "temperature": 0.7,
        "pronunciation_guide": [
            {"word": "Medical Guardian", "pronunciation": "med-ih-kul GAR-dee-un"}
        ],
        "transfer_phone_number": "+18005551234",
        "webhook": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook"
    }',
    config_status = 'active',
    updated_at = SYSDATETIMEOFFSET()
WHERE campaign_id = (
    SELECT campaign_id
    FROM engage360.campaigns_enhanced
    WHERE name = 'Device Activation - 2025'
);
```

**Verify Configuration:**

```sql
-- Check Bland AI configuration
SELECT
    c.name AS campaign_name,
    cc.pathway_id,
    cc.voice_id,
    cc.bland_parameters_global,
    cc.config_status
FROM engage360.campaign_call_configs_enhanced cc
INNER JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE c.name LIKE '%Device Activation%';
```

### 8.4 Configure Webhook URL

**Webhook:** Bland AI sends call results to this endpoint

**Setup Steps:**

1. **Navigate to:** Bland AI → Settings → Webhooks
2. **Webhook URL:** `https://ioe-function.azurewebsites.net/api/bland_ai_webhook`
3. **Events:** Check all events (call.completed, call.failed, etc.)
4. **Authentication:** None (webhook validates via call_id lookup)
5. **Test Webhook:**

```bash
# Send test webhook payload
curl -X POST https://ioe-function.azurewebsites.net/api/bland_ai_webhook \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "test-call-123",
    "to": "+15551234567",
    "from": "+15559876543",
    "status": "completed",
    "answered_by": "human",
    "call_length": 120,
    "recording_url": "https://...",
    "summary": "Member activated device successfully.",
    "concatenated_transcript": "Agent: Hello... Member: Yes, I activated it.",
    "metadata": {
      "member_id": "test-member-id",
      "enrollment_id": "test-enrollment-id",
      "campaign_id": "test-campaign-id",
      "batch_id": "test-batch-id",
      "attempt_id": "test-attempt-id"
    }
  }'

# Expected response: 200 OK (or 400 if duplicate)
```

### 8.5 Test Bland AI Integration

**End-to-end test:**

1. Upload test CSV to `fs-device-activation/landing/`
2. Wait for file processor to run (blob trigger)
3. Wait for scheduler to run (15-minute timer)
4. Check Application Insights for batch submission logs
5. Wait for Bland AI to make test call
6. Verify webhook received and processed

**Monitor logs:**

```bash
# Watch for batch submission
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Batch submitted' | top 10 by timestamp desc" \
  --offset 1h

# Watch for webhook processing
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Webhook received' | top 10 by timestamp desc" \
  --offset 1h
```

---

## 9. Post-Deployment Validation

### 9.1 Validate Function Registration

**Check all Device Activation functions are active:**

```bash
# List functions
az functionapp function list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?contains(name, 'device_activation')].{Name:name, Status:config.disabled}" -o table

# Expected output:
# Name                                          Status
# --------------------------------------------  --------
# device_activation_file_processor              False
# device_activation_scheduler                   False
# device_activation_campaign_closure            False
# operations_device_activation_file_processor   False
```

**Test HTTP trigger (device_activation_scheduler):**

```bash
# Invoke scheduler manually
curl -X POST https://ioe-function.azurewebsites.net/api/device_activation_scheduler?code=<function-key>

# Expected response:
# {
#   "status": "success",
#   "message": "Device Activation batch creation completed",
#   "batches_created": 2,
#   "calls_submitted": 150
# }
```

### 9.2 Validate Database Connectivity

**Test database connection from Function App:**

```bash
# Trigger scheduler to run eligibility query
curl -X POST https://ioe-function.azurewebsites.net/api/device_activation_scheduler?code=<function-key>

# Check Application Insights for database query logs
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Eligibility query' | top 5 by timestamp desc" \
  --offset 1h
```

**Expected log output:**

```
✅ [ELIGIBILITY] Database connection established
✅ [ELIGIBILITY] Eligibility query executed successfully
✅ [ELIGIBILITY] Found 125 eligible members
```

### 9.3 Validate Blob Trigger

**Test file processing:**

```bash
# Upload test CSV
az storage blob upload \
  --account-name stioefstorage \
  --container-name fs-device-activation \
  --file test_device_activation.csv \
  --name landing/MedicalGuardian_DeviceActivation_20251224_Delta.csv \
  --auth-mode login

# Wait 30 seconds, then check if blob moved to processed/
az storage blob list \
  --account-name stioefstorage \
  --container-name fs-device-activation \
  --prefix processed/ \
  --auth-mode login \
  --query "[?contains(name, '20251224')].{Name:name, Size:properties.contentLength}" -o table
```

**Expected output:**

```
Name                                                               Size
-----------------------------------------------------------------  ------
processed/MedicalGuardian_DeviceActivation_20251224_Delta.csv      15234
```

### 9.4 Validate Timer Trigger

**Check scheduler runs every 15 minutes:**

```bash
# Check last 3 scheduler invocations
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "requests | where name contains 'device_activation_scheduler' | top 3 by timestamp desc | project timestamp, duration, resultCode" \
  --offset 1h

# Expected output (every 15 minutes):
# timestamp                  | duration | resultCode
# ---------------------------|----------|------------
# 2025-12-24T14:15:00.000Z   | 8500     | 200
# 2025-12-24T14:00:00.000Z   | 9200     | 200
# 2025-12-24T13:45:00.000Z   | 7800     | 200
```

### 9.5 Validate Bland AI Integration

**Check batch submission logs:**

```bash
# Query batch submission events
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Batch submitted to Bland AI' | top 5 by timestamp desc" \
  --offset 1h
```

**Expected log output:**

```
✅ [BATCH-ORCHESTRATOR] Batch submitted to Bland AI
   - batch_id: abc-123-def-456
   - vendor_batch_id: bland_batch_789
   - members_count: 100
   - campaign_id: xyz-789-uvw-012
```

**Check webhook processing logs:**

```bash
# Query webhook events
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'Webhook received' | top 5 by timestamp desc" \
  --offset 1h
```

**Expected log output:**

```
✅ [WEBHOOK] Webhook received and processed
   - call_id: call_abc123
   - disposition: INTERESTED
   - member_id: member-456
   - enrollment_id: enrollment-789
```

### 9.6 Validate Database Updates

**Check staging table populated:**

```sql
-- Check most recent file processing
SELECT TOP 5
    file_id,
    processing_status,
    validation_status,
    COUNT(*) as row_count,
    MAX(created_at) as latest_timestamp
FROM engage360_stg.stg_device_activation_delta
GROUP BY file_id, processing_status, validation_status
ORDER BY MAX(created_at) DESC;

-- Expected result:
-- file_id                              | processing_status | validation_status | row_count | latest_timestamp
-- -------------------------------------|-------------------|-------------------|-----------|--------------------
-- file-2025-12-24-abc123               | Processed         | Valid             | 150       | 2025-12-24 14:30:00
```

**Check enrollments created:**

```sql
-- Check most recent enrollments
SELECT TOP 5
    enrollment_id,
    member_id,
    campaign_id,
    current_status,
    activation_start_date,
    created_at
FROM engage360.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    SELECT campaign_id
    FROM engage360.campaigns_enhanced
    WHERE name LIKE '%Device Activation%'
)
ORDER BY created_at DESC;

-- Expected result: New enrollments with status 'ENROLLED'
```

**Check batches created:**

```sql
-- Check most recent batches
SELECT TOP 5
    batch_id,
    campaign_id,
    batch_status,
    vendor_batch_id,
    batch_size,
    created_at
FROM engage360.outreach_batches
ORDER BY created_at DESC;

-- Expected result: Batches with status 'Submitted' and vendor_batch_id populated
```

### 9.7 Validate Campaign Closure (90-Day Auto-Unenroll)

**Test HTTP trigger (device_activation_campaign_closure):**

```bash
# Invoke campaign closure manually
curl -X GET https://ioe-function.azurewebsites.net/api/device_activation_campaign_closure?code=<function-key>

# Expected response:
# {
#   "success": true,
#   "request_id": "da-closure-http-20260122-143000",
#   "timestamp": "2026-01-22T14:30:00Z",
#   "result": {
#     "enrollments_closed": 15,
#     "campaigns_affected": ["Device Activation - Medicaid", "Device Activation - DTC/MA"],
#     "members_unenrolled": 15,
#     "execution_duration_seconds": 2.45
#   }
# }
```

**Verify timer trigger (hourly schedule):**

```bash
# Check last 3 campaign closure invocations
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "requests | where name contains 'device_activation_campaign_closure' | top 3 by timestamp desc | project timestamp, duration, resultCode" \
  --offset 3h

# Expected output (every hour at :00 minutes):
# timestamp                  | duration | resultCode
# ---------------------------|----------|------------
# 2026-01-22T14:00:00.000Z   | 2450     | 200
# 2026-01-22T13:00:00.000Z   | 2100     | 200
# 2026-01-22T12:00:00.000Z   | 2800     | 200
```

**Check campaign closure logs:**

```bash
# Query campaign closure events
az monitor app-insights query \
  --app ioe-function-appinsights \
  --analytics-query "traces | where message contains 'DA-CLOSURE' | top 5 by timestamp desc" \
  --offset 3h
```

**Expected log output:**

```
✅ [DA-CLOSURE] Device Activation Campaign Closure Scheduler TRIGGERED
✅ [DA-CLOSURE] Distributed lock acquired successfully
✅ [DA-CLOSURE] Found 15 enrollments to close
✅ [DA-CLOSURE] Successfully unenrolled 15 members
✅ [DA-CLOSURE] Campaigns affected: ['Device Activation - Medicaid', 'Device Activation - DTC/MA']
```

**Verify database updates (members unenrolled):**

```sql
-- Check recently unenrolled members (campaign closure)
SELECT TOP 10
    mce.enrollment_id,
    mce.member_id,
    c.name as campaign_name,
    mce.enrollment_status,
    mce.campaign_end_date,
    mce.updated_at,
    meh.reason
FROM engage360.member_campaign_enrollments_enhanced mce
JOIN engage360.campaigns_enhanced c ON mce.campaign_id = c.campaign_id
LEFT JOIN engage360.member_enrollment_status_history meh ON mce.enrollment_id = meh.enrollment_id
WHERE mce.enrollment_status = 'UNENROLLED'
  AND c.name LIKE '%Device Activation%'
  AND meh.reason = '90-day campaign window expired'
ORDER BY mce.updated_at DESC;

-- Expected result: Members with status 'UNENROLLED' and reason '90-day campaign window expired'
```

---

## 10. Rollback Procedures

### 10.1 Function App Rollback

**Scenario:** New deployment causes errors

**Rollback Steps:**

```bash
# Step 1: List recent deployments
az functionapp deployment list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[].{ID:id, Author:author, Status:status, DeployedTime:received_time}" -o table

# Step 2: Identify previous stable deployment ID
PREVIOUS_DEPLOYMENT_ID="<deployment-id-from-step-1>"

# Step 3: Rollback to previous deployment
az functionapp deployment source sync \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --deployment-id $PREVIOUS_DEPLOYMENT_ID

# Step 4: Restart Function App
az functionapp restart \
  --name ioe-function \
  --resource-group rg-ioe-prod

# Step 5: Verify rollback
az functionapp log tail \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  | grep "Successfully registered"
```

### 10.2 Database Schema Rollback

**Scenario:** Schema migration causes errors

**Rollback Steps:**

```sql
-- Step 1: Restore from backup (if major schema change)
RESTORE DATABASE [engage360]
FROM DISK = N'/var/opt/mssql/backup/engage360_pre_deployment_2025-12-24.bak'
WITH REPLACE, RECOVERY;

-- Step 2: OR manually revert specific changes
-- Example: Revert column rename
EXEC sp_rename
    'engage360_stg.stg_device_activation_delta.powersaver_mode',
    'battery_status',
    'COLUMN';

-- Step 3: Verify rollback
SELECT COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME IN ('battery_status', 'powersaver_mode');
```

### 10.3 Configuration Rollback

**Scenario:** New configuration breaks functionality

**Rollback App Settings:**

```bash
# Restore previous app settings from backup JSON
az functionapp config appsettings set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --settings @previous-settings-backup.json

# Or manually reset specific setting
az functionapp config appsettings set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --settings KEY_VAULT_URL=https://kv-ioe-prod-old.vault.azure.net/
```

**Rollback Key Vault Secret:**

```bash
# List secret versions
az keyvault secret list-versions \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --query "[].{Version:id, Enabled:attributes.enabled, Created:attributes.created}" -o table

# Restore previous version
az keyvault secret set-version \
  --vault-name kv-ioe-prod \
  --name SqlConnectionStringIOE \
  --version <previous-version-id>
```

### 10.4 Emergency Stop (Kill Switch)

**Scenario:** Critical production issue - need to stop all processing immediately

**Disable All Device Activation Functions:**

```bash
# Disable file processors (stop new CSV processing)
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_file_processor \
  --set config.disabled=true

az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name operations_device_activation_file_processor \
  --set config.disabled=true

# Disable scheduler (stop batch creation)
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_scheduler \
  --set config.disabled=true
```

**Re-enable After Fix:**

```bash
# Re-enable functions
az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_file_processor \
  --set config.disabled=false

az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name operations_device_activation_file_processor \
  --set config.disabled=false

az functionapp function update \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --function-name device_activation_scheduler \
  --set config.disabled=false
```

---

## 11. Monitoring Setup

### 11.1 Application Insights Configuration

**Application Insights is required for production monitoring**

**Verify Application Insights Connected:**

```bash
# Check Application Insights instrumentation key
az functionapp config appsettings list \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --query "[?name=='APPINSIGHTS_INSTRUMENTATIONKEY'].value" -o tsv
```

**If not configured:**

```bash
# Create Application Insights resource
az monitor app-insights component create \
  --app ioe-function-appinsights \
  --location eastus \
  --resource-group rg-ioe-prod \
  --application-type web

# Get instrumentation key
INSTRUMENTATION_KEY=$(az monitor app-insights component show \
  --app ioe-function-appinsights \
  --resource-group rg-ioe-prod \
  --query instrumentationKey -o tsv)

# Configure Function App to use Application Insights
az functionapp config appsettings set \
  --name ioe-function \
  --resource-group rg-ioe-prod \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY=$INSTRUMENTATION_KEY
```

### 11.2 Custom Alerts

**Alert #1: File Processing Failures**

```bash
# Create alert for blob trigger failures
az monitor metrics alert create \
  --name "Device Activation - File Processing Failures" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<subscription-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "count FunctionExecutionCount where FunctionName == 'device_activation_file_processor' and Success == false > 5" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --action-group <action-group-id> \
  --description "Alert when Device Activation file processing fails more than 5 times in 15 minutes"
```

**Alert #2: Scheduler Failures**

```bash
# Create alert for scheduler failures
az monitor metrics alert create \
  --name "Device Activation - Scheduler Failures" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<subscription-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "count FunctionExecutionCount where FunctionName == 'device_activation_scheduler' and Success == false > 3" \
  --window-size 1h \
  --evaluation-frequency 15m \
  --action-group <action-group-id> \
  --description "Alert when Device Activation scheduler fails more than 3 times in 1 hour"
```

**Alert #3: Webhook Processing Delays**

```bash
# Create alert for webhook delays
az monitor metrics alert create \
  --name "Device Activation - Webhook Delays" \
  --resource-group rg-ioe-prod \
  --scopes /subscriptions/<subscription-id>/resourceGroups/rg-ioe-prod/providers/Microsoft.Web/sites/ioe-function \
  --condition "avg FunctionExecutionUnits where FunctionName == 'bland_ai_webhook' > 10000" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --action-group <action-group-id> \
  --description "Alert when webhook processing takes longer than expected"
```

### 11.3 Dashboard Creation

**Create custom Application Insights dashboard:**

1. **Navigate to:** Azure Portal → Application Insights → ioe-function-appinsights
2. **Click:** Dashboards → New Dashboard
3. **Add Tiles:**

   - **Tile 1:** Failed Requests (device_activation_file_processor)
   - **Tile 2:** Function Execution Count (device_activation_scheduler)
   - **Tile 3:** Average Response Time (bland_ai_webhook)
   - **Tile 4:** Exceptions (all Device Activation functions)
   - **Tile 5:** Custom Query - Eligible Members Count
     ```kusto
     traces
     | where message contains "Found eligible members"
     | extend member_count = extract("Found ([0-9]+) eligible members", 1, message)
     | summarize avg(todouble(member_count)) by bin(timestamp, 1h)
     | render timechart
     ```

4. **Save Dashboard** as "Device Activation - Production Monitoring"

### 11.4 Log Analytics Queries

**Useful queries for monitoring:**

**Query 1: Recent File Processing Activity**

```kusto
traces
| where message contains "File processing"
| where timestamp > ago(24h)
| project timestamp, severityLevel, message
| order by timestamp desc
| take 50
```

**Query 2: Batch Submission Summary**

```kusto
traces
| where message contains "Batch submitted to Bland AI"
| where timestamp > ago(24h)
| summarize batches=count(), total_calls=sum(toint(extract("members_count: ([0-9]+)", 1, message))) by bin(timestamp, 1h)
| render columnchart
```

**Query 3: Webhook Disposition Distribution**

```kusto
traces
| where message contains "disposition:"
| where timestamp > ago(24h)
| extend disposition = extract("disposition: ([A-Z_]+)", 1, message)
| summarize count() by disposition
| render piechart
```

---

## 12. Deployment Checklist

### 12.1 Pre-Deployment Checklist

**Code Quality:**
- [ ] All unit tests passing (`pytest af_code/ --verbose`)
- [ ] Code formatted with black (`black --line-length 100 af_code/`)
- [ ] Linting issues resolved (`ruff check af_code/`)
- [ ] Type checking passed (`mypy af_code/`)
- [ ] Security scan clean (`bandit -r af_code/ -ll`)
- [ ] Code reviewed by team member

**Database:**
- [ ] Database backup created (production)
- [ ] SQL migration scripts tested on dev/test databases
- [ ] Schema changes documented
- [ ] Indexes created/updated
- [ ] Performance tested (query execution times)

**Configuration:**
- [ ] Key Vault secrets updated (if needed)
- [ ] Function App settings reviewed
- [ ] Blob storage containers created
- [ ] Bland AI configuration verified (pathway, voice, webhook)

**Documentation:**
- [ ] README.md updated (if needed)
- [ ] CLAUDE.md updated (if patterns changed)
- [ ] Architecture docs updated
- [ ] Deployment guide reviewed

### 12.2 Deployment Checklist

**Function App Deployment:**
- [ ] Login to Azure (`az login`)
- [ ] Set correct subscription (`az account set`)
- [ ] Deploy to Dev environment first
- [ ] Validate Dev deployment (run tests)
- [ ] Deploy to Test environment
- [ ] Validate Test deployment (UAT)
- [ ] Deploy to Production environment
- [ ] Verify function registration (check logs)

**Database Deployment:**
- [ ] Execute staging table creation script
- [ ] Execute schema migration scripts (in order)
- [ ] Create/update indexes
- [ ] Verify table structures (`INFORMATION_SCHEMA` queries)
- [ ] Seed test data (if needed)

**Blob Storage:**
- [ ] Create/verify containers (fs-device-activation, fs-ops)
- [ ] Create/verify folders (landing, processed, error)
- [ ] Configure lifecycle policies
- [ ] Test blob trigger with sample file

**Monitoring:**
- [ ] Verify Application Insights connected
- [ ] Create/update custom alerts
- [ ] Test alert notifications
- [ ] Create/update dashboard
- [ ] Test Log Analytics queries

### 12.3 Post-Deployment Checklist

**Functional Validation:**
- [ ] HTTP trigger test (device_activation_scheduler)
- [ ] Blob trigger test (upload CSV, verify processing)
- [ ] Timer trigger validation (check 15-minute runs)
- [ ] Database connectivity test (eligibility query)
- [ ] Bland AI batch submission test
- [ ] Webhook processing test (send test payload)

**Data Validation:**
- [ ] Staging table populated (check row counts)
- [ ] Enrollments created (check member_campaign_enrollments_enhanced)
- [ ] Batches created (check outreach_batches)
- [ ] Attempts created (check outreach_attempts)
- [ ] Webhooks logged (check bland_call_logs)

**Monitoring Validation:**
- [ ] Application Insights receiving telemetry
- [ ] Custom alerts configured and enabled
- [ ] Dashboard displaying correct data
- [ ] Log Analytics queries returning results

**Documentation:**
- [ ] Deployment notes recorded (date, version, changes)
- [ ] Known issues documented
- [ ] Rollback plan confirmed
- [ ] Team notified of deployment

### 12.4 Sign-Off

**Deployment Approvals:**

- [ ] **Developer:** Code quality verified, tests passed
- [ ] **Database Admin:** Schema changes approved, backups confirmed
- [ ] **DevOps:** Deployment successful, monitoring active
- [ ] **QA:** Functional testing completed, no critical issues
- [ ] **Product Owner:** UAT completed, ready for production use

**Deployment Record:**

```
Deployment Date: _______________
Deployed By: _______________
Environment: _______________
Version/Tag: _______________
Database Schema Version: _______________
Rollback Plan: _______________
Notes: _______________________________________________
```

---

## Related Documentation

**Architecture:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md) - Master architecture document
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md) - Database schema and SQL patterns
- [System Architecture Diagrams](../FLOWS/DEVICE_ACTIVATION_SYSTEM_ARCHITECTURE.md) - Component diagrams

**Testing:**
- [Testing Guide](DEVICE_ACTIVATION_TESTING_GUIDE.md) - Unit, integration, and E2E testing

**Reference:**
- [BusinessCaseID Mapping](../REFERENCE/DEVICE_ACTIVATION_BUSINESSCASEID_MAPPING.md) - BC-DA-001 through BC-DA-008
- [CSV Reference](../../DEVICE_ACTIVATION_CSV_REFERENCE.md) - CSV format and validation

**Troubleshooting:**
- [Troubleshooting Guide](DEVICE_ACTIVATION_TROUBLESHOOTING.md) - Common issues and solutions

---

**Document Version:** 1.0
**Last Updated:** 2025-12-24
**Maintained By:** AI-POD Team - Data Science
**Review Schedule:** Quarterly or after major releases
