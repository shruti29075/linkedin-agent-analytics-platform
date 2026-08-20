"""
Structured JSON Logger with Correlation ID Tracking
Ensures machine-parseable logging across all pipeline runs (Part 2 & Part 7).
"""

import logging
import sys
import uuid
from typing import Any, Dict, Optional
import structlog


def get_logger(module_name: str = "pipeline", correlation_id: Optional[str] = None):
    """
    Creates and returns a structured logger bound with a correlation ID.
    If no correlation_id is provided, a fresh UUID4 is generated.
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logger = structlog.get_logger(module_name)
    return logger.bind(correlation_id=correlation_id, service="linkedin-analytics-platform")
