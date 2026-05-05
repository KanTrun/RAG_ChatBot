"""Feedback schema."""

from typing import Literal

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    score: Literal[-1, 1]
    comment: str | None = Field(default=None, max_length=500)
