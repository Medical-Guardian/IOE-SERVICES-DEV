import azure.functions as func
import logging
import json
import traceback
from datetime import datetime

# Create the blueprint
partner_campaign_bp = func.Blueprint()

# Import services (following your existing pattern)
try:
    from af_code.partner_campaign_scheduler.services.campaign_qualifier import CampaignQualifier
    from af_code.partner_campaign_scheduler.services.member_eligibility import MemberEligibilityService
    from af_code.partner_campaign_scheduler.services.batch_orchestrator import BatchOrchestrator
    from af_code.partner_campaign_scheduler.services.status_tracker import StatusTracker
    from af_code.bland_ai_webhook.services.config_manager import ConfigManager
    from af_code.bland_ai_webhook.services.database_service import DatabaseService
    logging.info("✅ Partner Campaign Scheduler imports successful")
except ImportError as e:
    logging.error(f"❌ Import error in Partner Campaign Scheduler: {e}")
    raise

@partner_campaign_bp.schedule(
    schedule="0 */30 * * * *", 
    arg_name="timer", 
    run_on_startup=False
)
async def partner_campaign_scheduler_timer(timer: func.TimerRequest) -> None:
    """
    Partner Campaign Scheduler - Timer Function
    Runs every 30 minutes to process active Partner campaigns
    """
    start_time = datetime.utcnow()
    request_id = f"partner-scheduler-{start_time.strftime('%Y%m%d-%H%M%S')}"
    
    # Enhanced logging following your existing pattern
    logging.info("=" * 80)
    logging.info(f"🚀 [PARTNER-SCHEDULER] Timer triggered at {start_time.isoformat()}")
    logging.info(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
    logging.info("=" * 80)
    
    try:
        # Initialize services with enhanced logging
        logging.info("🔧 [PARTNER-SCHEDULER] Initializing services...")
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        logging.info("✅ [PARTNER-SCHEDULER] Database service initialized")
        
        campaign_qualifier = CampaignQualifier(db_service)
        member_service = MemberEligibilityService(db_service)
        batch_orchestrator = BatchOrchestrator(config_manager)
        status_tracker = StatusTracker(db_service)
        logging.info("✅ [PARTNER-SCHEDULER] All services initialized successfully")
        
        # Step 1: Find qualified campaigns
        logging.info("🔍 [PARTNER-SCHEDULER] Starting campaign qualification process...")
        qualified_campaigns = await campaign_qualifier.get_qualified_campaigns()
        
        if not qualified_campaigns:
            logging.info("📋 [PARTNER-SCHEDULER] No qualified Partner campaigns found - execution complete")
            _log_execution_summary(request_id, start_time, 0, 0, 0)
            return
            
        logging.info(f"📊 [PARTNER-SCHEDULER] Found {len(qualified_campaigns)} qualified campaigns")
        for campaign in qualified_campaigns:
            logging.info(f"  📌 Campaign: {campaign.name} (ID: {campaign.campaign_id})")
        
        # Processing metrics
        total_campaigns_processed = 0
        total_members_found = 0
        total_batches_submitted = 0
        
        # Step 2: Process each campaign
        for campaign in qualified_campaigns:
            logging.info("-" * 60)
            logging.info(f"🎯 [PARTNER-SCHEDULER] Processing campaign: {campaign.name}")
            logging.info(f"🏢 [PARTNER-SCHEDULER] Organization: {campaign.org_type}")
            logging.info(f"⏰ [PARTNER-SCHEDULER] Schedule: {campaign.scheduling_mode}, {campaign.frequency_value} {campaign.frequency_unit}")
            logging.info(f"📦 [PARTNER-SCHEDULER] Audience batch: {campaign.audience_file_batch}")
            
            # Step 3: Find eligible members for this campaign
            logging.info(f"👥 [PARTNER-SCHEDULER] Finding eligible members...")
            eligible_members = await member_service.get_eligible_members(campaign)
            
            if not eligible_members:
                logging.info(f"⚠️ [PARTNER-SCHEDULER] No eligible members found for campaign: {campaign.name}")
                continue
                
            logging.info(f"✅ [PARTNER-SCHEDULER] Found {len(eligible_members)} eligible members")
            total_members_found += len(eligible_members)
            
            # Step 4: Create and submit batches (1000 members per batch)
            logging.info(f"📦 [PARTNER-SCHEDULER] Creating batches (max 1000 per batch)...")
            batches = member_service.create_batches(eligible_members, batch_size=1000)
            logging.info(f"📊 [PARTNER-SCHEDULER] Created {len(batches)} batches")
            
            for batch_num, batch in enumerate(batches, 1):
                logging.info(f"🚀 [PARTNER-SCHEDULER] Submitting batch {batch_num}/{len(batches)} with {len(batch)} members")
                
                # Submit to Bland AI
                batch_result = await batch_orchestrator.submit_batch(campaign, batch)
                
                if batch_result.success:
                    # Track successful submissions
                    await status_tracker.log_batch_submission(campaign, batch, batch_result)
                    total_batches_submitted += 1
                    logging.info(f"✅ [PARTNER-SCHEDULER] Batch {batch_num} submitted successfully (Bland Batch ID: {batch_result.batch_id})")
                else:
                    logging.error(f"❌ [PARTNER-SCHEDULER] Batch {batch_num} submission failed: {batch_result.error}")
            
            total_campaigns_processed += 1
            logging.info(f"✅ [PARTNER-SCHEDULER] Campaign processing complete: {campaign.name}")
        
        # Final summary
        _log_execution_summary(request_id, start_time, total_campaigns_processed, total_members_found, total_batches_submitted)
        
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error("🚨 [PARTNER-SCHEDULER] CRITICAL ERROR during execution:")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Error: {str(e)}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Traceback: {error_details}")
        logging.error(f"🚨 [PARTNER-SCHEDULER] Request ID: {request_id}")
        
        # Log error summary
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logging.error("=" * 80)
        logging.error(f"💥 [PARTNER-SCHEDULER] EXECUTION FAILED")
        logging.error(f"⏱️ [PARTNER-SCHEDULER] Duration: {duration:.2f} seconds")
        logging.error(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
        logging.error("=" * 80)
        
        raise

def _log_execution_summary(request_id: str, start_time: datetime, campaigns_processed: int, members_found: int, batches_submitted: int):
    """Log execution summary following your existing logging pattern"""
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    logging.info("=" * 80)
    logging.info(f"🎉 [PARTNER-SCHEDULER] EXECUTION COMPLETED SUCCESSFULLY")
    logging.info(f"⏱️ [PARTNER-SCHEDULER] Total Duration: {duration:.2f} seconds")
    logging.info(f"📊 [PARTNER-SCHEDULER] Campaigns Processed: {campaigns_processed}")
    logging.info(f"👥 [PARTNER-SCHEDULER] Total Members Found: {members_found}")
    logging.info(f"📦 [PARTNER-SCHEDULER] Batches Submitted: {batches_submitted}")
    logging.info(f"📋 [PARTNER-SCHEDULER] Request ID: {request_id}")
    logging.info(f"🕒 [PARTNER-SCHEDULER] Next execution: 30 minutes")
    logging.info("=" * 80)