from pydantic import BaseModel, Field


class SourceData(BaseModel):
    bucket: str
    object_key: str
    filename: str
    size_bytes: int
    raw_data: bytes
    metadata: dict = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
