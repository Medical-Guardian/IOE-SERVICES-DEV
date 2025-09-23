# NEW FILE: This service is a modified copy for the DTC Wellness Check campaign.
# It handles all interactions with the Bland AI API and database logging for this specific campaign.

import logging
import json
import requests
import uuid
from typing import List, Dict
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# Import shared services and utilities
# Note: These imports assume the file is placed in af_code/af_dtc_wellness_check/services/
from af_code.af_dtc_intro_call.services.database_service import DatabaseService
from af_code.af_dtc_intro_call.utils.config import (
    KEY_VAULT_URL, BLAND_AI_BATCH_URL, GET_CAMPAIGN_CONFIG_QUERY,
    CREATE_BATCH_QUERY, CREATE_ATTEMPT_QUERY, GET_MEMBERS_WITH_ATTEMPTS_QUERY,
    UPDATE_BATCH_VENDOR_ID_QUERY, UPDATE_BATCH_FAILED_QUERY)


logger = logging.getLogger(__name__)

class BlandAIServiceWellness:
    """Service to handle Bland AI API operations for the Wellness Check campaign."""
    MEMBER_LIMIT = 1000

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("🤖 [BlandAIServiceWellness] Initializing Bland AI service for Wellness Check")

    def get_campaign_config(self, campaign_id: str) -> Dict:
        """Get campaign configuration from database."""
        logger.info(f"⚙️ [BlandAIServiceWellness] Getting campaign configuration for: {campaign_id}")
        try:
            results = self.db_service.execute_query(GET_CAMPAIGN_CONFIG_QUERY, (campaign_id,))
            if not results:
                raise ValueError(f"No active campaign configuration found for campaign_id: {campaign_id}")

            bland_parameters = results[0]['bland_parameters_global']
            config = json.loads(bland_parameters) if isinstance(bland_parameters, str) else bland_parameters
            logger.info(f"✅ [BlandAIServiceWellness] Campaign configuration retrieved: {list(config.keys())}")
            return config

        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error getting campaign config: {str(e)}")
            raise

    def create_outreach_batch(self, campaign_id: str, member_count: int) -> str:
        """Create outreach batch record in the database."""
        if not campaign_id or not isinstance(member_count, int) or member_count < 0:
            logger.error(f"❌ [BlandAIServiceWellness] Invalid input: campaign_id={campaign_id}, member_count={member_count}")
            raise ValueError("Invalid campaign_id or member_count")

        batch_id = str(uuid.uuid4())
        logger.info(f"📦 [BlandAIServiceWellness] Creating outreach batch: {batch_id}")

        try:
            self.db_service.execute_query(
                CREATE_BATCH_QUERY,
                (batch_id, campaign_id, member_count),
                fetch_results=False
            )
            logger.info(f"✅ [BlandAIServiceWellness] Outreach batch created: {batch_id}")
            return batch_id

        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error creating outreach batch: {str(e)}")
            raise

    def create_outreach_attempts(self, qualified_members: List[Dict], batch_id: str) -> List[str]:
        """Create outreach attempts for qualified members."""
        logger.info(f"📝 [BlandAIServiceWellness] Creating {len(qualified_members)} outreach attempts")
        attempt_ids = []
        try:
            for member in qualified_members:
                attempt_id = str(uuid.uuid4())
                self.db_service.execute_query(
                    CREATE_ATTEMPT_QUERY,
                    (attempt_id, member['enrollment_id'], batch_id),
                    fetch_results=False
                )
                attempt_ids.append(attempt_id)
            logger.info(f"✅ [BlandAIServiceWellness] Created {len(attempt_ids)} outreach attempts")
            return attempt_ids
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error creating outreach attempts: {str(e)}")
            raise

    def get_members_with_attempts(self, batch_id: str) -> List[Dict]:
        """Get members with their attempt IDs for Bland AI payload."""
        logger.info(f"👥 [BlandAIServiceWellness] Getting members with attempts for batch: {batch_id}")
        try:
            members = self.db_service.execute_query(GET_MEMBERS_WITH_ATTEMPTS_QUERY, (batch_id,))
            logger.info(f"✅ [BlandAIServiceWellness] Retrieved {len(members)} members with attempts")
            return members
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error getting members with attempts: {str(e)}")
            raise

    def build_bland_payload(self, config: Dict, members_with_attempts: List[Dict], batch_id: str) -> Dict:
        """Build Bland AI batch payload for the Wellness Check."""
        logger.info(f"🏗️ [BlandAIServiceWellness] Building Wellness Check Bland AI payload for {len(members_with_attempts)} members")
        try:
            global_config = {k: v for k, v in {
                "pathway_id": config.get("pathway_id"),
                "pathway_version": config.get("pathway_version"),
                "voice": config.get("voice"),
                "wait_for_greeting": config.get("wait_for_greeting"),
                "record": config.get("record"),
                "answered_by_enabled": config.get("answered_by_enabled"),
                "noise_cancellation": config.get("noise_cancellation"),
                "interruption_threshold": config.get("interruption_threshold"),
                "block_interruptions": config.get("block_interruptions"),
                "max_duration": config.get("max_duration"),
                "model": config.get("model"),
                "temperature": config.get("temperature"),
                "language": config.get("language"),
                "background_track": config.get("background_track"),
                "endpoint": config.get("endpoint"),
                "from": config.get("from"),
                "timezone": config.get("timezone"),
                "webhook": config.get("webhook")
            }.items() if v is not None}

            call_objects = []
            for member in members_with_attempts:
                dob_obj = member.get('dob')
                dob_str = dob_obj.strftime('%Y-%m-%d') if dob_obj else None

                # Build the request_data object with data from the SQL query
                request_data = {
                    # --- CHANGE AS PER REQUEST ---
                    # The value for call_type_code is now "completed" for the wellness check campaign.
                    "call_type_code": "completed",
                    # --- END CHANGE ---
                    "language_pref": member.get("language_pref"),
                    "first_name": member.get("first_name"),
                    "last_name": member.get("last_name"),
                    "service_address": member.get("address_street"),
                    "zip_code": member.get("address_zip"),
                    "primary_phone": member.get("primary_phone"),
                    "city": member.get("address_city"),
                    "state": member.get("address_state"),
                    "dob": dob_str
                }

                # Construct the final call object
                call_obj = {
                    "phone_number": member["primary_phone"],
                    "request_data": request_data,
                    "metadata": {
                        "batch_id": batch_id,
                        "campaign_id": str(member.get("campaign_id")),
                        "pathway_id": str(config.get("pathway_id")),
                        "attempt_id": str(member.get("attempt_id")),
                        "member_id": str(member.get("member_id")),
                        "salesforce_account_number": member.get("salesforce_account_number"),
                        "first_name": member.get("first_name"),
                        "last_name": member.get("last_name"),
                        "called_number": member.get("primary_phone"),
                        "language_pref": member.get("language_pref"),
                        "call_type_code": member.get("call_type")
                    }
                }

                call_objects.append(call_obj)

            payload = {"global": global_config, "call_objects": call_objects}
            logger.info(f"✅ [BlandAIServiceWellness] Wellness payload built: {len(call_objects)} call objects")
            return payload
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error building Bland AI payload: {str(e)}")
            raise

    def get_bland_api_key(self) -> str:
        """Get Bland AI API key from Azure Key Vault."""
        logger.info("🔑 [BlandAIServiceWellness] Getting Bland AI API key")
        try:
            if not KEY_VAULT_URL:
                raise ValueError("Environment variable 'KEY_VAULT_URL' is not set")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
            secret = client.get_secret("BlandAIkey")

            if not secret or not secret.value:
                raise ValueError("BlandAIkey secret is empty")

            logger.info("✅ [BlandAIServiceWellness] Bland AI API key retrieved")
            return secret.value
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Failed to fetch Bland AI API key: {str(e)}")
            raise

    def call_bland_ai_api(self, payload: Dict, api_key: str) -> Dict:
        """Make API call to Bland AI."""
        logger.info(f"🚀 [BlandAIServiceWellness] Making Bland AI API call with {len(payload.get('call_objects', []))} calls")
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(BLAND_AI_BATCH_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            logger.info(f"✅ [BlandAIServiceWellness] API call successful: {list(result.keys())}")
            return result
        except (requests.exceptions.Timeout, requests.exceptions.HTTPError, requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logger.error(f"💥 [BlandAIServiceWellness] API call failed: {str(e)}")
            raise

    def update_batch_with_vendor_id(self, batch_id: str, vendor_batch_id: str):
        """Update batch with vendor batch ID."""
        logger.info(f"🔄 [BlandAIServiceWellness] Updating batch {batch_id} with vendor ID: {vendor_batch_id}")
        try:
            self.db_service.execute_query(UPDATE_BATCH_VENDOR_ID_QUERY, (vendor_batch_id, batch_id), fetch_results=False)
            logger.info(f"✅ [BlandAIServiceWellness] Batch updated successfully")
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error updating batch with vendor ID: {str(e)}")
            raise

    def update_batch_failed(self, batch_id: str, error_message: str):
        """Update batch status to failed."""
        logger.info(f"❌ [BlandAIServiceWellness] Marking batch {batch_id} as failed: {error_message}")
        try:
            self.db_service.execute_query(UPDATE_BATCH_FAILED_QUERY, (error_message, batch_id), fetch_results=False)
            logger.info(f"✅ [BlandAIServiceWellness] Batch failure updated")
        except Exception as e:
            logger.error(f"💥 [BlandAIServiceWellness] Error updating batch as failed: {str(e)}")
            raise