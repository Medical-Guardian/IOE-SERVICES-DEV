import azure.functions as func
import logging
import traceback
from datetime import datetime

# Create the blueprint
batch_completion_bp = func.Blueprint()

# Import services (following existing IOE pattern)
try:
    from af_code.shared.batch_sync_coordinator import BatchSyncCoordinator
    from af_code.bland_ai_webhook.services.config_manager import ConfigManager
    from af_code.bland_ai_webhook.services.database_service import DatabaseService
    logging.info("✅ Batch Completion Reconciler imports successful")
except ImportError as e:
    logging.error(f"❌ Import error in Batch Completion Reconciler: {e}")
    raise

@batch_completion_bp.schedule(
    schedule="0 */30 * * * *",  # Every 30 minutes at minute 0
    arg_name="timer", 
    run_on_startup=False
)
async def batch_completion_reconciler_timer(timer: func.TimerRequest) -> None:
    """
    Batch Completion Reconciler - Timer Function
    
    Purpose:
    - Reconciles batch completion status with Bland AI API
    - Updates batch-level status only (individual calls handled by webhooks)
    - Uses distributed locking to prevent overlapping executions
    - Runs every 30 minutes to check stale batches
    
    Key Features:
    - Only processes batches that haven't been updated by webhooks recently
    - Focuses on batch-level completion status, not individual call details
    - Prevents concurrent execution through database locking
    - Comprehensive logging following IOE patterns
    """
    start_time = datetime.utcnow()
    request_id = f"batch-reconciler-{start_time.strftime('%Y%m%d-%H%M%S')}"
    
    # Enhanced logging following IOE pattern
    logging.info("=" * 80)
    logging.info(f"🔄 [BATCH-RECONCILER] Timer triggered at {start_time.isoformat()}")
    logging.info(f"📋 [BATCH-RECONCILER] Request ID: {request_id}")
    logging.info(f"🎯 [BATCH-RECONCILER] Purpose: Reconcile batch completion status with Bland AI")
    logging.info(f"⚡ [BATCH-RECONCILER] Scope: Batch-level status only (webhooks handle individual calls)")
    logging.info("=" * 80)
    
    # Initialize services
    config_manager = None
    db_service = None
    coordinator = None
    
    try:
        # Step 1: Initialize required services
        logging.info("🔧 [BATCH-RECONCILER] Initializing services...")
        config_manager = ConfigManager()
        db_service = DatabaseService(config_manager)
        coordinator = BatchSyncCoordinator(db_service, config_manager)
        logging.info("✅ [BATCH-RECONCILER] All services initialized successfully")
        
        # Step 2: Check API health before proceeding
        logging.info("🏥 [BATCH-RECONCILER] Checking Bland AI API health...")
        api_healthy = await coordinator.batch_monitor.check_api_health()
        
        if not api_healthy:
            logging.warning("⚠️ [BATCH-RECONCILER] Bland AI API not responding - skipping reconciliation")
            _log_execution_summary(request_id, start_time, skipped=True, reason="API health check failed")
            return
        
        logging.info("✅ [BATCH-RECONCILER] API health check passed")
        
        # Step 3: Execute with distributed locking to prevent overlaps
        logging.info("🔒 [BATCH-RECONCILER] Attempting to acquire distributed lock...")
        await coordinator.execute_with_lock(
            operation_name="batch_completion_sync", 
            max_duration_minutes=25  # Must be less than 30min timer interval
        )
        
        logging.info("✅ [BATCH-RECONCILER] Batch reconciliation process completed successfully")
        _log_execution_summary(request_id, start_time, skipped=False)
        
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error("🚨 [BATCH-RECONCILER] CRITICAL ERROR during execution:")
        logging.error(f"🚨 [BATCH-RECONCILER] Error: {str(e)}")
        logging.error(f"🚨 [BATCH-RECONCILER] Traceback: {error_details}")
        logging.error(f"🚨 [BATCH-RECONCILER] Request ID: {request_id}")
        
        # Log error summary
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logging.error("=" * 80)
        logging.error(f"💥 [BATCH-RECONCILER] EXECUTION FAILED")
        logging.error(f"⏱️ [BATCH-RECONCILER] Duration: {duration:.2f} seconds")
        logging.error(f"📋 [BATCH-RECONCILER] Request ID: {request_id}")
        logging.error(f"🔧 [BATCH-RECONCILER] Error Type: {type(e).__name__}")
        logging.error("=" * 80)
        
        # Don't re-raise - let timer continue on next cycle
        
    finally:
        # Step 4: Cleanup resources
        if db_service:
            try:
                await db_service.close_connections()
                logging.info("🧹 [BATCH-RECONCILER] Database connections closed")
            except Exception as cleanup_error:
                logging.error(f"⚠️ [BATCH-RECONCILER] Error during cleanup: {str(cleanup_error)}")

def _log_execution_summary(request_id: str, start_time: datetime, skipped: bool = False, reason: str = None):
    """
    Log execution summary following IOE logging pattern
    
    Args:
        request_id: Unique identifier for this execution
        start_time: When execution started
        skipped: Whether execution was skipped
        reason: Reason for skipping (if applicable)
    """
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    logging.info("=" * 80)
    
    if skipped:
        logging.info(f"⏭️ [BATCH-RECONCILER] EXECUTION SKIPPED")
        logging.info(f"❓ [BATCH-RECONCILER] Reason: {reason or 'Unknown'}")
    else:
        logging.info(f"🎉 [BATCH-RECONCILER] EXECUTION COMPLETED SUCCESSFULLY")
        logging.info(f"🔄 [BATCH-RECONCILER] Function: Batch completion status reconciliation")
        logging.info(f"⚡ [BATCH-RECONCILER] Scope: Batch-level status updates only")
        logging.info(f"🔗 [BATCH-RECONCILER] Integration: Works alongside webhook system")
    
    logging.info(f"⏱️ [BATCH-RECONCILER] Total Duration: {duration:.2f} seconds")
    logging.info(f"📋 [BATCH-RECONCILER] Request ID: {request_id}")
    logging.info(f"🕒 [BATCH-RECONCILER] Next execution: 30 minutes")
    logging.info(f"📊 [BATCH-RECONCILER] Execution time: {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Additional context for operators
    if not skipped:
        logging.info("📝 [BATCH-RECONCILER] Note: Individual call updates handled by webhooks")
        logging.info("🎯 [BATCH-RECONCILER] This function only reconciles batch completion status")
        logging.info("🔒 [BATCH-RECONCILER] Distributed locking prevents execution overlap")
    
    logging.info("=" * 80)