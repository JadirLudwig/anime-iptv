import asyncio
import os
import random
import logging
import re
import httpx
from fake_useragent import UserAgent
from bs4 import BeautifulSoup
from typing import Tuple, Optional, List, Dict

logger = logging.getLogger(__name__)

# User Agent settings
ua_provider = UserAgent(os='linux', browsers=['chrome'])

def get_session():
    """Returns an httpx client with standard headers to bypass basic bot detection."""
    return httpx.AsyncClient(
        follow_redirects=True, 
        verify=False,
        headers={
            "User-Agent": ua_provider.random,
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://animesonlinecc.to/"
        },
        timeout=15
    )

async def scrape_anime_episodes(anime_url: str):
    """
    Scrapes the anime main page to extract the Anime Name and a list of Episodes grouped by season.
    Lightweight version: uses HTTPX + BeautifulSoup. Works on Smartphones (Termux).
    """
    anime_name = "Unknown Anime"
    poster_url = None
    description = None
    episodes = []
    
    async with get_session() as client:
        try:
            logger.info(f"Loading anime page directly: {anime_url}")
            resp = await client.get(anime_url)
            if resp.status_code != 200:
                logger.error(f"Failed to load anime page, status: {resp.status_code}")
                return anime_name, poster_url, description, episodes
            
            soup = BeautifulSoup(resp.text, 'lxml')
            
            # Extract basic info
            h1 = soup.find('h1')
            if h1:
                anime_name = h1.text.strip()
            
            # Extract Poster
            poster_div = soup.select_one('div.poster img')
            if poster_div and poster_div.get('src'):
                poster_url = poster_div['src']
                
            # Extract Description
            desc_container = soup.select_one('div.wp-content, div.resume, #info div.wp-content')
            if desc_container:
                description = desc_container.text.strip()
                
            # Strategy for seasons (Dooplay)
            seen_urls = set()
            season_containers = soup.select('div.seasons div#seasons div.season, div#seasons div.temporada, #seasons .se-c')
            
            if season_containers:
                for s_idx, container in enumerate(season_containers):
                    season_num = s_idx + 1
                    season_title = container.find(['h3', 'span', 'div'], class_='title')
                    if season_title:
                        match = re.search(r'(\d+)', season_title.text)
                        if match: season_num = int(match.group(1))
                    
                    for a in container.find_all('a', href=True):
                        href = a['href']
                        if ('episodio' in href.lower() or 'episode' in href.lower()) and anime_url.split('/')[2] in href:
                            if href not in seen_urls:
                                seen_urls.add(href)
                                title = a.text.strip() or f"Episódio {len(seen_urls)}"
                                number_part = href.strip('/').split('-')[-1]
                                number = number_part if (number_part.replace('.','').isdigit()) else title.split()[-1]
                                episodes.append({
                                    "number": str(number)[:10],
                                    "season": season_num,
                                    "title": title[:150],
                                    "page_url": href
                                })
            
            # Fallback
            if not episodes:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if '/episodio/' in href.lower() and anime_url.split('/')[2] in href:
                        if href not in seen_urls:
                            seen_urls.add(href)
                            episodes.append({
                                "number": href.strip('/').split('-')[-1],
                                "season": 1,
                                "title": a.text.strip() or "Episódio",
                                "page_url": href
                            })
                            
            episodes.sort(key=lambda x: (int(x['season']), float(x['number']) if x['number'].replace('.','').isdigit() else 0))
                
        except Exception as e:
            logger.error(f"Error in lightweight scrape_anime_episodes: {e}")
            
    return anime_name, poster_url, description, episodes


async def scrape_episode_video(episode_page_url: str):
    """
    Captures video stream or IFRAME from the episode page without using a browser.
    Simulates the WordPress DooPlay (admin-ajax) logic.
    Returns: (stream_url, media_type, thumb_url, description)
    """
    stream_url = None
    media_type = None
    thumb_url = None
    description = None

    async with get_session() as client:
        try:
            logger.info(f"Loading episode page: {episode_page_url}")
            resp = await client.get(episode_page_url)
            if resp.status_code != 200:
                return None, None, None, None
            
            soup = BeautifulSoup(resp.text, 'lxml')
            
            # 1. Metadata (Thumb/Desc)
            img_el = soup.select_one('div.imagen img')
            if img_el and img_el.get('src'):
                thumb_url = img_el['src']
            desc_el = soup.select_one('div.wp-content, div.resume')
            if desc_el:
                description = desc_el.text.strip()

            # 2. Extract DooPlay Player Ajax Params
            # Usually: <li class="dooplay_player_option" data-post="ID" data-nume="1" data-type="video">
            ajax_url = f"{episode_page_url.split('/episodio/')[0]}/wp-admin/admin-ajax.php"
            player_options = soup.select('li.dooplay_player_option, li[data-post]')
            logger.info(f"Found {len(player_options)} player options via AJAX probes")

            for opt in player_options:
                post_id = opt.get('data-post')
                nume = opt.get('data-nume')
                type_val = opt.get('data-type')

                if not post_id or not nume: continue

                # Send AJAX Request (Simulate browser button click)
                ajax_data = {
                    "action": "doo_player_ajax",
                    "post": post_id,
                    "nume": nume,
                    "type": type_val
                }
                
                try:
                    ajax_resp = await client.post(ajax_url, data=ajax_data)
                    if ajax_resp.status_code == 200:
                        res = ajax_resp.json()
                        embed_html = res.get('embed_url', '') # This is actually HTML in Dooplay
                        
                        # Extract URL from iframe src in the embed_html
                        raw_url = None
                        if 'src="' in embed_html:
                            match = re.search(r'src="([^"]+)"', embed_html)
                            if match: raw_url = match.group(1).replace('&amp;', '&')
                        elif 'href="' in embed_html:
                            match = re.search(r'href="([^"]+)"', embed_html)
                            if match: raw_url = match.group(1).replace('&amp;', '&')
                        else:
                            # It might be a direct link
                            raw_url = embed_html.strip()

                        if raw_url:
                            logger.info(f"Found candidate URL from AJAX: {raw_url}")
                            
                            # Decide if we take it
                            # Ignore IP-locked Google Video URLs
                            if 'googlevideo.com' in raw_url: continue
                            
                            # Check for direct video extensions
                            if '.m3u8' in raw_url.lower():
                                stream_url, media_type = raw_url, '.m3u8'
                                break
                            if '.mp4' in raw_url.lower():
                                stream_url, media_type = raw_url, '.mp4'
                                break
                            
                            # If it's a known embed (YouTube/Blogger), save it as 'youtube'
                            if any(x in raw_url for x in ['youtube.com', 'blogger.com', 'blogspot.com', 'drive.google', 'ok.ru']):
                                stream_url, media_type = raw_url, 'youtube'
                                # continue search for direct if it was YouTube (often used as fallback)
                                if 'youtube' not in raw_url: break 

                except Exception as ex:
                    logger.warning(f"Failed to probe player option {nume}: {ex}")

            # 3. Fallback: Search for any iframe in the main page text
            if not stream_url:
                iframes = soup.find_all('iframe', src=True)
                for f in iframes:
                    src = f['src']
                    if 'youtube' in src or 'blogger' in src or 'drive.google' in src:
                        stream_url, media_type = src, 'youtube'
                        break

        except Exception as e:
            logger.error(f"Error in lightweight scrape_episode_video: {e}")
            
    return stream_url, media_type, thumb_url, description
