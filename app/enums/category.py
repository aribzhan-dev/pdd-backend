"""Driving licence categories a student can study for."""
from __future__ import annotations

import enum


class DrivingCategory(str, enum.Enum):
    """Study programme picked when a student account is created."""

    B = "B"
    B_C1 = "B_C1"

    @property
    def label(self) -> str:
        """Human-readable name shown in the UI (Russian)."""
        return CATEGORY_LABELS[self]


CATEGORY_LABELS: dict[DrivingCategory, str] = {
    DrivingCategory.B: "B",
    DrivingCategory.B_C1: "B, C1",
}
