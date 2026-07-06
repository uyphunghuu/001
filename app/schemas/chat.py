from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class Source(BaseModel):
    type: str
    name: str
    summary: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
