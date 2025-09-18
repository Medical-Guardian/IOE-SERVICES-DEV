import logging
import os

def setup_logging():
    """
    Configure logging for the application with a consistent format.
    """
    log_level = logging.DEBUG if os.environ.get("DEBUG_MODE", "false").lower() == "true" else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )