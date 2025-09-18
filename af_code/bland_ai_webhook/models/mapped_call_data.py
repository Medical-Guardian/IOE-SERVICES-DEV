from typing import Optional
from dataclasses import dataclass

@dataclass
class MappedCallData:
    """
    Data container that holds the transformed call information in our internal format.
    """
    disposition: str
    next_action: str
    duration_sec: Optional[int]
    response_summary: str
    vendor_session_id: str
    call_completed: bool
    opt_out_requested: bool
    contact_made: bool
    call_quality_score: Optional[float]
    sentiment_analysis: Optional[str]
    key_topics: Optional[str]