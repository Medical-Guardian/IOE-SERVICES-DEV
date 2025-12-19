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
    logger.info("🚀 [MAIN-LOGIC] Starting Device Activation batch creation")

    try:
        # Step 1: Get eligible members
        logger.info("📋 [MAIN-LOGIC] Step 1: Querying eligible members...")
        eligible_members = eligibility_service.get_eligible_members()

        if not eligible_members:
            logger.info("ℹ️ [MAIN-LOGIC] No eligible members found for calling")
            return {
                "success": True,
                "message": "No eligible members found for calling at this time",
                "total_eligible": 0,
                "batches_created": 0,
                "calls_submitted": 0,
            }

        logger.info(f"✅ [MAIN-LOGIC] Found {len(eligible_members)} eligible members")

        # Log summary by call attempt number
        call_attempt_summary = {}
        for member in eligible_members:
            attempt_num = member.get("call_attempt_number", 1)
            call_attempt_summary[attempt_num] = call_attempt_summary.get(attempt_num, 0) + 1

        logger.info("📊 [MAIN-LOGIC] Eligible members by call attempt:")
        for attempt_num in sorted(call_attempt_summary.keys()):
            logger.info(f"   Call {attempt_num}: {call_attempt_summary[attempt_num]} members")

        # Step 2: Create and submit batches
        logger.info(
            f"📦 [MAIN-LOGIC] Step 2: Creating batches for {len(eligible_members)} members..."
        )

        batch_results = batch_orchestrator.create_and_submit_batches(eligible_members)

        # Step 3: Log results
        success = batch_results.get("success", False)
        batches_created = batch_results.get("batches_created", 0)
        calls_submitted = batch_results.get("calls_submitted", 0)

        if success:
            logger.info("✅ [MAIN-LOGIC] Batch creation completed successfully")
            logger.info("📊 [MAIN-LOGIC] Summary:")
            logger.info(f"   Total eligible members: {len(eligible_members)}")
            logger.info(f"   Batches created: {batches_created}")
            logger.info(f"   Calls submitted to Bland AI: {calls_submitted}")

            return {
                "success": True,
                "message": "Device Activation batches created successfully",
                "total_eligible": len(eligible_members),
                "batches_created": batches_created,
                "calls_submitted": calls_submitted,
            }
        else:
            error_message = batch_results.get("error", "Unknown error occurred")
            logger.error(f"❌ [MAIN-LOGIC] Batch creation failed: {error_message}")

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
