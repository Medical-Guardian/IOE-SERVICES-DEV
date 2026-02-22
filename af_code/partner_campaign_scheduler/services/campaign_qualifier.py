import logging
import json
from typing import List
from datetime import datetime
import pytz
from ..models.qualified_campaign import QualifiedCampaign
from ...bland_ai_webhook.services.database_service import DatabaseService
from ...shared.timezone_utils import TimezoneConverter
from af_code.shared.schema_config import IOE_SCHEMA

logger = logging.getLogger(__name__)


class CampaignQualifier:
    """
    Service to identify Partner campaigns that are currently qualified to run
    Following existing IOE logging and error handling patterns
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("🔧 [CAMPAIGN-QUALIFIER] Service initialized")

    def get_qualified_campaigns(self) -> List[QualifiedCampaign]:
        """
        Find all Partner campaigns that are qualified to run right now
        """
        logger.info("🔍 [CAMPAIGN-QUALIFIER] Starting campaign qualification check...")

        try:
            # Get current UTC time (timezone-aware)
            now_utc = datetime.now(pytz.UTC)

            logger.info(
                f"⏰ [CAMPAIGN-QUALIFIER] Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

            # Query for active Partner campaigns with enhanced fields including Bland AI parameters
            query = f"""
                SELECT
                    c.campaign_id,
                    c.org_id,
                    c.name,
                    c.campaign_description,
                    c.contact_pref,
                    c.call_days_of_week,
                    c.operating_start_time,
                    c.operating_end_time,
                    c.operating_tz,
                    c.scheduling_mode,
                    c.frequency_value,
                    c.frequency_unit,
                    c.timezone_flag,
                    c.max_care_gaps_per_member,
                    c.audience_file_batch,
                    c.start_ts,
                    c.end_ts,
                    cc.config_id,
                    cc.call_type_id,
                    cc.bland_parameters_global,
                    o.org_type,
                    o.partner_contact_name,
                    o.org_name
                FROM {IOE_SCHEMA}.campaigns_enhanced c
                LEFT JOIN {IOE_SCHEMA}.campaign_call_configs_enhanced cc
                    ON c.campaign_id = cc.campaign_id
                    AND cc.config_status = 'active'
                LEFT JOIN {IOE_SCHEMA}.orgs o ON c.org_id = o.org_id
                WHERE c.campaign_type = 'Partner'
                  AND LOWER(c.status) IN ('active', 'testing')
                  AND c.primary_channel = 'voice'
                  AND c.audience_file_batch IS NOT NULL
            """

            logger.info("📊 [CAMPAIGN-QUALIFIER] Executing campaign query...")
            campaigns_data = self.db_service.execute_query(query, fetch_results=True)
            logger.info(
                f"📊 [CAMPAIGN-QUALIFIER] Found {len(campaigns_data)} total Partner campaigns in database"
            )

            qualified_campaigns = []

            for campaign_data in campaigns_data:
                campaign_name = campaign_data.get("name", "Unknown")
                campaign_id = campaign_data.get("campaign_id", "Unknown")
                logger.info("🔍 [CAMPAIGN-QUALIFIER] ============================================")
                logger.info(f"🔍 [CAMPAIGN-QUALIFIER] Evaluating campaign: {campaign_name}")
                logger.info(f"🔍 [CAMPAIGN-QUALIFIER] Campaign ID: {campaign_id}")
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Org: {campaign_data.get('org_name', 'Unknown')} (ID: {campaign_data.get('org_id', 'Unknown')})"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Status: {campaign_data.get('status', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Audience Batch: {campaign_data.get('audience_file_batch', 'None')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Contact Pref: {campaign_data.get('contact_pref', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Timezone Mode: {campaign_data.get('timezone_flag', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Operating TZ: {campaign_data.get('operating_tz', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Operating Hours: {campaign_data.get('operating_start_time', 'Unknown')} - {campaign_data.get('operating_end_time', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Call Days: {campaign_data.get('call_days_of_week', 'Unknown')}"
                )
                logger.info(
                    f"🔍 [CAMPAIGN-QUALIFIER] Frequency: {campaign_data.get('frequency_value', 'Unknown')} {campaign_data.get('frequency_unit', 'Unknown')}"
                )

                # Check timezone-aware start/end times
                logger.info(
                    "🔍 [CAMPAIGN-QUALIFIER] Step 1: Checking campaign start_ts/end_ts window..."
                )
                if not self._is_campaign_time_valid(campaign_data, now_utc):
                    logger.info(f"❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: {campaign_name}")
                    logger.info("   ⏰ Reason: Outside start_ts/end_ts window in campaign timezone")
                    logger.info(
                        "❌ [CAMPAIGN-QUALIFIER] ============================================"
                    )
                    continue

                logger.info(
                    "✅ [CAMPAIGN-QUALIFIER] Step 1 PASSED: Campaign is within start_ts/end_ts window"
                )

                # Check if campaign is qualified for current time and has valid configuration
                logger.info(
                    "🔍 [CAMPAIGN-QUALIFIER] Step 2: Checking operating hours and timezone qualification..."
                )
                is_time_qualified = self._is_campaign_qualified_now(campaign_data, now_utc)

                logger.info(
                    "🔍 [CAMPAIGN-QUALIFIER] Step 3: Validating flexible scheduling configuration..."
                )
                is_config_valid = self._validate_flexible_scheduling(campaign_data)

                if is_time_qualified and is_config_valid:
                    # Handle auto contact preference conversion
                    contact_pref = campaign_data["contact_pref"]
                    if contact_pref == "auto":
                        logger.info(
                            f"🔄 [CAMPAIGN-QUALIFIER] Converting contact_pref 'auto' to 'member_preference' for campaign: {campaign_name}"
                        )
                        contact_pref = "member_preference"

                    # Parse Bland AI parameters from bland_parameters_global JSON
                    bland_params = self._parse_bland_parameters(
                        campaign_data.get("bland_parameters_global"), campaign_name
                    )

                    qualified_campaign = QualifiedCampaign(
                        campaign_id=campaign_data["campaign_id"],
                        org_id=campaign_data["org_id"],
                        name=campaign_data["name"],
                        description=campaign_data["campaign_description"],
                        contact_pref=contact_pref,  # Use converted value
                        call_days_of_week=campaign_data["call_days_of_week"],
                        operating_start_time=campaign_data["operating_start_time"],
                        operating_end_time=campaign_data["operating_end_time"],
                        operating_tz=campaign_data["operating_tz"],
                        scheduling_mode=campaign_data["scheduling_mode"],
                        frequency_value=campaign_data["frequency_value"],
                        frequency_unit=campaign_data["frequency_unit"],
                        timezone_flag=campaign_data["timezone_flag"],
                        max_care_gaps=campaign_data["max_care_gaps_per_member"],
                        config_id=campaign_data["config_id"],
                        call_type_id=campaign_data["call_type_id"],
                        org_type=campaign_data["org_type"],
                        audience_file_batch=campaign_data["audience_file_batch"],
                        partner_contact_name=campaign_data.get("partner_contact_name"),
                        org_name=campaign_data.get("org_name"),
                        # Bland AI parameters from bland_parameters_global
                        bland_parameters_global=bland_params,
                        pathway_id=(bland_params.get("pathway_id") if bland_params else None),
                        voice_id=bland_params.get("voice_id") if bland_params else None,
                        webhook_url=(bland_params.get("webhook_url") if bland_params else None),
                        max_duration=(bland_params.get("max_duration") if bland_params else None),
                    )
                    qualified_campaigns.append(qualified_campaign)

                    logger.info(f"✅✅✅ [CAMPAIGN-QUALIFIER] Campaign QUALIFIED: {campaign_name}")
                    logger.info("✅ [CAMPAIGN-QUALIFIER] All qualification checks passed")
                    logger.info(
                        f"   📋 Operating hours: {campaign_data['operating_start_time']} - {campaign_data['operating_end_time']}"
                    )
                    logger.info(f"   📅 Days: {campaign_data['call_days_of_week']}")
                    logger.info(f"   🔄 Schedule: {campaign_data['scheduling_mode']}")
                    logger.info(f"   🌍 Timezone mode: {campaign_data['timezone_flag']}")
                    logger.info(f"   📦 Audience batch: {campaign_data['audience_file_batch']}")
                    logger.info(f"   📞 Contact pref: {contact_pref}")
                    logger.info(
                        f"   🎯 Pathway ID: {bland_params.get('pathway_id') if bland_params else 'None'}"
                    )
                    logger.info(
                        "✅ [CAMPAIGN-QUALIFIER] ============================================"
                    )
                else:
                    logger.info(f"❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: {campaign_name}")
                    if not is_time_qualified:
                        logger.info("   ❌ Failed Step 2: Not within operating hours/timezone")
                    if not is_config_valid:
                        logger.info("   ❌ Failed Step 3: Invalid scheduling configuration")
                    logger.info(
                        f"   ⏰ Operating hours: {campaign_data['operating_start_time']} - {campaign_data['operating_end_time']}"
                    )
                    logger.info(f"   📅 Allowed days: {campaign_data['call_days_of_week']}")
                    logger.info(
                        "❌ [CAMPAIGN-QUALIFIER] ============================================"
                    )

            logger.info(
                f"📊 [CAMPAIGN-QUALIFIER] QUALIFICATION COMPLETE: {len(qualified_campaigns)} campaigns qualified out of {len(campaigns_data)} total"
            )
            return qualified_campaigns

        except Exception as e:
            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] Error during qualification: {str(e)}")
            raise

    def _is_campaign_qualified_now(self, campaign_data: dict, now_utc: datetime) -> bool:
        """
        Check if a campaign is qualified to run at the current time using proper timezone handling
        """
        campaign_name = campaign_data.get("name", "Unknown")

        try:
            # Get campaign configuration
            start_time = campaign_data.get("operating_start_time")
            end_time = campaign_data.get("operating_end_time")
            timezone_flag = campaign_data.get("timezone_flag", "operating_tz")
            call_days_str = campaign_data.get("call_days_of_week", "")

            if not start_time or not end_time:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] Missing operating hours for campaign: {campaign_name}"
                )
                return False

            if not call_days_str:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] No call days defined for campaign: {campaign_name}"
                )
                return False

            # Convert string times to time objects if needed
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, "%H:%M:%S").time()
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, "%H:%M:%S").time()

            call_days = [day.strip() for day in call_days_str.split(",")]

            # Get US timezones using TimezoneConverter
            us_timezones = TimezoneConverter.get_us_timezones_pytz()

            if timezone_flag == "member_tz":
                # Check if ANY US timezone is currently within operating hours AND day
                any_timezone_qualified = False
                qualified_timezones = []

                for tz_name, tz in us_timezones.items():
                    now_in_tz = now_utc.astimezone(tz)
                    current_day_in_tz = now_in_tz.strftime("%A")
                    current_time_in_tz = now_in_tz.time()

                    # Check both day AND time for this timezone
                    if (
                        current_day_in_tz in call_days
                        and start_time <= current_time_in_tz <= end_time
                    ):
                        any_timezone_qualified = True
                        qualified_timezones.append(f"{tz_name} ({now_in_tz.strftime('%A %H:%M')})")

                if not any_timezone_qualified:
                    logger.info(
                        f"⏰ [CAMPAIGN-QUALIFIER] Member timezone check FAILED: {campaign_name}"
                    )
                    logger.info("   No US timezone currently qualifies")
                    logger.info(f"   Required: Days={call_days}, Hours={start_time}-{end_time}")
                    logger.info(
                        f"   Current: ET={now_utc.astimezone(us_timezones['Eastern']).strftime('%A %H:%M')}, "
                        f"CT={now_utc.astimezone(us_timezones['Central']).strftime('%A %H:%M')}, "
                        f"MT={now_utc.astimezone(us_timezones['Mountain']).strftime('%A %H:%M')}, "
                        f"PT={now_utc.astimezone(us_timezones['Pacific']).strftime('%A %H:%M')}"
                    )
                    return False

                logger.info(
                    f"✅ [CAMPAIGN-QUALIFIER] Member timezone check PASSED: {campaign_name}"
                )
                logger.info(f"   Qualified timezones: {', '.join(qualified_timezones)}")
                return True

            else:
                # operating_tz mode: Check the campaign's specific operating timezone
                operating_tz_name = campaign_data.get("operating_tz", "EST")
                # Convert to pytz using TimezoneConverter (handles EST → America/New_York)
                campaign_tz = TimezoneConverter.to_pytz(operating_tz_name)

                # Convert current UTC to campaign's operating timezone
                now_in_campaign_tz = now_utc.astimezone(campaign_tz)
                current_day_in_tz = now_in_campaign_tz.strftime("%A")
                current_time_in_tz = now_in_campaign_tz.time()

                logger.info(
                    f"🕐 [CAMPAIGN-QUALIFIER] Checking in {operating_tz_name} timezone: {now_in_campaign_tz.strftime('%A %H:%M:%S')}"
                )

                # Check day of week
                if current_day_in_tz not in call_days:
                    logger.info(f"📅 [CAMPAIGN-QUALIFIER] Day check FAILED: {campaign_name}")
                    logger.info(
                        f"   Current day in {operating_tz_name}: {current_day_in_tz}, Allowed: {call_days}"
                    )
                    return False

                logger.info(
                    f"📅 [CAMPAIGN-QUALIFIER] Day check PASSED: {campaign_name} ({current_day_in_tz})"
                )

                # Check time window
                if not (start_time <= current_time_in_tz <= end_time):
                    logger.info(f"⏰ [CAMPAIGN-QUALIFIER] Time check FAILED: {campaign_name}")
                    logger.info(
                        f"   Current time in {operating_tz_name}: {current_time_in_tz}, Window: {start_time}-{end_time}"
                    )
                    return False

                logger.info(
                    f"✅ [CAMPAIGN-QUALIFIER] Operating timezone check PASSED: {campaign_name}"
                )
                logger.info(
                    f"   {operating_tz_name}: {now_in_campaign_tz.strftime('%A %H:%M')}, Window: {start_time}-{end_time}"
                )
                return True

        except Exception as e:
            logger.error(
                f"🚨 [CAMPAIGN-QUALIFIER] Error checking qualification for {campaign_name}: {str(e)}"
            )
            import traceback

            logger.error(traceback.format_exc())
            return False

    def _validate_flexible_scheduling(self, campaign_data: dict) -> bool:
        """
        Validate that Flexible scheduling mode has required frequency values
        """
        campaign_name = campaign_data.get("name", "Unknown")
        scheduling_mode = campaign_data.get("scheduling_mode")

        logger.info(f"   🔍 [CAMPAIGN-QUALIFIER] Checking scheduling mode: {scheduling_mode}")

        if scheduling_mode == "Flexible":
            logger.info(
                "   🔍 [CAMPAIGN-QUALIFIER] Flexible mode detected - validating frequency settings..."
            )
            frequency_value = campaign_data.get("frequency_value")
            frequency_unit = campaign_data.get("frequency_unit")

            if not frequency_value or not frequency_unit:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] Flexible scheduling requires frequency_value and frequency_unit for campaign: {campaign_name}"
                )
                logger.warning(
                    f"   Current values: frequency_value={frequency_value}, frequency_unit={frequency_unit}"
                )
                return False

            if frequency_value <= 0:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] Invalid frequency_value: {frequency_value} for campaign: {campaign_name}"
                )
                return False

            if frequency_unit not in ["day", "week", "month"]:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] Invalid frequency_unit: {frequency_unit} for campaign: {campaign_name}"
                )
                return False

            logger.info(
                f"   ✅ [CAMPAIGN-QUALIFIER] Flexible scheduling validation passed: {frequency_value} per {frequency_unit}"
            )
        else:
            logger.info(
                f"   ✅ [CAMPAIGN-QUALIFIER] Scheduling mode '{scheduling_mode}' - no frequency validation needed"
            )

        return True

    def _is_campaign_time_valid(self, campaign_data: dict, now_utc: datetime) -> bool:
        """
        Check if current time is within campaign start_ts/end_ts windows
        using timezone-aware comparison in the campaign's operating timezone

        Args:
            campaign_data: Campaign configuration dictionary
            now_utc: Current UTC time (timezone-aware)

        Returns:
            bool: True if campaign is within time window, False otherwise

        Logic:
            1. Convert campaign's operating_tz to pytz timezone object
            2. Convert current UTC time to campaign's timezone
            3. Compare against start_ts and end_ts in campaign's timezone
        """
        campaign_name = campaign_data.get("name", "Unknown")
        start_ts = campaign_data.get("start_ts")  # From database (UTC)
        end_ts = campaign_data.get("end_ts")  # From database (UTC)
        operating_tz_str = campaign_data.get("operating_tz", "EST")

        # Convert operating_tz to pytz object
        campaign_tz = TimezoneConverter.to_pytz(operating_tz_str)

        # Convert current UTC time to campaign timezone
        now_in_campaign_tz = now_utc.astimezone(campaign_tz)

        # LOG 1: Current time comparison
        logger.info(f"🕐 [CAMPAIGN-QUALIFIER] ⏰ TIME COMPARISON for '{campaign_name}'")
        logger.info(f"   📍 Campaign timezone: {operating_tz_str}")
        logger.info(f"   🌍 Current time (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(
            f"   🌍 Current time ({operating_tz_str}): {now_in_campaign_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )

        # LOG 2: Database start_ts (if exists)
        if start_ts is not None:
            start_ts_in_campaign_tz = start_ts.astimezone(campaign_tz)

            logger.info(
                f"   📅 start_ts (UTC from DB): {start_ts.strftime('%Y-%m-%d %H:%M:%S %z')}"
            )
            logger.info(
                f"   📅 start_ts ({operating_tz_str}): {start_ts_in_campaign_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

            # Check if campaign has started (compare dates only, ignore time)
            if now_in_campaign_tz.date() < start_ts_in_campaign_tz.date():
                logger.info("   ❌ COMPARISON: Current date < start_ts date")
                logger.info(
                    f"      {now_in_campaign_tz.strftime('%Y-%m-%d')} < {start_ts_in_campaign_tz.strftime('%Y-%m-%d')} ({operating_tz_str})"
                )
                logger.warning(
                    f"❌ [CAMPAIGN-QUALIFIER] Campaign '{campaign_name}' has NOT started yet"
                )
                return False
            else:
                logger.info("   ✅ COMPARISON: Current date >= start_ts date")
                logger.info(
                    f"      {now_in_campaign_tz.strftime('%Y-%m-%d')} >= {start_ts_in_campaign_tz.strftime('%Y-%m-%d')} ({operating_tz_str})"
                )
        else:
            logger.info("   ℹ️  start_ts: NULL (no start restriction)")

        # LOG 3: Database end_ts (if exists)
        if end_ts is not None:
            end_ts_in_campaign_tz = end_ts.astimezone(campaign_tz)

            logger.info(f"   📅 end_ts (UTC from DB): {end_ts.strftime('%Y-%m-%d %H:%M:%S %z')}")
            logger.info(
                f"   📅 end_ts ({operating_tz_str}): {end_ts_in_campaign_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

            # Check if campaign has ended (compare dates only, ignore time)
            if now_in_campaign_tz.date() > end_ts_in_campaign_tz.date():
                logger.info("   ❌ COMPARISON: Current date > end_ts date")
                logger.info(
                    f"      {now_in_campaign_tz.strftime('%Y-%m-%d')} > {end_ts_in_campaign_tz.strftime('%Y-%m-%d')} ({operating_tz_str})"
                )
                logger.warning(f"❌ [CAMPAIGN-QUALIFIER] Campaign '{campaign_name}' has ENDED")
                return False
            else:
                logger.info("   ✅ COMPARISON: Current date <= end_ts date")
                logger.info(
                    f"      {now_in_campaign_tz.strftime('%Y-%m-%d')} <= {end_ts_in_campaign_tz.strftime('%Y-%m-%d')} ({operating_tz_str})"
                )
        else:
            logger.info("   ℹ️  end_ts: NULL (no end restriction)")

        # LOG 4: Final result summary
        logger.info(f"✅ [CAMPAIGN-QUALIFIER] Campaign '{campaign_name}' is WITHIN time window")
        if start_ts or end_ts:
            logger.info(f"   📊 Active window ({operating_tz_str}):")
            if start_ts:
                logger.info(
                    f"      Start: {start_ts.astimezone(campaign_tz).strftime('%Y-%m-%d %H:%M %Z')}"
                )
            if end_ts:
                logger.info(
                    f"      End: {end_ts.astimezone(campaign_tz).strftime('%Y-%m-%d %H:%M %Z')}"
                )

        return True

    def _parse_bland_parameters(self, bland_parameters_json: str, campaign_name: str) -> dict:
        """
        Parse bland_parameters_global JSON field from campaign_call_configs_enhanced

        Args:
            bland_parameters_json: JSON string containing Bland AI configuration
            campaign_name: Campaign name for logging

        Returns:
            Dictionary with pathway_id, voice_id, webhook_url, max_duration, etc.

        Example JSON:
        {
            "pathway_id": "partner-wellness-pathway-123",
            "voice_id": "partner-voice-456",
            "webhook_url": "https://ioe-functions.azurewebsites.net/api/bland_ai_webhook",
            "max_duration": "300",
            "analysis_schema": {
                "disposition_analysis": true,
                "sentiment_analysis": true
            }
        }
        """
        if not bland_parameters_json:
            logger.warning(
                f"⚠️ [CAMPAIGN-QUALIFIER] No bland_parameters_global configured for campaign: {campaign_name}"
            )
            logger.warning(
                "⚠️ [CAMPAIGN-QUALIFIER] Will use fallback environment variables for Bland AI configuration"
            )
            return {}

        try:
            bland_params = json.loads(bland_parameters_json)

            # Normalize field names with deprecation warnings
            from af_code.shared.bland_parameters_validator import (
                BlandParametersValidator,
            )

            validator = BlandParametersValidator()
            normalized_params, deprecated_fields = validator.normalize_field_names(bland_params)

            if deprecated_fields:
                logger.warning(
                    f"⚠️ [CAMPAIGN-QUALIFIER] Deprecated field names detected in campaign '{campaign_name}'"
                )
                for old_field in deprecated_fields:
                    new_field = validator.DEPRECATED_FIELD_MAPPINGS.get(old_field)
                    logger.warning(
                        f"⚠️ [CAMPAIGN-QUALIFIER]   - '{old_field}' is deprecated, use '{new_field}' instead"
                    )
                logger.warning(
                    "⚠️ [CAMPAIGN-QUALIFIER] Update bland_parameters_global in campaign_call_configs_enhanced to use new field names"
                )

            bland_params = normalized_params

            logger.info(
                f"📋 [CAMPAIGN-QUALIFIER] Parsed Bland AI parameters for campaign: {campaign_name}"
            )
            logger.info(f"   🎭 Pathway ID: {bland_params.get('pathway_id', 'Not configured')}")
            logger.info(f"   🎤 Voice ID: {bland_params.get('voice_id', 'Not configured')}")
            logger.info(f"   🔗 Webhook URL: {bland_params.get('webhook_url', 'Not configured')}")
            logger.info(f"   ⏱️ Max Duration: {bland_params.get('max_duration', 'Not configured')}")

            return bland_params

        except json.JSONDecodeError as e:
            logger.error(
                f"🚨 [CAMPAIGN-QUALIFIER] Failed to parse bland_parameters_global JSON for campaign: {campaign_name}"
            )
            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] JSON parse error: {str(e)}")
            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] Raw value: {bland_parameters_json}")
            logger.warning(
                "⚠️ [CAMPAIGN-QUALIFIER] Will use fallback environment variables for Bland AI configuration"
            )
            return {}
        except Exception as e:
            logger.error(
                f"🚨 [CAMPAIGN-QUALIFIER] Unexpected error parsing bland_parameters_global: {str(e)}"
            )
            import traceback

            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] Traceback: {traceback.format_exc()}")
            return {}
