# NEW: This file contains the main application logic, callable by any trigger.
import logging
import json
from typing import Dict

from .services.member_service import MemberQualificationService
from .services.blandai_service import BlandAIService


def create_bland_ai_batch_call(
    campaign_id: str,
    member_service: MemberQualificationService,
    bland_service: BlandAIService,
) -> Dict:
    """Main logic to find members, create a batch, and submit to Bland AI."""
    batch_id_for_error_handling = None

    # Enhanced debugging for wellness campaign
    WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
    is_wellness_campaign = campaign_id.upper() == WELLNESS_CAMPAIGN_ID.upper()

    if is_wellness_campaign:
        logging.info(
            f"🩺 [MAIN-DEBUG] Starting DTC Wellness Check qualification for campaign: {campaign_id}"
        )
        logging.info("🩺 [MAIN-DEBUG] Campaign identified as WELLNESS campaign")
    else:
        logging.info(
            f"📞 [MAIN-DEBUG] Starting DTC Intro Call qualification for campaign: {campaign_id}"
        )

    try:
        qualified_members = member_service.get_qualified_members(campaign_id)

        if is_wellness_campaign:
            logging.info(
                f"🩺 [MAIN-DEBUG] Wellness campaign qualification completed. Found {len(qualified_members) if qualified_members else 0} qualified members"
            )

        if not qualified_members:
            message = "No members qualified at the current time."
            logging.warning(f"⚠️ [MAIN] {message}")

            if is_wellness_campaign:
                logging.warning("🩺 [MAIN-DEBUG] WELLNESS CAMPAIGN - No qualified members found!")
                logging.warning("🩺 [MAIN-DEBUG] Common reasons for wellness campaigns:")
                logging.warning(
                    "🩺 [MAIN-DEBUG] 1. No members enrolled in wellness campaign with ENROLLED status"
                )
                logging.warning(
                    "🩺 [MAIN-DEBUG] 2. Current day not in campaign's call_days_of_week"
                )
                logging.warning("🩺 [MAIN-DEBUG] 3. Current time outside member's preferred_window")
                logging.warning("🩺 [MAIN-DEBUG] 4. Members already have attempts today")

            return {"success": False, "message": message}

        original_count = len(qualified_members)
        limited_members = qualified_members[: bland_service.MEMBER_LIMIT]

        config = bland_service.get_campaign_config(campaign_id)
        batch_id = bland_service.create_outreach_batch(campaign_id, len(limited_members))
        batch_id_for_error_handling = batch_id

        bland_service.create_outreach_attempts(limited_members, batch_id)
        members_with_attempts = bland_service.get_members_with_attempts(batch_id)
        # payload = bland_service.build_bland_payload(config, members_with_attempts)
        payload = bland_service.build_bland_payload(config, members_with_attempts, batch_id)
        api_key = bland_service.get_bland_api_key()
        response = bland_service.call_bland_ai_api(payload, api_key)

        vendor_batch_id = response.get("data", {}).get("batch_id")
        if not vendor_batch_id:
            raise ValueError("Bland AI API response did not contain a vendor batch_id.")

        bland_service.update_batch_with_vendor_id(batch_id, vendor_batch_id)

        result = {
            "success": True,
            "message": "Batch submitted successfully.",
            "batch_id": batch_id,
            "vendor_batch_id": vendor_batch_id,
            "processed_count": len(limited_members),
            "qualified_count": original_count,
        }
        logging.info(f"🎉 [MAIN] Success: {json.dumps(result)}")
        return result

    except Exception as e:
        error_msg = f"Batch creation failed: {str(e)}"
        logging.error(f"💥 [MAIN] {error_msg}", exc_info=True)
        if batch_id_for_error_handling:
            bland_service.update_batch_failed(batch_id_for_error_handling, error_msg)
        return {"success": False, "message": error_msg}
