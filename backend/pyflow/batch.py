"""Finite, JSON-compatible batches; not a long-lived message stream."""
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Item(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    index: int = Field(ge=0)
    value: Any


class Batch(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    batch_id: str = Field(min_length=1)
    kind: Literal["list", "text"]
    separator: str = ""
    count: int = Field(ge=0, le=1000)
    items: list[Item] = Field(max_length=1000)

    @model_validator(mode="after")
    def complete(self):
        if len(self.items) != self.count or {i.index for i in self.items} != set(range(self.count)):
            raise ValueError("Batch must contain every index exactly once")
        return self


def split_value(value: Any, separator: str) -> dict:
    if isinstance(value, str):
        if not separator:
            raise ValueError("Text separator cannot be empty")
        values, kind = value.split(separator), "text"
    elif isinstance(value, list):
        values, kind = value, "list"
    else:
        raise ValueError("Split accepts a list or text")
    return Batch(batch_id=str(uuid4()), kind=kind, separator=separator, count=len(values), items=[Item(index=i, value=v) for i, v in enumerate(values)]).model_dump()


def join_value(value: dict) -> Any:
    batch = Batch.model_validate(value)
    values = [item.value for item in sorted(batch.items, key=lambda x: x.index)]
    if batch.kind == "list":
        return values
    if not all(isinstance(v, str) for v in values):
        raise ValueError("A text batch can only join string values")
    return batch.separator.join(values)
