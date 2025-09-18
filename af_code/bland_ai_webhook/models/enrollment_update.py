from typing import Optional
from dataclasses import dataclass


@dataclass
class EnrollmentUpdate:
    """
    Container for enrollment status change decisions.

    This class communicates whether a member's enrollment status should change
    based on call outcomes, including the new status and decision rationale.
    """
    should_update: bool
    new_status: Optional[str]
    reason: str
    confidence_level: str  # 'high', 'medium', 'low'