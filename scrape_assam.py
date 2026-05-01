"""Targeted Assam-only scraper with 90s timeout."""
import sys, time, re, sqlite3, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

DB_FILE = "matdata_mitra.db"

ALLIANCES = {
    "INDIA": {"name": "INDIA Bloc", "color": "#1565C0"},
    "NDA": {"name": "National Democratic Alliance", "color": "#FF9933"},
    "OTHERS": {"name": "Others/Independent", "color": "#8b949e"},
}
PARTY_ALLIANCE = {"BJP": "NDA", "INC": "INDIA", "AITC": "INDIA", "TMC": "INDIA",
                  "CPI": "INDIA", "CPI(M)": "INDIA", "CPIM": "INDIA", "IND": "OTHERS",
                  "AGP": "NDA", "AIUDF": "OTHERS"}

def parse_rs(text):
    if not text: return 0.0
    text = text.replace('\xa0', ' ').strip()
    if 'Nil' in text: return 0.0
    m = re.search(r'Rs\s*([\d,]+)', text)
    if m:
        raw = m.group(1).replace(',', '')
        try: return round(float(raw) / 10000000, 4)
        except: pass
    return 0.0

def get_type(name):
    u = name.upper()
    if '(SC)' in u: return 'SC'
    if '(ST)' in u: return 'ST'
    return 'GEN'

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM candidates c JOIN constituencies co ON c.constituency_id=co.id WHERE co.state='Assam'")
if cur.fetchone()[0] > 0:
    print("Assam already has data!"); conn.close(); exit()

party_cache = {}
cur.execute("SELECT id, abbreviation FROM parties")
for r in cur.fetchall(): party_cache[r[1]] = r[0]
const_cache = {}

print("Starting Assam scrape...", flush=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    pg = context.new_page()

    base = "https://www.myneta.info/assam2026/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"
    print("Loading page 1...", flush=True)
    pg.goto(base, wait_until="domcontentloaded", timeout=90000)
    time.sleep(3)

    html = pg.content()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="w3-bordered")
    if not table or len(table.find_all("tr")) <= 1:
        print("No data - rate limited. Try again later.")
        browser.close(); conn.close(); exit()

    last_links = [a for a in soup.find_all("a") if a.text.strip() == "Last" and "page=" in (a.get("href") or "")]
    total_pages = 1
    if last_links:
        m = re.search(r"page=(\d+)", last_links[0]["href"])
        if m: total_pages = int(m.group(1))
    print(f"  {total_pages} pages", flush=True)

    inserted = 0
    for page_num in range(1, total_pages + 1):
        if page_num > 1:
            url = f"{base}&page={page_num}"
            time.sleep(1.5)
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(1.5)
            html = pg.content()
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table", class_="w3-bordered")
            if not table or len(table.find_all("tr")) <= 1:
                continue

        rows = table.find_all("tr")[1:]
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 7: continue
            a_tag = cols[1].find("a")
            if not a_tag: continue
            name = a_tag.text.strip()
            href = a_tag.get("href", "")
            myneta_id = 0
            id_m = re.search(r"candidate_id=(\d+)", href)
            if id_m: myneta_id = int(id_m.group(1))

            const_name = cols[2].text.strip()
            party_abbr = cols[3].text.strip()
            criminal = int(cols[4].text.strip()) if cols[4].text.strip().isdigit() else 0
            education = cols[5].text.strip()
            assets_cr = parse_rs(cols[6].text)
            liabilities_cr = parse_rs(cols[7].text) if len(cols) > 7 else 0.0

            ck = const_name.upper()
            if ck not in const_cache:
                cur.execute("INSERT INTO constituencies (name, state, type) VALUES (?, ?, ?)",
                            (const_name, "Assam", get_type(const_name)))
                const_cache[ck] = cur.lastrowid

            pk = party_abbr[:20].strip()
            if pk not in party_cache:
                akey = "OTHERS"
                for k, v in PARTY_ALLIANCE.items():
                    if k == pk or k in pk: akey = v; break
                cur.execute("SELECT id FROM alliances WHERE name = ?", (ALLIANCES[akey]["name"],))
                aid = cur.fetchone()
                aid = aid[0] if aid else 1
                cur.execute("INSERT OR IGNORE INTO parties (full_name, abbreviation, color, alliance_id) VALUES (?, ?, ?, ?)",
                            (party_abbr, pk, "#9E9E9E", aid))
                cur.execute("SELECT id FROM parties WHERE abbreviation = ?", (pk,))
                pid = cur.fetchone()
                if pid: party_cache[pk] = pid[0]

            party_id = party_cache.get(pk, 1)
            photo = f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=random&size=200"
            cur.execute("""INSERT INTO candidates (name, party_id, constituency_id, education,
                assets_cr, liabilities, criminal_cases, photo_url, myneta_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, party_id, const_cache[ck], education, assets_cr, liabilities_cr, criminal, photo, myneta_id))
            inserted += 1

        if page_num % 4 == 0 or page_num == total_pages:
            conn.commit()
            print(f"  p{page_num}/{total_pages}: {inserted} candidates", flush=True)

    conn.commit()
    browser.close()

print(f"\nAssam DONE: {inserted} candidates", flush=True)
cur.execute("SELECT COUNT(*) FROM candidates")
print(f"Total candidates in DB: {cur.fetchone()[0]}", flush=True)
conn.close()
