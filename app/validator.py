import httpx
import logging

logger = logging.getLogger(__name__)

async def is_link_alive(url: str) -> bool:
    """
    Checks if a given stream URL is still valid (does not return 403, 404, or timeout).
    """
    if not url:
        return False
        
    try:
        # Some CDNs block HEAD requests or act weirdly. We can try HEAD first, then fallback to GET with stream/range if needed.
        # But a simple HEAD with proper headers often works.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code in [200, 206, 302]: # 302 redirect happens often on CDNs
                return True
            logger.info(f"Link {url} returned status {resp.status_code}")
            return False
            
    except Exception as e:
        logger.warning(f"Validation error for {url}: {e}")
        return False
