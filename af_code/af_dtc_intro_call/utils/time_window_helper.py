import logging
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class TimeWindowHelper:
    """Helper class for time window operations"""
    
    TIME_WINDOWS = {
        'AM9-10': (datetime.time(9, 0), datetime.time(10, 0)),
        'PM1-3': (datetime.time(13, 0), datetime.time(15, 0)),
        'EV4-6': (datetime.time(16, 0), datetime.time(18, 0))
    }

    @classmethod
    def get_time_window_bounds(cls, preferred_window: str) -> Tuple[Optional[datetime.time], Optional[datetime.time]]:
        """Convert preferred window string to time bounds"""
        logger.info(f"⏰ [TimeWindowHelper] Converting preferred window: {preferred_window}")
        bounds = cls.TIME_WINDOWS.get(preferred_window, (None, None))
        if bounds == (None, None):
            logger.warning(f"⚠️ [TimeWindowHelper] Unknown preferred window: {preferred_window}")
        else:
            logger.info(f"✅ [TimeWindowHelper] Window bounds: {bounds[0].strftime('%H:%M:%S')} - {bounds[1].strftime('%H:%M:%S')}")
        return bounds