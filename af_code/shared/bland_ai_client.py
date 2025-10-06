import logging
import aiohttp
import json
from typing import Dict, Any, Optional
from datetime import datetime
from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BlandAIClient:
    """
    Shared Bland AI API client following IOE patterns
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.api_key = config_manager.get_config("BLAND_AI_API_KEY")
        self.base_url = config_manager.get_config("BLAND_AI_BASE_URL", "https://api.bland.ai")
        self.webhook_url = config_manager.get_config("BLAND_WEBHOOK_URL")
        
        if not self.api_key:
            logger.error("🚨 [BLAND-CLIENT] BLAND_AI_API_KEY not configured")
            raise ValueError("Bland AI API key is required")
        
        if not self.webhook_url:
            logger.error("🚨 [BLAND-CLIENT] BLAND_WEBHOOK_URL not configured")
            raise ValueError("Bland AI webhook URL is required")
        
        logger.info("🔧 [BLAND-CLIENT] Client initialized successfully")
        logger.info(f"🌐 [BLAND-CLIENT] Base URL: {self.base_url}")
        logger.info(f"🔗 [BLAND-CLIENT] Webhook URL: {self.webhook_url}")
    
    async def submit_batch_calls(self, batch_request) -> Dict[str, Any]:
        """
        Submit batch call request to Bland AI
        """
        logger.info(f"🚀 [BLAND-CLIENT] Submitting batch with {len(batch_request.calls)} calls")
        logger.info(f"📋 [BLAND-CLIENT] Campaign ID: {batch_request.campaign_id}")
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Generate unique batch ID
            timestamp = int(datetime.now().timestamp())
            batch_id = f"partner-{batch_request.campaign_id[-8:]}-{timestamp}"
            
            payload = {
                "batch_id": batch_id,
                "calls": batch_request.calls,
                "pathway_id": batch_request.pathway_id,
                "voice_id": batch_request.voice_id,
                "webhook_url": self.webhook_url,
                "max_duration": self.config_manager.get_config("BLAND_MAX_DURATION", "300"),  # 5 minutes default
                "analysis_schema": {
                    "disposition_analysis": True,
                    "sentiment_analysis": True,
                    "call_quality_scoring": True
                }
            }
            
            logger.info(f"📦 [BLAND-CLIENT] Batch ID: {batch_id}")
            logger.info(f"🎭 [BLAND-CLIENT] Pathway ID: {batch_request.pathway_id}")
            logger.info(f"🎤 [BLAND-CLIENT] Voice ID: {batch_request.voice_id}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/v1/batches",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)  # 60 second timeout
                ) as response:
                    
                    response_text = await response.text()
                    logger.info(f"📡 [BLAND-CLIENT] Response status: {response.status}")
                    
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"❌ [BLAND-CLIENT] Invalid JSON response: {response_text}")
                        return {
                            "success": False,
                            "error": f"Invalid JSON response: {response_text}",
                            "status_code": response.status
                        }
                    
                    if response.status == 200:
                        returned_batch_id = response_data.get("batch_id", batch_id)
                        logger.info(f"✅ [BLAND-CLIENT] Batch submitted successfully")
                        logger.info(f"📦 [BLAND-CLIENT] Returned Batch ID: {returned_batch_id}")
                        logger.info(f"📊 [BLAND-CLIENT] Calls queued: {len(batch_request.calls)}")
                        
                        return {
                            "success": True,
                            "batch_id": returned_batch_id,
                            "calls_submitted": len(batch_request.calls),
                            "response": response_data
                        }
                    else:
                        error_msg = response_data.get("error", f"HTTP {response.status}: {response_text}")
                        logger.error(f"❌ [BLAND-CLIENT] Batch submission failed: {error_msg}")
                        logger.error(f"📡 [BLAND-CLIENT] Response: {response_text}")
                        
                        return {
                            "success": False,
                            "error": error_msg,
                            "status_code": response.status,
                            "response": response_data
                        }
                        
        except aiohttp.ClientTimeout:
            error_msg = "Request timeout - Bland AI API did not respond within 60 seconds"
            logger.error(f"⏰ [BLAND-CLIENT] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except aiohttp.ClientError as e:
            error_msg = f"HTTP client error: {str(e)}"
            logger.error(f"🌐 [BLAND-CLIENT] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"🚨 [BLAND-CLIENT] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }