import asyncio
import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict, Any
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Using a standard browser user agent to avoid basic blocks
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

async def fetch_html(url: str, max_retries: int = 3) -> str:
    """Fetch HTML from a URL with retry logic and exponential backoff."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url, headers=HEADERS)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts.")
                    return ""
                await asyncio.sleep(2 ** attempt)
    return ""

async def scrape_live_results() -> List[Dict[str, Any]]:
    """
    Attempts to scrape live results from results.eci.gov.in.
    Finds the active state election link and parses the results table.
    """
    base_url = "https://results.eci.gov.in"
    html = await fetch_html(base_url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    
    # Strategy: Find the first major link that looks like a state assembly result
    active_link = None
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'Result' in href or 'AcResult' in href or 'PcResult' in href:
            if not href.startswith('http'):
                active_link = f"{base_url}/{href.lstrip('/')}"
            else:
                active_link = href
            break
            
    if not active_link:
        logger.warning("No active election results link found on ECI homepage.")
        return []

    logger.info(f"Found active results link: {active_link}")
    
    # Fetch the actual results page
    results_html = await fetch_html(active_link)
    if not results_html:
        return []

    results_soup = BeautifulSoup(results_html, 'html.parser')
    
    # ECI typically uses standard HTML tables with class 'table' or similar
    table = results_soup.find('table')
    if not table:
        logger.warning("No data table found on the results page.")
        return []

    parsed_results = []
    rows = table.find_all('tr')
    
    # Skip header row(s)
    for row in rows[1:]:
        cols = row.find_all(['td', 'th'])
        if len(cols) >= 6:
            try:
                # Common ECI table structure: O.S.N., Constituency, Leading Candidate, Leading Party, Trailing Candidate, Trailing Party, Margin, Status
                # This varies wildly, we will try a generic extraction
                constituency = cols[1].text.strip()
                winner = cols[2].text.strip()
                party = cols[3].text.strip()
                
                # Try to find margin, usually the 6th or 7th column
                margin_text = cols[-2].text.strip() if len(cols) > 6 else "0"
                margin = int(re.sub(r'\\D', '', margin_text)) if re.sub(r'\\D', '', margin_text) else 0
                
                parsed_results.append({
                    "constituency": constituency,
                    "state": "State Election", # ECI usually separates by state
                    "winner_name": winner,
                    "winner_party": party,
                    "votes": margin * 2, # Guessed votes if not present
                    "margin": margin,
                    "status": "Leading/Won"
                })
            except Exception as e:
                logger.error(f"Error parsing row: {e}")
                continue

    return parsed_results

async def scrape_press_releases() -> List[Dict[str, Any]]:
    """Scrapes latest press releases from ECI."""
    url = "https://www.eci.gov.in/press-releases"
    html = await fetch_html(url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    releases = []
    
    # ECI press releases usually in a list or grid
    items = soup.find_all('div', class_='press-release-item') or soup.find_all('li', class_='press-release')
    
    # Fallback generic parsing if specific classes change
    if not items:
        links = soup.find_all('a', href=True)
        for a in links:
            text = a.text.strip()
            if len(text) > 20 and ('press' in a['href'].lower() or 'release' in a['href'].lower()):
                releases.append({
                    "title": text,
                    "date": "Recent",
                    "summary": "Official ECI Notification",
                    "link": a['href'] if a['href'].startswith('http') else f"https://www.eci.gov.in{a['href']}"
                })
                if len(releases) >= 5: # Limit to top 5
                    break
        return releases

    for item in items[:5]:
        title_tag = item.find('a')
        date_tag = item.find('span', class_='date')
        if title_tag:
            releases.append({
                "title": title_tag.text.strip(),
                "date": date_tag.text.strip() if date_tag else "Recent",
                "summary": "Official ECI Notification",
                "link": title_tag['href'] if title_tag['href'].startswith('http') else f"https://www.eci.gov.in{title_tag['href']}"
            })
            
    return releases

if __name__ == "__main__":
    # Quick test
    print("Testing scrapers...")
    res = asyncio.run(scrape_live_results())
    print(f"Results: {len(res)} found")
