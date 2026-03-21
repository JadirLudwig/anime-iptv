from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Anime(Base):
    __tablename__ = "animes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    # The URL of the anime page on animesonlinecc.to
    base_url = Column(String, unique=True, index=True, nullable=False)
    last_sync_date = Column(DateTime, default=datetime.utcnow)
    poster_url = Column(String, nullable=True)
    description = Column(String, nullable=True)
    
    episodes = relationship("Episode", back_populates="anime", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    anime_id = Column(Integer, ForeignKey("animes.id"), nullable=False)
    number = Column(String, nullable=False) # E.g. Set "1", "2", "3.5", etc.
    season = Column(Integer, default=1)
    title = Column(String, nullable=True)
    thumb_url = Column(String, nullable=True)
    description = Column(String, nullable=True)
    
    # The URL of the specific episode page
    page_url = Column(String, unique=True, nullable=False) 
    
    # The captured media URL (.m3u8 or .mp4)
    stream_url = Column(String, nullable=True)
    # mp4 or m3u8
    media_type = Column(String, nullable=True)
    # Online, Expired, Renovating, Pending
    status = Column(String, default="Pending")
    last_checked = Column(DateTime, default=datetime.utcnow)

    anime = relationship("Anime", back_populates="episodes")
