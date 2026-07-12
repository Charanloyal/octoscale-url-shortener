from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, field_validator, ConfigDict

class URLBase(BaseModel):
    original_url: str

    @field_validator("original_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        if len(v) > 2048:
            raise ValueError("URL exceeds maximum length of 2048 characters")
        return v

class URLCreate(URLBase):
    custom_code: Optional[str] = None

    @field_validator("custom_code")
    @classmethod
    def validate_custom_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.isalnum():
                raise ValueError("Custom code must be alphanumeric")
            if not (3 <= len(v) <= 10):
                raise ValueError("Custom code must be between 3 and 10 characters")
        return v

class ClickAnalyticSchema(BaseModel):
    referrer: Optional[str]
    user_agent: Optional[str]
    clicked_at: datetime

    model_config = ConfigDict(from_attributes=True)

class URLResponse(URLBase):
    short_code: str
    short_url: str
    clicks: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class URLAnalyticsResponse(BaseModel):
    short_code: str
    original_url: str
    clicks: int
    created_at: datetime
    recent_clicks: List[ClickAnalyticSchema]

    model_config = ConfigDict(from_attributes=True)
