from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TagInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    definition: str = Field(min_length=1, max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("name", "definition")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("名称和定义不能为空")
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def aliases_clean(cls, values: list[str]) -> list[str]:
        result = list(dict.fromkeys(" ".join(v.split()) for v in values if v.strip()))
        if any(len(v) > 40 for v in result):
            raise ValueError("别名最多 40 字")
        return result


class Candidate(BaseModel):
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=30000)
    keywords: list[str] = Field(default_factory=list, max_length=50)
    tag_ids: list[int] = Field(default_factory=list, max_length=30)
    new_tags: list[TagInput] = Field(default_factory=list, max_length=10)
    accepted_new_tags: list[int] = Field(default_factory=list, max_length=10)


class SummaryInput(Candidate):
    record_date: date
    diary_ids: list[int] = Field(default_factory=list, max_length=100)
    session_ids: list[int] = Field(default_factory=list, max_length=100)
    source_type: Literal["in_app_ai", "external_discussion", "manual"]
    source_note: str = Field(default="", max_length=1000)
    confirmed: bool = False


class DiscussionInput(BaseModel):
    record_date: date
    diary_ids: list[int] = Field(min_length=1, max_length=100)
    title: str = Field(default="", max_length=200)
    question: str = Field(default="", max_length=10000)
    background: str = Field(default="", max_length=5000)
    base_summary_id: int | None = None


class MessageInput(BaseModel):
    task: Literal["analyze", "discuss", "summarize"] = "discuss"
    body: str = Field(min_length=1, max_length=10000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value


class GenerationInput(BaseModel):
    session_id: int
    message_id: int
    consent_external_ai: bool = False


class SuggestTagsInput(BaseModel):
    body: str = Field(min_length=1, max_length=30000)
    consent_external_ai: bool = False


class MergeTagInput(BaseModel):
    target_id: int
