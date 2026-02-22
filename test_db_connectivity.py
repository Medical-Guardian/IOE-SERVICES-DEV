#!/usr/bin/env python3
"""
Database Connectivity Test for IOE Azure Functions
Tests connection to Azure SQL Database using ConfigManager and DatabaseService
"""

import logging
import sys
from pathlib import Path

# Add af_code to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_database_connection():
    """Test database connectivity and query IOE schema tables"""
    try:
        logger.info("="*60)
        logger.info("🔍 IOE Database Connectivity Test")
        logger.info("="*60)

        # Step 1: Initialize ConfigManager
        logger.info("\n📋 Step 1: Initializing ConfigManager...")
        config_manager = ConfigManager()
        logger.info("✅ ConfigManager initialized successfully")

        # Step 2: Initialize DatabaseService
        logger.info("\n📋 Step 2: Initializing DatabaseService...")
        db_service = DatabaseService(config_manager)
        logger.info("✅ DatabaseService initialized successfully")

        # Step 3: Test basic connectivity
        logger.info("\n📋 Step 3: Testing basic connectivity (SELECT 1)...")
        connectivity_query = "SELECT 1 AS test_value"
        result = db_service.execute_query(connectivity_query, fetch_results=True)
        if result and result[0]['test_value'] == 1:
            logger.info("✅ Basic connectivity test PASSED")
        else:
            logger.error("❌ Basic connectivity test FAILED")
            return False

        # Step 4: Query IOE schema - member_devices table
        logger.info("\n📋 Step 4: Querying IOE.member_devices table...")
        member_devices_query = """
        SELECT
            COUNT(*) as total_records,
            COUNT(DISTINCT member_id) as unique_members
        FROM ioe.member_devices
        """
        result = db_service.execute_query(member_devices_query, fetch_results=True)
        if result:
            logger.info(f"✅ IOE.member_devices query successful")
            logger.info(f"   📊 Total Records: {result[0]['total_records']}")
            logger.info(f"   👥 Unique Members: {result[0]['unique_members']}")
        else:
            logger.warning("⚠️ No data returned from IOE.member_devices")

        # Step 5: Query IOE schema - campaigns_enhanced table
        logger.info("\n📋 Step 5: Querying IOE.campaigns_enhanced table...")
        campaigns_query = """
        SELECT
            COUNT(*) as total_campaigns,
            COUNT(CASE WHEN campaign_status = 'Active' THEN 1 END) as active_campaigns
        FROM ioe.campaigns_enhanced
        """
        result = db_service.execute_query(campaigns_query, fetch_results=True)
        if result:
            logger.info(f"✅ IOE.campaigns_enhanced query successful")
            logger.info(f"   📊 Total Campaigns: {result[0]['total_campaigns']}")
            logger.info(f"   ✅ Active Campaigns: {result[0]['active_campaigns']}")
        else:
            logger.warning("⚠️ No data returned from IOE.campaigns_enhanced")

        # Step 6: Query IOE schema - members table
        logger.info("\n📋 Step 6: Querying IOE.members table...")
        members_query = """
        SELECT
            COUNT(*) as total_members,
            COUNT(CASE WHEN is_active = 1 THEN 1 END) as active_members
        FROM ioe.members
        """
        result = db_service.execute_query(members_query, fetch_results=True)
        if result:
            logger.info(f"✅ IOE.members query successful")
            logger.info(f"   📊 Total Members: {result[0]['total_members']}")
            logger.info(f"   ✅ Active Members: {result[0]['active_members']}")
        else:
            logger.warning("⚠️ No data returned from IOE.members")

        logger.info("\n" + "="*60)
        logger.info("✅ All database connectivity tests completed successfully!")
        logger.info("="*60)
        return True

    except Exception as e:
        logger.error(f"\n❌ Database connectivity test FAILED")
        logger.error(f"   Error: {str(e)}")
        logger.exception("Full traceback:")
        return False


if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1)
