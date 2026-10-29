"""SQLAlchemy base and declarative model support."""

from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import DateTime, Uuid, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.attributes import set_committed_value


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime object is timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""
    pass


def _restore_utc(target, *_args) -> None:
    """SQLite returns DateTime(timezone=True) columns without tzinfo. Every timestamp is stored as UTC, so mark
    loaded values as UTC; otherwise the API serialises them without an offset and browsers read them as local
    time. PostgreSQL already returns aware values, so this is a no-op there."""
    state = inspect(target)
    for attr in state.mapper.column_attrs:
        if not isinstance(attr.columns[0].type, DateTime):
            continue
        value = state.dict.get(attr.key)
        if isinstance(value, datetime) and value.tzinfo is None:
            set_committed_value(target, attr.key, value.replace(tzinfo=timezone.utc))


event.listen(Base, "load", _restore_utc, propagate=True)
event.listen(Base, "refresh", _restore_utc, propagate=True)
