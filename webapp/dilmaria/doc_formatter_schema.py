from typing import Literal

from pydantic import BaseModel, Field


class StructuredBlock(BaseModel):
    type: Literal["title", "subtitle", "paragraph"]
    content: str = Field(min_length=1)


GenerationMode = Literal["placeholder", "replace_body"]


class DocFormatterPayload(BaseModel):
    filename: str
    content_type: str | None = None
    template_bytes: bytes
    text: str = Field(min_length=1)
    mode: GenerationMode = "placeholder"


class DocFormatterResult(BaseModel):
    document_bytes: bytes
