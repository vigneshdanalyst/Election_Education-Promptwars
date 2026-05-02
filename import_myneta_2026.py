import argparse
import html
import re
import sqlite3
import time
import urllib.parse
import urllib.request

DB_FILE = "matdata_mitra.db"

STATES = [
    {"name": "Assam", "slug": "Assam2026"},
    {"name": "Kerala", "slug": "Kerala2026"},
    {"name": "Puducherry", "slug": "Puducherry2026"},
    {"name": "Tamil Nadu", "slug": "TamilNadu2026"},
    {"name": "West Bengal", "slug": "WestBengal2026"},
]

PARTY_COLORS = {
    "DMK": "#D32F2F", "INC": "#1976D2", "BJP": "#F57C00", "AIADMK": "#388E3C",
    "ADMK": "#388E3C", "TMC": "#2E7D32", "AITC": "#2E7D32", "CPI": "#E53935",
    "CPI(M)": "#B71C1C", "CPIM": "#B71C1C", "IND": "#9E9E9E", "AAP": "#00BCD4",
}


def parse_rs(text):
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


def const_type(name):
    upper = name.upper()
    if "(SC)" in upper:
        return "SC"
    if "(ST)" in upper:
        return "ST"
    return "GEN"


def strip_tags(value):
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def get_html(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 VoteWiseIndia/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def decode_number(value, source_base):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/"
    digits = alphabet[:source_base]
    total = 0
    for power, char in enumerate(reversed(value)):
        if char in digits:
            total += digits.index(char) * (source_base ** power)
    return total


def decode_myneta_scripts(page_html):
    decoded = []
    pattern = re.compile(
        r'return decodeURIComponent\(escape\(r\)\)\}\("([^"]+)",(\d+),"([^"]+)",(\d+),(\d+),(\d+)\)\)',
        re.S,
    )
    for match in pattern.finditer(page_html):
        payload, _unused, alphabet, shift, source_base, _target_base = match.groups()
        shift = int(shift)
        source_base = int(source_base)
        delimiter = alphabet[source_base]

        output = []
        index = 0
        while index < len(payload):
            token = []
            while index < len(payload) and payload[index] != delimiter:
                token.append(payload[index])
                index += 1
            index += 1
            encoded = "".join(token)
            for digit, char in enumerate(alphabet):
                encoded = encoded.replace(char, str(digit))
            if encoded:
                try:
                    output.append(chr(decode_number(encoded, source_base) - shift))
                except ValueError:
                    pass
        decoded.append("".join(output))
    return "\n".join(decoded)


def ensure_alliance(cur):
    cur.execute("INSERT OR IGNORE INTO alliances (name, color) VALUES (?, ?)", ("Others/Independent", "#8b949e"))
    cur.execute("SELECT id FROM alliances WHERE name = ?", ("Others/Independent",))
    return cur.fetchone()[0]


def ensure_party(cur, abbreviation, alliance_id):
    abbreviation = (abbreviation or "IND")[:20].strip() or "IND"
    cur.execute("SELECT id FROM parties WHERE abbreviation = ?", (abbreviation,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        "INSERT INTO parties (abbreviation, full_name, color, alliance_id) VALUES (?, ?, ?, ?)",
        (abbreviation, abbreviation, PARTY_COLORS.get(abbreviation, "#9E9E9E"), alliance_id),
    )
    return cur.lastrowid


def ensure_constituency(cur, cache, state_name, name):
    key = (state_name, name.upper())
    if key in cache:
        return cache[key]

    cur.execute(
        "INSERT INTO constituencies (ac_no, name, state, type) VALUES (?, ?, ?, ?)",
        (len([item for item in cache if item[0] == state_name]) + 1, name, state_name, const_type(name)),
    )
    cache[key] = cur.lastrowid
    return cache[key]


def total_pages(page_html):
    pages = [1]
    for match in re.finditer(r"page=(\d+)", page_html):
        pages.append(int(match.group(1)))
    return max(pages)


def rows_from_html(page_html):
    page_html = page_html + "\n" + decode_myneta_scripts(page_html)
    parsed = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.I | re.S):
        if "candidate_id" not in row_html:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.I | re.S)
        if len(cells) < 7:
            continue
        link_match = re.search(r"<a[^>]+href=(?:['\"])?([^'\"\s>]*candidate_id=[^'\"\s>]*)['\"]?[^>]*>(.*?)</a>", row_html, flags=re.I | re.S)
        if not link_match:
            continue
        parsed.append((cells, link_match.group(1), strip_tags(link_match.group(2))))
    return parsed


def import_state(conn, state, dump=False):
    cur = conn.cursor()
    alliance_id = ensure_alliance(cur)
    base_url = f"https://www.myneta.info/{state['slug']}/index.php?action=summary&subAction=candidates_analyzed&sort=candidate"
    print(f"{state['name']}: loading page 1")
    page_html = get_html(base_url)
    if dump:
        with open("debug_myneta.html", "w", encoding="utf-8") as handle:
            handle.write(page_html)
        print("Wrote debug_myneta.html")
        return 0
    pages = total_pages(page_html)
    print(f"{state['name']}: {pages} pages")

    cur.execute("DELETE FROM candidates WHERE constituency_id IN (SELECT id FROM constituencies WHERE state = ?)", (state["name"],))
    cur.execute("DELETE FROM constituencies WHERE state = ?", (state["name"],))
    conn.commit()

    const_cache = {}
    inserted = 0
    for page in range(1, pages + 1):
        url = base_url if page == 1 else f"{base_url}&page={page}"
        if page != 1:
            page_html = get_html(url)

        for cols, href_raw, name in rows_from_html(page_html):
            href = urllib.parse.urljoin(url, href_raw)
            myneta_match = re.search(r"candidate_id=(\d+)", href)
            myneta_id = int(myneta_match.group(1)) if myneta_match else None
            constituency = strip_tags(cols[2])
            party = strip_tags(cols[3])[:20].strip() or "IND"
            criminal_text = strip_tags(cols[4])
            criminal_cases = int(criminal_text) if criminal_text.isdigit() else 0

            const_id = ensure_constituency(cur, const_cache, state["name"], constituency)
            party_id = ensure_party(cur, party, alliance_id)
            photo = f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=random&size=120"

            cur.execute(
                """
                INSERT INTO candidates (
                    name, party_id, constituency_id, education, assets_cr, liabilities,
                    criminal_cases, photo_url, myneta_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    party_id,
                    const_id,
                    strip_tags(cols[5]),
                    parse_rs(strip_tags(cols[6])),
                    parse_rs(strip_tags(cols[7])) if len(cols) > 7 else 0.0,
                    criminal_cases,
                    photo,
                    myneta_id,
                ),
            )
            inserted += 1

        conn.commit()
        print(f"{state['name']}: page {page}/{pages}, {inserted} candidates")
        time.sleep(0.2)

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import MyNeta 2026 candidates into SQLite.")
    parser.add_argument("--state", choices=[state["name"] for state in STATES])
    parser.add_argument("--dump", action="store_true", help="Write the first fetched page to debug_myneta.html and exit.")
    args = parser.parse_args()

    selected = [state for state in STATES if not args.state or state["name"] == args.state]

    with sqlite3.connect(DB_FILE) as conn:
        total = 0
        for state in selected:
            total += import_state(conn, state, dump=args.dump)
            if args.dump:
                break
        print(f"Done. Imported {total} candidates.")


if __name__ == "__main__":
    main()
