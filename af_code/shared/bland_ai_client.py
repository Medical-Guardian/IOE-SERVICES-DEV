import logging
import requests
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from ..bland_ai_webhook.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BlandAIClient:
    """
    Shared Bland AI API client following IOE patterns

    Uses synchronous HTTP requests (requests library) for batch submission.
    This follows the architecture pattern used by DTC Intro Call function.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        # Use the same Key Vault secret name as DTC functions
        self.api_key = config_manager.get_config("BlandAIkey")
        self.base_url = config_manager.get_config("BLAND_AI_BASE_URL", "https://api.bland.ai")

        if not self.api_key:
            logger.error("🚨 [BLAND-CLIENT] BlandAIkey not configured in Key Vault")
            raise ValueError("Bland AI API key is required")

        logger.info("🔧 [BLAND-CLIENT] Client initialized successfully")
        logger.info(f"🌐 [BLAND-CLIENT] Base URL: {self.base_url}")
        logger.info(f"ℹ️ [BLAND-CLIENT] Webhook URL will be provided per-batch from campaign configuration")

    def submit_batch_calls(self, batch_request) -> Dict[str, Any]:
        """
        Submit batch call request to Bland AI (SYNCHRONOUS)

        Uses requests.post() to make a blocking HTTP call.
        Waits for Bland AI to accept the batch and return a batch_id.
        Timeout: 60 seconds (blocks for max 60 seconds)

        Args:
            batch_request: BatchRequest object with calls, pathway_id, voice_id

        Returns:
            Dict with success status, batch_id, and error details if failed
        """
        logger.info(f"🚀 [BLAND-CLIENT] Submitting batch with {len(batch_request.calls)} calls")
        logger.info(f"📋 [BLAND-CLIENT] Campaign ID: {batch_request.campaign_id}")

        # Validate webhook_url is provided
        if not batch_request.webhook_url:
            error_msg = "Webhook URL is required in batch_request (from campaign bland_parameters_global)"
            logger.error(f"🚨 [BLAND-CLIENT] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Generate unique batch ID using UUID
            batch_id = str(uuid.uuid4())

            payload = {
                "batch_id": batch_id,
                "calls": batch_request.calls,
                "pathway_id": batch_request.pathway_id,
                "voice_id": batch_request.voice_id,
                "webhook_url": batch_request.webhook_url,  # From campaign configuration
                "max_duration": batch_request.max_duration or "300",  # From campaign or default
                "analysis_schema": {
                    "disposition_analysis": True,
                    "sentiment_analysis": True,
                    "call_quality_scoring": True
                }
            }

            logger.info(f"📦 [BLAND-CLIENT] Batch ID: {batch_id}")
            logger.info(f"🎭 [BLAND-CLIENT] Pathway ID: {batch_request.pathway_id}")
            logger.info(f"🎤 [BLAND-CLIENT] Voice ID: {batch_request.voice_id}")
            logger.info(f"🔗 [BLAND-CLIENT] Webhook URL: {batch_request.webhook_url}")
            logger.info(f"⏱️ [BLAND-CLIENT] Max Duration: {batch_request.max_duration or '300'}s")
            logger.info(f"📞 [BLAND-CLIENT] Number of calls: {len(batch_request.calls)}")
            logger.info(f"⏱️ [BLAND-CLIENT] Submitting with 60 second timeout (SYNCHRONOUS)")

            # Log complete payload for debugging (with first call sample)
            logger.info("=" * 80)
            logger.info("📋 [BLAND-CLIENT] COMPLETE BLAND AI BATCH PAYLOAD:")
            logger.info("=" * 80)
            logger.info(f"🌐 [BLAND-CLIENT] API Endpoint: {self.base_url}/v1/batches")
            logger.info(f"🔑 [BLAND-CLIENT] API Key: {'*' * 20}{self.api_key[-8:] if len(self.api_key) > 8 else '***'}")
            logger.info(f"📦 [BLAND-CLIENT] Payload Structure:")
            logger.info(f"   - batch_id: {payload['batch_id']}")
            logger.info(f"   - pathway_id: {payload['pathway_id']}")
            logger.info(f"   - voice_id: {payload['voice_id']}")
            logger.info(f"   - webhook_url: {payload['webhook_url']}")
            logger.info(f"   - max_duration: {payload['max_duration']}")
            logger.info(f"   - analysis_schema: {json.dumps(payload['analysis_schema'])}")
            logger.info(f"   - calls: [{len(payload['calls'])} calls]")

            # Log first call as sample
            if payload['calls']:
                logger.info(f"📞 [BLAND-CLIENT] Sample Call (first call):")
                sample_call = payload['calls'][0]
                logger.info(f"   - to: {sample_call.get('to')}")
                logger.info(f"   - request_data keys: {list(sample_call.get('request_data', {}).keys())}")
                logger.info(f"   - metadata keys: {list(sample_call.get('metadata', {}).keys())}")
                logger.info(f"📋 [BLAND-CLIENT] Full sample call:")
                logger.info(json.dumps(sample_call, indent=2, default=str))

            # Log FULL payload as JSON for debugging
            logger.info("📄 [BLAND-CLIENT] COMPLETE JSON PAYLOAD:")
            try:
                full_payload_json = json.dumps(payload, indent=2, default=str)
                logger.info(full_payload_json)
            except Exception as e:
                logger.error(f"❌ [BLAND-CLIENT] Error serializing payload to JSON: {str(e)}")

            logger.info("=" * 80)

            # SYNCHRONOUS HTTP POST - blocks until response or timeout
            response = requests.post(
                f"{self.base_url}/v1/batches",
                headers=headers,
                json=payload,
                timeout=60  # Wait max 60 seconds
            )

            logger.info(f"📡 [BLAND-CLIENT] Response status: {response.status_code}")
            logger.info(f"📡 [BLAND-CLIENT] Response headers: {dict(response.headers)}")
            logger.info(f"📡 [BLAND-CLIENT] Response content length: {len(response.content)} bytes")

            try:
                response_data = response.json()
                logger.info(f"📡 [BLAND-CLIENT] Response JSON: {json.dumps(response_data, indent=2)}")
            except json.JSONDecodeError:
                response_text = response.text
                logger.error(f"❌ [BLAND-CLIENT] Invalid JSON response (status {response.status_code})")
                logger.error(f"❌ [BLAND-CLIENT] Response text: '{response_text}'")
                logger.error(f"❌ [BLAND-CLIENT] Response content (raw bytes): {response.content}")
                logger.error(f"❌ [BLAND-CLIENT] Request URL: {self.base_url}/v1/batches")
                logger.error(f"❌ [BLAND-CLIENT] Request method: POST")
                return {
                    "success": False,
                    "error": f"Invalid JSON response (HTTP {response.status_code}): {response_text if response_text else 'Empty response'}",
                    "status_code": response.status_code
                }

            if response.status_code == 200:
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
                error_msg = response_data.get("error", f"HTTP {response.status_code}: {response.text}")
                logger.error(f"❌ [BLAND-CLIENT] Batch submission failed: {error_msg}")
                logger.error(f"📡 [BLAND-CLIENT] Response: {response.text}")

                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "response": response_data
                }

        except requests.exceptions.Timeout:
            error_msg = "Request timeout - Bland AI API did not respond within 60 seconds"
            logger.error(f"⏰ [BLAND-CLIENT] {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"HTTP request error: {str(e)}"
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