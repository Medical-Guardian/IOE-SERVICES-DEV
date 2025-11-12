from dataclasses import dataclass
from typing import List, Dict, Any, Optional


@dataclass
class BatchRequest:
    """Model for Bland AI batch call request with all global parameters (matching DTC implementation)"""

    campaign_id: str
    calls: List[Dict[str, Any]]

    # Core required parameters
    pathway_id: str
    voice_id: str

    # All optional global parameters from bland_parameters_global (following DTC pattern)
    # Store complete JSON for flexible parameter passing
    bland_parameters_global: Optional[Dict[str, Any]] = None


@dataclass
class BatchResult:
    """Model for batch submission result"""

    success: bool
    members_count: int
    campaign_id: str
    batch_id: Optional[str] = None
    error: Optional[str] = None
    submitted_members: Optional[List[str]] = None
