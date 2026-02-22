# Azure Configuration Reference: Where Resource Names Come From (Deployed)

**Last Verified:** 2026-02-20
**Python Version:** 3.12 | **Azure Functions Runtime:** v4

---

## Overview

When deployed on Azure, there is **no `local.settings.json`**. All configuration comes from two sources:

| Source | What It Holds | Where to Manage |
|--------|--------------|-----------------|
| **Azure Function App Settings** | Non-secret env vars (`KEY_VAULT_URL`, `DB_SCHEMA`, etc.) | Azure Portal → Function App → Configuration → Application Settings |
| **Azure Key Vault** | Secrets (connection strings, API keys) | Azure Portal → Key Vault → Secrets |

The code reads App Settings via `os.environ.get()` and Key Vault via `ConfigManager.get_config()`.

---

## Resource-by-Resource Reference

### 1. SQL Database Connection

| Field | Value |
|-------|-------|
| **Key Vault secret name** | `SqlConnectionStringIOE` |
| **App Setting controlling secret name** | `DB_CONNECTION_SECRET_NAME` (default: `"SqlConnectionStringIOE"`) |
| **Fallback env var** | `DB_CONNECTION_STRING` (direct string, for local testing only) |
| **Code location** | `af_code/bland_ai_webhook/services/config_manager.py:94` |

```python
# config_manager.py:94
secret_name = self.get_config("DB_CONNECTION_SECRET_NAME", "SqlConnectionStringIOE")
```

**→ Set in:** Azure Portal → Key Vault → Secret named `SqlConnectionStringIOE`

---

### 2. Database Schema Names ⬅ NEW (needs adding to App Settings)

| Field | Value |
|-------|-------|
| **App Setting** | `DB_SCHEMA` (default: `ioe`) |
| **App Setting** | `DB_SCHEMA_STG` (default: `ioe_stg`) |
| **Code location** | `af_code/shared/schema_config.py:16-17` |

```python
# schema_config.py:16-17
IOE_SCHEMA: str = os.environ.get("DB_SCHEMA", "ioe")
IOE_SCHEMA_STG: str = os.environ.get("DB_SCHEMA_STG", "ioe_stg")
```

**→ Set in:** Azure Portal → Function App (`IOE-function`) → Configuration → Application Settings
**NOT in Key Vault** — these are non-secret infrastructure config values.

> **Safe defaults:** The code defaults to `ioe` / `ioe_stg` if the App Settings are absent, so existing deployments continue working until the settings are explicitly added.

---

### 3. Blob Storage Containers

Container paths are **hardcoded** in function decorators — they cannot be changed without a code redeploy.

| Function | Container Path | Code Location |
|----------|---------------|---------------|
| DTC File Processor | `fs-dtc/landing/{name}` | `functions/dtc_file_processor.py:11` |
| Partner File Processor | `fs-partner/landing/{name}` | `functions/partner_file_processor.py:11` |
| Ops Device Activation | `fs-ops/landing/{name}` | `functions/operations_device_activation_file_processor.py:26` |
| Device Activation | `fs-device-activation/landing/{name}` | `functions/device_activation_file_processor.py` |

The **storage account** where these containers live is determined by the `AzureWebJobsStorage` App Setting (auto-managed by Azure when you link a Storage Account).

**→ Set in:** Azure Portal → Function App → Configuration → Application Settings (Azure auto-manages this)

---

### 4. Service Bus Queue

| Field | Value |
|-------|-------|
| **Queue name default** | `IOE-POSTCALL-ANALYSIS` |
| **App Setting to override** | `SERVICE_BUS_QUEUE_NAME` |
| **Key Vault secret (connection string)** | `IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT` |
| **App Setting controlling secret name** | `SERVICE_BUS_SECRET_NAME` (default: `"IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT"`) |
| **Code location (queue name)** | `af_code/bland_ai_webhook/services/service_bus_handler.py:29-31` |
| **Code location (secret name)** | `af_code/bland_ai_webhook/services/config_manager.py:113-115` |

```python
# service_bus_handler.py:29-31
self.queue_name = self.config_manager.get_config(
    "SERVICE_BUS_QUEUE_NAME", "IOE-POSTCALL-ANALYSIS"
)
```

**→ Queue name set in:** Azure Portal → Function App → Configuration (via `SERVICE_BUS_QUEUE_NAME` App Setting)
**→ Connection string set in:** Azure Portal → Key Vault → Secret `IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT`

---

### 5. Key Vault URL

| Field | Value |
|-------|-------|
| **App Setting** | `KEY_VAULT_URL` (required — no default) |
| **Code location** | `af_code/bland_ai_webhook/services/config_manager.py:22` |

```python
# config_manager.py:22
self._key_vault_url = os.environ.get("KEY_VAULT_URL")
```

**→ Set in:** Azure Portal → Function App → Configuration → Application Settings
Value: `https://<your-keyvault-name>.vault.azure.net/`

---

### 6. Bland AI Keys

| Secret Name | Retrieved Via |
|-------------|--------------|
| `BlandAIkey` | `config_manager.get_config("BlandAIkey")` |
| `Blandaitwilio` | `config_manager.get_config("Blandaitwilio")` |

**→ Set in:** Azure Portal → Key Vault → Secrets

---

### 7. Timer Schedules (Hardcoded — Redeploy to Change)

All timer schedules are **hardcoded** as CRON expressions in function decorators.

| Function | Schedule | Description | Code Location |
|----------|----------|-------------|---------------|
| DTC Intro Call Scheduler | `0 */10 * * * *` | Every 10 minutes | `functions/dtc_intro_call_scheduler.py:16` |
| DTC Wellness Check Scheduler | `0 */10 * * * *` | Every 10 minutes | `functions/dtc_wellness_check_scheduler.py:24` |
| Device Activation Scheduler | `0 */15 * * * *` | Every 15 minutes | `functions/device_activation_scheduler.py:45` |
| Partner Campaign Scheduler | `5 */30 * * * *` | Every 30 min at :05 (staggered) | `functions/partner_campaign_scheduler.py:35` |
| Batch Completion Reconciler | `0 */30 * * * *` | Every 30 min at :00 | `functions/batch_completion_reconciler.py:24` |

---

## Complete App Settings List

All App Settings for Azure Portal → Function App → Configuration:

| App Setting Name | Example Value | Required? | Notes |
|------------------|---------------|-----------|-------|
| `KEY_VAULT_URL` | `https://<keyvault>.vault.azure.net/` | **Required** | No default |
| `AzureWebJobsStorage` | Storage account connection string | **Required** | Azure auto-sets on link |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | **Required** | Azure auto-sets |
| `DB_CONNECTION_SECRET_NAME` | `SqlConnectionStringIOE` | Optional | Default: `SqlConnectionStringIOE` |
| `SERVICE_BUS_QUEUE_NAME` | `IOE-POSTCALL-ANALYSIS` | Optional | Default: `IOE-POSTCALL-ANALYSIS` |
| `SERVICE_BUS_SECRET_NAME` | `IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT` | Optional | Default: same |
| `SERVICE_BUS_MAX_RETRIES` | `3` | Optional | Default: `3` |
| `SERVICE_BUS_RETRY_DELAY_SECONDS` | `2` | Optional | Default: `2` |
| `SERVICE_BUS_MESSAGE_TTL_HOURS` | `24` | Optional | Default: `24` |
| `TIMEZONE` | `UTC` | Optional | Default: `UTC` |
| **`DB_SCHEMA`** | **`ioe`** | **NEW — Add this** | Default: `ioe` |
| **`DB_SCHEMA_STG`** | **`ioe_stg`** | **NEW — Add this** | Default: `ioe_stg` |

---

## Complete Key Vault Secrets List

| Secret Name | What It Contains |
|-------------|-----------------|
| `SqlConnectionStringIOE` | SQL Server connection string |
| `BlandAIkey` | Bland AI API key |
| `Blandaitwilio` | Twilio encryption key |
| `IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT` | Azure Service Bus connection string |

> **Note:** Key Vault secret names use hyphens. `ConfigManager` automatically converts underscores to hyphens when looking up Key Vault secrets (see `config_manager.py:64`: `key.replace("_", "-")`).

---

## How to Add DB_SCHEMA / DB_SCHEMA_STG to Azure

### Option A: Azure Portal (Recommended)

1. Azure Portal → **Function Apps** → `IOE-function`
2. **Settings** → **Configuration** → **Application Settings** → `+ New application setting`
3. Add `DB_SCHEMA` = `ioe` → **OK**
4. Add `DB_SCHEMA_STG` = `ioe_stg` → **OK**
5. Click **Save** → Function App restarts automatically

### Option B: Azure CLI

```bash
az functionapp config appsettings set \
  --name IOE-function \
  --resource-group <your-resource-group> \
  --settings DB_SCHEMA=ioe DB_SCHEMA_STG=ioe_stg
```

### Option C: Local Development (`local.settings.json`)

```json
{
  "IsEncrypted": false,
  "Values": {
    "DB_SCHEMA": "ioe",
    "DB_SCHEMA_STG": "ioe_stg",
    "KEY_VAULT_URL": "https://...",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true"
  }
}
```

---

## Key Source Files

| Topic | File | Lines |
|-------|------|-------|
| All env var reads | `af_code/bland_ai_webhook/services/config_manager.py` | 20–130 |
| Schema config | `af_code/shared/schema_config.py` | 16–17 |
| Service Bus config | `af_code/bland_ai_webhook/services/service_bus_handler.py` | 26–38 |
| DTC blob trigger | `functions/dtc_file_processor.py` | 11 |
| Partner blob trigger | `functions/partner_file_processor.py` | 10–13 |
| Ops blob trigger | `functions/operations_device_activation_file_processor.py` | 25–26 |
| DTC Intro Call timer | `functions/dtc_intro_call_scheduler.py` | 16 |
| DTC Wellness timer | `functions/dtc_wellness_check_scheduler.py` | 24 |
| Device Activation timer | `functions/device_activation_scheduler.py` | 45 |
| Partner Campaign timer | `functions/partner_campaign_scheduler.py` | 35 |
| Batch Reconciler timer | `functions/batch_completion_reconciler.py` | 24 |

---

## Summary

| Config Category | Where It Lives | Can Change Without Redeploy? |
|----------------|---------------|------------------------------|
| Blob container names | Hardcoded in function decorators | No — requires code change + redeploy |
| Timer schedules | Hardcoded in function decorators | No — requires code change + redeploy |
| Secrets (connection strings, API keys) | Azure Key Vault | Yes — update secret value |
| Non-secret config (schema names, queue names, timezone) | Azure Function App Settings | Yes — update App Setting + restart |
| `DB_SCHEMA` / `DB_SCHEMA_STG` | Azure Function App Settings | Yes — **add these now** |
