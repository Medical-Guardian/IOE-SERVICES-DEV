"""
Device Activation Scheduler - Main Logic
BusinessCaseID: BC-TBD (Device Activation System)
Created: 2025-12-07

This module contains the main orchestration logic for the Device Activation campaign scheduler.
It coordinates between EligibilityService and BatchOrchestrator to:
1. Find eligible members for device activation calls
2. Create batches for Bland AI submission
3. Submit batches and track results

Pattern: Follows af_code/af_dtc_intro_call/main_logic.py structure
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def create_device_activation_batch(
    eligibility_service,
    batch_orchestrator,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Main logic for creating Device Activation call batches

    This function orchestrates the entire batch creation workflow:
    1. Query eligible members using EligibilityService
    2. Validate business hours for each member
    3. Create batches using BatchOrchestrator
    4. Submit batches to Bland AI
    5. Track and log results

    Args:
        eligibility_service: EligibilityService instance for member queries
        batch_orchestrator: BatchOrchestrator instance for batch creation
        force: If True, bypass some validation checks (for testing)

    Returns:
        Dict with:
            - success (bool): Whether batch creation succeeded
            - message (str): Result message
            - total_eligible (int): Number of eligible members found
            - batches_created (int): Number of batches created
            - calls_submitted (int): Number of calls submitted to Bland AI

    BusinessCaseID: BC-TBD (Device Activation System)
    """
    logger.info("=" * 80)
    logger.info("🚀 [MAIN-LOGIC] DEVICE ACTIVATION SCHEDULER - BATCH CREATION START")
    logger.info("=" * 80)

    try:
        # ========================================================================
        # STEP 1: CAMPAIGN QUALIFICATION
        # ========================================================================
        logger.info("")
        logger.info("🔍 [MAIN-LOGIC] ============================================")
        logger.info("🔍 [MAIN-LOGIC] STEP 1: CAMPAIGN QUALIFICATION")
        logger.info("🔍 [MAIN-LOGIC] ============================================")
        logger.info("🔍 [MAIN-LOGIC] Campaign Type: Device Activation / Operations")
        logger.info("🔍 [MAIN-LOGIC] Qualification Criteria:")
        logger.info("   ✓ Status = 'Active'")
        logger.info("   ✓ Campaign Type IN ('Operations', 'Device Activation', 'DeviceActivation')")
        logger.info("   ✓ Within 90-day activation window (activation_start_date to campaign_end_date)")
        logger.info("   ✓ Not in callback queue (priority)")
        logger.info("   ✓ Frequency rules (Call 1-3: 2 biz days, Call 4: 5 biz days, Call 5+: 7 calendar days)")

        # ========================================================================
        # STEP 2: MEMBER QUALIFICATION & ELIGIBILITY
        # ========================================================================
        logger.info("")
        logger.info("📋 [MAIN-LOGIC] ============================================")
        logger.info("📋 [MAIN-LOGIC] STEP 2: MEMBER QUALIFICATION & ELIGIBILITY")
        logger.info("📋 [MAIN-LOGIC] ============================================")
        logger.info("📋 [MAIN-LOGIC] Querying database for potential members...")

        eligible_members = eligibility_service.get_eligible_members()

        if not eligible_members:
            logger.info("")
            logger.info("⚠️ [MAIN-LOGIC] ============================================")
            logger.info("⚠️ [MAIN-LOGIC] NO ELIGIBLE MEMBERS FOUND")
            logger.info("⚠️ [MAIN-LOGIC] ============================================")
            logger.info("⚠️ [MAIN-LOGIC] Possible reasons:")
            logger.info("   - No active Device Activation campaigns")
            logger.info("   - All members outside business hours")
            logger.info("   - All members have recent attempts (frequency protection)")
            logger.info("   - All members in callback queue (higher priority)")
            logger.info("   - All members outside 90-day campaign window")
            logger.info("=" * 80)
            return {
                "success": True,
                "message": "No eligible members found for calling at this time",
                "total_eligible": 0,
                "batches_created": 0,
                "calls_submitted": 0,
            }

        logger.info(f"✅ [MAIN-LOGIC] Total Qualified Members: {len(eligible_members)}")
        logger.info("")

        # Log detailed statistics
        call_attempt_summary = {}
        timezone_summary = {}
        customer_type_summary = {}
        device_brand_summary = {}

        for member in eligible_members:
            # Call attempt distribution
            attempt_num = member.get("call_attempt_number", 1)
            call_attempt_summary[attempt_num] = call_attempt_summary.get(attempt_num, 0) + 1

            # Timezone distribution
            tz = member.get("timezone", "Unknown")
            timezone_summary[tz] = timezone_summary.get(tz, 0) + 1

            # Customer type distribution
            cust_type = member.get("customer_type", "Unknown")
            customer_type_summary[cust_type] = customer_type_summary.get(cust_type, 0) + 1

            # Device brand distribution
            device_brand = member.get("device_brand", "Unknown")
            device_brand_summary[device_brand] = device_brand_summary.get(device_brand, 0) + 1

        logger.info("📊 [MAIN-LOGIC] ============================================")
        logger.info("📊 [MAIN-LOGIC] QUALIFICATION STATISTICS")
        logger.info("📊 [MAIN-LOGIC] ============================================")

        logger.info("📊 [MAIN-LOGIC] Call Attempt Distribution:")
        for attempt_num in sorted(call_attempt_summary.keys()):
            logger.info(f"   📞 Call #{attempt_num}: {call_attempt_summary[attempt_num]} members")

        logger.info("")
        logger.info("📊 [MAIN-LOGIC] Timezone Distribution:")
        for tz in sorted(timezone_summary.keys()):
            logger.info(f"   🕒 {tz}: {timezone_summary[tz]} members")

        logger.info("")
        logger.info("📊 [MAIN-LOGIC] Customer Type Distribution:")
        for cust_type in sorted(customer_type_summary.keys()):
            logger.info(f"   👥 {cust_type}: {customer_type_summary[cust_type]} members")

        logger.info("")
        logger.info("📊 [MAIN-LOGIC] Device Brand Distribution:")
        for brand in sorted(device_brand_summary.keys()):
            logger.info(f"   📱 {brand}: {device_brand_summary[brand]} devices")

        logger.info("📊 [MAIN-LOGIC] ============================================")

        # ========================================================================
        # STEP 3: BATCH CREATION & SUBMISSION
        # ========================================================================
        logger.info("")
        logger.info("📦 [MAIN-LOGIC] ============================================")
        logger.info("📦 [MAIN-LOGIC] STEP 3: BATCH CREATION & BLAND AI SUBMISSION")
        logger.info("📦 [MAIN-LOGIC] ============================================")
        logger.info(f"📦 [MAIN-LOGIC] Total members to batch: {len(eligible_members)}")
        logger.info("📦 [MAIN-LOGIC] Batch size limit: 100 members per batch (Bland AI limit)")
        logger.info("📦 [MAIN-LOGIC] Creating batches and submitting to Bland AI...")

        batch_results = batch_orchestrator.create_and_submit_batches(eligible_members)

        # ========================================================================
        # STEP 4: RESULTS SUMMARY
        # ========================================================================
        success = batch_results.get("success", False)
        batches_created = batch_results.get("batches_created", 0)
        calls_submitted = batch_results.get("calls_submitted", 0)

        logger.info("")
        logger.info("=" * 80)
        logger.info("📊 [MAIN-LOGIC] FINAL RESULTS SUMMARY")
        logger.info("=" * 80)

        if success:
            logger.info("✅ [MAIN-LOGIC] Status: SUCCESS")
            logger.info("")
            logger.info("📊 [MAIN-LOGIC] Campaign Metrics:")
            logger.info(f"   ✓ Total Qualified Members: {len(eligible_members)}")
            logger.info(f"   ✓ Batches Created: {batches_created}")
            logger.info(f"   ✓ Calls Submitted to Bland AI: {calls_submitted}")
            logger.info(f"   ✓ Success Rate: {(calls_submitted/len(eligible_members)*100):.1f}%")
            logger.info("")
            logger.info("📊 [MAIN-LOGIC] Next Steps:")
            logger.info("   1. Bland AI will process calls asynchronously")
            logger.info("   2. Webhook will receive call results")
            logger.info("   3. Database will be updated with dispositions")
            logger.info("   4. Next scheduler run will handle remaining members")
            logger.info("=" * 80)

            return {
                "success": True,
                "message": "Device Activation batches created successfully",
                "total_eligible": len(eligible_members),
                "batches_created": batches_created,
                "calls_submitted": calls_submitted,
            }
        else:
            error_message = batch_results.get("error", "Unknown error occurred")
            logger.error("❌ [MAIN-LOGIC] Status: FAILED")
            logger.error(f"❌ [MAIN-LOGIC] Error: {error_message}")
            logger.error("")
            logger.error("📊 [MAIN-LOGIC] Partial Results:")
            logger.error(f"   ✗ Total Qualified Members: {len(eligible_members)}")
            logger.error(f"   ✗ Batches Created: {batches_created}")
            logger.error(f"   ✗ Calls Submitted: {calls_submitted}")
            logger.error(f"   ✗ Calls Failed: {len(eligible_members) - calls_submitted}")
            logger.error("=" * 80)

            return {
                "success": False,
                "message": f"Batch creation failed: {error_message}",
                "total_eligible": len(eligible_members),
                "batches_created": batches_created,
                "calls_submitted": calls_submitted,
            }

    except Exception as e:
        logger.error(f"💥 [MAIN-LOGIC] Critical error in batch creation: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"Critical error: {str(e)}",
            "total_eligible": 0,
            "batches_created": 0,
            "calls_submitted": 0,
        }
