import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from ..models.mapped_call_data import MappedCallData

logger = logging.getLogger(__name__)


class StatusMapper:
    """
    Sophisticated translation engine that converts Bland AI webhook data into our internal format.
    """

    def __init__(self):
        """
        Initialize the status mapper with predefined translation rules.
        """
        self.status_disposition_mapping = {
            ('completed', 'CONTACT_MADE'): {
                'disposition': 'Completed',
                'next_action': 'Close',
                'contact_made': True
            },
            ('completed', 'NO_CONTACT_MADE'): {
                'disposition': 'NoAnswer',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('completed', 'NO_ANSWER'): {
                'disposition': 'NoAnswer',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('completed', 'VOICEMAIL'): {
                'disposition': 'NoAnswer',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('completed', 'BUSY'): {
                'disposition': 'NoAnswer',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('completed', 'OPT_OUT'): {
                'disposition': 'OptOut',
                'next_action': 'Close',
                'contact_made': True
            },
            ('failed', None): {
                'disposition': 'Failed',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('failed', 'INVALID_NUMBER'): {
                'disposition': 'Failed',
                'next_action': 'Escalate',
                'contact_made': False
            },
            ('in-progress', None): {
                'disposition': 'Pending',
                'next_action': 'Retry',
                'contact_made': False
            },
            ('cancelled', None): {
                'disposition': 'Failed',
                'next_action': 'Retry',
                'contact_made': False
            }
        }
        self.fallback_mapping = {
            'disposition': 'Failed',
            'next_action': 'Escalate',
            'contact_made': False
        }
        logger.info("🔄 [STATUS-MAPPER] Status mapping engine initialized with comprehensive rules")
        logger.info(f"📋 [STATUS-MAPPER] Loaded {len(self.status_disposition_mapping)} specific mapping rules")

    def map_webhook_to_internal_format(self, webhook_data: Dict[str, Any]) -> MappedCallData:
        """
        Transform Bland AI webhook data into our standardized internal format.

        Args:
            webhook_data: Complete webhook payload from Bland AI

        Returns:
            MappedCallData: Standardized call information ready for database storage
        """
        logger.info("🔄 [STATUS-MAPPER] Beginning webhook data transformation")
        status = webhook_data.get('status', '').lower()
        disposition_tag = webhook_data.get('disposition_tag')
        call_id = webhook_data.get('call_id', '')
        logger.info(f"📊 [STATUS-MAPPER] Core status - Status: '{status}', Disposition: '{disposition_tag}'")

        mapping_key = (status, disposition_tag)
        mapping_rule = self.status_disposition_mapping.get(
            mapping_key, self.status_disposition_mapping.get((status, None), self.fallback_mapping)
        )
        logger.info(f"✅ [STATUS-MAPPER] Found mapping rule for {mapping_key}")

        disposition = mapping_rule['disposition']
        next_action = mapping_rule['next_action']
        contact_made = mapping_rule['contact_made']
        logger.info(f"📋 [STATUS-MAPPER] Mapped results - Disposition: '{disposition}', Next Action: '{next_action}'")

        duration_sec = self._extract_call_duration(webhook_data)
        if duration_sec:
            logger.info(f"⏱️ [STATUS-MAPPER] Call duration extracted: {duration_sec} seconds")
        else:
            logger.warning("⚠️ [STATUS-MAPPER] No call duration information available")

        response_summary = self._build_response_summary(webhook_data, disposition, contact_made)
        logger.info(f"📝 [STATUS-MAPPER] Response summary created: {len(response_summary)} characters")

        call_quality_score = self._extract_call_quality(webhook_data)
        sentiment_analysis = self._extract_sentiment(webhook_data)
        key_topics = self._extract_key_topics(webhook_data)

        mapped_data = MappedCallData(
            disposition=disposition,
            next_action=next_action,
            duration_sec=duration_sec,
            response_summary=response_summary,
            vendor_session_id=call_id,
            call_completed=(status == 'completed'),
            opt_out_requested=(disposition_tag == 'OPT_OUT'),
            contact_made=contact_made,
            call_quality_score=call_quality_score,
            sentiment_analysis=sentiment_analysis,
            key_topics=key_topics
        )

        logger.info("✅ [STATUS-MAPPER] Webhook data transformation completed successfully")
        logger.info(f"📦 [STATUS-MAPPER] Final mapped disposition: {mapped_data.disposition}")
        return mapped_data

    def _extract_call_duration(self, webhook_data: Dict[str, Any]) -> Optional[int]:
        duration_fields = ['call_length', 'corrected_duration', 'duration_seconds', 'duration']
        for field_name in duration_fields:
            if field_name in webhook_data:
                duration_value = webhook_data[field_name]
                if isinstance(duration_value, (int, float)):
                    return int(duration_value)
                elif isinstance(duration_value, str):
                    try:
                        return int(float(duration_value))
                    except ValueError:
                        if ':' in duration_value:
                            try:
                                parts = duration_value.split(':')
                                if len(parts) == 2:
                                    minutes, seconds = parts
                                    return int(minutes) * 60 + int(seconds)
                            except ValueError:
                                continue
        return None

    def _build_response_summary(self, webhook_data: Dict[str, Any], disposition: str, contact_made: bool) -> str:
        summary_parts = [f"Call disposition: {disposition}"]
        summary_parts.append(
            "Contact was successfully made with the member" if contact_made else "No contact was made with the member")
        if disposition_tag := webhook_data.get('disposition_tag'):
            summary_parts.append(f"Specific outcome: {disposition_tag}")
        if duration_sec := self._extract_call_duration(webhook_data):
            minutes = duration_sec // 60
            seconds = duration_sec % 60
            summary_parts.append(f"Call duration: {minutes}m {seconds}s")
        if error_message := webhook_data.get('error_message'):
            summary_parts.append(f"Error details: {error_message}")
        if ai_summary := webhook_data.get('summary'):
            if isinstance(ai_summary, str) and len(ai_summary.strip()) > 0:
                summary_parts.append(f"AI Summary: {ai_summary.strip()}")
        return " | ".join(summary_parts)

    def _extract_call_quality(self, webhook_data: Dict[str, Any]) -> Optional[float]:
        analysis = webhook_data.get('analysis', {})
        if isinstance(analysis, dict):
            quality_score = analysis.get('call_quality_score') or analysis.get('quality_rating')
            if isinstance(quality_score, (int, float)):
                return float(quality_score)
        return None

    def _extract_sentiment(self, webhook_data: Dict[str, Any]) -> Optional[str]:
        analysis = webhook_data.get('analysis', {})
        if isinstance(analysis, dict):
            sentiment = analysis.get('sentiment') or analysis.get('overall_sentiment')
            if isinstance(sentiment, str):
                return sentiment.strip()
        return None

    def _extract_key_topics(self, webhook_data: Dict[str, Any]) -> Optional[str]:
        analysis = webhook_data.get('analysis', {})
        if isinstance(analysis, dict):
            topics = analysis.get('key_topics') or analysis.get('topics') or analysis.get('themes')
            if isinstance(topics, list):
                return ", ".join(str(topic) for topic in topics[:5])
            elif isinstance(topics, str):
                return topics.strip()
        return None