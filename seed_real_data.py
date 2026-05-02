"""
VoteWise India — MyNeta Playwright Scraper
Uses a real headless Chromium browser to scrape data (bypasses rate limiting).
Scrapes from the paginated summary/candidates_analyzed pages.
"""
import sys, time, re, sqlite3, urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

DB_FILE = "matdata_mitra.db"

STATES = [
    {"name": "Tamil Nadu",   "slug": "TamilNadu2026"},
    {"name": "West Bengal",  "slug": "WestBengal2026"},
    {"name": "Assam",        "slug": "assam2026"},
    {"name": "Kerala",       "slug": "kerala2026"},
    {"name": "Puducherry",   "slug": "puducherry2026"},
]

ALLIANCES = {
    "INDIA":    {"name": "INDIA Bloc",                  "color": "#1565C0"},
    "NDA":      {"name": "National Democratic Alliance", "color": "#FF9933"},
    "AIADMK+":  {"name": "AIADMK Alliance",             "color": "#4CAF50"},
    "OTHERS":   {"name": "Others/Independent",           "color": "#8b949e"},
}

PARTY_ALLIANCE = {
    "DMK": "INDIA", "INC": "INDIA", "VCK": "INDIA", "CPI": "INDIA",
    "CPI(M)": "INDIA", "CPIM": "INDIA", "MDMK": "INDIA", "AITC": "INDIA",
    "TMC": "INDIA", "IUML": "INDIA", "RSP": "INDIA",
    "BJP": "NDA", "PMK": "NDA", "JD(U)": "NDA",
    "AIADMK": "AIADMK+", "ADMK": "AIADMK+", "DMDK": "AIADMK+",
    "IND": "OTHERS", "NTK": "OTHERS",
}

PARTY_COLORS = {
    "DMK": "#D32F2F", "INC": "#1976D2", "BJP": "#F57C00", "AIADMK": "#388E3C",
    "ADMK": "#388E3C", "TMC": "#2E7D32", "AITC": "#2E7D32", "CPI": "#E53935",
    "CPI(M)": "#B71C1C", "CPIM": "#B71C1C", "PMK": "#FDD835", "NTK": "#D84315",
    "VCK": "#6A1B9A", "MDMK": "#0D47A1", "IND": "#9E9E9E", "DMDK": "#1B5E20",
}

def parse_rs(text):
    if not text: return 0.0
    text = text.replace('\xa0', ' ').strip()
    if 'Nil' in text: return 0.0
    m = re.search(r'Rs\s*([\d,]+)', text)
    if m:
        raw = m.group(1).replace(',', '')
        try: return round(float(raw) / 10000000, 4)
        except: pass
    c = re.search(r'(\d+)\s*Crore', text)
    if c: return float(c.group(1))
    l = re.search(r'(\d+)\s*Lac', text)
    if l: return round(float(l.group(1)) / 100, 4)
    return 0.0

def get_type(name):
    u = name.upper()
    if '(SC)' in u: return 'SC'
    if '(ST)' in u: return 'ST'
    return 'GEN'


def parse_table(table, state_name, cur, conn, const_cache, party_cache):
    """Parse rows from a w3-bordered table and insert into DB. Returns count inserted."""
    rows = table.find_all('tr')[1:]  # skip header
    inserted = 0

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 7: continue

        a_tag = cols[1].find('a')
        if not a_tag: continue
        name = a_tag.text.strip()
        href = a_tag.get('href', '')
        myneta_id = 0
        id_m = re.search(r'candidate_id=(\d+)', href)
        if id_m: myneta_id = int(id_m.group(1))

        const_name = cols[2].text.strip()
        party_abbr = cols[3].text.strip()
        crim_text = cols[4].text.strip()
        criminal = int(crim_text) if crim_text.isdigit() else 0
        education = cols[5].text.strip()
        assets_cr = parse_rs(cols[6].text)
        liabilities_cr = parse_rs(cols[7].text) if len(cols) > 7 else 0.0

        # Constituency
        ck = const_name.upper()
        if ck not in const_cache:
            cur.execute("INSERT INTO constituencies (name, state, type) VALUES (?, ?, ?)",
                        (const_name, state_name, get_type(const_name)))
            const_cache[ck] = cur.lastrowid

        # Party
        pk = party_abbr[:20].strip()
        if pk not in party_cache:
            akey = "OTHERS"
            for k, v in PARTY_ALLIANCE.items():
                if k == pk or k in pk: akey = v; break
            cur.execute("SELECT id FROM alliances WHERE name = ?", (ALLIANCES[akey]['name'],))
            aid = cur.fetchone()
            aid = aid[0] if aid else 1
            color = PARTY_COLORS.get(pk, "#9E9E9E")
            cur.execute("INSERT OR IGNORE INTO parties (full_name, abbreviation, color, alliance_id) VALUES (?, ?, ?, ?)",
                        (party_abbr, pk, color, aid))
            cur.execute("SELECT id FROM parties WHERE abbreviation = ?", (pk,))
            pid = cur.fetchone()
            if pid: party_cache[pk] = pid[0]

        party_id = party_cache.get(pk, 1)
        const_id = const_cache[ck]
        photo = f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=random&size=200"

        cur.execute("""
            INSERT INTO candidates (name, party_id, constituency_id, education,
                assets_cr, liabilities, criminal_cases, photo_url, myneta_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, party_id, const_id, education, assets_cr, liabilities_cr, criminal, photo, myneta_id))
        inserted += 1

    return inserted


def scrape_state(page, state_name, slug, conn):
    base_url = f"https://www.myneta.info/{slug}/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"
    cur = conn.cursor()

    # Navigate to page 1
    print(f"  Loading page 1...", flush=True)
    page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
    time.sleep(3)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='w3-bordered')
    if not table or len(table.find_all('tr')) <= 1:
        print(f"  SKIP {state_name}: no data on page 1", flush=True)
        return

    # Find total pages
    last_links = [a for a in soup.find_all('a') if a.text.strip() == 'Last' and 'page=' in (a.get('href') or '')]
    total_pages = 1
    if last_links:
        m = re.search(r'page=(\d+)', last_links[0]['href'])
        if m: total_pages = int(m.group(1))
    print(f"  {total_pages} pages to scrape", flush=True)

    # Caches
    const_cache = {}
    cur.execute("SELECT id, UPPER(name) FROM constituencies WHERE state = ?", (state_name,))
    for r in cur.fetchall(): const_cache[r[1]] = r[0]
    party_cache = {}
    cur.execute("SELECT id, abbreviation FROM parties")
    for r in cur.fetchall(): party_cache[r[1]] = r[0]

    total_inserted = 0
    failed = []

    # Process page 1
    count = parse_table(table, state_name, cur, conn, const_cache, party_cache)
    total_inserted += count
    conn.commit()

    # Process remaining pages
    for pg in range(2, total_pages + 1):
        url = f"{base_url}&page={pg}"
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            time.sleep(1.5)
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            tbl = soup.find('table', class_='w3-bordered')
            if tbl and len(tbl.find_all('tr')) > 1:
                count = parse_table(tbl, state_name, cur, conn, const_cache, party_cache)
                total_inserted += count
            else:
                failed.append(pg)
        except Exception as e:
            failed.append(pg)

        if pg % 5 == 0 or pg == total_pages:
            conn.commit()
            print(f"    p{pg}/{total_pages}: {total_inserted} candidates", flush=True)

    conn.commit()
    if failed:
        print(f"  {state_name}: {total_inserted} candidates ({len(failed)} pages failed)", flush=True)
    else:
        print(f"  {state_name}: {total_inserted} candidates ✓", flush=True)


def main():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    print("=" * 60, flush=True)
    print("MATDATA MITRA — MyNeta Playwright Scraper", flush=True)
    print("=" * 60, flush=True)

    # Check what states we already have data for
    cur.execute("SELECT DISTINCT co.state FROM constituencies co JOIN candidates ca ON ca.constituency_id = co.id")
    existing = set(r[0] for r in cur.fetchall())
    if existing:
        print(f"Already have data for: {existing}", flush=True)
        states_to_do = [s for s in STATES if s['name'] not in existing]
    else:
        cur.execute("DELETE FROM candidates")
        cur.execute("DELETE FROM constituencies")
        conn.commit()
        states_to_do = STATES

    if not states_to_do:
        print("All states already scraped!", flush=True)
    else:
        print(f"States to scrape: {[s['name'] for s in states_to_do]}", flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        for i, state in enumerate(states_to_do):
            print(f"\n--- {state['name']} ({i+1}/{len(states_to_do)}) ---", flush=True)
            # Create fresh context per state
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800}
            )
            pg = context.new_page()
            try:
                scrape_state(pg, state['name'], state['slug'], conn)
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
            context.close()
            # Long cooldown between states
            if i < len(states_to_do) - 1:
                wait = 90
                print(f"  Cooling down {wait}s before next state...", flush=True)
                time.sleep(wait)

        browser.close()

    # Summary
    print("\n" + "=" * 60, flush=True)
    cur.execute("SELECT COUNT(*) FROM constituencies")
    print(f"Total Constituencies: {cur.fetchone()[0]}", flush=True)
    cur.execute("SELECT COUNT(*) FROM candidates")
    print(f"Total Candidates:     {cur.fetchone()[0]}", flush=True)
    cur.execute("""
        SELECT co.state, COUNT(DISTINCT co.id), COUNT(ca.id)
        FROM constituencies co
        LEFT JOIN candidates ca ON ca.constituency_id = co.id
        GROUP BY co.state ORDER BY co.state
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:20s}  {r[1]:4d} const  {r[2]:5d} candidates", flush=True)
    print("=" * 60, flush=True)
    conn.close()

if __name__ == "__main__":
    main()
