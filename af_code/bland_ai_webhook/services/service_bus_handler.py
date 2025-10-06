# /bland_ai_webhook/services/service_bus_handler.py

import logging
import json
from typing import Dict, Any, Optional

# FIX: Import the asynchronous version of the ServiceBusClient
from azure.servicebus.aio import ServiceBusClient as AsyncServiceBusClient
from azure.servicebus import ServiceBusMessage
from ..services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class ServiceBusHandler:
    """
    Handles Service Bus operations for sending webhook data to post-call analysis queue.
    Implements retry logic with exponential backoff and dead letter queue support.
    """

    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the ServiceBusHandler with configuration.

        Args:
            config_manager: Configuration manager for accessing Service Bus settings
        """
        self.config_manager = config_manager
        self.connection_string = self.config_manager.get_service_bus_connection_string()
        self.enabled = self.connection_string is not None
        self.queue_name = self.config_manager.get_config(
            "SERVICE_BUS_QUEUE_NAME", "IOE-POSTCALL-ANALYSIS"
        )
        self.max_retries = int(self.config_manager.get_config("SERVICE_BUS_MAX_RETRIES", "3"))
        self.retry_delay = int(
            self.config_manager.get_config("SERVICE_BUS_RETRY_DELAY_SECONDS", "2")
        )
        self.message_ttl_hours = int(
            self.config_manager.get_config("SERVICE_BUS_MESSAGE_TTL_HOURS", "24")
        )

        if not self.connection_string:
            logger.warning("⚠️ [SERVICE-BUS] SERVICE_BUS_CONNECTION_STRING not configured - Service Bus disabled")
            return

        logger.info(
            f"🚌 [SERVICE-BUS] Handler initialized - Queue: {self.queue_name}, Max retries: {self.max_retries}"
        )

    async def send_analysis_message(
        self, webhook_data: Dict[str, Any], mapped_data: Dict[str, Any], request_id: str
    ) -> tuple[bool, Optional[str]]:
        """
        Send message to Service Bus for post-call analysis with retry logic.

        Args:
            webhook_data: Original webhook payload
            mapped_data: Mapped call data
            request_id: Unique request identifier

        Returns:
            tuple[bool, Optional[str]]: (success, message_id or error_message)
        """
        if not self.enabled:
            logger.warning(f"⚠️ [SERVICE-BUS] Service Bus not enabled, skipping message for request_id: {request_id}")
            return True, "service_bus_disabled"
            
        logger.info(f"🚌 [SERVICE-BUS] Sending analysis message for request_id: {request_id}")

        message_content = self._prepare_message_content(webhook_data, mapped_data, request_id)

        for attempt in range(self.max_retries):
            try:
                # FIX: Use the asynchronous client with 'async with'
                async with AsyncServiceBusClient.from_connection_string(
                    self.connection_string
                ) as client:
                    sender = client.get_queue_sender(queue_name=self.queue_name)

                    async with sender:
                        message = ServiceBusMessage(
                            body=json.dumps(message_content),
                            content_type="application/json",
                            subject="postcall-analysis",
                            message_id=f"{webhook_data['call_id']}_{request_id}",
                            correlation_id=request_id,
                            time_to_live=self.message_ttl_hours * 3600,  # Convert hours to seconds
                            application_properties={
                                "source": "bland_webhook",
                                "priority": self._determine_priority(webhook_data, mapped_data),
                                "call_type": "outbound",
                                "campaign_info": webhook_data.get("metadata", {}).get(
                                    "campaign_id", "unknown"
                                ),
                                "attempt_number": attempt + 1,
                            },
                        )

                        await sender.send_messages(message)
                        message_id = message.message_id

                        logger.info(
                            f"✅ [SERVICE-BUS] Message sent successfully - ID: {message_id}"
                        )
                        return True, message_id

            except Exception as e:
                logger.error(
                    f"🚨 [SERVICE-BUS] Send attempt {attempt + 1}/{self.max_retries} failed: {str(e)}"
                )

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)  # Exponential backoff
                    logger.info(f"⏳ [SERVICE-BUS] Retrying in {delay} seconds...")
                    # In an async function, we should use an async-compatible sleep
                    import asyncio

                    await asyncio.sleep(delay)
                    continue

                # All retries exhausted
                logger.error("❌ [SERVICE-BUS] All retries exhausted. Message sending failed.")
                return False, str(e)

        return False, "Maximum retries exceeded"

    def _prepare_message_content(
        self, webhook_data: Dict[str, Any], mapped_data: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        """
        Prepare the message content for Service Bus.

        Args:
            webhook_data: Original webhook payload
            mapped_data: Mapped call data
            request_id: Unique request identifier

        Returns:
            Dict[str, Any]: Prepared message content
        """
        from datetime import datetime

        return {
            "call_id": webhook_data["call_id"],
            "campaign_id": webhook_data.get("metadata", {}).get("campaign_id", "unknown"),
            "timestamp": datetime.utcnow().isoformat(),
            "webhook_received": True,
            "priority": self._determine_priority(webhook_data, mapped_data),
            "request_id": request_id,
            "disposition": mapped_data.disposition,
            "contact_made": mapped_data.contact_made,
            "opt_out_requested": mapped_data.opt_out_requested,
            "call_completed": mapped_data.call_completed,
            "duration_sec": mapped_data.duration_sec,
            "phone_number": webhook_data.get("to"),
            "attempt_id": webhook_data.get("metadata", {}).get("attempt_id"),
        }

    def _determine_priority(self, webhook_data: Dict[str, Any], mapped_data: Dict[str, Any]) -> str:
        """
        Determine message priority based on call characteristics.

        Args:
            webhook_data: Original webhook payload
            mapped_data: Mapped call data

        Returns:
            str: Priority level (high, normal, low)
        """
        # High priority conditions
        transcript = webhook_data.get("concatenated_transcript", "").lower()
        if any(
            [
                "emergency" in transcript,
                "urgent" in transcript,
                mapped_data.opt_out_requested,
                mapped_data.duration_sec is not None
                and mapped_data.duration_sec < 30,  # Very short calls
                webhook_data.get("metadata", {}).get("campaign_priority") == "high",
            ]
        ):
            return "high"

        # Low priority conditions
        if (
            mapped_data.duration_sec is not None and mapped_data.duration_sec > 600
        ):  # Calls longer than 10 minutes
            return "low"

        return "normal"
