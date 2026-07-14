"""
Utility Functions
"""
import os
import sys
import logging
from datetime import datetime
from typing import Optional

def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """Setup logging configuration"""
    log_level = level or os.environ.get('LOG_LEVEL', 'INFO')
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Suppress noisy loggers
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

def get_timestamp() -> str:
    """Get current timestamp as string"""
    return datetime.now().isoformat()

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def safe_int(value, default: int = 0) -> int:
    """Safely convert to int"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
