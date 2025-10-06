import logging
from typing import List
from datetime import datetime
from ..models.qualified_campaign import QualifiedCampaign
from ..models.eligible_member import EligibleMember
from ..models.batch_request import BatchResult
from ...shared.database_service import DatabaseService

logger = logging.getLogger(__name__)

class StatusTracker:
    """
    Service to track batch submissions and create outreach attempt records
    """
    
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("🔧 [STATUS-TRACKER] Service initialized")
    
    async def log_batch_submission(self, campaign: QualifiedCampaign, members: List[EligibleMember], batch_result: BatchResult) -> None:
        """
        Log successful batch submission using existing outreach tables
        """
        logger.info(f"📋 [STATUS-TRACKER] Logging batch submission for campaign: {campaign.name}")
        logger.info(f"📦 [STATUS-TRACKER] Bland Batch ID: {batch_result.batch_id}")
        logger.info(f"👥 [STATUS-TRACKER] Members count: {batch_result.members_count}")
        
        try:
            # Step 1: Create batch record in outreach_batches
            batch_id = await self._create_batch_record(campaign, batch_result)
            
            # Step 2: Create individual outreach attempt records
            await self._create_outreach_attempts(campaign, members, batch_id, batch_result)
            
            logger.info(f"✅ [STATUS-TRACKER] Successfully logged batch submission")
            logger.info(f"📦 [STATUS-TRACKER] Internal Batch ID: {batch_id}")
            logger.info(f"🔗 [STATUS-TRACKER] Duplicate prevention: handled via outreach_attempts table")
            
        except Exception as e:
            logger.error(f"🚨 [STATUS-TRACKER] Error logging batch submission: {str(e)}")
            raise
    
    async def _create_batch_record(self, campaign: QualifiedCampaign, batch_result: BatchResult) -> str:
        """
        Create batch tracking record using existing outreach_batches table
        """
        logger.info(f"📝 [STATUS-TRACKER] Creating batch tracking record...")
        
        query = """
            INSERT INTO engage360.outreach_batches (
                batch_id,
                campaign_id, 
                vendor_batch_id, 
                batch_status,
                total_calls_intended,
                submitted_ts
            ) OUTPUT INSERTED.batch_id
            VALUES (NEWID(), %s, %s, %s, %s, SYSDATETIMEOFFSET())
        """
        
        params = (
            campaign.campaign_id,
            batch_result.batch_id,  # Bland AI batch ID goes to vendor_batch_id
            'Submitted',            # Use existing constraint values
            batch_result.members_count
        )
        
        result = self.db_service.execute_query(query, params, fetch_results=True)
        batch_id = result[0]['batch_id']
        
        logger.info(f"✅ [STATUS-TRACKER] Created batch record with ID: {batch_id}")
        return batch_id
    
    async def _create_outreach_attempts(self, campaign: QualifiedCampaign, members: List[EligibleMember], 
                                      batch_id: str, batch_result: BatchResult) -> None:
        """
        Create individual outreach attempt records using existing outreach_attempts table
        """
        logger.info(f"📞 [STATUS-TRACKER] Creating outreach attempt records for {len(members)} members...")
        
        # Build bulk insert query for better performance
        values_list = []
        params = []
        
        for member in members:
            # Only create records for members who were actually submitted (have valid phone numbers)
            if member.member_id in (batch_result.submitted_members or []):
                values_list.append("(NEWID(), %s, %s, %s, %s, SYSDATETIMEOFFSET(), %s, %s)")
                params.extend([
                    member.enrollment_id,     # Use enrollment_id FK (existing table structure)
                    batch_id,                 # FK to outreach_batches
                    'Voice',                  # Channel (matches constraint)
                    batch_result.batch_id,    # vendor_session_id (Bland AI batch ID)
                    'Pending',                # disposition (matches constraint)
                    0                         # retry_seq (default)
                ])
        
        if not values_list:
            logger.warning(f"⚠️ [STATUS-TRACKER] No valid members to create outreach attempts for")
            return
        
        query = f"""
            INSERT INTO engage360.outreach_attempts (
                attempt_id, 
                enrollment_id, 
                batch_id, 
                channel,
                vendor_session_id,
                attempt_ts,
                disposition,
                retry_seq
            ) VALUES {', '.join(values_list)}
        """
        
        rows_affected = self.db_service.execute_query(query, params, fetch_results=False)
        
        logger.info(f"✅ [STATUS-TRACKER] Created {rows_affected} outreach attempt records")
    
    # Note: _track_batch_members method removed - duplicate prevention handled by existing tables
    
    async def update_batch_status(self, vendor_batch_id: str, new_status: str, error_message: str = None) -> None:
        """
        Update batch status using existing outreach_batches table
        """
        logger.info(f"🔄 [STATUS-TRACKER] Updating batch status: {vendor_batch_id} -> {new_status}")
        
        query = """
            UPDATE engage360.outreach_batches
            SET batch_status = %s,
                status_reason = %s,
                updated_ts = SYSDATETIMEOFFSET()
            WHERE vendor_batch_id = %s
        """
        
        params = (new_status, error_message, vendor_batch_id)
        rows_affected = self.db_service.execute_query(query, params, fetch_results=False)
        
        if rows_affected > 0:
            logger.info(f"✅ [STATUS-TRACKER] Updated batch status successfully")
        else:
            logger.warning(f"⚠️ [STATUS-TRACKER] No batch found with vendor ID: {vendor_batch_id}")
    
    async def get_batch_statistics(self, campaign_id: str) -> dict:
        """
        Get batch submission statistics using existing outreach_batches table
        """
        logger.info(f"📊 [STATUS-TRACKER] Getting batch statistics for campaign: {campaign_id}")
        
        query = """
            SELECT 
                COUNT(*) as total_batches,
                SUM(total_calls_intended) as total_members_submitted,
                COUNT(CASE WHEN batch_status = 'Submitted' THEN 1 END) as submitted_batches,
                COUNT(CASE WHEN batch_status = 'Failed' THEN 1 END) as failed_batches,
                MAX(submitted_ts) as last_submission_ts
            FROM engage360.outreach_batches
            WHERE campaign_id = %s
              AND CAST(submitted_ts AS DATE) = CAST(SYSDATETIMEOFFSET() AS DATE)
        """
        
        result = self.db_service.execute_query(query, (campaign_id,), fetch_results=True)
        stats = result[0] if result else {}
        
        logger.info(f"📈 [STATUS-TRACKER] Campaign statistics: {stats}")
        return stats