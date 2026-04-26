import ctypes
import logging

logger = logging.getLogger(__name__)


def lock_workstation() -> bool:
    try:
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            error_code = ctypes.GetLastError()
            logger.error("LockWorkStation failed with error code %d", error_code)
            return False
        logger.info("Workstation locked successfully")
        return True
    except Exception as e:
        logger.error("Failed to lock workstation: %s", e)
        return False
