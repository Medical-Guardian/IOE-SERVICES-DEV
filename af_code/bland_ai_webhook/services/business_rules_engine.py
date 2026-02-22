"""
Business Rules Engine for IOE Campaign Processing.

Purpose: Applies campaign-specific business logic to determine member enrollment
status updates based on call outcomes and disposition results.

Owner: IOE Development Team
BusinessCaseIDs: BC-104, BC-105
"""

from __future__ import annotations

import logging
import json
from typing import Dict, Any, Optional, List

from ..models.mapped_call_data import MappedCallData
from ..models.enrollment_update import EnrollmentUpdate
from ..services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


# =============================================================================
# In-file "campaign modules"
# =============================================================================


class _CampaignRuleHandler:
    """
    Interface for campaign-specific decision logic.

    BusinessCaseID: BC-104
    """

    def applicable(self, rule_name: Optional[str], campaign_id: Optional[str]) -> bool:
        """
        Check if this handler applies to the given rule and campaign.

        BusinessCaseID: BC-104
        """
        raise NotImplementedError

    def decide(self, webhook_data: Dict[str, Any], mapped: MappedCallData) -> EnrollmentUpdate:
        """
        Make enrollment decision based on call outcome.

        BusinessCaseID: BC-104
        """
        raise NotImplementedError


class _DtcIntroCall_34CC9155_Handler(_CampaignRuleHandler):
    """
    Campaign module for:
      - call_type_code: DTC_INTRO_CALL
      - campaign_id:   34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC

    Disposition matrix (idempotent behavior is enforced at DB layer):
      - Completed  & contact_made & not opt_out_requested -> ENROLLED (high)
      - OptOut     & opt_out_requested                    -> OPTED_OUT (high)
      - NoAnswer                                            PENDING   (medium)
      - Failed                                              PENDING   (low)
    """

    RULE = "DTC_INTRO_CALL"
    CAMPAIGN = "34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC"

    def applicable(self, rule_name: Optional[str], campaign_id: Optional[str]) -> bool:
        return rule_name == self.RULE and campaign_id == self.CAMPAIGN

    def decide(self, webhook_data: Dict[str, Any], mapped: MappedCallData) -> EnrollmentUpdate:
        disp = mapped.disposition
        disposition_tag = webhook_data.get("disposition_tag", "")

        # COMPLETED_ACTION -> ENROLLED (specific rule for this disposition tag)
        if disposition_tag == "COMPLETED_ACTION":
            return EnrollmentUpdate(
                should_update=True,
                new_status="ENROLLED",
                reason="DTC_INTRO_CALL: COMPLETED_ACTION disposition; enrolling member",
                confidence_level="high",
            )

        # Completed -> ENROLLED if spoke and not opted-out
        if disp == "Completed" and mapped.contact_made and not mapped.opt_out_requested:
            return EnrollmentUpdate(
                should_update=True,
                new_status="ENROLLED",
                reason="DTC_INTRO_CALL: Completed with contact; enrolling",
                confidence_level="high",
            )

        # INTERESTED -> ENROLLED (successful intro call)
        if disposition_tag == "INTERESTED":
            return EnrollmentUpdate(
                should_update=True,
                new_status="ENROLLED",
                reason="DTC_INTRO_CALL: Member interested; enrolling",
                confidence_level="high",
            )

        # OptOut -> OPTED_OUT if explicit request
        if disp == "OptOut" and mapped.opt_out_requested:
            return EnrollmentUpdate(
                should_update=True,
                new_status="OPTED_OUT",
                reason="DTC_INTRO_CALL: Member requested opt-out",
                confidence_level="high",
            )

        # NoAnswer -> Keep ENROLLED (retry)
        if disp == "NoAnswer":
            return EnrollmentUpdate(
                should_update=False,
                new_status=None,
                reason="DTC_INTRO_CALL: No answer - keeping ENROLLED for retry",
                confidence_level="medium",
            )

        # Failed -> Keep ENROLLED (retry)
        if disp == "Failed":
            return EnrollmentUpdate(
                should_update=False,
                new_status=None,
                reason="DTC_INTRO_CALL: Failed call - keeping ENROLLED for retry",
                confidence_level="low",
            )

        # No change for everything else
        return EnrollmentUpdate(
            should_update=False,
            new_status=None,
            reason="DTC_INTRO_CALL: No matching disposition condition",
            confidence_level="low",
        )


class _DeviceActivation_Handler(_CampaignRuleHandler):
    """
    Campaign module for Device Activation calls.

    call_type_code: DEVICE_ACTIVATION
    campaign_ids: 0F69659B-491B-40E2-88C3-ABC7D87385B2, BA865458-60F9-4EBB-9FB5-D195B532CF5A

    Business Rules:
    - ALL dispositions (including OPTED_OUT) → NO enrollment status change
    - Opt-outs treated as NoAnswer (member remains ENROLLED)
    - Frequency protection via outreach_attempts table only
    - Members remain ENROLLED throughout campaign lifecycle

    Updated: 2025-12-24
    BusinessCaseID: BC-104
    """

    RULE = "DEVICE_ACTIVATION"
    CAMPAIGN_IDS = [
        "0F69659B-491B-40E2-88C3-ABC7D87385B2",
        "BA865458-60F9-4EBB-9FB5-D195B532CF5A",
    ]

    def applicable(self, rule_name: Optional[str], campaign_id: Optional[str]) -> bool:
        """Check if this is a Device Activation campaign."""
        # Match by call_type_code OR campaign_id
        return rule_name == self.RULE or (
            campaign_id and campaign_id.upper() in [c.upper() for c in self.CAMPAIGN_IDS]
        )

    def decide(self, webhook_data: Dict[str, Any], mapped: MappedCallData) -> EnrollmentUpdate:
        """
        Apply Device Activation business rules.

        ALL dispositions (including opt-outs) → NO status change.
        Opt-outs are treated as NoAnswer and logged in outreach_attempts only.
        """
        # Log disposition for transparency
        disposition = mapped.disposition
        logger.info(f"🔧 [BUSINESS-RULES] Device Activation - Disposition: {disposition}")

        # Special handling for opt-outs (treat as NoAnswer)
        if mapped.opt_out_requested:
            logger.info("🔧 [BUSINESS-RULES] Device Activation - Opt-out treated as NoAnswer")
            logger.info("🔧 [BUSINESS-RULES] ℹ️ Member remains ENROLLED (frequency-based calling)")

        # ALL dispositions: No status change
        return EnrollmentUpdate(
            should_update=False,
            new_status=None,
            reason=f"DEVICE_ACTIVATION: Frequency-based calling (no status change for {disposition})",
            confidence_level="high",
        )


def _get_campaign_handler(
    rule_name: Optional[str], campaign_id: Optional[str]
) -> Optional[_CampaignRuleHandler]:
    """Return the first handler that applies to (rule_name, campaign_id)."""
    handlers: List[_CampaignRuleHandler] = [
        _DtcIntroCall_34CC9155_Handler(),
        _DeviceActivation_Handler(),  # Added 2025-12-23 for Device Activation standardization
        # Add more campaign modules here in the future.
    ]
    for h in handlers:
        if h.applicable(rule_name, campaign_id):
            return h
    return None


# =============================================================================
# Core engine
# =============================================================================


class BusinessRulesEngine:
    """
    Applies business logic to determine enrollment status updates based on webhook outcomes.
    Resolution order:
      1) Campaign module (by call_type_code + campaign_id)
      2) ENROLLMENT_RULES JSON (optional), keyed by disposition
      3) Default fallback (OptOut only): if opt_out_requested -> OPTED_OUT; else no update
    """

    def __init__(self, config_manager: ConfigManager = None):
        self.config_manager = config_manager or ConfigManager()
        self.enrollment_rules = self._load_rules()
        logger.info("📈 [BUSINESS-RULES] Engine initialized.")

    # ---- rules loading (kept for backward compatibility) ----
    def _load_rules(self) -> Dict[str, Dict]:
        """
        Try loading ENROLLMENT_RULES JSON. If missing/invalid, fallback is OptOut-only.
        Expected JSON shape (optional):
          {
            "Completed": {"new_status":"ENROLLED", "confidence":"high"},
            "OptOut":    {"new_status":"OPTED_OUT","confidence":"high"},
            ...
          }
        """
        rules_config = self.config_manager.get_config("ENROLLMENT_RULES", "{}")
        try:
            rules = json.loads(rules_config)
            if not isinstance(rules, dict):
                raise ValueError("ENROLLMENT_RULES must be a JSON object")
            return rules
        except Exception as e:
            logger.error(f"🚨 [BUSINESS-RULES] Failed to load rules: {e}")
            # Minimal default fallback (OptOut only)
            return {
                "OptOut": {
                    "new_status": "OPTED_OUT",
                    "confidence": "high",
                    "condition": lambda data: data.opt_out_requested,
                }
            }

    # ---- main decision ----
    def determine_enrollment_update(
        self, webhook_data: Dict[str, Any], mapped_data: MappedCallData
    ) -> EnrollmentUpdate:
        """
        Compute the enrollment update decision for this call.
        """
        logger.info(f"📈 [BUSINESS-RULES] Evaluating disposition: {mapped_data.disposition}")

        metadata = webhook_data.get("metadata", {}) or {}
        rule_name = metadata.get("call_type_code")  # e.g., "DTC_INTRO_CALL"
        campaign_id = metadata.get("campaign_id")  # e.g., "34CC9155-..."

        # (1) Campaign-specific module
        handler = _get_campaign_handler(rule_name, campaign_id)
        if handler:
            decision = handler.decide(webhook_data, mapped_data)
            if decision.should_update:
                logger.info(
                    f"✅ [BUSINESS-RULES] Campaign module applied: {rule_name}/{campaign_id}"
                )
                return decision

        # (2) Optional JSON rules (disposition-indexed)
        for disposition, rule in (self.enrollment_rules or {}).items():
            condition = rule.get("condition", lambda data: True)
            if mapped_data.disposition == disposition and (
                not callable(condition) or condition(mapped_data)
            ):
                logger.info(f"✅ [BUSINESS-RULES] Matched JSON rule for disposition: {disposition}")
                return EnrollmentUpdate(
                    should_update=True,
                    new_status=rule.get("new_status", "PENDING"),
                    reason=f"Config fallback matched for {disposition}",
                    confidence_level=rule.get("confidence", "low"),
                )

        # (3) Default fallback - handle common disposition mappings
        # If we have a 'Completed' disposition but no specific rule matched,
        # check if it should be enrolled based on contact status
        if (
            mapped_data.disposition == "Completed"
            and mapped_data.contact_made
            and not mapped_data.opt_out_requested
        ):
            logger.info("📋 [BUSINESS-RULES] Default fallback: Completed with contact -> ENROLLED")
            return EnrollmentUpdate(
                should_update=True,
                new_status="ENROLLED",
                reason="Default fallback: Completed call with contact made",
                confidence_level="medium",
            )
        elif mapped_data.disposition == "OptOut" and mapped_data.opt_out_requested:
            logger.info("📋 [BUSINESS-RULES] Default fallback: OptOut requested -> OPTED_OUT")
            return EnrollmentUpdate(
                should_update=True,
                new_status="OPTED_OUT",
                reason="Default fallback: Opt-out requested",
                confidence_level="high",
            )

        # No update for other cases
        logger.info("📋 [BUSINESS-RULES] No update (no matching rule or condition).")
        return EnrollmentUpdate(
            should_update=False,
            new_status=None,
            reason="No matching rule; no default action applies",
            confidence_level="low",
        )
