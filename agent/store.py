"""SQLite state. One row per listing ever seen, so nothing is reported twice."""
import sqlite3, os, datetime
import config

DB = os.path.join(config.DATA_DIR, "listings.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    uid          TEXT PRIMARY KEY,
    source       TEXT,
    url          TEXT,
    title        TEXT,
    price        INTEGER,
    sqm          REAL,
    rooms        REAL,
    plz          TEXT,
    area         TEXT,
    commute      INTEGER,
    move_in      TEXT,
    score        INTEGER,
    verdict      TEXT,
    reasons      TEXT,
    body         TEXT,
    first_seen   TEXT,
    reported     INTEGER DEFAULT 0,
    drafted      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    ts TEXT, source TEXT, fetched INTEGER, new INTEGER, matched INTEGER, note TEXT
);
"""

EXTRA_COLS = {
    "posted": "TEXT",
    "scam_risk": "INTEGER DEFAULT 0",
    "scam_flags": "TEXT",
    "checked": "INTEGER DEFAULT 0",   # 1 once the ad page itself has been read
    "last_seen": "TEXT",             # last scan that still saw this uid live
    "status": "TEXT DEFAULT ''",
    # What the matcher read at scan time, kept so a rescore sees the same facts.
    # NULL avail marks a row stored before these existed (see rescore.py).
    "avail": "TEXT",
    "warm": "REAL",     # '' | contacted | dismissed -- set from the dashboard
}


def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    # The dashboard reads while a scan writes; WAL lets both happen at once.
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    have = {r["name"] for r in c.execute("PRAGMA table_info(listings)")}
    for col, decl in EXTRA_COLS.items():
        if col not in have:
            c.execute(f"ALTER TABLE listings ADD COLUMN {col} {decl}")
    c.commit()
    return c

def seen(c, uid):
    return c.execute("SELECT 1 FROM listings WHERE uid=?", (uid,)).fetchone() is not None

def add(c, rec):
    rec = dict(rec)
    rec["first_seen"] = datetime.datetime.now().isoformat(timespec="seconds")
    cols = ",".join(rec)
    marks = ",".join("?" * len(rec))
    c.execute(f"INSERT OR IGNORE INTO listings ({cols}) VALUES ({marks})", list(rec.values()))

def log_run(c, source, fetched, new, matched, note=""):
    c.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
              (datetime.datetime.now().isoformat(timespec="seconds"),
               source, fetched, new, matched, note))

def unreported_hits(c):
    return c.execute(
        "SELECT * FROM listings WHERE reported=0 AND verdict IN ('HIT','MAYBE') "
        "ORDER BY score DESC, commute ASC").fetchall()

def mark_reported(c, uids):
    c.executemany("UPDATE listings SET reported=1 WHERE uid=?", [(u,) for u in uids])
