"""Content languages supported by the platform."""
from __future__ import annotations

import enum


class Language(str, enum.Enum):
    """Russian is the primary language and the fallback for Kazakh."""

    RU = "ru"
    KZ = "kz"


DEFAULT_LANGUAGE: Language = Language.RU
