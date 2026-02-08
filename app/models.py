"""Pydantic models for request and response validation."""

from pydantic import BaseModel, field_validator
from typing import Optional


class VideoRequest(BaseModel):
    """Request model for video download."""
    url: str

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and length."""
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')

        # Length check (prevent DoS)
        if len(v) > 2000:
            raise ValueError('URL too long')

        return v


class VideoResponse(BaseModel):
    """Response model for video download."""
    success: bool
    download_id: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    platform: Optional[str] = None
