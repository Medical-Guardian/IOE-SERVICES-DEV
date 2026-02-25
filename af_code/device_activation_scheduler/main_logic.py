"""
Device Activation Scheduler - Main Logic

BusinessCaseID: BC-DA-001 (Core Orchestration System)
Created: 2025-12-07
Updated: 2025-12-24 - Added comprehensive documentation and BusinessCaseID mapping

This module contains the main orchestration logic for the Device Activation campaign scheduler.
It coordinates between multiple services to identify eligible members and submit call batches
to Bland AI for automated device activation calls.

PURPOSE:
--------
The Device Activation scheduler runs every 15 minutes (timer trigger) to:
1. Query database for members eligible for device activation calls
2. Validate business hours (dual-timezone: MG EST + member timezone)
3. Create batches of up to 100 members per batch
4. Submit batches to Bland AI for automated calling
5. Track results and log comprehensive statistics

This is the **entry point** for the entire Device Activation call workflow. All other
components (EligibilityService, BatchOrchestrator, CallbackScheduler) are orchestrated
by this module.

ORCHESTRATION FLOW:
-------------------
The `create_device_activation_batch()` function implements a 3-step workflow:

**STEP 1: Campaign Qualification**
    - Validate campaign is Active
    - Confirm campaign type is 'Device Activation' or 'Operations'
    - Check campaigns are within operating hours
    - Log qualification criteria

**STEP 2: Member Qualification & Eligibility**
    - Call EligibilityService.get_eligible_members()
    - EligibilityService performs:
        - SQL query for eligible members (200+ line query)
        - Business hours validation (dual-timezone)
        - Returns filtered member list
    - If no eligible members:
        - Log diagnostic checklist
        - Return early with success=True, calls_submitted=0
    - If eligible members found:
        - Log detailed statistics:
            - Call attempt distribution (Call 1, 2, 3, 4, 5+)
            - Timezone distribution (EST, CST, MST, PST)
            - Customer type distribution (DTC, MA, Medicaid)
            - Device brand distribution

**STEP 3: Batch Creation & Bland AI Submission**
    - Call BatchOrchestrator.create_and_submit_batches(eligible_members)
    - BatchOrchestrator performs:
        - Split members into batches of 100 (Bland AI limit)
        - For each batch:
            - Phase 1: INSERT outreach_batches (status='Pending')
            - Phase 2: INSERT outreach_attempts (disposition='Pending')
            - Phase 3: Submit to Bland AI, UPDATE with vendor_batch_id
        - Return summary: batches_created, calls_submitted, success
    - Log final results summary

**STEP 4: Results Summary**
    - Calculate success metrics
    - Log comprehensive results:
        - Total qualified members
        - Batches created
        - Calls submitted
        - Success rate percentage
    - Log next steps (webhook processing, next scheduler run)
    - Return result dictionary

TIMER TRIGGER CONFIGURATION:
-----------------------------
This function is called by the device_activation_scheduler Azure Function:

```python
# In functions/device_activation_scheduler.py
@device_activation_bp.timer_trigger(
    schedule="0 */15 * * * *",  # Every 15 minutes
    arg_name="timer",
    run_on_startup=False,
    use_monitor=False
)
def timer_device_activation(timer: func.TimerRequest) -> None:
    # Initialize services
    config_manager = ConfigManager()
    db_service = DatabaseService(config_manager)
    eligibility_service = EligibilityService(db_service)
    batch_orchestrator = BatchOrchestrator(db_service, config_manager)

    # Call main logic
    result = create_device_activation_batch(
        eligibility_service=eligibility_service,
        batch_orchestrator=batch_orchestrator,
        force=False
    )
```

**Schedule:** Every 15 minutes (0, 15, 30, 45 past the hour)
**Run on Startup:** False (prevents duplicate processing during deployment)
**Monitoring:** Disabled (uses custom logging instead)

HTTP TRIGGER SUPPORT:
---------------------
The function is also registered as an HTTP trigger for manual execution:

```python
# Manual trigger via HTTP POST
@device_activation_bp.route(route="device-activation-scheduler", methods=["POST"])
def http_device_activation(req: func.HttpRequest) -> func.HttpResponse:
    # Same initialization as timer trigger
    result = create_device_activation_batch(...)
    return func.HttpResponse(json.dumps(result), status_code=200)
```

**Endpoint:** POST /api/device-activation-scheduler
**Use Cases:**
- Manual batch creation outside schedule
- Testing and debugging
- Emergency processing after system downtime

LOGGING OUTPUT:
---------------
The function produces comprehensive logging output for monitoring and debugging:

**Start:**
```
================================================================================
🚀 [MAIN-LOGIC] DEVICE ACTIVATION SCHEDULER - BATCH CREATION START
================================================================================
```

**Step 1: Campaign Qualification:**
```
🔍 [MAIN-LOGIC] STEP 1: CAMPAIGN QUALIFICATION
🔍 [MAIN-LOGIC] Campaign Type: Device Activation / Operations
🔍 [MAIN-LOGIC] Qualification Criteria:
   ✓ Status = 'Active'
   ✓ Campaign Type IN ('Operations', 'Device Activation')
   ✓ Within 90-day activation window
```

**Step 2: Member Qualification:**
```
📋 [MAIN-LOGIC] STEP 2: MEMBER QUALIFICATION & ELIGIBILITY
✅ [MAIN-LOGIC] Total Qualified Members: 25

📊 [MAIN-LOGIC] QUALIFICATION STATISTICS
📊 [MAIN-LOGIC] Call Attempt Distribution:
   📞 Call #1: 5 members
   📞 Call #2: 8 members
   📞 Call #5: 12 members

📊 [MAIN-LOGIC] Timezone Distribution:
   🕒 America/Chicago: 10 members
   🕒 America/New_York: 15 members
```

**Step 3: Batch Creation:**
```
📦 [MAIN-LOGIC] STEP 3: BATCH CREATION & BLAND AI SUBMISSION
📦 [MAIN-LOGIC] Total members to batch: 25
📦 [MAIN-LOGIC] Batch size limit: 100 members per batch
```

**Final Results:**
```
================================================================================
📊 [MAIN-LOGIC] FINAL RESULTS SUMMARY
================================================================================
✅ [MAIN-LOGIC] Status: SUCCESS

📊 [MAIN-LOGIC] Campaign Metrics:
   ✓ Total Qualified Members: 25
   ✓ Batches Created: 1
   ✓ Calls Submitted to Bland AI: 25
   ✓ Success Rate: 100.0%

📊 [MAIN-LOGIC] Next Steps:
   1. Bland AI will process calls asynchronously
   2. Webhook will receive call results
   3. Database will be updated with dispositions
   4. Next scheduler run will handle remaining members
================================================================================
```

ERROR SCENARIOS:
----------------
**No Eligible Members:**
- Log diagnostic checklist with possible reasons
- Return success=True (not an error), calls_submitted=0
- Next scheduler run will check again

**Batch Creation Fails:**
- Log error details with partial results
- Return success=False with error message
- Eligible members remain in database for next run

**Critical Exception:**
- Log full stack trace (exc_info=True)
- Return success=False with error message
- Azure Functions runtime will retry on next schedule

RELATED COMPONENTS:
-------------------
- **EligibilityService** (BC-DA-003): Gets eligible members from database
- **BatchOrchestrator** (BC-DA-004): Creates batches and submits to Bland AI
- **CallbackScheduler** (BC-DA-005): Processes callback requests (not called from this function yet)
- **DatabaseService**: Executes SQL queries
- **ConfigManager**: Retrieves secrets from Key Vault

RELATED DOCUMENTATION:
----------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Scheduler Internals: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_SCHEDULER_INTERNALS.md
- Call Sequence: documentation/device_activation/FLOWS/DEVICE_ACTIVATION_CALL_SEQUENCE.md

PATTERN REFERENCE:
------------------
This module follows the same orchestration pattern as:
- af_code/af_dtc_intro_call/main_logic.py (DTC Intro Call scheduler)
- af_code/partner_campaign_scheduler/main_logic.py (Partner Campaign scheduler)

All three schedulers share common patterns:
- Service initialization
- Eligibility determination
- Batch creation and submission
- Comprehensive logging and metrics

EXAMPLES:
---------
Basic usage (called by timer trigger):
    >>> from af_code.device_activation_scheduler.main_logic import create_device_activation_batch
    >>> from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService
    >>> from af_code.device_activation_scheduler.services.batch_orchestrator import BatchOrchestrator
    >>>
    >>> # Initialize services
    >>> eligibility_service = EligibilityService(db_service)
    >>> batch_orchestrator = BatchOrchestrator(db_service, config_manager)
    >>>
    >>> # Run scheduler
    >>> result = create_device_activation_batch(
    ...     eligibility_service=eligibility_service,
    ...     batch_orchestrator=batch_orchestrator,
    ...     force=False
    ... )
    >>>
    >>> print(f"Success: {result['success']}")
    >>> print(f"Calls submitted: {result['calls_submitted']}")
    Success: True
    Calls submitted: 25

NOTES:
------
- Runs every 15 minutes via timer trigger
- HTTP trigger available for manual execution
- No eligible members is a success case (not an error)
- Business hours validation happens in EligibilityService
- Batch size limited to 100 members (Bland AI constraint)
- All logging uses emoji prefixes for visibility in Application Insights
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

    BusinessCaseID: BC-DA-001
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
        logger.info(
            "   ✓ Within 90-day activation window (activation_start_date to campaign_end_date)"
        )
        logger.info("   ✓ Not in callback queue (priority)")
        logger.info(
            "   ✓ Frequency rules (Call 1-3: 2 biz days, Call 4: 5 biz days, Call 5+: 7 calendar days)"
        )

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
            attempt_num = member.get("call_attempt_number") or 1
            call_attempt_summary[attempt_num] = call_attempt_summary.get(attempt_num, 0) + 1

            # Timezone distribution
            tz = member.get("timezone") or "Unknown"
            timezone_summary[tz] = timezone_summary.get(tz, 0) + 1

            # Customer type distribution
            cust_type = member.get("customer_type") or "Unknown"
            customer_type_summary[cust_type] = customer_type_summary.get(cust_type, 0) + 1

            # Device brand distribution
            device_brand = member.get("device_brand") or "Unknown"
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
        logger.info(f"📦 [MAIN-LOGIC] Total eligible members: {len(eligible_members)}")
        logger.info(
            "📦 [MAIN-LOGIC] Batch size: 20 members per run (single batch per 15-minute cadence)"
        )
        logger.info(
            "📦 [MAIN-LOGIC] Processing top 20 qualified members and submitting to Bland AI..."
        )

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
