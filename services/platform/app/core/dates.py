"""Normalize source dates without inventing publication timestamps."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except ValueError:
            try:
                result = parsedate_to_datetime(str(value))
            except (ValueError, TypeError, OverflowError):
                return None
    if result.tzinfo:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    return result


def iso_date(value):
    result = parse_date(value)
    return result.isoformat() + 'Z' if result else None
