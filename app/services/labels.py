"""Turn enum members into the {value, label} pairs the UI renders."""
from __future__ import annotations

from typing import Protocol

from app.schemas.common import LabeledValue


class Labeled(Protocol):
    """Any enum in app.enums: an English value plus a Russian label."""

    value: str

    @property
    def label(self) -> str: ...


def to_labeled(member: Labeled) -> LabeledValue:
    """Render one enum member for the client."""
    return LabeledValue(value=member.value, label=member.label)
