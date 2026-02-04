from pydantic import BaseModel
from typing import List, Optional


class BlogCreate(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = []
    cover_image: Optional[str] = None
    type: Optional[str] = None


class BlogUpdate(BaseModel):
    title: Optional[str]
    content: Optional[str]
    tags: Optional[List[str]]
    cover_image: Optional[str]
    type: Optional[str]
