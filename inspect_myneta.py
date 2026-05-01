"""Debug why Assam/Kerala/Puducherry return 0 candidates."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import httpx, asyncio
from bs4 import BeautifulSoup

async def check():
    states = [
        ("Assam p1", "https://www.myneta.info/assam2026/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"),
        ("Kerala p1", "https://www.myneta.info/kerala2026/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"),
        ("Puducherry p1", "https://www.myneta.info/puducherry2026/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"),
        ("WB p12", "https://www.myneta.info/WestBengal2026/index.php?action=summary&subAction=candidates_analyzed&sort=candidate&page=12"),
    ]
    async with httpx.AsyncClient(
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10)
    ) as client:
        for label, url in states:
            r = await client.get(url, timeout=25.0)
            print(f"\n{label}: status={r.status_code} len={len(r.text)}")
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', class_='w3-bordered')
            if table:
                rows = table.find_all('tr')
                print(f"  Table: {len(rows)} rows")
                if len(rows) > 1:
                    cols = rows[1].find_all('td')
                    print(f"  First row cols: {len(cols)}")
                    if cols:
                        a = cols[1].find('a') if len(cols) > 1 else None
                        print(f"  Col1 a-tag: {a}")
                        print(f"  Col1 text: {cols[1].text.strip()[:50]}")
                        if a: print(f"  href: {a.get('href')}")
            else:
                tables = soup.find_all('table')
                print(f"  No w3-bordered. Total tables: {len(tables)}")
                for i, t in enumerate(tables[:6]):
                    print(f"    [{i}] class={t.get('class')} rows={len(t.find_all('tr'))}")
            await asyncio.sleep(0.5)

asyncio.run(check())
