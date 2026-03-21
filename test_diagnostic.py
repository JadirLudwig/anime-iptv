import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
from playwright.async_api import async_playwright
import random

async def test_animesonline(url):
    print(f"--- Diagnosing {url} ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox'
        ])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            java_script_enabled=True
        )
        page = await context.new_page()

        found = []
        async def handle_response(response):
            try:
                ct = response.headers.get("content-type", "").lower()
                url_str = response.url.lower()
                # Print any media related requests or suspected video URLs
                if "video" in ct or "mpegurl" in ct or ".m3u" in url_str or ".mp4" in url_str:
                    print(f"[MEDIA/VIDEO FOUND] Content-Type: {ct} | URL: {response.url}")
                    found.append(response.url)
            except Exception as e:
                pass

        page.on('response', handle_response)
        
        try:
            print("Navigating...")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            print("Finding player buttons...")
            buttons = await page.query_selector_all("li.dooplay_player_option, .player-option, .player-options li")
            print(f"Found {len(buttons)} player buttons")
            if buttons:
                for idx, btn in enumerate(buttons):
                    print(f"Clicking button {idx}")
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(3000)
                    await page.mouse.click(960, 500)
                    await page.wait_for_timeout(2000)
            else:
                for _ in range(3):
                    await page.mouse.click(960, 300)
                    await page.wait_for_timeout(2000)
                    
            print("Finished clicking, waiting for final requests...")
            await page.wait_for_timeout(5000)
            
        except Exception as e:
            print("Error:", e)
        finally:
            await browser.close()
        
        print("Total media found:", len(found))

if __name__ == "__main__":
    asyncio.run(test_animesonline("https://animesonlinecc.to/episodio/darwin-jihen-episodio-1/"))
