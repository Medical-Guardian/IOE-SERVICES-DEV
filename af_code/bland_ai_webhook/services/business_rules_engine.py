import logging
import json
from typing import Dict, Any
from ..models.mapped_call_data import MappedCallData
from ..models.enrollment_update import EnrollmentUpdate
from ..services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class BusinessRulesEngine:
    """
    Applies business logic to determine enrollment status updates based on webhook outcomes.
    Supports dynamic rules loaded from configuration.
    """

    def __init__(self, config_manager: ConfigManager = None):
        """
        Initialize the BusinessRulesEngine with dynamic rules.

        Args:
            config_manager: Configuration manager for loading rules
        """
        self.config_manager = config_manager or ConfigManager()
        self.enrollment_rules = self._load_rules()
        logger.info(f"📈 [BUSINESS-RULES] Business rules engine initialized with {len(self.enrollment_rules)} rules")

    def _load_rules(self) -> Dict[str, Dict]:
        """
        Load enrollment rules from configuration.

        Returns:
            Dict[str, Dict]: Dictionary of rules
        """
        rules_config = self.config_manager.get_config("ENROLLMENT_RULES", '{}')
        try:
            rules = json.loads(rules_config)
            if not isinstance(rules, dict):
                raise ValueError("ENROLLMENT_RULES must be a JSON object")
            return rules
        except Exception as e:
            logger.error(f"🚨 [BUSINESS-RULES] Failed to load rules: {str(e)}")
            return {
                'Completed': {
                    'new_status': 'ENROLLED',
                    'confidence': 'high',
                    'condition': lambda data: data.contact_made and not data.opt_out_requested
                },
                'OptOut': {
                    'new_status': 'OPTED_OUT',
                    'confidence': 'high',
                    'condition': lambda data: data.opt_out_requested
                },
                'NoAnswer': {
                    'new_status': 'PENDING',
                    'confidence': 'medium',
                    'condition': lambda data: not data.contact_made
                },
                'Failed': {
                    'new_status': 'PENDING',
                    'confidence': 'low',
                    'condition': lambda data: True
                }
            }

    def determine_enrollment_update(self, webhook_data: Dict[str, Any],
                                    mapped_data: MappedCallData) -> EnrollmentUpdate:
        """
        Determine if an enrollment status update is needed based on business rules.

        Args:
            webhook_data: Original webhook payload
            mapped_data: Mapped call data

        Returns:
            EnrollmentUpdate: Decision on whether to update enrollment status
        """
        logger.info(f"📈 [BUSINESS-RULES] Evaluating enrollment update for disposition: {mapped_data.disposition}")

        for disposition, rule in self.enrollment_rules.items():
            condition = rule.get('condition', lambda data: True)
            if callable(condition) and mapped_data.disposition == disposition and condition(mapped_data):
                logger.info(f"✅ [BUSINESS-RULES] Matched rule for disposition: {disposition}")
                return EnrollmentUpdate(
                    should_update=True,
                    new_status=rule.get('new_status', 'PENDING'),
                    reason=f"Disposition {disposition} with contact_made={mapped_data.contact_made}, opt_out={mapped_data.opt_out_requested}",
                    confidence_level=rule.get('confidence', 'low')
                )

        logger.info("📋 [BUSINESS-RULES] No enrollment update required")
        return EnrollmentUpdate(
            should_update=False,
            new_status=None,
            reason="No matching business rule for update",
            confidence_level="low"
        )