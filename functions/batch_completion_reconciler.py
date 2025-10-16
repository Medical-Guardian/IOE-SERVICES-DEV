import azure.functions as func
import logging
import traceback
import json
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

@batch_completion_bp.timer_trigger(
    schedule="0 */30 * * * *",  # Every 30 minutes at minute 0 (before partner scheduler)
    arg_name="timer", 
    run_on_startup=False
)
def batch_completion_reconciler_timer(timer: func.TimerRequest) -> None:
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
    
    try:
        # Call the shared batch reconciliation logic
        _execute_batch_reconciliation(request_id, start_time, trigger_type="timer")
        
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

@batch_completion_bp.route(route="batch_completion_reconciler", methods=["GET", "POST"])
def batch_completion_reconciler_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    Batch Completion Reconciler - HTTP Trigger Function
    
    Allows manual triggering of batch reconciliation process
    Useful for:
    - Manual reconciliation outside of scheduled times
    - Testing and debugging
    - On-demand status synchronization
    
    Returns JSON response with execution details
    """
    start_time = datetime.utcnow()
    request_id = f"batch-reconciler-http-{start_time.strftime('%Y%m%d-%H%M%S')}"
    
    # Enhanced logging for HTTP trigger
    logging.info("=" * 80)
    logging.info(f"🌐 [BATCH-RECONCILER-HTTP] HTTP trigger invoked at {start_time.isoformat()}")
    logging.info(f"📋 [BATCH-RECONCILER-HTTP] Request ID: {request_id}")
    logging.info(f"🎯 [BATCH-RECONCILER-HTTP] Purpose: Manual batch completion reconciliation")
    logging.info(f"🔗 [BATCH-RECONCILER-HTTP] Method: {req.method}")
    logging.info("=" * 80)
    
    try:
        # Call the same core logic as timer function
        result = _execute_batch_reconciliation(request_id, start_time, trigger_type="http")
        
        # Return success response
        response_data = {
            "success": True,
            "request_id": request_id,
            "execution_time": start_time.isoformat(),
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            "message": "Batch reconciliation completed successfully",
            "trigger_type": "http"
        }
        
        logging.info(f"✅ [BATCH-RECONCILER-HTTP] HTTP request completed successfully")
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        # Return error response
        error_details = traceback.format_exc()
        logging.error(f"🚨 [BATCH-RECONCILER-HTTP] HTTP request failed: {str(e)}")
        
        response_data = {
            "success": False,
            "request_id": request_id,
            "execution_time": start_time.isoformat(),
            "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            "error": str(e),
            "error_type": type(e).__name__,
            "trigger_type": "http"
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=500,
            mimetype="application/json"
        )

def _execute_batch_reconciliation(request_id: str, start_time: datetime, trigger_type: str = "timer") -> bool:
    """
    Core batch reconciliation logic shared between timer and HTTP triggers
    
    Args:
        request_id: Unique identifier for this execution
        start_time: When execution started
        trigger_type: Type of trigger ("timer" or "http")
        
    Returns:
        bool: True if successful, raises exception if failed
    """
    # Initialize services
    config_manager = None
    db_service = None
    coordinator = None
    
    try:
        # Step 1: Initialize required services
        logging.info(f"🔧 [BATCH-RECONCILER] Step 1: Initializing services (Trigger: {trigger_type.upper()})...")
        logging.info("🔧 [BATCH-RECONCILER] Step 1.1: Creating ConfigManager...")
        config_manager = ConfigManager()
        logging.info("✅ [BATCH-RECONCILER] Step 1.1: ConfigManager created successfully")
        logging.info(f"🔧 [BATCH-RECONCILER] Step 1.1: ConfigManager memory location: {id(config_manager)}")
        
        logging.info("🔧 [BATCH-RECONCILER] Step 1.2: Creating DatabaseService...")
        db_service = DatabaseService(config_manager)
        logging.info("✅ [BATCH-RECONCILER] Step 1.2: DatabaseService created successfully")
        logging.info(f"🔧 [BATCH-RECONCILER] Step 1.2: DatabaseService memory location: {id(db_service)}")
        
        logging.info("🔧 [BATCH-RECONCILER] Step 1.3: Creating BatchSyncCoordinator...")
        coordinator = BatchSyncCoordinator(db_service, config_manager)
        logging.info("✅ [BATCH-RECONCILER] Step 1.3: BatchSyncCoordinator created successfully")
        logging.info(f"🔧 [BATCH-RECONCILER] Step 1.3: BatchSyncCoordinator memory location: {id(coordinator)}")
        
        logging.info(f"✅ [BATCH-RECONCILER] Step 1: All services initialized successfully (Trigger: {trigger_type.upper()})")
        
        # Step 2: Check API health before proceeding
        logging.info(f"🏥 [BATCH-RECONCILER] Step 2: Checking Bland AI API health (Trigger: {trigger_type.upper()})...")
        logging.info("🏥 [BATCH-RECONCILER] Step 2.1: Accessing batch_monitor from coordinator...")
        logging.info(f"🏥 [BATCH-RECONCILER] Step 2.1: Batch monitor enabled: {getattr(coordinator.batch_monitor, 'enabled', 'unknown')}")
        logging.info("🏥 [BATCH-RECONCILER] Step 2.1: Calling batch_monitor.check_api_health()...")
        try:
            health_check_start = datetime.utcnow()
            api_healthy = coordinator.batch_monitor.check_api_health()
            health_check_duration = (datetime.utcnow() - health_check_start).total_seconds()
            logging.info(f"🏥 [BATCH-RECONCILER] Step 2.1: API health check result: {api_healthy}")
            logging.info(f"🏥 [BATCH-RECONCILER] Step 2.1: Health check duration: {health_check_duration:.3f}s")
        except Exception as health_error:
            logging.warning(f"⚠️ [BATCH-RECONCILER] Step 2.1: API health check failed: {str(health_error)}")
            logging.warning(f"⚠️ [BATCH-RECONCILER] Step 2.1: Health check exception type: {type(health_error).__name__}")
            logging.warning(f"⚠️ [BATCH-RECONCILER] Step 2.1: Health check traceback: {traceback.format_exc()}")
            api_healthy = False
        
        if not api_healthy:
            logging.warning(f"⚠️ [BATCH-RECONCILER] Step 2: Bland AI API not responding - skipping reconciliation (Trigger: {trigger_type.upper()})")
            _log_execution_summary(request_id, start_time, skipped=True, reason="API health check failed", trigger_type=trigger_type)
            return True  # Return success for skipped execution
        
        logging.info(f"✅ [BATCH-RECONCILER] Step 2: API health check passed (Trigger: {trigger_type.upper()})")
        
        # Step 3: Execute batch reconciliation using Bland AI API
        logging.info(f"🔒 [BATCH-RECONCILER] Step 3: Starting batch reconciliation process (Trigger: {trigger_type.upper()})...")
        logging.info("🔒 [BATCH-RECONCILER] Step 3.1: Querying for stale batches requiring reconciliation...")
        reconciliation_start = datetime.utcnow()

        try:
            # Query for batches that need reconciliation (submitted but not completed/failed)
            stale_batches_query = """
                SELECT batch_id, vendor_batch_id, campaign_id, total_calls_intended,
                       batch_status, submitted_ts, last_status_check_ts
                FROM engage360.outreach_batches
                WHERE batch_status IN ('Submitted', 'Pending')
                  AND vendor_batch_id IS NOT NULL
                  AND (last_status_check_ts IS NULL
                       OR DATEDIFF(MINUTE, last_status_check_ts, SYSDATETIMEOFFSET()) >= 15)
                ORDER BY submitted_ts ASC
            """

            stale_batches = db_service.execute_query(stale_batches_query, (), fetch_results=True)

            if not stale_batches:
                logging.info("📊 [BATCH-RECONCILER] Step 3.1: No stale batches requiring reconciliation found")
                reconciliation_duration = (datetime.utcnow() - reconciliation_start).total_seconds()
                logging.info(f"📊 [BATCH-RECONCILER] Step 3: Batch reconciliation completed - Duration: {reconciliation_duration:.3f}s")
            else:
                logging.info(f"📊 [BATCH-RECONCILER] Step 3.1: Found {len(stale_batches)} stale batches to reconcile")

                # Step 3.2: Process each stale batch
                batches_updated = 0
                batches_failed = 0

                for batch in stale_batches:
                    batch_id = batch['batch_id']
                    vendor_batch_id = batch['vendor_batch_id']
                    total_calls_intended = batch['total_calls_intended']

                    logging.info(f"🔍 [BATCH-RECONCILER] Step 3.2: Processing batch {vendor_batch_id}")

                    try:
                        # Call Bland AI API to get batch logs
                        import requests

                        bland_api_key = config_manager.get_config('BlandAIkey')
                        api_url = f"https://api.bland.ai/v2/batches/{vendor_batch_id}/logs"
                        headers = {"authorization": bland_api_key}

                        logging.info(f"🌐 [BATCH-RECONCILER] Calling Bland AI API for batch logs...")
                        response = requests.get(api_url, headers=headers, timeout=30)
                        response.raise_for_status()

                        batch_logs = response.json()
                        logging.info(f"✅ [BATCH-RECONCILER] Retrieved batch logs from Bland AI")

                        # Parse batch completion status from logs
                        batch_status = _parse_batch_status_from_logs(batch_logs)

                        if batch_status:
                            # Update outreach_batches table
                            update_query = """
                                UPDATE engage360.outreach_batches
                                SET batch_status = %s,
                                    total_calls_completed = %s,
                                    total_calls_failed = %s,
                                    last_status_check_ts = SYSDATETIMEOFFSET(),
                                    api_reconciled = 1,
                                    updated_ts = SYSDATETIMEOFFSET()
                                WHERE batch_id = %s
                            """

                            params = (
                                batch_status['status'],
                                batch_status.get('completed_count', 0),
                                batch_status.get('failed_count', 0),
                                batch_id
                            )

                            db_service.execute_query(update_query, params, fetch_results=False)
                            batches_updated += 1

                            logging.info(f"✅ [BATCH-RECONCILER] Updated batch {vendor_batch_id}")
                            logging.info(f"   - Status: {batch_status['status']}")
                            logging.info(f"   - Completed: {batch_status.get('completed_count', 0)}")
                            logging.info(f"   - Failed: {batch_status.get('failed_count', 0)}")
                        else:
                            # Just update last check timestamp
                            update_ts_query = """
                                UPDATE engage360.outreach_batches
                                SET last_status_check_ts = SYSDATETIMEOFFSET()
                                WHERE batch_id = %s
                            """
                            db_service.execute_query(update_ts_query, (batch_id,), fetch_results=False)
                            logging.info(f"ℹ️ [BATCH-RECONCILER] No status change for batch {vendor_batch_id}")

                    except requests.exceptions.RequestException as api_error:
                        batches_failed += 1
                        logging.error(f"❌ [BATCH-RECONCILER] API error for batch {vendor_batch_id}: {str(api_error)}")

                        # Update last check timestamp even on error
                        update_ts_query = """
                            UPDATE engage360.outreach_batches
                            SET last_status_check_ts = SYSDATETIMEOFFSET(),
                                status_reason = %s
                            WHERE batch_id = %s
                        """
                        db_service.execute_query(update_ts_query, (f"API error: {str(api_error)[:200]}", batch_id), fetch_results=False)

                    except Exception as batch_error:
                        batches_failed += 1
                        logging.error(f"❌ [BATCH-RECONCILER] Error processing batch {vendor_batch_id}: {str(batch_error)}")
                        logging.error(f"❌ [BATCH-RECONCILER] Traceback: {traceback.format_exc()}")

                reconciliation_duration = (datetime.utcnow() - reconciliation_start).total_seconds()
                logging.info(f"📊 [BATCH-RECONCILER] Step 3: Batch reconciliation completed - Duration: {reconciliation_duration:.3f}s")
                logging.info(f"📊 [BATCH-RECONCILER] Summary: {batches_updated} updated, {batches_failed} failed, {len(stale_batches)} total")

        except Exception as reconcile_error:
            logging.error(f"🚨 [BATCH-RECONCILER] Step 3: Reconciliation error: {str(reconcile_error)}")
            logging.error(f"🚨 [BATCH-RECONCILER] Step 3: Error type: {type(reconcile_error).__name__}")
            logging.error(f"🚨 [BATCH-RECONCILER] Step 3: Error traceback: {traceback.format_exc()}")
            raise
        
        logging.info(f"✅ [BATCH-RECONCILER] All steps completed successfully (Trigger: {trigger_type.upper()})")
        _log_execution_summary(request_id, start_time, skipped=False, trigger_type=trigger_type)
        
        return True
        
    finally:
        # Step 4: Cleanup resources
        logging.info(f"🧹 [BATCH-RECONCILER] Step 4: Starting cleanup process (Trigger: {trigger_type.upper()})...")
        cleanup_start = datetime.utcnow()
        if db_service:
            try:
                logging.info("🧹 [BATCH-RECONCILER] Step 4.1: DatabaseService cleanup...")
                logging.info(f"🧹 [BATCH-RECONCILER] Step 4.1: DatabaseService reference: {id(db_service)}")
                # DatabaseService cleanup (if needed) - currently no explicit cleanup required
                cleanup_duration = (datetime.utcnow() - cleanup_start).total_seconds()
                logging.info("✅ [BATCH-RECONCILER] Step 4.1: DatabaseService cleanup completed")
                logging.info(f"✅ [BATCH-RECONCILER] Step 4: All cleanup completed successfully - Duration: {cleanup_duration:.3f}s")
            except Exception as cleanup_error:
                logging.error(f"⚠️ [BATCH-RECONCILER] Step 4: Error during cleanup: {str(cleanup_error)}")
                logging.error(f"⚠️ [BATCH-RECONCILER] Step 4: Cleanup error type: {type(cleanup_error).__name__}")
                logging.error(f"⚠️ [BATCH-RECONCILER] Step 4: Cleanup error traceback: {traceback.format_exc()}")
        else:
            logging.info("ℹ️ [BATCH-RECONCILER] Step 4: No services to cleanup")

def _parse_batch_status_from_logs(batch_logs: dict) -> dict:
    """
    Parse Bland AI batch logs to extract completion status and statistics.

    Args:
        batch_logs: Response from Bland AI /v2/batches/{batch_id}/logs endpoint

    Returns:
        dict with keys: status, completed_count, failed_count
        or None if status cannot be determined
    """
    try:
        # Look for "complete" event type in logs
        if not batch_logs or not isinstance(batch_logs, dict):
            return None

        # Bland AI batch logs structure: list of events
        events = batch_logs.get('events', []) or batch_logs.get('logs', [])

        if not events:
            return None

        # Find the most recent completion event
        completion_event = None
        for event in reversed(events):
            if event.get('event_type') == 'complete':
                completion_event = event
                break

        if completion_event:
            # Extract statistics from completion event
            data = completion_event.get('data', {}) or {}

            completed_count = data.get('completed_count', 0) or data.get('successful_calls', 0)
            failed_count = data.get('failed_count', 0) or data.get('failed_calls', 0)
            total_count = data.get('total_count', 0)

            return {
                'status': 'Completed',
                'completed_count': completed_count,
                'failed_count': failed_count,
                'total_count': total_count
            }

        # Check for in-progress status
        for event in reversed(events):
            event_type = event.get('event_type', '').lower()
            if event_type in ['in progress', 'dispatching', 'validating']:
                # Still in progress, update timestamp but don't change status
                return None

        # If no clear status found, return None
        return None

    except Exception as e:
        logging.error(f"❌ [BATCH-RECONCILER] Error parsing batch logs: {str(e)}")
        return None

def _log_execution_summary(request_id: str, start_time: datetime, skipped: bool = False, reason: str = None, trigger_type: str = "timer"):
    """
    Log execution summary following IOE logging pattern
    
    Args:
        request_id: Unique identifier for this execution
        start_time: When execution started
        skipped: Whether execution was skipped
        reason: Reason for skipping (if applicable)
        trigger_type: Type of trigger that initiated execution
    """
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    logging.info("=" * 80)
    
    if skipped:
        logging.info(f"⏭️ [BATCH-RECONCILER] EXECUTION SKIPPED (Trigger: {trigger_type.upper()})")
        logging.info(f"❓ [BATCH-RECONCILER] Reason: {reason or 'Unknown'}")
    else:
        logging.info(f"🎉 [BATCH-RECONCILER] EXECUTION COMPLETED SUCCESSFULLY (Trigger: {trigger_type.upper()})")
        logging.info(f"🔄 [BATCH-RECONCILER] Function: Batch completion status reconciliation")
        logging.info(f"⚡ [BATCH-RECONCILER] Scope: Batch-level status updates only")
        logging.info(f"🔗 [BATCH-RECONCILER] Integration: Works alongside webhook system")
    
    logging.info(f"⏱️ [BATCH-RECONCILER] Total Duration: {duration:.3f} seconds")
    logging.info(f"📋 [BATCH-RECONCILER] Request ID: {request_id}")
    logging.info(f"🚀 [BATCH-RECONCILER] Trigger Type: {trigger_type.upper()}")
    logging.info(f"🕒 [BATCH-RECONCILER] Next timer execution: 30 minutes")
    logging.info(f"📊 [BATCH-RECONCILER] Execution time: {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Additional context for operators
    if not skipped:
        logging.info("📝 [BATCH-RECONCILER] Note: Individual call updates handled by webhooks")
        logging.info("🎯 [BATCH-RECONCILER] This function only reconciles batch completion status")
        logging.info("🔒 [BATCH-RECONCILER] Distributed locking prevents execution overlap")
        if trigger_type == "http":
            logging.info("🌐 [BATCH-RECONCILER] HTTP trigger allows manual reconciliation")
    
    logging.info("=" * 80)