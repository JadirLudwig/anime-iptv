import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Anime, Episode
from .scraper import scrape_anime_episodes, scrape_episode_video
from .validator import is_link_alive

logger = logging.getLogger(__name__)

async def sync_anime_updates(anime_id: int):
    """
    Scrapes the anime page. Adds any new episodes found to the database as Pending.
    """
    db = SessionLocal()
    anime = db.query(Anime).filter(Anime.id == anime_id).first()
    if not anime:
        db.close()
        return

    base_url = anime.base_url
    db.close()

    logger.info(f"Syncing anime updates for {base_url}...")
    anime_name, poster_url, description, scraped_episodes = await scrape_anime_episodes(base_url)

    db = SessionLocal()
    anime = db.query(Anime).filter(Anime.id == anime_id).first()
    if anime_name and anime_name != "Unknown Anime":
        anime.name = anime_name
    if poster_url:
        anime.poster_url = poster_url
    if description:
        anime.description = description

    new_count = 0
    for ep_data in scraped_episodes:
        existing_ep = db.query(Episode).filter(
            Episode.anime_id == anime_id, 
            Episode.page_url == ep_data["page_url"]
        ).first()

        if not existing_ep:
            new_ep = Episode(
                anime_id=anime_id,
                number=ep_data["number"],
                season=ep_data["season"],
                title=ep_data["title"],
                page_url=ep_data["page_url"],
                status="Pending"
            )
            db.add(new_ep)
            new_count += 1
            
    anime.last_sync_date = datetime.utcnow()
    db.commit()
    db.close()
    
    logger.info(f"Finished sync for {base_url}. Found {new_count} new episodes.")

    # Trigger resolve task asynchronously
    asyncio.create_task(resolve_missing_streams())

_resolver_running = False

async def resolve_missing_streams():
    global _resolver_running
    if _resolver_running:
        return
    _resolver_running = True
    logger.info("Resolver loop started — will process all pending episodes...")

    try:
        while True:
            db = SessionLocal()
            pending_ep = db.query(Episode).filter(
                Episode.status.in_(["Pending", "Renovating", "Expired", "Failed"])
            ).first()

            if not pending_ep:
                db.close()
                logger.info("Resolver loop finished — no more pending episodes.")
                break

            pending_ep.status = "Renovating"
            db.commit()
            ep_id = pending_ep.id
            page_url = pending_ep.page_url
            db.close()

            logger.info(f"Resolving stream for episode ID {ep_id} ({page_url})")
            stream_url, media_type, thumb_url, ep_description = await scrape_episode_video(page_url)

            db = SessionLocal()
            ep = db.query(Episode).filter(Episode.id == ep_id).first()
            if stream_url:
                ep.stream_url = stream_url
                ep.media_type = media_type
                ep.status = "Online"
                ep.thumb_url = thumb_url
                ep.description = ep_description
                logger.info(f"Episode {ep_id} resolved successfully.")
            else:
                ep.status = "Failed"

            ep.last_checked = datetime.utcnow()
            db.commit()
            db.close()

            await asyncio.sleep(3)
    finally:
        _resolver_running = False


async def auto_refresh_episode(episode_id: int):
    db = SessionLocal()
    ep = db.query(Episode).filter(Episode.id == episode_id).first()
    if not ep:
        db.close()
        return False
        
    ep.status = "Renovating"
    ep.last_checked = datetime.utcnow()
    db.commit()
    page_url = ep.page_url
    ep_id = ep.id
    db.close()
    
    stream_url, media_type, thumb_url, ep_description = await scrape_episode_video(page_url)
    
    db = SessionLocal()
    ep = db.query(Episode).filter(Episode.id == ep_id).first()
    if stream_url:
        ep.stream_url = stream_url
        ep.media_type = media_type
        ep.status = "Online"
        ep.thumb_url = thumb_url
        ep.description = ep_description
    else:
        ep.status = "Failed"
        
    ep.last_checked = datetime.utcnow()
    db.commit()
    db.close()
    return bool(stream_url)


async def check_all_streams_task():
    """
    Validates established stream links randomly or progressively.
    Also calls sync_anime_updates for all animes to check for new episodes.
    """
    # 1. Check for new episodes
    db = SessionLocal()
    animes = db.query(Anime).all()
    anime_ids = [a.id for a in animes]
    db.close()

    for aid in anime_ids:
        await sync_anime_updates(aid)

    # 2. Check a batch of stream URLs (e.g. 50 oldest checked episodes)
    db = SessionLocal()
    eps = db.query(Episode).filter(Episode.status == "Online").order_by(Episode.last_checked.asc()).limit(50).all()
    
    tasks = []
    for ep in eps:
        tasks.append((ep.id, ep.stream_url))
    db.close()
    
    for ep_id, url in tasks:
        alive = await is_link_alive(url)
        if not alive:
            logger.info(f"Episode ID {ep_id} stream is dead. Queuing for renovation...")
            db = SessionLocal()
            e = db.query(Episode).filter(Episode.id == ep_id).first()
            if e:
                e.status = "Expired"
            db.commit()
            db.close()
            # Queue the resolver
            asyncio.create_task(resolve_missing_streams())


def start_background_jobs(scheduler):
    # Runs the global checker & syncer every 45 minutes
    scheduler.add_job(check_all_streams_task, 'interval', minutes=45)
    # Resolver heartbeat (in case jobs got dropped, run every 5 mins to resolve pending ones)
    scheduler.add_job(resolve_missing_streams, 'interval', minutes=5)
