from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import ApiModel

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Answer = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class AnswerItem(ApiModel):
    question: Question
    answer: Answer


class AnswersIn(ApiModel):
    items: list[AnswerItem] = Field(max_length=50)


class AnswersOut(ApiModel):
    items: list[AnswerItem]
