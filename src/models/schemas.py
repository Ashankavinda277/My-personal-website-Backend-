from pydantic import BaseModel
from typing import List, Optional

class BlogCreate(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = []

class BlogUpdate(BaseModel):
    title: Optional[str]
    content: Optional[str]
    tags: Optional[List[str]]
