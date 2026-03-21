import asyncio
import os
import random
import logging
from playwright.async_api import async_playwright
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Use system chromium if BROWSER_PATH is set (Termux/TV Box)
BROWSER_PATH = os.environ.get("BROWSER_PATH")

async def _human_delay(page, min_ms=1000, max_ms=3000):
    delay = random.uniform(min_ms, max_ms)
    await page.wait_for_timeout(delay)

async def scrape_anime_episodes(anime_url: str):
    """
    Scrapes the anime main page to extract the Anime Name and a list of Episodes grouped by season.
    Returns: (anime_name, poster_url, description, episodes)
    """
    ua = UserAgent(os='linux', browsers=['chrome'])
    random_ua = ua.random
    
    anime_name = "Unknown Anime"
    poster_url = None
    description = None
    episodes = []
    
    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        }
        if BROWSER_PATH:
            launch_args["executable_path"] = BROWSER_PATH
            
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(user_agent=random_ua, java_script_enabled=True)
        page = await context.new_page()

        try:
            logger.info(f"Navigating to fetch episodes for {anime_url}")
            await page.goto(anime_url, wait_until='domcontentloaded', timeout=30000)
            await _human_delay(page, 2000, 4000)
            
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            h1 = soup.find('h1')
            if h1:
                anime_name = h1.text.strip()
                
            # Extract Poster
            poster_div = soup.select_one('div.poster img')
            if poster_div and poster_div.get('src'):
                poster_url = poster_div['src']
            elif soup.find('meta', property='og:image'):
                poster_url = soup.find('meta', property='og:image')['content']
                
            # Extract Description (Synopsis)
            description = None
            desc_container = soup.select_one('div.wp-content, div.resume, #info div.wp-content')
            if desc_container:
                description = desc_container.text.strip().replace('\t', '').replace('\r', '')
                
            # Try to find seasons (common in Dooplay theme)
            season_containers = soup.select('div.seasons div#seasons div.season, div#seasons div.temporada, #seasons .se-c')
            
            seen_urls = set()
            
            if season_containers:
                logger.info(f"Found {len(season_containers)} season containers")
                for s_idx, container in enumerate(season_containers):
                    # Try to extract season number from ID or title
                    season_num = s_idx + 1
                    season_title = container.find(['h3', 'span', 'div'], class_='title')
                    if season_title:
                        import re
                        match = re.search(r'(\d+)', season_title.text)
                        if match:
                            season_num = int(match.group(1))
                    
                    # Find episodes within this season
                    ep_links = container.find_all('a', href=True)
                    for a in ep_links:
                        href = a['href']
                        if ('episodio' in href.lower() or 'episode' in href.lower()) and anime_url.split('/')[2] in href:
                            if href not in seen_urls:
                                seen_urls.add(href)
                                title = a.text.strip() or f"Episódio {len(seen_urls)}"
                                number_part = href.strip('/').split('-')[-1]
                                number = number_part if (number_part.isdigit() or '.' in number_part) else title.split()[-1]
                                
                                episodes.append({
                                    "number": str(number)[:10],
                                    "season": season_num,
                                    "title": title[:150],
                                    "page_url": href
                                })
            
            # Fallback if no specific season containers found
            if not episodes:
                logger.info("No season containers found, falling back to global link search")
                links = soup.find_all('a', href=True)
                for a in links:
                    href = a['href']
                    if ('episodio' in href.lower() or 'episode' in href.lower()) and anime_url.split('/')[2] in href:
                        if href not in seen_urls:
                            seen_urls.add(href)
                            title = a.text.strip() or "Episódio"
                            number_part = href.strip('/').split('-')[-1]
                            number = number_part if number_part.isdigit() else title.split()[-1]
                            episodes.append({
                                "number": str(number)[:10],
                                "season": 1,
                                "title": title[:100],
                                "page_url": href
                            })
                            
            # Sort episodes: first by season, then by number
            try:
                def sort_key(x):
                    s = int(x['season'])
                    try:
                        n = float(x['number'].replace('.','',1))
                    except:
                        n = 0
                    return (s, n)
                    
                episodes.sort(key=sort_key)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Error scraping episodes from {anime_url}: {e}")
        finally:
            await browser.close()
            
    return anime_name, poster_url, description, episodes


async def scrape_episode_video(episode_page_url: str):
    """
    Loads the episode page and intercepts network requests to capture .m3u8 or .mp4.
    
    Strategy for animesonlinecc.to (Dooplay/WordPress theme):
    1. Load the episode page.
    2. Intercept the admin-ajax.php response which returns an iframe URL.
    3. Navigate to that iframe URL.
    4. Capture any .m3u8 or video Content-Type response from the iframe's player.
    
    Returns: (stream_url, media_type, thumb_url, description)
    """
    ua = UserAgent(os='linux', browsers=['chrome'])
    random_ua = ua.random
    
    stream_url = None
    media_type = None
    thumb_url = None
    description = None
    iframe_urls = []

    async with async_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--allow-running-insecure-content'
            ]
        }
        if BROWSER_PATH:
            launch_args["executable_path"] = BROWSER_PATH
            
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            user_agent=random_ua,
            java_script_enabled=True
        )

        # --- PHASE 1: Main page — capture iframe URL from admin-ajax response ---
        page = await context.new_page()

        async def capture_ajax_iframe(response):
            """Capture admin-ajax.php responses that return an iframe embed URL."""
            nonlocal stream_url, media_type
            if stream_url:
                return
            try:
                if 'admin-ajax' in response.url:
                    body = await response.text()
                    import re
                    # Look for YouTube embed URLs specifically
                    yt_found = re.findall(r'(https?://(?:www\.)?youtube(?:-nocookie)?\.com/embed/[^"\\\s]+)', body)
                    for u in yt_found:
                        u = u.replace('\\/', '/').split('"')[0].split("'")[0]
                        if u not in iframe_urls:
                            iframe_urls.append(u)
                            logger.info(f"Captured YouTube embed from ajax: {u}")
                    # Also catch blogger/drive embeds
                    src_found = re.findall(r'src[\\]?=[\\]?"(https?://[^"\\]+)"', body)
                    for u in src_found:
                        u = u.replace('\\/', '/')
                        if 'youtube' in u or 'drive.google' in u or 'blogger' in u:
                            if u not in iframe_urls:
                                iframe_urls.append(u)
                                logger.info(f"Captured embed src from ajax: {u}")
            except Exception:
                pass

        async def capture_stream_direct(response):
            """Capture direct video streams from any response."""
            nonlocal stream_url, media_type
            if stream_url:
                return
            try:
                url = response.url
                url_lower = url.lower()
                ct = response.headers.get("content-type", "").lower()

                # Skip IP-locked Google Video URLs — they won't work on other devices
                if 'googlevideo.com' in url_lower:
                    logger.info(f"Skipping IP-locked googlevideo.com URL")
                    return

                if '.m3u8' in url_lower:
                    stream_url = url
                    media_type = '.m3u8'
                    logger.info(f"Captured m3u8 via URL extension: {url}")
                elif '.mp4' in url_lower and 'thumbnail' not in url_lower and 'poster' not in url_lower:
                    stream_url = url
                    media_type = '.mp4'
                    logger.info(f"Captured mp4 via URL extension: {url}")
                elif 'mpegurl' in ct or 'x-mpegurl' in ct:
                    stream_url = url
                    media_type = '.m3u8'
                    logger.info(f"Captured m3u8 via Content-Type: {url}")
                elif 'video/mp4' in ct and 'googlevideo' not in url_lower:
                    stream_url = url
                    media_type = '.mp4'
                    logger.info(f"Captured video/mp4 via Content-Type: {url}")
            except Exception:
                pass

        page.on('response', capture_ajax_iframe)
        page.on('response', capture_stream_direct)

        try:
            logger.info(f"Phase 1: Loading episode page {episode_page_url}")
            await page.goto(episode_page_url, wait_until='domcontentloaded', timeout=30000)
            await _human_delay(page, 2000, 3000)

            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Capture Thumbnail
            img_el = soup.select_one('div.imagen img')
            if img_el and img_el.get('src'):
                thumb_url = img_el['src']
            elif soup.find('meta', property='og:image'):
                thumb_url = soup.find('meta', property='og:image')['content']
                
            # Capture Episode Description
            desc_el = soup.select_one('div.wp-content, div.resume')
            if desc_el:
                description = desc_el.text.strip().replace('\t', '').replace('\r', '')

            # Click each player option button (HD, SD, etc.) to trigger the ajax request
            buttons = await page.query_selector_all(
                "li.dooplay_player_option, li[data-post], .doo_player_option, .player-option, .server-item"
            )
            logger.info(f"Found {len(buttons)} player option buttons")

            if buttons:
                for btn in buttons[:4]:
                    if stream_url:
                        break
                    try:
                        await btn.click(timeout=3000)
                        await _human_delay(page, 2000, 3000)
                    except Exception:
                        pass
            else:
                # Fallback: click in the center of the page where the player usually renders
                await page.mouse.click(760, 400)
                await _human_delay(page, 3000, 5000)

            # Also get iframes directly from the rendered page
            if not stream_url:
                iframes_on_page = await page.query_selector_all("iframe")
                for iframe_el in iframes_on_page:
                    try:
                        src = await iframe_el.get_attribute('src')
                        if src and src.startswith('http') and src not in iframe_urls:
                            iframe_urls.append(src)
                            logger.info(f"Found iframe src directly on page: {src}")
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Phase 1 error for {episode_page_url}: {e}")

        # --- PHASE 2: Navigate into iframe URLs to capture actual video stream ---
        if not stream_url and iframe_urls:
            logger.info(f"Phase 2: Checking {len(iframe_urls)} iframe URL(s) for video stream")
            for iframe_url in iframe_urls[:5]:
                if stream_url:
                    break
                # YouTube embeds: save directly as type 'youtube' — do NOT navigate
                if 'youtube.com/embed/' in iframe_url or 'youtube-nocookie.com/embed/' in iframe_url:
                    stream_url = iframe_url
                    media_type = 'youtube'
                    logger.info(f"Saved YouTube embed URL directly: {iframe_url}")
                    break
                # Blogger video embeds
                if 'blogger.com' in iframe_url or 'blogspot.com' in iframe_url:
                    stream_url = iframe_url
                    media_type = 'youtube'
                    logger.info(f"Saved Blogger embed URL directly: {iframe_url}")
                    break
                try:
                    iframe_page = await context.new_page()
                    iframe_page.on('response', capture_stream_direct)
                    await iframe_page.goto(iframe_url, wait_until='domcontentloaded', timeout=20000)
                    await _human_delay(iframe_page, 2000, 3000)
                    await iframe_page.mouse.click(640, 360)
                    await _human_delay(iframe_page, 3000, 5000)
                    await iframe_page.close()
                except Exception as e:
                    logger.error(f"Phase 2 iframe error ({iframe_url}): {e}")

        await browser.close()
            
    if stream_url:
        logger.info(f"Successfully captured stream: {stream_url} ({media_type})")
    else:
        logger.warning(f"No stream found for {episode_page_url}")
        
    return stream_url, media_type, thumb_url, description
