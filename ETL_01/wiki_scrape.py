"""
wikipedia_scrape.py

Pulls team and stadium information from the USL Championship
Wikipedia page and updates the local SQLite database with any
new data — stadium capacity, surface, stadium names, coaches,
and newly added expansion teams.

Usage:
    python wikipedia_scrape.py              # Preview mode (no DB changes)
    python wikipedia_scrape.py --update     # Write changes to database

Prerequisites:
    pip install requests beautifulsoup4 lxml
"""

import sqlite3
import pandas as pd
import sys
import requests

# ================================================================
# CONFIGURATION
# ================================================================

# Wikipedia URL for general info or info on a specific season.
# Swap the URL as needed.
WIKI_URL = "https://en.wikipedia.org/wiki/Miami_FC"

# Path to your SQLite database (same folder as this script)
DB_PATH = "usl_championship_26.db"

# In command line, Use "wikipedia_scrape.py" for just previewing,
# and "wikipedia_scrape.py --update" for updating.
#
# sys.argv is a list of everything typed on the command line:
#   sys.argv[0] = "wikipedia_scrape.py"
#   sys.argv[1] = "--update" (if provided)
UPDATE_MODE = "--update" in sys.argv

# The season to update coaches for. Change this when a new
# season starts so you're writing to the right year's records.
CURRENT_SEASON = 2026

# When targeting a specific team's Wikipedia page for roster ingestion,
# set these to the team's abbreviation and full name as stored (or to
# be stored) in the database.  Leave blank to use overview-page mode.
TEAM_ABV  = "M"
TEAM_NAME = "Miami FC"

# Force a specific page mode: 'team', 'overview', or '' (auto-detect).
# Use 'team' when the URL is a club page so navbox tables with a
# 'Team' column don't trigger false overview detection.
PAGE_MODE = "team"


# ================================================================
# PHASE 1: PULL TABLES FROM WIKIPEDIA
# ================================================================
# pd.read_html() is remarkably powerful — give it a URL and it
# returns a list of every <table> on the page, each as a DataFrame.
#
# Wikipedia pages often have 10-20 tables (infoboxes, standings,
# stats, etc.), so we need to figure out which one has the data
# we want.

print(f"Fetching tables from:\n  {WIKI_URL}\n")

try:
    # Fetch the page ourselves with a User-Agent header.
    # Wikipedia blocks requests that don't identify themselves.
    # This is standard etiquette for web scraping — you tell the
    # server who you are so they can contact you if there's an issue.
    response = requests.get(WIKI_URL, headers={
        "User-Agent": "USLChampionshipDataProject/1.0 (personal research)"
    })
    response.raise_for_status()  # Raises an error if status != 200

    # Pass the HTML string to read_html instead of the URL
    tables = pd.read_html(response.text)
    print(f"Found {len(tables)} tables on the page.\n")
except Exception as e:
    print(f"ERROR fetching page: {e}")
    print("Make sure you have internet access and the URL is correct.")
    print("You may also need to install: pip install requests beautifulsoup4 lxml")
    sys.exit(1)


# ================================================================
# PHASE 2: FIND THE RIGHT TABLE
# ================================================================
# We'll scan each table's columns looking for keywords that suggest
# it contains team/stadium information. Common column names on
# Wikipedia USL pages include "Team", "Stadium", "Capacity", "City",
# "Head coach", etc.
#
# We print a summary of every table so you can see what's available
# and adjust the target_index if the page layout changes.

STADIUM_KEYWORDS = {'stadium', 'venue', 'capacity', 'ground'}
TEAM_KEYWORDS = {'team', 'club', 'city', 'location'}

best_index = None
best_score = 0

for i, df in enumerate(tables):
    # Flatten column names (some tables have multi-level headers)
    col_names = []
    for c in df.columns:
        if isinstance(c, tuple):
            col_names.append(' '.join(str(x) for x in c))
        else:
            col_names.append(str(c))

    col_lower = {c.lower() for c in col_names}

    # Score this table: how many of our keywords appear in its columns?
    stadium_hits = len(col_lower & STADIUM_KEYWORDS)
    team_hits = len(col_lower & TEAM_KEYWORDS)
    score = stadium_hits + team_hits

    # Print a preview of every table (first few columns, first row)
    preview_cols = col_names[:6]
    print(f"  Table {i}: {df.shape[0]} rows x {df.shape[1]} cols")
    print(f"    Columns: {preview_cols}{'...' if len(col_names) > 6 else ''}")
    if len(df) > 0:
        print(f"    Row 0:   {list(df.iloc[0, :4])}")
    if score > 0:
        print(f"    ★ Keyword matches: {score} (stadium: {stadium_hits}, team: {team_hits})")
    print()

    if score > best_score:
        best_score = score
        best_index = i

# Detect squad tables (team-page mode: No. / Pos. / Player / Nation)
SQUAD_KEYWORDS = {'no', 'pos', 'player', 'nation'}
squad_table_indices = []
for i, df in enumerate(tables):
    col_set = {str(c).lower().strip().rstrip('.') for c in df.columns}
    if len(col_set & SQUAD_KEYWORDS) >= 3:
        squad_table_indices.append(i)

if PAGE_MODE:
    page_mode = PAGE_MODE
    print(f"Page mode forced by config: '{page_mode}'")
elif best_score >= 1:
    page_mode = 'overview'
elif squad_table_indices:
    page_mode = 'team'
    print(f"Team page detected — squad tables at indices: {squad_table_indices}")
else:
    print("Could not auto-detect the teams/stadiums table.")
    print("Look at the table summaries above, pick the right index,")
    print("and set target_index manually in the script.")
    sys.exit(1)

if page_mode == 'overview':
    print(f"Best match: Table {best_index} (score: {best_score})")
    print("=" * 60)

    wiki_df = tables[best_index]

    # Flatten multi-level column headers into simple strings
    if isinstance(wiki_df.columns, pd.MultiIndex):
        wiki_df.columns = [' '.join(str(x) for x in col).strip() for col in wiki_df.columns]

    # Normalize column names to lowercase for easier matching
    wiki_df.columns = [str(c).lower().strip() for c in wiki_df.columns]

    print(f"\nSelected table columns: {list(wiki_df.columns)}")
    print(f"\nFull table preview:")
    print(wiki_df.to_string())
    print()

elif page_mode == 'team':
    # ================================================================
    # TEAM PAGE MODE: ROSTER INGESTION
    # ================================================================
    # Combine all detected squad tables, clean player names, and
    # upsert into the players + season_rosters tables.
    # ================================================================

    import re

    # ---- inline helpers (find_wiki_column not yet defined) ----------

    def _find_col(df, candidates):
        """Return first df column name matching any candidate as a whole word."""
        for col in df.columns:
            for term in candidates:
                if re.search(r'\b' + re.escape(term) + r'\b', col, re.IGNORECASE):
                    return col
        return None

    def _clean_name(raw):
        """Strip loan notes and Wikipedia footnote refs from a player name."""
        if pd.isna(raw):
            return ""
        s = str(raw).strip()
        s = re.sub(r'\s*\(on loan from[^)]*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\s*\[.*?\]', '', s)
        s = re.sub(r'\s*\(\s*\)', '', s)   # remove empty parens left after ref removal
        return s.strip()

    def _parse_jersey(raw):
        """Return jersey number as int, or None for '—' / missing."""
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return None
        s = str(raw).strip()
        if s in ('—', '-', ''):
            return None
        try:
            return int(s)
        except ValueError:
            return None

    # ---- Parse all squad tables ------------------------------------

    print(f"Processing team page: {TEAM_NAME} ({TEAM_ABV})")
    print(f"Squad tables at indices: {squad_table_indices}\n")

    all_players = []
    for idx in squad_table_indices:
        df = tables[idx].copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [' '.join(str(x) for x in c).strip() for c in df.columns]
        df.columns = [str(c).lower().strip().rstrip('.') for c in df.columns]

        no_col     = _find_col(df, ['no'])
        pos_col    = _find_col(df, ['pos'])
        nation_col = _find_col(df, ['nation', 'nationality'])
        player_col = _find_col(df, ['player', 'name'])

        print(f"  Table {idx}: jersey={no_col!r}, pos={pos_col!r}, "
              f"nation={nation_col!r}, player={player_col!r}")

        for _, row in df.iterrows():
            name = _clean_name(row.get(player_col, '') if player_col else '')
            if not name:
                continue
            all_players.append({
                'name':     name,
                'jersey':   _parse_jersey(row.get(no_col) if no_col else None),
                'position': (str(row.get(pos_col, '')).strip() if pos_col else '') or None,
                'nation':   (str(row.get(nation_col, '')).strip() if nation_col else '') or None,
            })

    print(f"\nPlayers found: {len(all_players)}")
    for p in all_players:
        no_str = str(p['jersey']).rjust(2) if p['jersey'] is not None else ' —'
        print(f"  #{no_str}  {p['position'] or '??'}  {p['nation'] or '???'}  {p['name']}")

    # ---- Connect and ensure team exists ----------------------------

    print(f"\n{'=' * 60}")
    conn_t = sqlite3.connect(DB_PATH)
    cur_t  = conn_t.cursor()

    cur_t.execute("SELECT team_abv FROM teams WHERE team_abv = ?", (TEAM_ABV,))
    team_exists = cur_t.fetchone() is not None

    if not team_exists:
        if UPDATE_MODE:
            cur_t.execute("PRAGMA foreign_keys = ON;")
            cur_t.execute("SELECT COALESCE(MAX(stadium_id), 0) FROM stadiums")
            sid = cur_t.fetchone()[0] + 1
            cur_t.execute(
                "INSERT INTO stadiums (stadium_id, name) VALUES (?, ?)",
                (sid, f"{TEAM_NAME} Stadium (placeholder)")
            )
            cur_t.execute(
                "INSERT INTO teams (team_abv, name, stadium_id) VALUES (?, ?, ?)",
                (TEAM_ABV, TEAM_NAME, sid)
            )
            print(f"Inserted team '{TEAM_NAME}' ({TEAM_ABV}) with placeholder stadium (id={sid}).")
        else:
            print(f"NOTE: Team '{TEAM_NAME}' ({TEAM_ABV}) not in DB — will be inserted on --update.")

    # ---- Preview or apply ------------------------------------------

    if not UPDATE_MODE:
        print(f"\nPREVIEW MODE — {len(all_players)} players would be ingested "
              f"for {TEAM_NAME} season {CURRENT_SEASON}.")
        print(f"Run with --update to apply:  python wiki_scrape.py --update")
        conn_t.close()
        sys.exit(0)

    cur_t.execute("PRAGMA foreign_keys = ON;")
    new_players   = 0
    roster_inserts = 0
    roster_updates = 0

    for p in all_players:
        cur_t.execute("SELECT player_id FROM players WHERE name = ?", (p['name'],))
        row = cur_t.fetchone()
        if row:
            player_id = row[0]
            # Fill in missing nation / position if we have them now
            if p['nation']:
                cur_t.execute(
                    "UPDATE players SET nation = ? WHERE player_id = ? AND nation IS NULL",
                    (p['nation'], player_id)
                )
            if p['position']:
                cur_t.execute(
                    "UPDATE players SET position = ? WHERE player_id = ? AND position IS NULL",
                    (p['position'], player_id)
                )
        else:
            cur_t.execute(
                "INSERT INTO players (name, nation, position) VALUES (?, ?, ?)",
                (p['name'], p['nation'], p['position'])
            )
            player_id = cur_t.lastrowid
            new_players += 1

        cur_t.execute(
            "SELECT jersey_number FROM season_rosters "
            "WHERE season = ? AND team_abv = ? AND player_id = ?",
            (CURRENT_SEASON, TEAM_ABV, player_id)
        )
        existing = cur_t.fetchone()
        if existing is None:
            cur_t.execute(
                "INSERT INTO season_rosters (season, team_abv, player_id, jersey_number) "
                "VALUES (?, ?, ?, ?)",
                (CURRENT_SEASON, TEAM_ABV, player_id, p['jersey'])
            )
            roster_inserts += 1
        else:
            cur_t.execute(
                "UPDATE season_rosters SET jersey_number = ? "
                "WHERE season = ? AND team_abv = ? AND player_id = ?",
                (p['jersey'], CURRENT_SEASON, TEAM_ABV, player_id)
            )
            roster_updates += 1

    conn_t.commit()
    print(f"✓ Players: {new_players} inserted.")
    print(f"✓ Roster rows: {roster_inserts} inserted, {roster_updates} updated.")
    print(f"✓ {TEAM_NAME} ({TEAM_ABV}) roster for {CURRENT_SEASON} written to {DB_PATH}.")
    conn_t.close()
    sys.exit(0)


# ================================================================
# PHASE 3: MATCH TO EXISTING DATABASE RECORDS
# ================================================================
# Wikipedia uses full team names, and so does our database, but
# there may be slight differences (e.g., "FC Tulsa" vs "FC Tulsa").
# We'll try exact matching first, then fall back to fuzzy matching
# on city name or abbreviation.

print("=" * 60)
print("MATCHING AGAINST DATABASE")
print("=" * 60)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Pull existing teams and stadiums.
# LEFT JOIN so teams without a stadium yet are still included.
cursor.execute("""
    SELECT t.team_abv, t.name, t.city, t.conference, t.stadium_id,
           s.name as stadium_name, s.capacity, s.surface,
           t.kit_manufacturer, t.kit_sponsor
    FROM teams t
    LEFT JOIN stadiums s ON t.stadium_id = s.stadium_id
""")
db_teams = cursor.fetchall()
col_names_db = ['team_abv', 'team_name', 'city', 'conference', 'stadium_id',
                'stadium_name', 'capacity', 'surface', 'kit_manufacturer', 'kit_sponsor']

print(f"\nDatabase has {len(db_teams)} teams.")
print(f"Wikipedia table has {len(wiki_df)} rows.\n")

# Build a lookup structure for matching.
# We'll try to match on team name, falling back to city.
def normalize(text):
    """Lowercase, strip whitespace and common suffixes for matching."""
    if pd.isna(text):
        return ""
    text = str(text).lower().strip()
    # Remove common suffixes that differ between sources
    for suffix in [' fc', ' sc', ' cf']:
        if text.endswith(suffix):
            text = text[:-len(suffix)].strip()
    return text


def clean_wiki_text(text):
    """Strip Wikipedia footnote references like [i][186] and whitespace."""
    if pd.isna(text):
        return ""
    text = str(text).strip()
    # Remove bracketed footnote references: [i], [186], [ii][188], etc.
    import re
    text = re.sub(r'\[.*?\]', '', text)
    return text.strip()


# Try to detect which Wikipedia columns map to what we need.
# This is heuristic — we look for columns containing key terms.
def find_wiki_column(df, candidates):
    """Find the first column name matching any candidate term.

    First pass: whole-word match (e.g. 'Team' matches 'Team').
    Second pass: startswith match to catch Wikipedia template suffixes
    like 'Teamvte' (the vte view/talk/edit marker appended by MediaWiki).
    """
    import re as _re
    for col in df.columns:
        for term in candidates:
            if _re.search(r'\b' + _re.escape(term) + r'\b', col, _re.IGNORECASE):
                return col
    for col in df.columns:
        for term in candidates:
            if str(col).lower().startswith(term.lower()):
                return col
    return None

wiki_team_col = find_wiki_column(wiki_df, ['team', 'club'])
wiki_stadium_col = find_wiki_column(wiki_df, ['stadium', 'venue', 'ground'])
wiki_capacity_col = find_wiki_column(wiki_df, ['capacity'])
wiki_surface_col = find_wiki_column(wiki_df, ['surface', 'pitch'])
wiki_city_col = find_wiki_column(wiki_df, ['city', 'location'])
wiki_coach_col = find_wiki_column(wiki_df, ['head coach', 'coach', 'manager'])
wiki_conference_col = find_wiki_column(wiki_df, ['conference'])
wiki_founded_col = find_wiki_column(wiki_df, ['founded'])
wiki_joined_col = find_wiki_column(wiki_df, ['joined', 'joining'])

print("Detected column mapping:")
print(f"  Team:       {wiki_team_col}")
print(f"  Stadium:    {wiki_stadium_col}")
print(f"  Capacity:   {wiki_capacity_col}")
print(f"  Surface:    {wiki_surface_col}")
print(f"  City:       {wiki_city_col}")
print(f"  Coach:      {wiki_coach_col}")
print(f"  Conference: {wiki_conference_col}")
print(f"  Founded:    {wiki_founded_col}")
print(f"  Joined:     {wiki_joined_col}")
print()

# If we couldn't find the team column, we can't proceed
if wiki_team_col is None:
    print("ERROR: Could not identify the team name column.")
    print("Check the table preview above and adjust the script.")
    conn.close()
    sys.exit(1)


# ================================================================
# PHASE 3.5: BUILD CONFERENCE MAP AND PERSONNEL MAP
# ================================================================
# Conference map: parse the page HTML to find which heading
# (Eastern Conference / Western Conference) precedes each standings
# table, then record every team name in that table as E or W.
#
# Personnel map: separately detect the table that has coach/captain
# columns and build a lookup keyed by normalized team name.

from bs4 import BeautifulSoup

conference_map = {}   # normalize(team_name) → 'E' or 'W'
soup = BeautifulSoup(response.text, 'lxml')

# Walk all elements in document order, tracking the most recent
# conference heading so each table is stamped with the right value.
current_conf = None
for elem in soup.find_all(['h2', 'h3', 'table']):
    if elem.name in ('h2', 'h3'):
        text = elem.get_text(strip=True).lower()
        if 'eastern' in text:
            current_conf = 'E'
        elif 'western' in text:
            current_conf = 'W'
        elif elem.name == 'h2':
            current_conf = None   # top-level section reset
    elif elem.name == 'table' and current_conf:
        try:
            conf_df = pd.read_html(str(elem))[0]
            if isinstance(conf_df.columns, pd.MultiIndex):
                conf_df.columns = [' '.join(str(x) for x in c).strip() for c in conf_df.columns]
            conf_df.columns = [str(c).lower().strip() for c in conf_df.columns]
            t_col = find_wiki_column(conf_df, ['team', 'club'])
            if t_col:
                for name in conf_df[t_col]:
                    conference_map[normalize(str(name))] = current_conf
        except Exception:
            pass

print(f"Conference map: {len(conference_map)} teams detected")
for name, conf in sorted(conference_map.items()):
    print(f"  {name}: {conf}")
print()

# Personnel map: find the table with coach/captain columns.
personnel_map = {}   # normalize(team_name) → {'coach': ..., 'captain': ...}

PERSONNEL_KEYWORDS = {'coach', 'manager', 'captain', 'sponsor', 'manufacturer'}
for i, df in enumerate(tables):
    col_set = {str(c).lower().strip() for c in df.columns}
    # Use substring matching — column names like 'head coach' and
    # 'captain(s)' won't hit an exact set intersection.
    has_personnel = any(any(kw in col for kw in PERSONNEL_KEYWORDS) for col in col_set)
    has_team = any('team' in c or 'club' in c for c in col_set)
    if has_personnel and has_team:
        pers_df = df.copy()
        if isinstance(pers_df.columns, pd.MultiIndex):
            pers_df.columns = [' '.join(str(x) for x in c).strip() for c in pers_df.columns]
        pers_df.columns = [str(c).lower().strip() for c in pers_df.columns]

        pers_team_col    = find_wiki_column(pers_df, ['team', 'club'])
        pers_coach_col   = find_wiki_column(pers_df, ['head coach', 'coach', 'manager'])
        pers_captain_col = find_wiki_column(pers_df, ['captain'])
        pers_kit_mfr_col = find_wiki_column(pers_df, ['kit manufacturer', 'manufacturer'])
        pers_kit_spo_col = find_wiki_column(pers_df, ['kit sponsor', 'sponsor'])

        print(f"Personnel table: Table {i}")
        print(f"  Team: {pers_team_col}  Coach: {pers_coach_col}  Captain: {pers_captain_col}")
        print(f"  Kit manufacturer: {pers_kit_mfr_col}  Kit sponsor: {pers_kit_spo_col}")

        for _, row in pers_df.iterrows():
            t_name = str(row.get(pers_team_col, ''))
            t_norm = normalize(t_name)
            if not t_norm:
                continue
            personnel_map[t_norm] = {
                'coach':            clean_wiki_text(row.get(pers_coach_col,   '')) if pers_coach_col   else '',
                'captain':          clean_wiki_text(row.get(pers_captain_col, '')) if pers_captain_col else '',
                'kit_manufacturer': clean_wiki_text(row.get(pers_kit_mfr_col, '')) if pers_kit_mfr_col else '',
                'kit_sponsor':      clean_wiki_text(row.get(pers_kit_spo_col, '')) if pers_kit_spo_col else '',
            }
        print(f"  Built personnel map for {len(personnel_map)} teams")
        print()
        break  # only need the first matching table
else:
    print("No personnel table found.")
    print()


# ================================================================
# PHASE 4: COMPARE AND GENERATE UPDATES
# ================================================================

updates = []       # (sql_string, params_tuple) to execute in order
new_teams = []     # Track new teams for the summary
match_count = 0
miss_count = 0

# Pre-fetch the next available stadium_id.
cursor.execute("SELECT COALESCE(MAX(stadium_id), 0) FROM stadiums")
next_stadium_id = cursor.fetchone()[0] + 1

# Pre-load all existing abbreviations so new ones don't collide.
# We add to this set as we generate abbrevs in the loop below.
cursor.execute("SELECT team_abv FROM teams")
used_abbrevs = {row[0] for row in cursor.fetchall()}

for _, wiki_row in wiki_df.iterrows():
    wiki_name = str(wiki_row.get(wiki_team_col, ''))
    wiki_name_norm = normalize(wiki_name)

    # Try to match against our database teams
    matched_team = None
    for db_row in db_teams:
        db_dict = dict(zip(col_names_db, db_row))
        db_name_norm = normalize(db_dict['team_name'])
        db_city_norm = normalize(db_dict['city'])

        # Match on normalized name, or check if one contains the other
        if (db_name_norm == wiki_name_norm or
            db_name_norm in wiki_name_norm or
            wiki_name_norm in db_name_norm):
            matched_team = db_dict
            break

        # Fallback: match on city name
        if wiki_city_col and pd.notna(wiki_row.get(wiki_city_col)):
            wiki_city_norm = normalize(wiki_row[wiki_city_col])
            if db_city_norm and wiki_city_norm and (
                db_city_norm.split(',')[0] in wiki_city_norm or
                wiki_city_norm in db_city_norm):
                matched_team = db_dict
                break

    # ==============================================================
    # UNMATCHED ROWS → NEW TEAM INSERTS
    # ==============================================================
    # If no match was found, this is likely an expansion team that
    # isn't in our database yet. We'll collect what Wikipedia gives
    # us and generate INSERT statements for both a new stadium and
    # a new team.

    if matched_team is None:
        wiki_name_clean = clean_wiki_text(wiki_name)

        # Parse what we can from the Wikipedia row
        new_stadium_name = clean_wiki_text(wiki_row.get(wiki_stadium_col, '')) if wiki_stadium_col else ''

        # Parse capacity (digits only — take the first run of 4+ digits
        # to avoid grabbing footnote numbers like [186])
        new_capacity = None
        if wiki_capacity_col and pd.notna(wiki_row.get(wiki_capacity_col)):
            import re as _re
            cap_match = _re.search(r'\d{4,}', str(wiki_row[wiki_capacity_col]).replace(',', ''))
            if cap_match:
                new_capacity = int(cap_match.group())

        # Conference from the heading-based map built in Phase 3.5
        new_conference = conference_map.get(wiki_name_norm)

        # Parse the "joined" year (when they enter the league)
        new_joined = None
        if wiki_joined_col and pd.notna(wiki_row.get(wiki_joined_col)):
            joined_digits = ''.join(c for c in str(wiki_row[wiki_joined_col]) if c.isdigit())
            # Take first 4 digits as the year
            if len(joined_digits) >= 4:
                new_joined = int(joined_digits[:4])

        # Coach, captain, and kit info from the personnel map built in Phase 3.5
        pers = personnel_map.get(wiki_name_norm, {})
        new_coach        = pers.get('coach', '')
        new_captain      = pers.get('captain', '')
        new_kit_mfr      = pers.get('kit_manufacturer', '')
        new_kit_sponsor  = pers.get('kit_sponsor', '')

        # Derive a placeholder abbreviation from the team name initials.
        # team_abv is the primary key so it must be unique and non-empty.
        # Review and correct these after the run — they are placeholders.
        import re as _re
        words = _re.sub(r'[^a-zA-Z\s]', '', wiki_name_clean).split()
        stop = {'fc', 'sc', 'cf', 'ac', 'united', 'city', 'the'}
        sig = [w for w in words if w.lower() not in stop] or words
        base_abbr = ''.join(w[0].upper() for w in sig[:4])
        new_abbr = base_abbr
        suffix = 2
        while new_abbr in used_abbrevs:
            new_abbr = base_abbr + str(suffix)
            suffix += 1
        used_abbrevs.add(new_abbr)

        # Assign stadium ID
        sid = next_stadium_id
        next_stadium_id += 1

        print(f"  ★ NEW TEAM: '{wiki_name_clean}'")
        print(f"      team_abv={new_abbr} (derived placeholder), stadium_id={sid}")
        print(f"      Stadium: {new_stadium_name} (capacity: {new_capacity})")
        print(f"      Conference: {new_conference}")
        print(f"      Joined: {new_joined}")
        print(f"      Coach: {new_coach}")
        print(f"      Captain: {new_captain if new_captain else '(none listed)'}")
        print(f"      Kit manufacturer: {new_kit_mfr if new_kit_mfr else '(none listed)'}")
        print(f"      Kit sponsor: {new_kit_sponsor if new_kit_sponsor else '(none listed)'}")
        print(f"      ⚠ team_abv is a derived placeholder — update manually before referencing")

        # Stadium INSERT must come before team INSERT (foreign key).
        # City and surface are not available on this page — left NULL.
        updates.append((
            "INSERT INTO stadiums (stadium_id, name, capacity) VALUES (?, ?, ?)",
            (sid, new_stadium_name, new_capacity)
        ))

        updates.append((
            "INSERT INTO teams (team_abv, name, conference, member_since, stadium_id, kit_manufacturer, kit_sponsor) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (new_abbr, wiki_name_clean, new_conference, new_joined, sid, new_kit_mfr or None, new_kit_sponsor or None)
        ))

        if new_coach:
            updates.append((
                "INSERT INTO season_staff (season, team_abv, role, name) VALUES (?, ?, ?, ?)",
                (CURRENT_SEASON, new_abbr, 'Head Coach', new_coach)
            ))

        # Captain stored in season_staff; player FK resolved later
        # when rosters are loaded.
        if new_captain:
            updates.append((
                "INSERT INTO season_staff (season, team_abv, role, name) VALUES (?, ?, ?, ?)",
                (CURRENT_SEASON, new_abbr, 'Captain', new_captain)
            ))

        new_teams.append(wiki_name_clean)
        miss_count += 1
        continue

    # ==============================================================
    # MATCHED ROWS → CHECK FOR UPDATES
    # ==============================================================
    match_count += 1
    team_abv = matched_team['team_abv']
    stadium_id = matched_team['stadium_id']
    label = f"{matched_team['team_name']} ({team_abv})"

    # --- Check capacity ---
    if wiki_capacity_col and pd.notna(wiki_row.get(wiki_capacity_col)):
        raw_cap = str(wiki_row[wiki_capacity_col])
        # Wikipedia capacities often have commas, brackets, footnotes
        # Strip everything except digits
        clean_cap = ''.join(c for c in raw_cap if c.isdigit())
        if clean_cap:
            new_cap = int(clean_cap)
            old_cap = matched_team['capacity']
            if old_cap is None or old_cap != new_cap:
                print(f"  {label}: capacity {old_cap} → {new_cap}")
                updates.append((
                    "UPDATE stadiums SET capacity = ? WHERE stadium_id = ?",
                    (new_cap, stadium_id)
                ))

    # --- Check surface ---
    if wiki_surface_col and pd.notna(wiki_row.get(wiki_surface_col)):
        new_surface = clean_wiki_text(wiki_row[wiki_surface_col])
        old_surface = matched_team['surface']
        if old_surface is None and new_surface:
            print(f"  {label}: surface (empty) → {new_surface}")
            updates.append((
                "UPDATE stadiums SET surface = ? WHERE stadium_id = ?",
                (new_surface, stadium_id)
            ))

    # --- Check stadium name ---
    if wiki_stadium_col and pd.notna(wiki_row.get(wiki_stadium_col)):
        new_stadium = clean_wiki_text(wiki_row[wiki_stadium_col])
        old_stadium = matched_team['stadium_name']
        if old_stadium and normalize(old_stadium) != normalize(new_stadium):
            print(f"  {label}: stadium name '{old_stadium}' → '{new_stadium}'")
            updates.append((
                "UPDATE stadiums SET name = ? WHERE stadium_id = ?",
                (new_stadium, stadium_id)
            ))

    # --- Check head coach, captain, and kit info (from personnel_map) ---
    pers = personnel_map.get(wiki_name_norm, {})
    new_coach       = pers.get('coach', '')
    new_captain     = pers.get('captain', '')
    new_kit_mfr     = pers.get('kit_manufacturer', '')
    new_kit_sponsor = pers.get('kit_sponsor', '')

    for role, new_name in [('Head Coach', new_coach), ('Captain', new_captain)]:
        if not new_name:
            continue
        cursor.execute(
            "SELECT name FROM season_staff WHERE team_abv = ? AND season = ? AND role = ?",
            (team_abv, CURRENT_SEASON, role)
        )
        result = cursor.fetchone()
        old_name = result[0] if result else None

        if old_name is None:
            print(f"  {label}: {role} (empty) → {new_name}")
            updates.append((
                "INSERT INTO season_staff (season, team_abv, role, name) VALUES (?, ?, ?, ?)",
                (CURRENT_SEASON, team_abv, role, new_name)
            ))
        elif normalize(old_name) != normalize(new_name):
            print(f"  {label}: {role} '{old_name}' → {new_name}")
            updates.append((
                "UPDATE season_staff SET name = ? WHERE team_abv = ? AND season = ? AND role = ?",
                (new_name, team_abv, CURRENT_SEASON, role)
            ))

    # --- Check conference ---
    new_conf = conference_map.get(wiki_name_norm)
    if new_conf and matched_team.get('conference') != new_conf:
        print(f"  {label}: conference → {new_conf}")
        updates.append((
            "UPDATE teams SET conference = ? WHERE team_abv = ?",
            (new_conf, team_abv)
        ))

    # --- Check kit manufacturer and sponsor ---
    for col, new_val in [('kit_manufacturer', new_kit_mfr), ('kit_sponsor', new_kit_sponsor)]:
        if not new_val:
            continue
        old_val = matched_team.get(col)
        if old_val != new_val:
            print(f"  {label}: {col} '{old_val}' → '{new_val}'")
            updates.append((
                f"UPDATE teams SET {col} = ? WHERE team_abv = ?",
                (new_val, team_abv)
            ))


# ================================================================
# PHASE 5: APPLY OR PREVIEW
# ================================================================

print(f"\n{'=' * 60}")
print(f"RESULTS")
print(f"{'=' * 60}")
print(f"  Matched:    {match_count} teams")
print(f"  New teams:  {len(new_teams)} ({', '.join(new_teams) if new_teams else 'none'})")
print(f"  Updates:    {len(updates)} total changes\n")

if len(updates) == 0:
    print("Nothing to update — your database is already current!")
elif UPDATE_MODE:
    print("APPLYING UPDATES...")
    cursor.execute("PRAGMA foreign_keys = ON;")
    for sql, params in updates:
        cursor.execute(sql, params)
    conn.commit()
    print(f"✓ Applied {len(updates)} updates to the database.")
else:
    print("PREVIEW MODE — no changes written.")
    print("Review the changes above, then run with --update to apply:")
    print(f"  python wikipedia_scrape.py --update")

conn.close()
