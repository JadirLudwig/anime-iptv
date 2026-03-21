from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class AnimeCreate(BaseModel):
    base_url: str

class EpisodeResponse(BaseModel):
    id: int
    anime_id: int
    number: str
    season: int
    title: Optional[str]
    thumb_url: Optional[str]
    description: Optional[str]
    page_url: str
    stream_url: Optional[str]
    media_type: Optional[str]
    status: str
    last_checked: datetime

    class Config:
        orm_mode = True

class AnimeResponse(BaseModel):
    id: int
    name: str
    base_url: str
    poster_url: Optional[str]
    description: Optional[str]
    last_sync_date: datetime
    episodes: List[EpisodeResponse] = []

    class Config:
        orm_mode = True
