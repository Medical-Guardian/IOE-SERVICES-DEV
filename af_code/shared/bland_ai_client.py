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
        # Use the same Key Vault secret names as DTC functions
        self.api_key = config_manager.get_config("BlandAIkey")
        self.encrypted_key = config_manager.get_config("Blandaitwilio")  # Twilio encryption key
        self.batch_url = config_manager.get_config("BLAND_AI_BATCH_URL", "https://api.bland.ai/v2/batches/create")

        if not self.api_key:
            logger.error("🚨 [BLAND-CLIENT] BlandAIkey not configured in Key Vault")
            raise ValueError("Bland AI API key is required")

        if not self.encrypted_key:
            logger.warning("⚠️ [BLAND-CLIENT] Blandaitwilio (encrypted_key) not configured in Key Vault")
            logger.warning("⚠️ [BLAND-CLIENT] encrypted_key header will not be sent (DTC pattern requires this)")

        logger.info("🔧 [BLAND-CLIENT] Client initialized successfully")
        logger.info(f"🌐 [BLAND-CLIENT] Batch URL: {self.batch_url}")
        logger.info(f"🔑 [BLAND-CLIENT] API Key (BlandAIkey): {'✅ Configured' if self.api_key else '❌ Missing'}")
        logger.info(f"🔐 [BLAND-CLIENT] Encrypted Key (Blandaitwilio): {'✅ Configured' if self.encrypted_key else '❌ Missing'}")
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

        try:
            # Build headers following DTC pattern (3 headers total)
            headers = {
                "Authorization": f"Bearer {self.api_key}",  # 1. Bland AI API authentication
                "Content-Type": "application/json",          # 2. JSON payload format
            }

            # 3. Add encrypted_key header if available (DTC pattern - Twilio encryption key)
            if self.encrypted_key:
                headers["encrypted_key"] = self.encrypted_key
                logger.info("🔐 [BLAND-CLIENT] Added encrypted_key header (Blandaitwilio)")
            else:
                logger.warning("⚠️ [BLAND-CLIENT] encrypted_key header NOT added (Blandaitwilio not configured)")

            # Build DTC-style payload with ALL global configuration parameters
            # Following EXACT structure from af_dtc_intro_call/services/blandai_service.py
            # Extract all 18+ parameters from bland_parameters_global JSON
            bland_params = batch_request.bland_parameters_global or {}

            # Build global_config with ALL parameters (filter None values like DTC)
            global_config = {
                k: v
                for k, v in {
                    "pathway_id": batch_request.pathway_id,
                    "pathway_version": bland_params.get("pathway_version"),
                    "voice": batch_request.voice_id,
                    "wait_for_greeting": bland_params.get("wait_for_greeting"),
                    "record": bland_params.get("record"),
                    "answered_by_enabled": bland_params.get("answered_by_enabled"),
                    "noise_cancellation": bland_params.get("noise_cancellation"),
                    "interruption_threshold": bland_params.get("interruption_threshold"),
                    "block_interruptions": bland_params.get("block_interruptions"),
                    "max_duration": bland_params.get("max_duration"),
                    "model": bland_params.get("model"),
                    "temperature": bland_params.get("temperature"),
                    "language": bland_params.get("language"),
                    "background_track": bland_params.get("background_track"),
                    "endpoint": bland_params.get("endpoint"),
                    "from": bland_params.get("from"),  # "from" phone number
                    "timezone": bland_params.get("timezone"),
                    "webhook": bland_params.get("webhook") or bland_params.get("webhook_url"),  # Support both field names
                }.items()
                if v is not None  # Only include non-None values (DTC pattern)
            }

            logger.info(f"🔧 [BLAND-CLIENT] Built global config with {len(global_config)} parameters")
            logger.info(f"📋 [BLAND-CLIENT] Included parameters: {list(global_config.keys())}")

            # Validate required webhook parameter
            if "webhook" not in global_config or not global_config["webhook"]:
                error_msg = "Webhook URL is required in bland_parameters_global JSON"
                logger.error(f"🚨 [BLAND-CLIENT] {error_msg}")
                logger.error(f"🚨 [BLAND-CLIENT] Available parameters: {list(global_config.keys())}")
                return {
                    "success": False,
                    "error": error_msg
                }

            # Convert "calls" to "call_objects" with "phone_number" field (DTC format)
            call_objects = []
            for call in batch_request.calls:
                call_obj = {
                    "phone_number": call["to"],  # Rename "to" to "phone_number"
                    "request_data": call["request_data"],
                    "metadata": call["metadata"]
                }
                call_objects.append(call_obj)

            payload = {
                "global": global_config,
                "call_objects": call_objects
            }

            logger.info(f"📞 [BLAND-CLIENT] Number of calls: {len(call_objects)}")
            logger.info(f"⏱️ [BLAND-CLIENT] Submitting with 60 second timeout (SYNCHRONOUS)")

            # Log complete payload for debugging (with first call sample)
            logger.info("=" * 80)
            logger.info("📋 [BLAND-CLIENT] COMPLETE BLAND AI BATCH PAYLOAD:")
            logger.info("=" * 80)
            logger.info(f"🌐 [BLAND-CLIENT] API Endpoint: {self.batch_url}")
            logger.info(f"📨 [BLAND-CLIENT] Headers ({len(headers)} total):")
            for header_name, header_value in headers.items():
                if header_name == "Authorization":
                    logger.info(f"     • {header_name}: Bearer {'*' * 20}{self.api_key[-8:] if len(self.api_key) > 8 else '***'}")
                elif header_name == "encrypted_key":
                    logger.info(f"     • {header_name}: {'*' * 20}{self.encrypted_key[-8:] if len(self.encrypted_key) > 8 else '***'}")
                else:
                    logger.info(f"     • {header_name}: {header_value}")
            logger.info(f"📦 [BLAND-CLIENT] Payload Structure:")
            logger.info(f"   - global: {len(global_config)} parameters")
            # Log ALL global parameters
            for param_name, param_value in global_config.items():
                logger.info(f"     • {param_name}: {param_value}")
            logger.info(f"   - call_objects: [{len(call_objects)} calls]")

            # Log first call as sample
            if call_objects:
                logger.info(f"📞 [BLAND-CLIENT] Sample Call (first call):")
                sample_call = call_objects[0]
                logger.info(f"   - phone_number: {sample_call.get('phone_number')}")
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
                self.batch_url,  # Use configured batch URL (default: https://api.bland.ai/v2/batches/create)
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
                logger.error(f"❌ [BLAND-CLIENT] Request URL: {self.batch_url}")
                logger.error(f"❌ [BLAND-CLIENT] Request method: POST")
                return {
                    "success": False,
                    "error": f"Invalid JSON response (HTTP {response.status_code}): {response_text if response_text else 'Empty response'}",
                    "status_code": response.status_code
                }

            if response.status_code == 200:
                # Bland AI returns batch_id in the response
                returned_batch_id = response_data.get("batch_id")
                logger.info(f"✅ [BLAND-CLIENT] Batch submitted successfully")
                logger.info(f"📦 [BLAND-CLIENT] Returned Batch ID: {returned_batch_id}")
                logger.info(f"📊 [BLAND-CLIENT] Calls queued: {len(call_objects)}")

                return {
                    "success": True,
                    "batch_id": returned_batch_id,
                    "calls_submitted": len(call_objects),
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