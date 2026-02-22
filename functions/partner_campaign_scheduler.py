import azure.functions as func
import logging
import json
import traceback
from datetime import datetime


# Create the blueprint
partner_campaign_bp = func.Blueprint()

# Import services (following your existing pattern)
try:
    from af_code.partner_campaign_scheduler.services.campaign_qualifier import (
        CampaignQualifier,
    )
    from af_code.partner_campaign_scheduler.services.member_eligibility import (
        MemberEligibilityService,
    )
    from af_code.partner_campaign_scheduler.services.batch_orchestrator import (
        BatchOrchestrator,
    )
    from af_code.partner_campaign_scheduler.services.status_tracker import StatusTracker
    from af_code.bland_ai_webhook.services.config_manager import ConfigManager
    from af_code.bland_ai_webhook.services.database_service import DatabaseService

    logging.info("✅ Partner Campaign Scheduler imports successful")
except ImportError as e:
    logging.error(f"❌ Import error in Partner Campaign Scheduler: {e}")
    raise

# Configuration: Maximum members to process per scheduler run
MAX_MEMBERS_PER_RUN = 80  # Change this value to adjust rate limiting


@partner_campaign_bp.timer_trigger(
    schedule="5 */30 * * * *",  # Every 30 minutes at minute 5 (staggered from batch reconciler)
    arg_name="timer",
    run_on_startup=False,
)
def partner_campaign_scheduler_timer(timer: func.TimerRequest) -> None:
    """
    Partner Campaign Scheduler - Timer Function
    Runs every 30 minutes to process active Partner campaigns
    """
    start_time = datetime.utcnow()
    request_id = f"partner-scheduler-timer-{start_time.strftime('%Y%m%d-%H%M%S')}"

    # Enhanced logging following your existing pattern
    logging.info("=" * 80)
    logging.info(f"🚀 [PARTNER-SCHEDULER] Timer triggered at {start_time.isoformat()}")
    logging.info(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
    logging.info("🎯 [PARTNER-SCHEDULER] Trigger Type: TIMER")
    logging.info("=" * 80)

    try:
        # Call shared execution logic
        _execute_partner_campaign_scheduler(request_id, start_time, trigger_type="timer")

    except Exception as e:
        error_details = traceback.format_exc()
        logging.error("🚨 [PARTNER-SCHEDULER] CRITICAL ERROR during timer execution:")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Error: {str(e)}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Traceback: {error_details}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Request ID: {request_id}")
        # Don't re-raise - let timer continue on next cycle


@partner_campaign_bp.route(route="partner_campaign_scheduler", methods=["GET", "POST"])
def partner_campaign_scheduler_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    Partner Campaign Scheduler - HTTP Trigger Function

    Allows manual triggering of partner campaign processing
    Useful for:
    - Manual campaign execution outside of scheduled times
    - Testing and debugging
    - On-demand campaign processing

    Returns JSON response with execution details
    """
    start_time = datetime.utcnow()
    request_id = f"partner-scheduler-http-{start_time.strftime('%Y%m%d-%H%M%S')}"

    # Enhanced logging for HTTP trigger
    logging.info("=" * 80)
    logging.info(f"🌐 [PARTNER-SCHEDULER-HTTP] HTTP trigger invoked at {start_time.isoformat()}")
    logging.info(f"📋 [PARTNER-SCHEDULER-HTTP] Request ID: {request_id}")
    logging.info("🎯 [PARTNER-SCHEDULER-HTTP] Purpose: Manual partner campaign processing")
    logging.info(f"🔗 [PARTNER-SCHEDULER-HTTP] Method: {req.method}")
    logging.info("=" * 80)

    try:
        # Call shared execution logic
        result = _execute_partner_campaign_scheduler(request_id, start_time, trigger_type="http")

        # Return success response
        response_data = {
            "success": True,
            "request_id": request_id,
            "execution_time": start_time.isoformat(),
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            "campaigns_processed": result.get("campaigns_processed", 0),
            "members_found": result.get("members_found", 0),
            "batches_submitted": result.get("batches_submitted", 0),
            "message": "Partner campaign processing completed successfully",
            "trigger_type": "http",
        }

        logging.info("✅ [PARTNER-SCHEDULER-HTTP] HTTP request completed successfully")
        return func.HttpResponse(
            json.dumps(response_data), status_code=200, mimetype="application/json"
        )

    except Exception as e:
        # Return error response
        logging.error(f"🚨 [PARTNER-SCHEDULER-HTTP] HTTP request failed: {str(e)}")

        response_data = {
            "success": False,
            "request_id": request_id,
            "execution_time": start_time.isoformat(),
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            "error": str(e),
            "error_type": type(e).__name__,
            "trigger_type": "http",
        }

        return func.HttpResponse(
            json.dumps(response_data), status_code=500, mimetype="application/json"
        )


def _execute_partner_campaign_scheduler(
    request_id: str, start_time: datetime, trigger_type: str = "timer"
) -> dict:
    """
    Core partner campaign scheduler logic shared between timer and HTTP triggers

    Args:
        request_id: Unique identifier for this execution
        start_time: When execution started
        trigger_type: Type of trigger ("timer" or "http")

    Returns:
        dict: Execution results with campaigns_processed, members_found, batches_submitted
    """
    try:
        # Step 1: Initialize services with enhanced logging
        logging.info("🔧 [PARTNER-SCHEDULER] Step 1: Initializing services...")
        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.1: Creating ConfigManager...")
        config_manager = ConfigManager()
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.1: ConfigManager created successfully")

        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.2: Creating DatabaseService...")
        db_service = DatabaseService(config_manager)
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.2: DatabaseService created successfully")

        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.3: Creating service components...")
        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.3a: Creating CampaignQualifier...")
        campaign_qualifier = CampaignQualifier(db_service)
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.3a: CampaignQualifier created")

        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.3b: Creating MemberEligibilityService...")
        member_service = MemberEligibilityService(db_service)
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.3b: MemberEligibilityService created")

        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.3c: Creating BatchOrchestrator...")
        batch_orchestrator = BatchOrchestrator(config_manager, db_service)
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.3c: BatchOrchestrator created")

        logging.info("🔧 [PARTNER-SCHEDULER] Step 1.3d: Creating StatusTracker...")
        status_tracker = StatusTracker(db_service)
        logging.info("✅ [PARTNER-SCHEDULER] Step 1.3d: StatusTracker created")

        logging.info("✅ [PARTNER-SCHEDULER] Step 1: All services initialized successfully")

        # Step 2: Find qualified campaigns
        logging.info("🔍 [PARTNER-SCHEDULER] Step 2: Starting campaign qualification process...")
        logging.info(
            "🔍 [PARTNER-SCHEDULER] Step 2.1: Calling campaign_qualifier.get_qualified_campaigns()..."
        )
        qualified_campaigns = campaign_qualifier.get_qualified_campaigns()
        logging.info(
            f"🔍 [PARTNER-SCHEDULER] Step 2.1: Retrieved {len(qualified_campaigns) if qualified_campaigns else 0} campaigns"
        )

        if not qualified_campaigns:
            logging.info(
                "📋 [PARTNER-SCHEDULER] Step 2: No qualified Partner campaigns found - execution complete"
            )
            _log_execution_summary(request_id, start_time, 0, 0, 0, trigger_type)
            return {
                "campaigns_processed": 0,
                "members_found": 0,
                "batches_submitted": 0,
            }

        logging.info(
            f"📊 [PARTNER-SCHEDULER] Step 2: Found {len(qualified_campaigns)} qualified campaigns"
        )
        for i, campaign in enumerate(qualified_campaigns, 1):
            logging.info(
                f"  📌 [PARTNER-SCHEDULER] Campaign {i}: {campaign.name} (ID: {campaign.campaign_id})"
            )

        # Initialize processing metrics
        total_campaigns_processed = 0
        total_members_found = 0
        total_batches_submitted = 0

        # Step 3: Process each campaign
        logging.info("🎯 [PARTNER-SCHEDULER] Step 3: Processing qualified campaigns...")
        for campaign_num, campaign in enumerate(qualified_campaigns, 1):
            logging.info("=" * 60)
            logging.info(
                f"🎯 [PARTNER-SCHEDULER] Step 3.{campaign_num}: Processing campaign: {campaign.name}"
            )
            logging.info(
                f"🏢 [PARTNER-SCHEDULER] Step 3.{campaign_num}: Organization: {campaign.org_type}"
            )
            logging.info(
                f"⏰ [PARTNER-SCHEDULER] Step 3.{campaign_num}: Schedule: {campaign.scheduling_mode}, {campaign.frequency_value} {campaign.frequency_unit}"
            )
            logging.info(
                f"📦 [PARTNER-SCHEDULER] Step 3.{campaign_num}: Audience batch: {campaign.audience_file_batch}"
            )

            # Step 3.x.1: Find eligible members for this campaign
            logging.info(
                f"👥 [PARTNER-SCHEDULER] Step 3.{campaign_num}.1: Finding eligible members..."
            )
            logging.info(
                f"👥 [PARTNER-SCHEDULER] Step 3.{campaign_num}.1: Calling member_service.get_eligible_members()..."
            )
            eligible_members = member_service.get_eligible_members(campaign)
            logging.info(
                f"👥 [PARTNER-SCHEDULER] Step 3.{campaign_num}.1: Retrieved {len(eligible_members) if eligible_members else 0} members"
            )

            if not eligible_members:
                logging.info(
                    f"⚠️ [PARTNER-SCHEDULER] Step 3.{campaign_num}.1: No eligible members found for campaign: {campaign.name}"
                )
                logging.info(
                    f"⚠️ [PARTNER-SCHEDULER] Step 3.{campaign_num}: Skipping campaign - no eligible members"
                )
                continue

            logging.info(
                f"✅ [PARTNER-SCHEDULER] Step 3.{campaign_num}.1: Found {len(eligible_members)} eligible members"
            )
            total_members_found += len(eligible_members)

            # Step 3.x.2: Limit to first MAX_MEMBERS_PER_RUN members only
            limited_members = eligible_members[:MAX_MEMBERS_PER_RUN]

            logging.info(
                f"📦 [PARTNER-SCHEDULER] Step 3.{campaign_num}.2: Processing {len(limited_members)} of {len(eligible_members)} eligible members (max {MAX_MEMBERS_PER_RUN} per run)"
            )
            if len(eligible_members) > MAX_MEMBERS_PER_RUN:
                logging.info(
                    f"⏳ [PARTNER-SCHEDULER] Step 3.{campaign_num}.2: Remaining {len(eligible_members) - MAX_MEMBERS_PER_RUN} members will be processed in next run (30 min)"
                )

            # Step 3.x.3: Submit single batch (no loop)
            logging.info(
                f"📋 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Processing batch with {len(limited_members)} members"
            )

            # Submit batch to Bland AI (SYNCHRONOUS - waits for confirmation)
            try:
                logging.info(
                    f"🚀 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Submitting batch to Bland AI..."
                )

                result = batch_orchestrator.submit_batch(campaign, limited_members)

                if result.success:
                    logging.info(
                        f"✅ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Batch submitted successfully!"
                    )
                    logging.info(
                        f"📦 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Bland AI Batch ID: {result.batch_id}"
                    )
                    logging.info(
                        f"📊 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Calls queued: {result.members_count}"
                    )
                    logging.info(
                        f"🔔 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Webhooks will be received as calls complete"
                    )
                    total_batches_submitted += 1
                else:
                    logging.error(
                        f"❌ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Batch submission failed"
                    )
                    logging.error(
                        f"❌ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Error: {result.error}"
                    )
                    logging.warning(
                        f"⚠️ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: {len(limited_members)} members will not be called"
                    )

            except Exception as e:
                logging.error(
                    f"🚨 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Exception during batch submission"
                )
                logging.error(f"🚨 [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Error: {str(e)}")
                logging.warning(
                    f"⚠️ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: {len(limited_members)} members will not be called"
                )

            logging.info(
                f"✅ [PARTNER-SCHEDULER] Step 3.{campaign_num}.3: Batch processing completed"
            )

            total_campaigns_processed += 1
            logging.info(
                f"✅ [PARTNER-SCHEDULER] Step 3.{campaign_num}: Campaign processing complete: {campaign.name}"
            )

        # Step 4: Final summary
        logging.info("🎉 [PARTNER-SCHEDULER] Step 4: All campaigns processed successfully")
        _log_execution_summary(
            request_id,
            start_time,
            total_campaigns_processed,
            total_members_found,
            total_batches_submitted,
            trigger_type,
        )

        # Return results
        return {
            "campaigns_processed": total_campaigns_processed,
            "members_found": total_members_found,
            "batches_submitted": total_batches_submitted,
        }

    except Exception as e:
        error_details = traceback.format_exc()
        logging.error("🚨 [PARTNER-SCHEDULER] CRITICAL ERROR during execution:")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Error: {str(e)}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Error Type: {type(e).__name__}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Traceback: {error_details}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Request ID: {request_id}")

        # Log error summary with execution context
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logging.error("=" * 80)
        logging.error("💥 [PARTNER-SCHEDULER] EXECUTION FAILED")
        logging.error(f"⏱️ [PARTNER-SCHEDULER] Duration: {duration:.2f} seconds")
        logging.error(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
        logging.error(f"🔧 [PARTNER-SCHEDULER] Error Type: {type(e).__name__}")
        logging.error(
            f"📊 [PARTNER-SCHEDULER] Partial Results: {locals().get('total_campaigns_processed', 0)} campaigns, {locals().get('total_members_found', 0)} members, {locals().get('total_batches_submitted', 0)} batches"
        )
        logging.error("=" * 80)

        raise


def _log_execution_summary(
    request_id: str,
    start_time: datetime,
    campaigns_processed: int,
    members_found: int,
    batches_submitted: int,
    trigger_type: str = "timer",
):
    """Log execution summary following your existing logging pattern"""
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()

    logging.info("=" * 80)
    logging.info(
        f"🎉 [PARTNER-SCHEDULER] EXECUTION COMPLETED SUCCESSFULLY (Trigger: {trigger_type.upper()})"
    )
    logging.info(f"⏱️ [PARTNER-SCHEDULER] Total Duration: {duration:.2f} seconds")
    logging.info(f"📊 [PARTNER-SCHEDULER] Campaigns Processed: {campaigns_processed}")
    logging.info(f"👥 [PARTNER-SCHEDULER] Total Members Found: {members_found}")
    logging.info(f"📦 [PARTNER-SCHEDULER] Batches Submitted: {batches_submitted}")
    logging.info(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
    logging.info(f"🚀 [PARTNER-SCHEDULER] Trigger Type: {trigger_type.upper()}")
    logging.info("🕒 [PARTNER-SCHEDULER] Next timer execution: 30 minutes")
    if trigger_type == "http":
        logging.info("🌐 [PARTNER-SCHEDULER] HTTP trigger allows manual execution anytime")
    logging.info("=" * 80)
