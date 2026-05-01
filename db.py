import sqlite3
import random
from datetime import datetime

DB_FILE = "matdata_mitra.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Drop existing tables to ensure clean schema (since we are doing a massive rewrite)
    cursor.executescript("""
        DROP TABLE IF EXISTS parties;
        DROP TABLE IF EXISTS alliances;
        DROP TABLE IF EXISTS constituencies;
        DROP TABLE IF EXISTS candidates;
        DROP TABLE IF EXISTS results;
        DROP TABLE IF EXISTS elector_stats;
        DROP TABLE IF EXISTS historical_results;
        DROP TABLE IF EXISTS election_steps;
        DROP TABLE IF EXISTS chat_history;
        DROP TABLE IF EXISTS press_releases;
    """)

    # Alliances
    cursor.execute("""
        CREATE TABLE alliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            color TEXT
        )
    """)

    # Parties
    cursor.execute("""
        CREATE TABLE parties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            abbreviation TEXT UNIQUE,
            full_name TEXT,
            color TEXT,
            alliance_id INTEGER,
            founded INTEGER,
            symbol TEXT,
            president TEXT,
            ideology TEXT,
            FOREIGN KEY (alliance_id) REFERENCES alliances (id)
        )
    """)

    # Constituencies
    cursor.execute("""
        CREATE TABLE constituencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ac_no INTEGER,
            name TEXT,
            state TEXT,
            type TEXT -- GEN, SC, ST
        )
    """)

    # Candidates
    cursor.execute("""
        CREATE TABLE candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            party_id INTEGER,
            constituency_id INTEGER,
            age INTEGER,
            gender TEXT,
            education TEXT,
            profession TEXT,
            pan_status TEXT,
            assets_cr REAL,
            movable_assets REAL,
            immovable_assets REAL,
            liabilities REAL,
            criminal_cases INTEGER,
            incumbent BOOLEAN,
            photo_url TEXT,
            myneta_id INTEGER,
            detailed_scraped BOOLEAN DEFAULT 0,
            FOREIGN KEY (party_id) REFERENCES parties (id),
            FOREIGN KEY (constituency_id) REFERENCES constituencies (id)
        )
    """)

    # Results
    cursor.execute("""
        CREATE TABLE results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constituency_id INTEGER UNIQUE,
            winner_candidate_id INTEGER,
            runner_up_candidate_id INTEGER,
            votes INTEGER,
            margin INTEGER,
            status TEXT, -- Won, Leading
            FOREIGN KEY (constituency_id) REFERENCES constituencies (id),
            FOREIGN KEY (winner_candidate_id) REFERENCES candidates (id),
            FOREIGN KEY (runner_up_candidate_id) REFERENCES candidates (id)
        )
    """)

    # Elector Stats
    cursor.execute("""
        CREATE TABLE elector_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            constituency_id INTEGER UNIQUE,
            male INTEGER,
            female INTEGER,
            third_gender INTEGER,
            new_electors INTEGER,
            total INTEGER,
            turnout_percentage REAL,
            FOREIGN KEY (constituency_id) REFERENCES constituencies (id)
        )
    """)

    # Historical Results
    cursor.execute("""
        CREATE TABLE historical_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER,
            party_id INTEGER,
            seats_won INTEGER,
            vote_share REAL,
            FOREIGN KEY (party_id) REFERENCES parties (id)
        )
    """)

    # Election Steps
    cursor.execute("""
        CREATE TABLE election_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_number INTEGER UNIQUE,
            step_name TEXT,
            description TEXT,
            citizen_action TEXT,
            typical_days TEXT,
            status TEXT -- Done, Today, Upcoming
        )
    """)

    # Chat History
    cursor.execute("""
        CREATE TABLE chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Press Releases
    cursor.execute("""
        CREATE TABLE press_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            date TEXT,
            summary TEXT,
            link TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    seed_data(cursor)
    conn.commit()
    conn.close()

def seed_data(cursor):
    print("Seeding database...")
    
    # 1. Alliances
    alliances = [
        ("NDA", "#FF9933"),
        ("INDIA", "#58a6ff"),
        ("Others", "#9E9E9E")
    ]
    cursor.executemany("INSERT INTO alliances (name, color) VALUES (?, ?)", alliances)
    
    # Map alliance names to IDs
    cursor.execute("SELECT id, name FROM alliances")
    alliance_map = {row['name']: row['id'] for row in cursor.fetchall()}

    # 2. Parties
    parties = [
        ("BJP", "Bharatiya Janata Party", "#FF6D00", alliance_map["NDA"], 1980, "Lotus", "J. P. Nadda", "Right-wing"),
        ("INC", "Indian National Congress", "#1565C0", alliance_map["INDIA"], 1885, "Hand", "Mallikarjun Kharge", "Center-left"),
        ("AAP", "Aam Aadmi Party", "#00BCD4", alliance_map["INDIA"], 2012, "Broom", "Arvind Kejriwal", "Centrist"),
        ("TMC", "All India Trinamool Congress", "#388E3C", alliance_map["INDIA"], 1998, "Flowers & Grass", "Mamata Banerjee", "Center-left"),
        ("DMK", "Dravida Munnetra Kazhagam", "#E53935", alliance_map["INDIA"], 1949, "Rising Sun", "M. K. Stalin", "Center-left"),
        ("ADMK", "All India Anna Dravida Munnetra Kazhagam", "#4CAF50", alliance_map["NDA"], 1972, "Two Leaves", "Edappadi K. Palaniswami", "Centrist"),
        ("IND", "Independent", "#9E9E9E", alliance_map["Others"], None, "Various", "N/A", "N/A")
    ]
    cursor.executemany("INSERT INTO parties (abbreviation, full_name, color, alliance_id, founded, symbol, president, ideology) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", parties)

    cursor.execute("SELECT id, abbreviation FROM parties")
    party_map = {row['abbreviation']: row['id'] for row in cursor.fetchall()}

    # 3. Constituencies (mocking 50 out of 543 for speed, spreading across states)
    states = ["Uttar Pradesh", "Maharashtra", "West Bengal", "Bihar", "Tamil Nadu", "Madhya Pradesh", "Karnataka", "Gujarat", "Rajasthan", "Andhra Pradesh", "Delhi"]
    constituencies = []
    c_id = 1
    for state in states:
        for i in range(1, 6): # 5 per state
            ctype = random.choices(["GEN", "SC", "ST"], weights=[0.75, 0.15, 0.1])[0]
            constituencies.append((c_id, i, f"{state} Const {i}", state, ctype))
            c_id += 1
    
    cursor.executemany("INSERT INTO constituencies (id, ac_no, name, state, type) VALUES (?, ?, ?, ?, ?)", constituencies)

    # 4. Candidates & Elector Stats
    candidates = []
    results = []
    elector_stats = []
    
    for c in constituencies:
        cid = c[0]
        
        # Elector stats
        total_electors = random.randint(1500000, 2500000)
        male = int(total_electors * 0.52)
        female = int(total_electors * 0.48)
        new_electors = random.randint(20000, 50000)
        turnout = round(random.uniform(55.0, 85.0), 2)
        elector_stats.append((cid, male, female, 0, new_electors, total_electors, turnout))

        # Generate candidates for this constituency
        num_candidates = random.randint(3, 10)
        # Ensure at least one NDA and one INDIA candidate
        party_pool = ["BJP", "INC", "AAP", "TMC", "DMK", "ADMK"]
        random.shuffle(party_pool)
        
        cands_in_const = []
        for i in range(num_candidates):
            party_abbr = party_pool[i] if i < len(party_pool) else "IND"
            pid = party_map[party_abbr]
            age = random.randint(25, 75)
            gender = random.choice(["Male", "Female"])
            education = random.choice(["10th Pass", "12th Pass", "Graduate", "Post Graduate", "Doctorate"])
            assets = round(random.uniform(0.5, 50.0), 2)
            criminal = random.choices([0, 1, 2, 5], weights=[0.8, 0.1, 0.05, 0.05])[0]
            incumbent = (i == 0) # Just make the first one incumbent
            photo = "https://ui-avatars.com/api/?name=" + party_abbr + "+Candidate&background=random"
            
            # Using placeholder IDs for now, we will insert and get IDs
            cands_in_const.append({
                "name": f"{party_abbr} Candidate {cid}-{i+1}",
                "party_id": pid,
                "cid": cid,
                "age": age,
                "gender": gender,
                "edu": education,
                "assets": assets,
                "crim": criminal,
                "incumbent": incumbent,
                "photo": photo
            })
            
        # Insert candidates and get their IDs
        inserted_cands = []
        for cand in cands_in_const:
            cursor.execute("""
                INSERT INTO candidates (name, party_id, constituency_id, age, gender, education, assets_cr, criminal_cases, incumbent, photo_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cand["name"], cand["party_id"], cand["cid"], cand["age"], cand["gender"], cand["edu"], cand["assets"], cand["crim"], cand["incumbent"], cand["photo"]))
            inserted_cands.append(cursor.lastrowid)
        
        # Result for this constituency
        winner_id = inserted_cands[0]
        runner_up_id = inserted_cands[1]
        votes_polled = int(total_electors * (turnout / 100))
        margin = random.randint(5000, 200000)
        results.append((cid, winner_id, runner_up_id, votes_polled, margin, "Won"))

    cursor.executemany("INSERT INTO elector_stats (constituency_id, male, female, third_gender, new_electors, total, turnout_percentage) VALUES (?, ?, ?, ?, ?, ?, ?)", elector_stats)
    cursor.executemany("INSERT INTO results (constituency_id, winner_candidate_id, runner_up_candidate_id, votes, margin, status) VALUES (?, ?, ?, ?, ?, ?)", results)

    # 5. Historical Results (Mocking 2019 and 2024)
    history = [
        (2019, party_map["BJP"], 303, 37.36),
        (2019, party_map["INC"], 52, 19.49),
        (2019, party_map["TMC"], 22, 4.07),
        (2024, party_map["BJP"], 240, 36.56),
        (2024, party_map["INC"], 99, 21.19),
        (2024, party_map["TMC"], 29, 4.37)
    ]
    cursor.executemany("INSERT INTO historical_results (year, party_id, seats_won, vote_share) VALUES (?, ?, ?, ?)", history)

    # 6. Election Steps
    steps = [
        (1, "Notification", "Official gazette notification", "Check voter list", "1 day", "Done"),
        (2, "Nomination", "Filing of candidate nominations", "Review affidavits", "7 days", "Done"),
        (3, "Scrutiny", "Checking valid nominations", "-", "1 day", "Done"),
        (4, "Withdrawal", "Last date to withdraw", "Check final candidate list", "2 days", "Done"),
        (5, "Campaigning", "Political rallies and outreach", "Attend local rallies", "14 days", "Done"),
        (6, "Polling", "Voting day", "Vote", "1-7 phases", "Today"),
        (7, "Counting", "Result declaration", "Watch live results", "1 day", "Upcoming")
    ]
    cursor.executemany("INSERT INTO election_steps (step_number, step_name, description, citizen_action, typical_days, status) VALUES (?, ?, ?, ?, ?, ?)", steps)

    print("Database seeding complete.")

if __name__ == "__main__":
    init_db()
