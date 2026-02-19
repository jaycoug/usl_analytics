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
WIKI_URL = "https://en.wikipedia.org/wiki/USL_Championship"

# Path to your SQLite database (same folder as this script)
DB_PATH = "usl_championship.db"

# In command line, Use "wikipedia_scrape.py" for just previewing,
# and "wikipedia_scrape.py --update" for updating.
#
# sys.argv is a list of everything typed on the command line:
#   sys.argv[0] = "wikipedia_scrape.py"
#   sys.argv[1] = "--update" (if provided)
UPDATE_MODE = "--update" in sys.argv

# The season to update coaches for. Change this when a new
# season starts so you're writing to the right year's records.
CURRENT_SEASON = 2025


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

if best_index is None:
    print("Could not auto-detect the teams/stadiums table.")
    print("Look at the table summaries above, pick the right index,")
    print("and set target_index manually in the script.")
    sys.exit(1)

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

# Pull existing teams and stadiums
cursor.execute("""
    SELECT t.team_id, t.name, t.city, t.stadium_id,
           s.name as stadium_name, s.capacity, s.surface
    FROM teams t
    JOIN stadiums s ON t.stadium_id = s.stadium_id
""")
db_teams = cursor.fetchall()
col_names_db = ['team_id', 'team_name', 'city', 'stadium_id',
                'stadium_name', 'capacity', 'surface']

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
    """Find the first column name containing any of the candidate terms."""
    for col in df.columns:
        for term in candidates:
            if term in col:
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
# PHASE 4: COMPARE AND GENERATE UPDATES
# ================================================================

updates = []       # (sql_string, params_tuple) to execute in order
new_teams = []     # Track new teams for the summary
match_count = 0
miss_count = 0

# Pre-fetch the next available IDs for new teams/stadiums.
# We query the current max and will increment from there.
cursor.execute("SELECT COALESCE(MAX(team_id), 99) FROM teams")
next_team_id = cursor.fetchone()[0] + 1

cursor.execute("SELECT COALESCE(MAX(stadium_id), 29) FROM stadiums")
next_stadium_id = cursor.fetchone()[0] + 1

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
        new_city = clean_wiki_text(wiki_row.get(wiki_city_col, '')) if wiki_city_col else ''
        new_stadium_name = clean_wiki_text(wiki_row.get(wiki_stadium_col, '')) if wiki_stadium_col else ''
        new_coach = clean_wiki_text(wiki_row.get(wiki_coach_col, '')) if wiki_coach_col else ''

        # Parse capacity (digits only)
        new_capacity = None
        if wiki_capacity_col and pd.notna(wiki_row.get(wiki_capacity_col)):
            cap_digits = ''.join(c for c in str(wiki_row[wiki_capacity_col]) if c.isdigit())
            if cap_digits:
                new_capacity = int(cap_digits)

        # Determine conference from the Wikipedia row.
        # The Wikipedia table often has a "Conference" column with
        # values like "Eastern Conference" or "Western Conference".
        new_conference = None
        if wiki_conference_col and pd.notna(wiki_row.get(wiki_conference_col)):
            conf_raw = str(wiki_row[wiki_conference_col]).lower()
            if 'east' in conf_raw:
                new_conference = 'E'
            elif 'west' in conf_raw:
                new_conference = 'W'

        # Parse the "joined" year (when they enter the league)
        new_joined = None
        if wiki_joined_col and pd.notna(wiki_row.get(wiki_joined_col)):
            joined_digits = ''.join(c for c in str(wiki_row[wiki_joined_col]) if c.isdigit())
            # Take first 4 digits as the year
            if len(joined_digits) >= 4:
                new_joined = int(joined_digits[:4])

        # Abbreviation can't be reliably scraped — we'll leave it
        # blank and flag it for manual entry.
        new_abbr = ''

        # Assign IDs
        sid = next_stadium_id
        tid = next_team_id
        next_stadium_id += 1
        next_team_id += 1

        print(f"  ★ NEW TEAM: '{wiki_name_clean}'")
        print(f"      team_id={tid}, stadium_id={sid}")
        print(f"      City: {new_city}")
        print(f"      Stadium: {new_stadium_name} (capacity: {new_capacity})")
        print(f"      Conference: {new_conference}")
        print(f"      Joined: {new_joined}")
        print(f"      Coach: {new_coach}")
        print(f"      ⚠ Abbreviation left blank — set manually later")

        # Stadium INSERT must come before team INSERT (foreign key)
        updates.append((
            "INSERT INTO stadiums (stadium_id, name, city, capacity, surface) VALUES (?, ?, ?, ?, ?)",
            (sid, new_stadium_name, new_city, new_capacity, None)
        ))

        updates.append((
            "INSERT INTO teams (team_id, name, city, abbreviation, conference, member_since, stadium_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, wiki_name_clean, new_city, new_abbr, new_conference, new_joined, sid)
        ))

        # Also add the coach to season_staff if we have one
        if new_coach:
            updates.append((
                "INSERT INTO season_staff (season, team_id, role, name) VALUES (?, ?, ?, ?)",
                (CURRENT_SEASON, tid, 'Head Coach', new_coach)
            ))

        new_teams.append(wiki_name_clean)
        miss_count += 1
        continue

    # ==============================================================
    # MATCHED ROWS → CHECK FOR UPDATES
    # ==============================================================
    match_count += 1
    team_id = matched_team['team_id']
    stadium_id = matched_team['stadium_id']
    label = f"{matched_team['team_name']} ({team_id})"

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

    # --- Check head coach ---
    # Query the current coach from season_staff for this team.
    # If the Wikipedia coach differs, generate an update.
    if wiki_coach_col and pd.notna(wiki_row.get(wiki_coach_col)):
        new_coach = clean_wiki_text(wiki_row[wiki_coach_col])

        if new_coach:
            cursor.execute(
                "SELECT name FROM season_staff WHERE team_id = ? AND season = ? AND role = 'Head Coach'",
                (team_id, CURRENT_SEASON)
            )
            result = cursor.fetchone()
            old_coach = result[0] if result else None

            if old_coach is None:
                # No coach record exists yet — insert one
                print(f"  {label}: coach (empty) → {new_coach}")
                updates.append((
                    "INSERT INTO season_staff (season, team_id, role, name) VALUES (?, ?, ?, ?)",
                    (CURRENT_SEASON, team_id, 'Head Coach', new_coach)
                ))
            elif normalize(old_coach) != normalize(new_coach):
                # Coach has changed — update the existing record
                print(f"  {label}: coach '{old_coach}' → '{new_coach}'")
                updates.append((
                    "UPDATE season_staff SET name = ? WHERE team_id = ? AND season = ? AND role = 'Head Coach'",
                    (new_coach, team_id, CURRENT_SEASON)
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
