"""Response envelope and shared field types."""
from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

T = TypeVar("T")

#: A Kazakhstan IIN: exactly 12 digits.
IIN = Annotated[str, StringConstraints(pattern=r"^\d{12}$")]

#: Passwords are issued by staff, so the floor is modest but non-empty.
Password = Annotated[str, StringConstraints(min_length=6, max_length=128)]

#: Free-form phone number, normalised on the client.
PhoneNumber = Annotated[
    str, StringConstraints(min_length=5, max_length=20, strip_whitespace=True)
]

PersonName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]


class ORMModel(BaseModel):
    """Base for schemas read straight from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class LabeledValue(BaseModel):
    """An enum rendered for the UI: English value plus its Russian label."""

    value: str
    label: str


class Page(BaseModel, Generic[T]):
    """Paginated collection with the metadata the client needs."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    limit: int = Field(ge=1)

    @property
    def pages(self) -> int:
        """Total number of pages for the current limit."""
        if self.limit <= 0:
            return 0
        return -(-self.total // self.limit)


class Message(BaseModel):
    """Plain acknowledgement for endpoints with nothing else to return."""

    detail: str
