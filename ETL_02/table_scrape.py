"""
table_scrape.py

Extracts every HTML table from any URL, then:
  1. Saves them as an .RData file — one R data frame per table,
     named table_0, table_1, ... — ready to load in R.
  2. Generates a .md file ranking each scraped table against every
     table in a target SQLite database by column-name similarity,
     from highest relevance to lowest.

Usage:
    python table_scrape.py              # Preview (prints summary, no files written)
    python table_scrape.py --save       # Write .RData and .md output files

Configuration:
    Edit the CONFIGURATION block below to point at your URL,
    database, and preferred output file stem.  Everything else is
    automatic — the script works against any page and any SQLite DB.

Prerequisites:
    pip install requests pandas lxml pyreadr beautifulsoup4

------------------------------------------------------------------------
TESTING STATUS AND KNOWN LIMITATIONS (as of 2026-04-04)
------------------------------------------------------------------------
UNTESTED AGAINST FBREF.COM:
    FBref (fbref.com) and all other Sports Reference sites are
    protected by Cloudflare's browser-integrity challenge.  The server
    returns HTTP 403 with a JavaScript fingerprinting page before any
    content is served.  This script — and any Python library that uses
    plain HTTP requests — cannot pass that challenge.  Targeting FBref
    with this script will always fail at the fetch step.

    For a working FBref pipeline, see the recommendations at the bottom
    of this docstring.

SITES THIS SCRIPT WORKS WELL WITH:
    - Wikipedia / Wikimedia projects (static HTML, no bot protection)
    - Government and academic data portals (static HTML tables)
    - Most sports league official sites without Cloudflare
    - Any site that serves full HTML tables without a JS challenge

GENERAL LIMITATIONS:
    - JavaScript-rendered tables (React, Vue, etc.) are not visible to
      requests + BeautifulSoup; a headless browser (Playwright/Selenium)
      would be needed.
    - Sites behind Cloudflare, Akamai, or similar bot-management layers
      block plain HTTP requests regardless of User-Agent.
    - Pagination is not handled; only the tables present on the initial
      page load are captured.
    - Some sites require session cookies or login; this script does not
      manage authentication.

RECOMMENDED APPROACH FOR FBREF.COM:
    Use the R package worldfootballR, which is purpose-built for FBref
    and handles their rate limits and table structure internally:

        install.packages("worldfootballR")
        library(worldfootballR)

        # Example — pull USL Championship squad stats:
        df <- fb_season_team_stats(
                country = "USA",
                gender  = "M",
                season_end_year = 2026,
                tier    = "3rd",
                stat_type = "standard"
              )

    worldfootballR returns standard R data frames that can be written
    directly to your SQLite database via RSQLite / DBI, making it a
    clean drop-in for this pipeline.

    See: https://jaseziv.github.io/worldfootballR/
------------------------------------------------------------------------
"""

import sys
import re
import sqlite3
import requests
import pandas as pd
from bs4 import BeautifulSoup, Comment

# ================================================================
# CONFIGURATION
# ================================================================

# Any URL whose page contains HTML <table> elements.
URL = "https://fbref.com/en/comps/73/stats/USL-Championship-Stats#all_stats_squads_standard"

# Path to your SQLite database.  Set to "" to skip DB matching.
DB_PATH = "usl_championship_26.db"

# Output file stem (no extension).  Two files are written:
#   <OUTPUT_STEM>.RData   — loadable R data frames
#   <OUTPUT_STEM>.md      — relevance match report
OUTPUT_STEM = "scraped_tables"

# User-agent sent with the HTTP request.
# Some sites (e.g. FBref) block non-browser agents outright; a
# realistic browser string is the most reliable default here.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ================================================================

SAVE_MODE = "--save" in sys.argv


# ----------------------------------------------------------------
# STEP 1: FETCH PAGE AND PARSE ALL TABLES
# ----------------------------------------------------------------

print(f"Fetching: {URL}\n")
try:
    response = requests.get(
        URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
        },
    )
    response.raise_for_status()

    # Some sites (notably FBref / Sports Reference) embed their data
    # tables inside HTML comments to deter scrapers.  BeautifulSoup
    # can find those comments and splice the raw HTML back into the
    # document tree before we hand it to pd.read_html.
    soup = BeautifulSoup(response.text, "lxml")
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        if "<table" in comment:
            comment.replace_with(BeautifulSoup(str(comment), "lxml"))

    raw_tables = pd.read_html(str(soup))
    print(f"Found {len(raw_tables)} table(s) on the page.\n")
except Exception as e:
    print(f"ERROR fetching page: {e}")
    print("Check the URL and your internet connection.")
    print("You may also need:  pip install requests lxml beautifulsoup4")
    sys.exit(1)

# Flatten multi-level column headers into plain strings and strip
# whitespace.  Produce a clean list indexed to match table_0 ... table_N.
tables: list[pd.DataFrame] = []
for i, df in enumerate(raw_tables):
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(str(x) for x in col).strip() for col in df.columns
        ]
    df.columns = [str(c).strip() for c in df.columns]
    tables.append(df)
    col_preview = list(df.columns[:6])
    print(
        f"  table_{i}: {df.shape[0]} rows × {df.shape[1]} cols"
        f" — {col_preview}{'...' if df.shape[1] > 6 else ''}"
    )

print()


# ----------------------------------------------------------------
# STEP 2: READ TARGET DATABASE SCHEMA
# ----------------------------------------------------------------

db_schema: dict[str, list[str]] = {}   # { db_table_name: [col, ...] }

if DB_PATH:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        for (tname,) in cur.fetchall():
            cur.execute(f"PRAGMA table_info({tname})")
            db_schema[tname] = [row[1] for row in cur.fetchall()]
        conn.close()
        print(
            f"Database '{DB_PATH}': {len(db_schema)} table(s) — "
            f"{', '.join(db_schema)}\n"
        )
    except Exception as e:
        print(f"WARNING: Could not read database '{DB_PATH}': {e}")
        print("DB match recommendations will be skipped.\n")
else:
    print("No DB_PATH set — skipping DB match recommendations.\n")


# ----------------------------------------------------------------
# STEP 3: RELEVANCE SCORING
# ----------------------------------------------------------------
# Each (scraped table, DB table) pair gets a score in [0, 1.5].
#
# Column overlap score (0–1):
#   For every column in the scraped table, find the DB column whose
#   token-set has the highest Jaccard similarity to it, then average
#   those best-match scores across all scraped columns.
#
# Name bonus (0–0.5):
#   Jaccard between the DB table-name tokens and all column-name
#   tokens in the scraped table, weighted 0.5×.  This rewards a DB
#   table called "stadiums" when the web table has a "stadium" column.


def _normalize(text: str) -> str:
    """Lowercase, replace punctuation with spaces, collapse runs."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(_normalize(text).split())


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _column_overlap(web_cols: list[str], db_cols: list[str]) -> float:
    if not web_cols or not db_cols:
        return 0.0
    db_sets = [_tokens(c) for c in db_cols]
    return sum(
        max(_jaccard(_tokens(wc), ds) for ds in db_sets)
        for wc in web_cols
    ) / len(web_cols)


def _name_bonus(web_cols: list[str], db_table_name: str) -> float:
    all_web_tokens: set[str] = set()
    for c in web_cols:
        all_web_tokens |= _tokens(c)
    return _jaccard(_tokens(db_table_name), all_web_tokens) * 0.5


# Build the full (score, table_index, db_table_name) list.
all_matches: list[tuple[float, int, str]] = []

if db_schema:
    for i, df in enumerate(tables):
        web_cols = list(df.columns)
        for db_tname, db_cols in db_schema.items():
            score = _column_overlap(web_cols, db_cols) + _name_bonus(
                web_cols, db_tname
            )
            all_matches.append((score, i, db_tname))

    all_matches.sort(reverse=True)

    print("Top relevance matches (scraped → DB table):")
    for score, wi, dbt in all_matches[:20]:
        print(f"  table_{wi:>2}  →  {dbt:<28} score: {score:.3f}")
    print()


# ----------------------------------------------------------------
# STEP 4: PREVIEW EXIT (no --save)
# ----------------------------------------------------------------

if not SAVE_MODE:
    print("Preview mode — no files written.")
    print("Run with --save to write .RData and .md output files.")
    sys.exit(0)


# ----------------------------------------------------------------
# STEP 5: WRITE .RData FILE
# ----------------------------------------------------------------

try:
    import pyreadr
except ImportError:
    print("ERROR: pyreadr is required to write .RData files.")
    print("Install it with:  pip install pyreadr")
    sys.exit(1)

rdata_path = OUTPUT_STEM + ".RData"

# pyreadr requires homogeneous column types; coerce object columns
# to str so mixed-type columns don't cause write errors.
rdata_dict: dict[str, pd.DataFrame] = {}
for i, df in enumerate(tables):
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].astype(str)
    rdata_dict[f"table_{i}"] = out

pyreadr.write_rdata(rdata_path, rdata_dict)
print(f"Wrote {rdata_path}  ({len(rdata_dict)} data frame(s))")


# ----------------------------------------------------------------
# STEP 6: WRITE .md REPORT
# ----------------------------------------------------------------

md_path = OUTPUT_STEM + ".md"

def _col_preview(cols: list[str], n: int = 5) -> str:
    shown = ", ".join(f"`{c}`" for c in cols[:n])
    if len(cols) > n:
        shown += f", …+{len(cols) - n}"
    return shown


lines: list[str] = [
    "# Table Scrape Report",
    "",
    f"**Source URL:** {URL}  ",
    f"**Database:** `{DB_PATH or '(none)'}`  ",
    f"**Tables scraped:** {len(tables)}  ",
    f"**R data file:** `{rdata_path}`  ",
    "",
    "---",
    "",
    "## Scraped Tables",
    "",
]

for i, df in enumerate(tables):
    lines += [
        f"### `table_{i}`",
        f"- **Shape:** {df.shape[0]} rows × {df.shape[1]} cols",
        f"- **Columns:** {_col_preview(list(df.columns), 8)}",
        "",
    ]

lines += [
    "---",
    "",
    "## DB Match Recommendations",
    "",
]

if not all_matches:
    lines.append("_No database loaded — no match data available._")
else:
    lines += [
        "Ranked from highest to lowest relevance score.  "
        "Score = column-name Jaccard overlap (0–1) + DB table-name "
        "token bonus (0–0.5).  A score above 0.15 generally indicates "
        "a plausible structural match.",
        "",
        "| Rank | Scraped Table | DB Table | Score | Scraped Columns (preview) |",
        "|-----:|:-------------|:---------|------:|:--------------------------|",
    ]
    for rank, (score, wi, dbt) in enumerate(all_matches, 1):
        df = tables[wi]
        lines.append(
            f"| {rank} "
            f"| `table_{wi}` "
            f"| `{dbt}` "
            f"| {score:.3f} "
            f"| {_col_preview(list(df.columns))} |"
        )

    # Per-DB-table summary: best scraped match for each DB table.
    best_for_db: dict[str, tuple[int, float]] = {}
    for score, wi, dbt in all_matches:
        if dbt not in best_for_db:
            best_for_db[dbt] = (wi, score)

    lines += [
        "",
        "---",
        "",
        "## Best Match per DB Table",
        "",
        "| DB Table | Best Scraped Table | Score | DB Schema (preview) |",
        "|:---------|:------------------|------:|:--------------------|",
    ]
    for dbt, (wi, score) in sorted(
        best_for_db.items(), key=lambda kv: -kv[1][1]
    ):
        db_cols_prev = _col_preview(db_schema[dbt])
        lines.append(
            f"| `{dbt}` | `table_{wi}` | {score:.3f} | {db_cols_prev} |"
        )

lines += ["", "---", "", "_Generated by table\\_scrape.py_", ""]

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Wrote {md_path}")
