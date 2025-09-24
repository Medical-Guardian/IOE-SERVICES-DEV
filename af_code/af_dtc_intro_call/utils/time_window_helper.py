import logging
from typing import Tuple, Optional
from datetime import datetime, time

logger = logging.getLogger(__name__)

class TimeWindowHelper:
    """Helper class for time window operations"""
    
    TIME_WINDOWS = {
        'AM9-10': (time(9, 0), time(10, 0)),
        'PM1-3': (time(13, 0), time(15, 0)),
        'EV4-6': (time(2, 0), time(8, 0))
        #'EV4-6': (time(16, 0), time(19, 0))
    }

    @classmethod
    def get_time_window_bounds(cls, preferred_window: str) -> Tuple[Optional[time], Optional[time]]:
        """Convert preferred window string to time bounds"""
        logger.info(f"⏰ [TimeWindowHelper] Converting preferred window: {preferred_window}")
        bounds = cls.TIME_WINDOWS.get(preferred_window, (None, None))
        if bounds == (None, None):
            logger.warning(f"⚠️ [TimeWindowHelper] Unknown preferred window: {preferred_window}")
        else:
            logger.info(f"✅ [TimeWindowHelper] Window bounds: {bounds[0].strftime('%H:%M:%S')} - {bounds[1].strftime('%H:%M:%S')}")
        return bounds