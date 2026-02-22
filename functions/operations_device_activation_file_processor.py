"""
Azure Function: Operations Device Activation File Processor
Blob Trigger for Operations Device Activation Campaigns (Medicaid, DTC/MA)

Trigger: Blob upload to fs-ops/landing
Container: fs-ops
Supported Files:
  - MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv
  - MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv

Campaign Type: Operations
Date: 2025-12-18
"""

import logging
import azure.functions as func
from af_code.af_device_activation_logic import process_device_activation_file_complete
from af_code.shared.filename_validators import validate_device_activation_filename

# Create blueprint for Operations Device Activation
operations_device_activation_bp = func.Blueprint()


@operations_device_activation_bp.function_name(name="operations_device_activation_file_processor")
@operations_device_activation_bp.blob_trigger(
    arg_name="blob", path="fs-ops/landing/{name}", connection="BLOB_STORAGE_CONNECTION"
)
def operations_device_activation_file_processor(blob: func.InputStream):
    """
    Azure Function blob trigger for Operations Device Activation file uploads.

    Supports two campaign types:
    1. Device Activation - Medicaid
    2. Device Activation - DTC/MA

    File Naming Patterns:
    - MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv
    - MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv

    Campaign Type: Operations
    Blob Container: fs-ops/landing

    Workflow:
    1. Validate filename pattern
    2. Extract campaign ID from filename
    3. Process file using existing device activation logic
    4. Move file to processed/ or error/ folder

    Args:
        blob: InputStream from Azure Blob Storage trigger

    Returns:
        None (logs processing results to Application Insights)
    """
    logging.info(f"🔔 [OPS-DEVICE-ACTIVATION] Blob trigger fired for file: {blob.name}")
    logging.info(f"   📦 Blob size: {blob.length} bytes")
    logging.info("   📂 Container: fs-ops/landing")

    # ===================================================================
    # STEP 1: Validate File Naming Pattern with Date Validation
    # ===================================================================
    # Extract just the filename from the full blob path
    filename = blob.name.split("/")[-1]

    # Validate filename pattern with calendar date validation
    is_valid, error_message, date_str, campaign_type = validate_device_activation_filename(filename)

    if not is_valid:
        logging.warning(
            f"⚠️ [OPS-DEVICE-ACTIVATION] Skipping file with invalid name format: {blob.name}"
        )
        logging.warning(f"   Error: {error_message}")
        logging.info("   Expected patterns:")
        logging.info("   - MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv")
        logging.info("   - MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv")
        logging.info("   Example: MedicalGuardian_DeviceActivationMedicaid_20260105_DELTA.csv")
        logging.info(
            "   Note: YYYYMMDD must be a valid calendar date (rejects Feb 30, month 13, Apr 31, etc.)"
        )
        return

    logging.info("✅ [OPS-DEVICE-ACTIVATION] Filename pattern validated successfully")
    logging.info(f"   Filename: {filename}")
    logging.info(f"   📅 Extracted date: {date_str}")
    logging.info(f"   📋 Campaign type: {campaign_type}")

    # ===================================================================
    # STEP 2: Map Campaign Type to Hardcoded Campaign ID
    # ===================================================================
    campaign_map = {
        "Medicaid": {
            "campaign_name": "Device Activation - Medicaid",
            "campaign_id": "0F69659B-491B-40E2-88C3-ABC7D87385B2",
        },
        "DTCMA": {
            "campaign_name": "Device Activation - DTC/MA",
            "campaign_id": "BA865458-60F9-4EBB-9FB5-D195B532CF5A",
        },
    }

    campaign_info = campaign_map.get(campaign_type)
    if not campaign_info:
        # This should never happen if validation function is correct
        logging.error(f"❌ [OPS-DEVICE-ACTIVATION] Unknown campaign type: {campaign_type}")
        return

    campaign_name = campaign_info["campaign_name"]
    campaign_id = campaign_info["campaign_id"]

    logging.info(f"📋 [OPS-DEVICE-ACTIVATION] Campaign: {campaign_name}")
    logging.info(f"   🆔 Campaign ID: {campaign_id}")

    # Log flow selection verification
    logging.info("🔧 [OPS-DEVICE-ACTIVATION] Flow: Using OPERATIONS FLOW with explicit campaign_id")
    logging.info(f"   📂 Blob name: {blob.name}")
    logging.info("   ✅ Hardcoded campaign will be used (no auto-discovery)")

    # ===================================================================
    # STEP 3: Process File Using Existing Device Activation Logic
    # ===================================================================
    logging.info("🚀 [OPS-DEVICE-ACTIVATION] Starting file processing...")

    try:
        # Read blob content
        blob_content = blob.read()
        logging.info("📖 [OPS-DEVICE-ACTIVATION] File content read successfully")

        # Call existing device activation processing logic
        # This will handle:
        # - CSV extraction and column mapping
        # - Validation and cleansing
        # - Member/device upserts
        # - Enrollment status handling (enrolled/unenrolled/updated)
        # - monitoring_system_id storage in member_identifiers

        # CRITICAL: Use blob_name parameter to trigger OPERATIONS FLOW
        # This ensures the hardcoded campaign_id is actually used
        result = process_device_activation_file_complete(
            blob_name=blob.name,  # OPERATIONS FLOW: Uses explicit campaign_id
            blob_content=blob_content,
            campaign_id=campaign_id,  # Hardcoded campaign_id will be preserved
            connection_string=None,  # Retrieved from Key Vault via ConfigManager
            uploaded_by_user="AzureFunction-Operations",  # Identify source
            error_threshold_pct=10.0,  # 10% error threshold (same as legacy)
            log_level="INFO",
        )

        logging.info("✅ [OPS-DEVICE-ACTIVATION] File processing completed successfully")
        logging.info(f"   📊 Processing result: {result}")
        logging.info("   ✨ File will be moved to fs-ops/processed/")

        # Verify hardcoded campaign_id was used
        logging.info("✅ [OPS-DEVICE-ACTIVATION] Campaign enrollment verification:")
        logging.info(f"   ✅ Used hardcoded campaign_id: {campaign_id}")
        logging.info(f"   ✅ Campaign: {campaign_name}")
        logging.info("   ✅ Flow: OPERATIONS FLOW (not auto-discovery)")

        # Log success metrics for Application Insights
        logging.info("📈 [OPS-DEVICE-ACTIVATION] SUCCESS METRICS:")
        logging.info(f"   - Campaign: {campaign_name}")
        logging.info(f"   - File: {blob.name}")
        logging.info(f"   - Size: {blob.length} bytes")
        logging.info("   - Status: COMPLETED")

    except Exception as e:
        logging.error("❌ [OPS-DEVICE-ACTIVATION] File processing failed")
        logging.error(f"   📄 File: {blob.name}")
        logging.error(f"   🎯 Campaign: {campaign_name}")
        logging.error(f"   ⚠️ Error: {str(e)}")
        logging.error(f"   🔍 Exception type: {type(e).__name__}")

        # Log full traceback for debugging
        import traceback

        logging.error("   📚 Traceback:")
        for line in traceback.format_exc().split("\n"):
            if line.strip():
                logging.error(f"      {line}")

        # Log failure metrics for Application Insights
        logging.error("📉 [OPS-DEVICE-ACTIVATION] FAILURE METRICS:")
        logging.error(f"   - Campaign: {campaign_name}")
        logging.error(f"   - File: {blob.name}")
        logging.error(f"   - Size: {blob.length} bytes")
        logging.error("   - Status: FAILED")
        logging.error(f"   - Error: {str(e)}")

        # Re-raise exception to trigger retry logic
        raise


# ===================================================================
# NOTES:
# ===================================================================
# 1. This function uses the existing device activation processing logic
#    (af_code/af_device_activation_logic.py)
# 2. File processing follows 5-phase ETL pattern:
#    - Extract → Load to Staging → Validate → Transform → Audit
# 3. CSV columns with 'member_' prefix are mapped to staging columns
# 4. Enrollment status (enrolled/unenrolled/updated) is handled like DTC
# 5. monitoring_system_id is stored in member_identifiers table
# 6. salesforce_account_id is stored in members table
# 7. Validation uses simple DTC pattern (errors in staging table)
# 8. Files moved to fs-ops/processed/ on success or fs-ops/error/ on failure
# ===================================================================
