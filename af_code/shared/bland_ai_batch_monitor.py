import logging
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from ..bland_ai_webhook.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BlandAIBatchMonitor:
    """
    Bland AI Batch Monitoring client for v2 API endpoints
    Handles batch status checking and completion monitoring
    Following IOE patterns for API communication and error handling
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.api_key = config_manager.get_config("BLAND_AI_API_KEY")
        self.base_url = config_manager.get_config("BLAND_AI_BASE_URL", "https://api.bland.ai")
        
        if not self.api_key:
            logger.error("🚨 [BATCH-MONITOR] BLAND_AI_API_KEY not configured")
            raise ValueError("Bland AI API key is required for batch monitoring")
        
        logger.info("🔧 [BATCH-MONITOR] Batch monitor initialized successfully")
        logger.info(f"🌐 [BATCH-MONITOR] Base URL: {self.base_url}")
    
    async def get_batch_summary_status(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get batch-level status summary from Bland AI v2 API
        
        Args:
            batch_id: The Bland AI batch ID to check
            
        Returns:
            Dict with batch status information or None if error
        """
        logger.info(f"📊 [BATCH-MONITOR] Getting batch status for: {batch_id}")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Get batch metadata
                async with session.get(
                    f"{self.base_url}/v2/batches/{batch_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status == 404:
                        logger.warning(f"⚠️ [BATCH-MONITOR] Batch not found: {batch_id}")
                        return None
                    
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"❌ [BATCH-MONITOR] API error {response.status}: {response_text}")
                        return None
                    
                    batch_data = await response.json()
                    logger.info(f"✅ [BATCH-MONITOR] Retrieved batch metadata for: {batch_id}")
                    
                    # Analyze batch completion status
                    return await self._analyze_batch_status(batch_id, batch_data)
                    
        except aiohttp.ClientTimeout:
            logger.error(f"⏰ [BATCH-MONITOR] Timeout getting batch status for: {batch_id}")
            return None
            
        except aiohttp.ClientError as e:
            logger.error(f"🌐 [BATCH-MONITOR] HTTP error getting batch status: {str(e)}")
            return None
            
        except Exception as e:
            logger.error(f"🚨 [BATCH-MONITOR] Unexpected error getting batch status: {str(e)}")
            return None
    
    async def get_batch_detailed_logs(self, batch_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get detailed batch logs from Bland AI v2 API
        
        Args:
            batch_id: The Bland AI batch ID to get logs for
            
        Returns:
            List of log entries or None if error
        """
        logger.info(f"📋 [BATCH-MONITOR] Getting detailed logs for batch: {batch_id}")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Get batch logs
                async with session.get(
                    f"{self.base_url}/v2/batches/{batch_id}/logs",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)  # Longer timeout for logs
                ) as response:
                    
                    if response.status == 404:
                        logger.warning(f"⚠️ [BATCH-MONITOR] Batch logs not found: {batch_id}")
                        return None
                    
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"❌ [BATCH-MONITOR] API error getting logs {response.status}: {response_text}")
                        return None
                    
                    logs_data = await response.json()
                    logs = logs_data.get('data', [])
                    
                    logger.info(f"✅ [BATCH-MONITOR] Retrieved {len(logs)} log entries for batch: {batch_id}")
                    return logs
                    
        except aiohttp.ClientTimeout:
            logger.error(f"⏰ [BATCH-MONITOR] Timeout getting batch logs for: {batch_id}")
            return None
            
        except aiohttp.ClientError as e:
            logger.error(f"🌐 [BATCH-MONITOR] HTTP error getting batch logs: {str(e)}")
            return None
            
        except Exception as e:
            logger.error(f"🚨 [BATCH-MONITOR] Unexpected error getting batch logs: {str(e)}")
            return None
    
    async def get_recent_batches(self, hours_back: int = 24) -> Optional[List[Dict[str, Any]]]:
        """
        Get list of recent batches for reconciliation
        
        Args:
            hours_back: How many hours back to look for batches
            
        Returns:
            List of batch metadata or None if error
        """
        logger.info(f"📅 [BATCH-MONITOR] Getting batches from last {hours_back} hours...")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Get batch list (may need pagination for large volumes)
                async with session.get(
                    f"{self.base_url}/v2/batches/list",
                    headers=headers,
                    params={"take": 100},  # Adjust as needed
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(f"❌ [BATCH-MONITOR] API error getting batch list {response.status}: {response_text}")
                        return None
                    
                    batches_data = await response.json()
                    all_batches = batches_data.get('data', [])
                    
                    # Filter to recent batches only
                    cutoff_time = datetime.now().replace(microsecond=0)
                    cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - hours_back)
                    
                    recent_batches = []
                    for batch in all_batches:
                        created_at_str = batch.get('created_at', '')
                        if created_at_str:
                            try:
                                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                if created_at >= cutoff_time:
                                    recent_batches.append(batch)
                            except ValueError:
                                # Skip batches with invalid timestamps
                                continue
                    
                    logger.info(f"✅ [BATCH-MONITOR] Found {len(recent_batches)} recent batches out of {len(all_batches)} total")
                    return recent_batches
                    
        except aiohttp.ClientTimeout:
            logger.error(f"⏰ [BATCH-MONITOR] Timeout getting recent batches")
            return None
            
        except aiohttp.ClientError as e:
            logger.error(f"🌐 [BATCH-MONITOR] HTTP error getting recent batches: {str(e)}")
            return None
            
        except Exception as e:
            logger.error(f"🚨 [BATCH-MONITOR] Unexpected error getting recent batches: {str(e)}")
            return None
    
    async def _analyze_batch_status(self, batch_id: str, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze batch data to determine completion status
        
        Args:
            batch_id: The batch ID being analyzed
            batch_data: Raw batch data from API
            
        Returns:
            Analyzed status information
        """
        logger.debug(f"🔍 [BATCH-MONITOR] Analyzing batch status for: {batch_id}")
        
        try:
            # Extract call objects from batch data
            call_objects = batch_data.get('data', {}).get('call_objects', [])
            total_calls = len(call_objects)
            
            if total_calls == 0:
                logger.warning(f"⚠️ [BATCH-MONITOR] No call objects found in batch: {batch_id}")
                return {
                    "batch_id": batch_id,
                    "is_complete": False,
                    "has_failures": False,
                    "total_calls": 0,
                    "total_completed": 0,
                    "total_failed": 0,
                    "completion_percentage": 0.0
                }
            
            # Count call statuses
            completed_count = 0
            failed_count = 0
            in_progress_count = 0
            
            for call_obj in call_objects:
                status = call_obj.get('status', '').lower()
                
                if status in ['completed', 'answered', 'finished']:
                    completed_count += 1
                elif status in ['failed', 'error', 'no_answer', 'busy', 'cancelled']:
                    failed_count += 1
                else:
                    # Assume in progress if not clearly completed or failed
                    in_progress_count += 1
            
            # Determine completion status
            calls_processed = completed_count + failed_count
            is_complete = (calls_processed == total_calls)
            has_failures = (failed_count > 0)
            completion_percentage = (calls_processed / total_calls) * 100 if total_calls > 0 else 0
            
            status_summary = {
                "batch_id": batch_id,
                "is_complete": is_complete,
                "has_failures": has_failures,
                "total_calls": total_calls,
                "total_completed": completed_count,
                "total_failed": failed_count,
                "total_in_progress": in_progress_count,
                "completion_percentage": round(completion_percentage, 2),
                "analyzed_at": datetime.now().isoformat()
            }
            
            logger.info(f"📊 [BATCH-MONITOR] Batch analysis complete for {batch_id}:")
            logger.info(f"   📞 Total calls: {total_calls}")
            logger.info(f"   ✅ Completed: {completed_count}")
            logger.info(f"   ❌ Failed: {failed_count}")
            logger.info(f"   ⏳ In progress: {in_progress_count}")
            logger.info(f"   📈 Completion: {completion_percentage:.1f}%")
            logger.info(f"   🎯 Is complete: {is_complete}")
            
            return status_summary
            
        except Exception as e:
            logger.error(f"🚨 [BATCH-MONITOR] Error analyzing batch status: {str(e)}")
            return {
                "batch_id": batch_id,
                "is_complete": False,
                "has_failures": True,
                "error": str(e)
            }
    
    async def check_api_health(self) -> bool:
        """
        Check if Bland AI API is accessible
        
        Returns:
            bool: True if API is responding, False otherwise
        """
        logger.info("🏥 [BATCH-MONITOR] Checking Bland AI API health...")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Try to get batch list as a health check
                async with session.get(
                    f"{self.base_url}/v2/batches/list",
                    headers=headers,
                    params={"take": 1},  # Minimal request
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    is_healthy = response.status in [200, 404]  # 404 is ok if no batches exist
                    
                    if is_healthy:
                        logger.info("✅ [BATCH-MONITOR] Bland AI API is healthy")
                    else:
                        logger.warning(f"⚠️ [BATCH-MONITOR] Bland AI API returned status: {response.status}")
                    
                    return is_healthy
                    
        except Exception as e:
            logger.error(f"🚨 [BATCH-MONITOR] API health check failed: {str(e)}")
            return False