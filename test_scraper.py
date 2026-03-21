import asyncio
import logging
import sys

# Setup basic logging to see everything
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

from app.scraper import scrape_anime_episodes, scrape_episode_video

async def test():
    # 1. Fetch Darwin Jihen anime page
    # Since I don't have the exact URL, let me just try to search it or use a likely URL structure
    # animesonlinecc.to/anime/darwin-jihen
    url = "https://animesonlinecc.to/anime/darwin-jihen/"
    print(f"--- Fetching Episodes from {url} ---")
    name, eps = await scrape_anime_episodes(url)
    print(f"Name: {name}")
    print(f"Episodes Output: {len(eps)} found")
    
    if not eps:
        print("No episodes found, scraping failed!")
        return
        
    for ep in eps[:2]:
        print(f"Ep {ep['number']} -> {ep['page_url']}")
        
    print(f"\n--- Testing Video Extraction on {eps[0]['page_url']} ---")
    stream_url, media_type = await scrape_episode_video(eps[0]['page_url'])
    print(f"Result Stream URL: {stream_url}")
    print(f"Result Media Type: {media_type}")

if __name__ == "__main__":
    asyncio.run(test())
