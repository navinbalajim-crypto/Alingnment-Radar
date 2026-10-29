"""Secure logging configuration with sensitive data masking."""

import logging
import re
import sys
from typing import Any

# Patterns to mask in logs
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
BEARER_REGEX = re.compile(r"Bearer\s+([A-Za-z0-9\-_\.=]+)", re.IGNORECASE)
OTP_REGEX = re.compile(r"\b(otp|code|verification_code)\s*[:=]\s*['\"]?(\d{6})['\"]?", re.IGNORECASE)
API_KEY_REGEX = re.compile(r"\b(api[_-]?key|secret|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?", re.IGNORECASE)


class SensitiveDataFilter(logging.Filter):
    """Filter that masks emails, tokens, OTPs, and API credentials from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            msg = EMAIL_REGEX.sub("[REDACTED_EMAIL]", msg)
            msg = BEARER_REGEX.sub("Bearer [REDACTED_TOKEN]", msg)
            msg = OTP_REGEX.sub(r"\1: [REDACTED_CODE]", msg)
            msg = API_KEY_REGEX.sub(r"\1: [REDACTED_SECRET]", msg)
            record.msg = msg

        if record.args:
            cleaned_args: list[Any] = []
            for arg in record.args if isinstance(record.args, (list, tuple)) else [record.args]:
                if isinstance(arg, str):
                    s = EMAIL_REGEX.sub("[REDACTED_EMAIL]", arg)
                    s = BEARER_REGEX.sub("Bearer [REDACTED_TOKEN]", s)
                    s = OTP_REGEX.sub(r"\1: [REDACTED_CODE]", s)
                    s = API_KEY_REGEX.sub(r"\1: [REDACTED_SECRET]", s)
                    cleaned_args.append(s)
                else:
                    cleaned_args.append(arg)
            record.args = tuple(cleaned_args) if isinstance(record.args, tuple) else cleaned_args

        return True


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure standard application logger with sensitive data redaction."""
    logger = logging.getLogger("alignment_radar")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = setup_logging()
