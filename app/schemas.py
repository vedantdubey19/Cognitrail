from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class NewWorkspace(Strict):
    name: str = Field(min_length=1, max_length=100)


class ResearchRequest(Strict):
    workspace_id: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=5, max_length=2000)
    urls: list[str] = Field(default_factory=list, max_length=6)
    web_search: bool = False
    max_web_sources: int = Field(4, ge=0, le=6)


class Plan(Strict):
    subquestions: list[str] = Field(min_length=1, max_length=4)
    search_queries: list[str] = Field(min_length=1, max_length=4)


class Approval(Strict):
    approved: Literal[True]
    subquestions: list[str] | None = Field(None, min_length=1, max_length=4)
