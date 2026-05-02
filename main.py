from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from collections import Counter
import os
import re
import time
import urllib.parse
import math
import asyncio
from dotenv import load_dotenv
import db
import sqlite3
import logging
import httpx
from bs4 import BeautifulSoup

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VoteWise India API")
app.mount("/static", StaticFiles(directory="static"), name="static")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class ChatRequest(BaseModel):
    message: str
    history: list
    language: str = "english"

ELECTION_STATES_2026 = {
    "Assam": {
        "seats": 126,
        "candidates": 720,
        "electors": 24958139,
        "turnout": 85.96,
        "slug": "Assam2026",
        "center": [26.2006, 92.9376],
        "source_url": "https://www.myneta.info/Assam2026/",
    },
    "Kerala": {
        "seats": 140,
        "candidates": 863,
        "electors": 27142952,
        "turnout": 78.27,
        "slug": "Kerala2026",
        "center": [10.8505, 76.2711],
        "source_url": "https://www.myneta.info/Kerala2026/",
    },
    "Puducherry": {
        "seats": 30,
        "candidates": 291,
        "electors": 950311,
        "turnout": 89.87,
        "slug": "Puducherry2026",
        "center": [11.9416, 79.8083],
        "source_url": "https://www.myneta.info/Puducherry2026/",
    },
    "Tamil Nadu": {
        "seats": 234,
        "candidates": 3992,
        "electors": 57343291,
        "turnout": 84.69,
        "slug": "TamilNadu2026",
        "center": [11.1271, 78.6569],
        "source_url": "https://www.myneta.info/TamilNadu2026/",
    },
    "West Bengal": {
        "seats": 294,
        "candidates": 2920,
        "electors": 68251008,
        "turnout": 92.93,
        "slug": "WestBengal2026",
        "center": [22.9868, 87.8550],
        "source_url": "https://www.myneta.info/WestBengal2026/",
    },
}

LIVE_CACHE = {}
LIVE_CACHE_SECONDS = 900
DB_FALLBACK_FILES = ["matdata_mitra.db", "election_data.db"]

PARTY_COLORS = {
    "DMK": "#D32F2F", "INC": "#1976D2", "BJP": "#F57C00", "AIADMK": "#388E3C",
    "ADMK": "#388E3C", "TMC": "#2E7D32", "AITC": "#2E7D32", "CPI": "#E53935",
    "CPI(M)": "#B71C1C", "CPIM": "#B71C1C", "IND": "#9E9E9E", "AAP": "#00BCD4",
}

PARTY_FULL_NAMES = {
    "BJP": "Bharatiya Janata Party",
    "INC": "Indian National Congress",
    "AAP": "Aam Aadmi Party",
    "TMC": "All India Trinamool Congress",
    "DMK": "Dravida Munnetra Kazhagam",
    "ADMK": "All India Anna Dravida Munnetra Kazhagam",
    "AIADMK": "All India Anna Dravida Munnetra Kazhagam",
    "CPI": "Communist Party of India",
    "CPI(M)": "Communist Party of India (Marxist)",
    "CPIM": "Communist Party of India (Marxist)",
}

def _state_summary(name, meta):
    polled = round(meta["electors"] * (meta["turnout"] / 100))
    return {
        "state": name,
        "seats": meta["seats"],
        "candidates": meta["candidates"],
        "electors": meta["electors"],
        "turnout": meta["turnout"],
        "polled": polled,
        "source_url": meta["source_url"],
        "center": meta["center"],
    }

def _dashboard_summary(state=None):
    selected = (
        {state: ELECTION_STATES_2026[state]}
        if state in ELECTION_STATES_2026
        else ELECTION_STATES_2026
    )
    rows = [_state_summary(name, meta) for name, meta in selected.items()]
    electors = sum(row["electors"] for row in rows)
    polled = sum(row["polled"] for row in rows)
    turnout = round((polled / electors) * 100, 2) if electors else 0
    return {
        "stats": {
            "seats": sum(row["seats"] for row in rows),
            "candidates": sum(row["candidates"] for row in rows),
            "electors": electors,
            "polled": polled,
            "turnout": turnout,
        },
        "state_summaries": rows,
    }

def _parse_rs(text):
    text = (text or "").replace("\xa0", " ").strip()
    if not text or "Nil" in text:
        return 0.0
    match = re.search(r"Rs\s*([\d,]+)", text)
    if match:
        return round(float(match.group(1).replace(",", "")) / 10000000, 4)
    match = re.search(r"(\d+(?:\.\d+)?)\s*Crore", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*Lac", text, re.I)
    if match:
        return round(float(match.group(1)) / 100, 4)
    return 0.0

def _cache_get(key):
    item = LIVE_CACHE.get(key)
    if item and time.time() - item["time"] < LIVE_CACHE_SECONDS:
        return item["value"]
    return None

def _cache_set(key, value):
    LIVE_CACHE[key] = {"time": time.time(), "value": value}
    return value

async def _fetch_myneta_soup(url):
    headers = {"User-Agent": "Mozilla/5.0 VoteWiseIndia/1.0"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

def _candidate_page_url(state, page=1):
    meta = ELECTION_STATES_2026.get(state)
    if not meta:
        return None
    url = f"https://www.myneta.info/{meta['slug']}/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"
    if page > 1:
        url += f"&page={page}"
    return url

async def _scrape_myneta_candidate_detail(url):
    try:
        soup = await _fetch_myneta_soup(url)
        age = None
        gender = None
        for th in soup.find_all('th'):
            text = th.get_text(strip=True).lower()
            td = th.find_next_sibling('td')
            if td:
                val = td.get_text(" ", strip=True)
                if 'age' in text:
                    try:
                        age = int(re.search(r'(\d+)', val).group(1))
                    except Exception:
                        pass
                if 'sex' in text or 'gender' in text:
                    gender = val if val else None
        return age, gender
    except Exception:
        return None, None

async def _scrape_myneta_candidates(state, page=1, limit=50):
    cache_key = ("candidates", state, page, limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = _candidate_page_url(state, page)
    if not url:
        return {"total": 0, "page": page, "limit": limit, "data": [], "source": "none"}

    soup = await _fetch_myneta_soup(url)
    table = soup.find("table", class_="w3-bordered")
    rows = []
    if table:
        for index, row in enumerate(table.find_all("tr")[1:], start=1):
            cols = row.find_all("td")
            if len(cols) < 7:
                continue
            link = cols[1].find("a")
            name = link.get_text(" ", strip=True) if link else cols[1].get_text(" ", strip=True)
            href = urllib.parse.urljoin(url, link.get("href", "")) if link else url
            candidate_id = re.search(r"candidate_id=(\d+)", href)
            party = cols[3].get_text(" ", strip=True) or "IND"
            party_key = party[:20].strip()
            criminal_text = cols[4].get_text(" ", strip=True)
            rows.append({
                "id": f"live-{state}-{candidate_id.group(1) if candidate_id else page}-{index}",
                "name": name,
                "party_abbr": party_key,
                "party_color": PARTY_COLORS.get(party_key, "#9E9E9E"),
                "constituency_name": cols[2].get_text(" ", strip=True),
                "const_type": "SC" if "(SC)" in cols[2].get_text().upper() else "ST" if "(ST)" in cols[2].get_text().upper() else "GEN",
                "state_name": state,
                "education": cols[5].get_text(" ", strip=True),
                "assets_cr": _parse_rs(cols[6].get_text(" ", strip=True)),
                "liabilities": _parse_rs(cols[7].get_text(" ", strip=True)) if len(cols) > 7 else 0,
                "criminal_cases": int(criminal_text) if criminal_text.isdigit() else 0,
                "photo_url": f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=random&size=120",
                "myneta_url": href,
                "source": "MyNeta",
                "age": None,
                "gender": None,
            })

    return _cache_set(cache_key, {
        "total": ELECTION_STATES_2026[state]["candidates"],
        "page": page,
        "limit": limit,
        "data": rows[:limit],
        "source": "MyNeta",
        "source_url": url,
    })

async def _scrape_state_constituencies(state):
    cache_key = ("constituencies", state)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    seen = {}
    soup = await _fetch_myneta_soup(ELECTION_STATES_2026[state]["source_url"])
    for link in soup.find_all("a"):
        text = link.get_text(" ", strip=True)
        href = link.get("href", "")
        if not text or text.upper() == "ALL CONSTITUENCIES" or "constituency_id" not in href:
            continue
        if text not in seen:
            index = len(seen) + 1
            angle = index * 2.399963
            radius = 0.12 + (index % 12) * 0.025
            seen[text] = {
                "id": f"live-{state}-{len(seen) + 1}",
                "name": text,
                "state": state,
                "type": "SC" if "(SC)" in text.upper() else "ST" if "(ST)" in text.upper() else "GEN",
                "ac_no": index,
                "source": "MyNeta",
                "source_url": urllib.parse.urljoin(ELECTION_STATES_2026[state]["source_url"], href),
                "lat": round(ELECTION_STATES_2026[state]["center"][0] + radius * 0.7 * math.sin(angle), 5),
                "lng": round(ELECTION_STATES_2026[state]["center"][1] + radius * math.cos(angle), 5),
            }

    rows = list(seen.values())
    if not rows:
        rows = [{
            "id": f"state-{state}",
            "name": f"{state} Assembly Constituencies",
            "state": state,
            "type": "LIVE",
            "ac_no": "",
            "source": "Summary",
            "source_url": ELECTION_STATES_2026[state]["source_url"],
            "lat": ELECTION_STATES_2026[state]["center"][0],
            "lng": ELECTION_STATES_2026[state]["center"][1],
        }]
    return _cache_set(cache_key, rows)

async def _live_constituencies(state=None):
    states = [state] if state in ELECTION_STATES_2026 else list(ELECTION_STATES_2026.keys())
    rows = []
    for state_name in states:
        rows.extend(await _scrape_state_constituencies(state_name))
    return rows

async def _candidate_sample(state=None, pages=2):
    states = [state] if state in ELECTION_STATES_2026 else list(ELECTION_STATES_2026.keys())
    sample = []
    for state_name in states:
        for page in range(1, pages + 1):
            try:
                sample.extend((await _scrape_myneta_candidates(state_name, page=page, limit=50))["data"])
            except Exception as exc:
                logger.warning(f"MyNeta candidate sample failed for {state_name}: {exc}")
                break
    return sample

async def _live_parties():
    sample = await _candidate_sample(pages=2)
    counts = Counter()
    for row in sample:
        party_abbr = (row.get("party_abbr") or "").strip()
        if party_abbr and party_abbr != "IND":
            counts[party_abbr] += 1

    parties = []
    for index, (abbr, _count) in enumerate(counts.most_common(), start=1):
        parties.append({
            "id": f"live-{index}",
            "abbreviation": abbr,
            "full_name": PARTY_FULL_NAMES.get(abbr, abbr),
            "color": PARTY_COLORS.get(abbr, "#9E9E9E"),
            "source": "MyNeta",
        })
    return parties

def _read_parties_from_db_file(db_file):
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT p.id, p.abbreviation, p.full_name, p.color
            FROM parties p
            WHERE p.abbreviation IS NOT NULL
              AND p.abbreviation != 'IND'
            ORDER BY p.abbreviation
        """)
        return [dict(row) for row in c.fetchall()]
    except sqlite3.Error as exc:
        logger.warning(f"Unable to read parties from {db_file}: {exc}")
        return []
    finally:
        if conn:
            conn.close()

def _is_int(value):
    return value is not None and str(value).isdigit()

def _state_page_for_global_offset(offset):
    running = 0
    for state_name, meta in ELECTION_STATES_2026.items():
        state_total = meta["candidates"]
        if offset < running + state_total:
            inner_offset = offset - running
            return state_name, (inner_offset // 50) + 1
        running += state_total
    return list(ELECTION_STATES_2026.keys())[-1], 1

def _local_candidate_count(state=None):
    conn = db.get_db_connection()
    cur = conn.cursor()
    if state:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM candidates c
            JOIN constituencies co ON c.constituency_id = co.id
            WHERE co.state = ?
            """,
            (state,),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM candidates c
            JOIN constituencies co ON c.constituency_id = co.id
            WHERE co.state IN (?, ?, ?, ?, ?)
            """,
            tuple(ELECTION_STATES_2026.keys()),
        )
    count = cur.fetchone()[0]
    conn.close()
    return count

def _local_candidate_threshold(state=None):
    if state in ELECTION_STATES_2026:
        return int(ELECTION_STATES_2026[state]["candidates"] * 0.8)
    return int(sum(meta["candidates"] for meta in ELECTION_STATES_2026.values()) * 0.8)

@app.on_event("startup")
async def startup_event():
    # Only init db if it's empty in a real scenario. 
    # For now, it's already initialized by our script.
    pass

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/config")
async def get_config():
    return {
        "counting_date": os.getenv("COUNTING_DATE", "May 4, 2026 08:00:00"),
        "states": list(ELECTION_STATES_2026.keys()),
    }

@app.get("/api/overview")
async def get_overview(state: str = None, constituency_id: str = None):
    if not _is_int(constituency_id):
        return _dashboard_summary(state)
    constituency_id = int(constituency_id)

    conn = db.get_db_connection()
    c = conn.cursor()
    
    where_clause = " WHERE 1=1"
    params = []
    if state:
        where_clause += " AND state = ?"
        params.append(state)
    if constituency_id:
        where_clause += " AND id = ?"
        params.append(constituency_id)

    c.execute(f"SELECT COUNT(*) FROM constituencies {where_clause}", params)
    total_seats = c.fetchone()[0]
    
    cand_where = " WHERE 1=1"
    cand_params = []
    if constituency_id:
        cand_where += " AND constituency_id = ?"
        cand_params.append(constituency_id)
    elif state:
        cand_where += " AND constituency_id IN (SELECT id FROM constituencies WHERE state = ?)"
        cand_params.append(state)
        
    c.execute(f"SELECT COUNT(*) FROM candidates {cand_where}", cand_params)
    total_cands = c.fetchone()[0]
    
    c.execute(f"SELECT COUNT(DISTINCT party_id) FROM candidates {cand_where}", cand_params)
    total_parties = c.fetchone()[0]
    
    e_where = " WHERE 1=1"
    e_params = []
    if constituency_id:
        e_where += " AND constituency_id = ?"
        e_params.append(constituency_id)
    elif state:
        e_where += " AND constituency_id IN (SELECT id FROM constituencies WHERE state = ?)"
        e_params.append(state)
        
    c.execute(f"SELECT SUM(total), AVG(turnout_percentage) FROM elector_stats {e_where}", e_params)
    elector_data = c.fetchone()
    total_electors = elector_data[0] or 0
    avg_turnout = elector_data[1] or 0

    share_query = """
        SELECT p.abbreviation, p.color, COUNT(r.id) as seats
        FROM results r
        JOIN candidates c_win ON r.winner_candidate_id = c_win.id
        JOIN parties p ON c_win.party_id = p.id
        JOIN constituencies const ON r.constituency_id = const.id
        WHERE r.status IN ('Won', 'Leading')
    """
    share_params = []
    if state:
        share_query += " AND const.state = ?"
        share_params.append(state)
    if constituency_id:
        share_query += " AND const.id = ?"
        share_params.append(constituency_id)

    share_query += " GROUP BY p.id"
    c.execute(share_query, share_params)
    party_shares = [dict(row) for row in c.fetchall()]

    conn.close()
    return {
        "stats": {
            "seats": total_seats,
            "candidates": total_cands,
            "parties": total_parties,
            "electors": total_electors,
            "polled": round(total_electors * (avg_turnout / 100)) if avg_turnout else 0,
            "turnout": round(avg_turnout, 2) if avg_turnout else 0
        },
        "party_shares": party_shares,
        "state_summaries": []
    }

@app.get("/api/states")
async def get_states():
    return list(ELECTION_STATES_2026.keys())

@app.get("/api/constituencies")
async def get_constituencies_list(state: str = None):
    try:
        return await _live_constituencies(state)
    except Exception as exc:
        logger.warning(f"MyNeta constituency list unavailable, using database fallback: {exc}")

    conn = db.get_db_connection()
    c = conn.cursor()
    if state:
        c.execute("SELECT * FROM constituencies WHERE state = ? ORDER BY name", (state,))
    else:
        c.execute("SELECT * FROM constituencies ORDER BY state, name")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/parties")
async def get_parties():
    try:
        parties = _read_parties_from_db_file(db.DB_FILE)
        if parties:
            return parties

        # If runtime points to an empty/wrong SQLite file, recover from known local files.
        for db_file in DB_FALLBACK_FILES:
            if db_file == db.DB_FILE:
                continue
            parties = _read_parties_from_db_file(db_file)
            if parties:
                logger.warning(f"Using fallback party source from {db_file}")
                return parties
    except sqlite3.Error as exc:
        logger.warning(f"Database unavailable for /api/parties, using live fallback: {exc}")
    try:
        return await _live_parties()
    except Exception as live_exc:
        logger.error(f"Live fallback failed for /api/parties: {live_exc}")
        return []

@app.get("/api/candidates")
async def get_candidates(page: int = 1, limit: int = 50, party: str = None, gender: str = None, reserved: str = None, state: str = None, constituency_id: str = None):
    local_is_ready = False
    if not _is_int(constituency_id):
        try:
            local_is_ready = _local_candidate_count(state) >= _local_candidate_threshold(state)
        except sqlite3.Error as exc:
            logger.warning(f"Database unavailable for candidate readiness check, using live fallback: {exc}")
    if not _is_int(constituency_id) and not local_is_ready:
        try:
            if state in ELECTION_STATES_2026:
                live = await _scrape_myneta_candidates(state, page=page, limit=limit)
            else:
                offset = max(0, (page - 1) * limit)
                state_name, state_page = _state_page_for_global_offset(offset)
                live = await _scrape_myneta_candidates(state_name, page=state_page, limit=limit)
                live["total"] = sum(meta["candidates"] for meta in ELECTION_STATES_2026.values())
                live["page"] = page
                live["state_page"] = state_page
                live["state_name"] = state_name
            if party:
                live["data"] = [row for row in live["data"] if row["party_abbr"].upper() == party.upper()]
            if reserved:
                live["data"] = [row for row in live["data"] if row["const_type"] == reserved]
            live["storage"] = "live"
            return live
        except Exception as exc:
            logger.warning(f"MyNeta candidates unavailable, using database fallback: {exc}")
    elif constituency_id:
        constituency_id = int(constituency_id)

    conn = None
    try:
        conn = db.get_db_connection()
        c = conn.cursor()

        query = """
            SELECT c.*, p.abbreviation as party_abbr, p.color as party_color, const.name as constituency_name, const.type as const_type, const.state as state_name
            FROM candidates c
            JOIN parties p ON c.party_id = p.id
            JOIN constituencies const ON c.constituency_id = const.id
            WHERE 1=1
        """
        params = []

        if state:
            query += " AND const.state = ?"
            params.append(state)
        elif not constituency_id:
            query += " AND const.state IN (?, ?, ?, ?, ?)"
            params.extend(ELECTION_STATES_2026.keys())
        if constituency_id:
            query += " AND c.constituency_id = ?"
            params.append(constituency_id)
        if party:
            query += " AND p.abbreviation = ?"
            params.append(party)
        if gender:
            query += " AND c.gender = ?"
            params.append(gender)
        if reserved:
            query += " AND const.type = ?"
            params.append(reserved)

        c.execute(f"SELECT COUNT(*) FROM ({query}) AS sub", params)
        total = c.fetchone()[0]

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, (page - 1) * limit])

        c.execute(query, params)
        candidates = [dict(row) for row in c.fetchall()]

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "source": "SQLite",
            "storage": "db",
            "data": candidates
        }
    except sqlite3.Error as exc:
        logger.warning(f"Database unavailable for /api/candidates: {exc}")
        try:
            if state in ELECTION_STATES_2026:
                live = await _scrape_myneta_candidates(state, page=page, limit=limit)
            else:
                offset = max(0, (page - 1) * limit)
                state_name, state_page = _state_page_for_global_offset(offset)
                live = await _scrape_myneta_candidates(state_name, page=state_page, limit=limit)
                live["total"] = sum(meta["candidates"] for meta in ELECTION_STATES_2026.values())
                live["page"] = page
                live["state_page"] = state_page
                live["state_name"] = state_name
            if party:
                live["data"] = [row for row in live["data"] if row["party_abbr"].upper() == party.upper()]
            if reserved:
                live["data"] = [row for row in live["data"] if row["const_type"] == reserved]
            live["storage"] = "live"
            return live
        except Exception as live_exc:
            logger.error(f"Live fallback failed for /api/candidates: {live_exc}")
            raise HTTPException(status_code=503, detail="Candidates temporarily unavailable")
    finally:
        if conn:
            conn.close()

@app.get("/api/candidate/{id}")
async def get_candidate_detail(id: int):
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT c.*, p.full_name as party_name, p.abbreviation as party_abbr, p.color as party_color,
               co.name as constituency_name, co.state as state_name
        FROM candidates c
        JOIN parties p ON c.party_id = p.id
        JOIN constituencies co ON c.constituency_id = co.id
        WHERE c.id = ?
    """, (id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return dict(row)



import scraper

@app.get("/api/results/live")
async def get_live_results():
    # 1. ATTEMPT REAL-TIME SCRAPING FIRST
    try:
        scraped_data = await scraper.scrape_live_results()
        if scraped_data:
            logger.info("Successfully fetched live data from ECI!")
            # Map scraped data to frontend format
            for r in scraped_data:
                r['const_name'] = r['constituency']
                r['constituency_id'] = "🔴 LIVE"
                r['winner_color'] = "#9E9E9E" # Default gray
                party_upper = r['winner_party'].upper()
                if "BJP" in party_upper: r['winner_color'] = "#FF6D00"
                elif "INC" in party_upper: r['winner_color'] = "#1565C0"
                elif "AAP" in party_upper: r['winner_color'] = "#00BCD4"
                elif "TMC" in party_upper: r['winner_color'] = "#388E3C"
                elif "DMK" in party_upper: r['winner_color'] = "#E53935"
                elif "ADMK" in party_upper: r['winner_color'] = "#4CAF50"
            return scraped_data
    except Exception as e:
        logger.error(f"Live scraping failed: {e}")

    # 2. FALLBACK TO DATABASE IF BLOCKED BY CLOUDFLARE/403
    logger.warning("Falling back to local database for live results...")
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT r.*, 
               const.name as const_name, const.state as state,
               w.name as winner_name, pw.abbreviation as winner_party, pw.color as winner_color
        FROM results r
        JOIN constituencies const ON r.constituency_id = const.id
        JOIN candidates w ON r.winner_candidate_id = w.id
        JOIN parties pw ON w.party_id = pw.id
    """)
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/results/history")
async def get_results_history():
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT h.*, p.abbreviation as party_abbr, p.color as party_color
        FROM historical_results h
        JOIN parties p ON h.party_id = p.id
        ORDER BY h.year, h.seats_won DESC
    """)
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/timeline")
async def get_timeline():
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM election_steps ORDER BY step_number")
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/elector-stats")
async def get_elector_stats():
    summary = _dashboard_summary()
    return {
        "summary": {
            "total": summary["stats"]["electors"],
            "male": 0,
            "female": 0,
            "third": 0,
            "new": 0,
            "polled": summary["stats"]["polled"],
        },
        "state_turnout_2026": {
            row["state"]: f"{row['turnout']:.2f}%"
            for row in summary["state_summaries"]
        },
        "state_summaries": summary["state_summaries"],
        "gender_split": {"Male": 51.3, "Female": 48.6, "Third": 0.1},
        "age_groups": {"18-25": 15, "26-40": 35, "41-60": 30, "60+": 20}
    }

@app.get("/api/stats/advanced")
async def get_advanced_stats(state: str = None, constituency_id: str = None):
    if not _is_int(constituency_id):
        try:
            candidates = await _candidate_sample(state=state, pages=3)
            total_cands = len(candidates) or 1
            crore_count = sum(1 for cand in candidates if cand["assets_cr"] >= 1)
            crim_count = sum(1 for cand in candidates if cand["criminal_cases"] > 0)
            edu_data = {}
            party_data = {}
            for cand in candidates:
                education = cand["education"] or "Not Available"
                party = cand["party_abbr"] or "Other"
                edu_data[education] = edu_data.get(education, 0) + 1
                party_data[party] = party_data.get(party, 0) + 1
            return {
                "crorepatis": {"count": crore_count, "percentage": round((crore_count / total_cands) * 100, 2)},
                "criminal_cases": {"count": crim_count, "percentage": round((crim_count / total_cands) * 100, 2)},
                "education": edu_data,
                "gender_ratio": dict(sorted(party_data.items(), key=lambda item: item[1], reverse=True)[:8]),
                "sample_size": len(candidates),
                "source": "MyNeta live sample",
            }
        except Exception as exc:
            logger.warning(f"MyNeta advanced stats unavailable, using database fallback: {exc}")
    elif constituency_id:
        constituency_id = int(constituency_id)

    conn = db.get_db_connection()
    c = conn.cursor()
    
    where = " WHERE 1=1"
    params = []
    if constituency_id:
        where += " AND constituency_id = ?"
        params.append(constituency_id)
    elif state:
        where += " AND constituency_id IN (SELECT id FROM constituencies WHERE state = ?)"
        params.append(state)
        
    # Crorepatis
    c.execute(f"SELECT COUNT(*) FROM candidates {where}", params)
    total_cands = c.fetchone()[0] or 1
    
    c.execute(f"SELECT COUNT(*) FROM candidates {where} AND assets_cr >= 1", params)
    crore_count = c.fetchone()[0]
    
    # Criminal
    c.execute(f"SELECT COUNT(*) FROM candidates {where} AND criminal_cases > 0", params)
    crim_count = c.fetchone()[0]
    
    # Education breakdown
    c.execute(f"SELECT education, COUNT(*) FROM candidates {where} GROUP BY education", params)
    edu_data = {row[0]: row[1] for row in c.fetchall()}
    
    # Gender ratio
    c.execute(f"SELECT gender, COUNT(*) FROM candidates {where} GROUP BY gender", params)
    gender_data = {row[0]: row[1] for row in c.fetchall()}

    conn.close()
    return {
        "crorepatis": {"count": crore_count, "percentage": round((crore_count/total_cands)*100, 2)},
        "criminal_cases": {"count": crim_count, "percentage": round((crim_count/total_cands)*100, 2)},
        "education": edu_data,
        "gender_ratio": gender_data
    }

@app.get("/api/voter")
async def get_voter(epic: str):
    if not epic or not epic.strip():
        raise HTTPException(status_code=400, detail="EPIC number is required")
    epic_clean = epic.strip().upper()
    if not re.match(r'^[A-Z0-9]{3,15}$', epic_clean):
        raise HTTPException(status_code=400, detail="Invalid EPIC format. Expected alphanumeric, 3-15 characters.")
    return {
        "epic": epic_clean,
        "name": "Sample Voter",
        "state": "Delhi",
        "constituency": "New Delhi",
        "booth": "14A, Primary School"
    }

@app.get("/api/constituency/{id}")
async def get_constituency_detail(id: int):
    conn = db.get_db_connection()
    c = conn.cursor()
    
    # Get details
    c.execute("SELECT * FROM constituencies WHERE id = ?", (id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Not found")
    
    details = dict(row)
    
    # Get candidates
    c.execute("""
        SELECT c.*, p.abbreviation as party_abbr, p.color as party_color, p.full_name as party_name 
        FROM candidates c
        JOIN parties p ON c.party_id = p.id
        WHERE c.constituency_id = ?
        ORDER BY p.abbreviation
    """, (id,))
    
    details['candidates'] = [dict(r) for r in c.fetchall()]
    
    conn.close()
    return details


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    system_prompt = "You are VoteWise India, an expert on Indian elections, ECI rules, voter rights, and constitutional democratic processes. Be concise, factual, and cite ECI guidelines. You must always reply in English, regardless of the user's language."
    
    if GROQ_API_KEY:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=GROQ_API_KEY)
            
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(request.history)
            messages.append({"role": "user", "content": request.message})
            
            chat_completion = await client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
            )
            return {"response": chat_completion.choices[0].message.content, "sources": ["https://eci.gov.in"]}
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            
    # Fallback
    return {
        "response": f"[Local LLM mock] Here is an answer regarding: {request.message}. Please consult eci.gov.in for official details.",
        "sources": ["https://eci.gov.in"]
    }
