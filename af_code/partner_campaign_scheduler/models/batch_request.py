from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class BatchRequest:
    """Model for Bland AI batch call request"""
    campaign_id: str
    calls: List[Dict[str, Any]]
    pathway_id: str
    voice_id: str

@dataclass  
class BatchResult:
    """Model for batch submission result"""
    success: bool
    members_count: int
    campaign_id: str
    batch_id: Optional[str] = None
    error: Optional[str] = None
    submitted_members: Optional[List[str]] = None