import sqlite3
import pandas as pd

# --- Connect to SQLite ---
# sqlite3.connect() does two things:
#   - If the file doesn't exist, it CREATES it
#   - If it does exist, it opens it
# So this one line gives us a brand-new database.
conn = sqlite3.connect("usl_championship.db")

# A "cursor" is how you send SQL commands to the database.
# Think of it like a pen — the connection opens the notebook,
# the cursor writes in it.
cursor = conn.cursor()

# SQLite doesn't enforce foreign keys by default (for backward
# compatibility). This turns that enforcement on, so if you try
# to insert a player_snap with a team_id that doesn't exist in
# the teams table, it'll reject it.
cursor.execute("PRAGMA foreign_keys = ON;")

print("Database created and connected.")
print(f"SQLite version: {sqlite3.sqlite_version}")

# --- Define the Schema ---
# cursor.executescript() lets us run multiple SQL statements at once.
# The triple-quoted string (""") is Python's way of writing multi-line
# strings — very handy for SQL.
#
# A few SQL concepts to note:
#   PRIMARY KEY   = unique identifier for each row; no duplicates allowed
#   FOREIGN KEY   = "this column's values must exist in that other table"
#   NOT NULL      = this column can't be left blank
#   INTEGER/TEXT/REAL = data types (whole number, text, decimal number)
#   IF NOT EXISTS = don't error if the table already exists (makes the
#                   script safe to re-run)

cursor.executescript("""

-- ============================================================
-- TIER 1: Reference tables (rarely change)
-- ============================================================

CREATE TABLE IF NOT EXISTS stadiums (
    stadium_id   INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    city         TEXT,
    capacity     INTEGER,
    surface      TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    team_id      INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    city         TEXT,
    abbreviation TEXT,
    conference   TEXT CHECK (conference IN ('E', 'W')),
    member_since INTEGER,
    stadium_id   INTEGER,
    FOREIGN KEY (stadium_id) REFERENCES stadiums(stadium_id)
);

-- Players as a pure reference table — no team assignment here,
-- because a player's team can change season to season.
CREATE TABLE IF NOT EXISTS players (
    player_id    INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    dob          DATE,
    nation       TEXT,
    position     TEXT,
    dom_foot     TEXT
);

-- ============================================================
-- TIER 2: Season-specific tables (change annually)
-- ============================================================

-- This replaces the team_id and jersey_2025 columns that were
-- on the players table, PLUS the captains_2025 column from teams.
-- One row per player per team per season.
CREATE TABLE IF NOT EXISTS season_rosters (
    season       INTEGER NOT NULL,
    team_id      INTEGER NOT NULL,
    player_id    INTEGER NOT NULL,
    jersey_number INTEGER,
    is_captain   INTEGER DEFAULT 0,   -- SQLite has no BOOLEAN; use 0/1
    PRIMARY KEY (season, team_id, player_id),
    FOREIGN KEY (team_id)   REFERENCES teams(team_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

-- Coaching staff, separated from the teams table so it can
-- change year to year without adding columns.
CREATE TABLE IF NOT EXISTS season_staff (
    season       INTEGER NOT NULL,
    team_id      INTEGER NOT NULL,
    role         TEXT NOT NULL,
    name         TEXT NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS season_team_stats (
    season             INTEGER NOT NULL,
    team_id            INTEGER NOT NULL,
    games_played       INTEGER,
    goals_for          INTEGER,
    goals_against      INTEGER,
    clean_sheets       INTEGER,
    possession_avg     REAL,
    avg_pass_accuracy  REAL,
    top_scorer_id      INTEGER,
    PRIMARY KEY (season, team_id),
    FOREIGN KEY (team_id)      REFERENCES teams(team_id),
    FOREIGN KEY (top_scorer_id) REFERENCES players(player_id)
);

-- ============================================================
-- TIER 3: Match-level tables (grow weekly)
-- ============================================================

CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY,
    date          DATE,
    home_team_id  INTEGER,
    away_team_id  INTEGER,
    home_score    INTEGER,
    away_score    INTEGER,
    competition   TEXT,
    stadium_id    INTEGER,
    weather       TEXT,
    attendance    INTEGER,
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (stadium_id)   REFERENCES stadiums(stadium_id)
);

CREATE TABLE IF NOT EXISTS appearances (
    match_id        INTEGER NOT NULL,
    player_id       INTEGER NOT NULL,
    team_id         INTEGER NOT NULL,
    minutes_played  INTEGER,
    is_starter      INTEGER,
    goals           INTEGER DEFAULT 0,
    shots           INTEGER,
    passes          INTEGER,
    assists         INTEGER DEFAULT 0,
    interceptions   INTEGER,
    duels_won       INTEGER,
    yellow_cards    INTEGER DEFAULT 0,
    red_cards       INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id)  REFERENCES matches(match_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id)   REFERENCES teams(team_id)
);

-- ============================================================
-- TIER 4: Snapshot ingestion layer
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_snapshots (
    snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id      INTEGER NOT NULL,
    snap_date    DATE NOT NULL,
    source_file  TEXT,
    ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS player_snaps (
    snap_date                    DATE NOT NULL,
    team_id                      INTEGER NOT NULL,
    player_id                    INTEGER NOT NULL,
    snapshot_id                  INTEGER,
    games_played                 INTEGER,
    mins_played                  INTEGER,
    starts                       INTEGER,
    subbed_on                    INTEGER,
    subbed_off                   INTEGER,
    goals_conceded               INTEGER,
    saves                        INTEGER,
    catches                      INTEGER,
    punches                      INTEGER,
    goals                        INTEGER,
    penalties                    INTEGER,
    mins_per_goal                REAL,
    shots_on_target              INTEGER,
    shooting_accuracy            REAL,
    successful_crosses           INTEGER,
    crossing_accuracy            REAL,
    assists                      INTEGER,
    key_passes                   INTEGER,
    penalties_won                INTEGER,
    offsides                     INTEGER,
    tackles_won                  INTEGER,
    tackles_success_rate         REAL,
    clearances                   INTEGER,
    blocks                       INTEGER,
    interceptions                INTEGER,
    successful_passes            INTEGER,
    passing_accuracy             REAL,
    pass_accuracy_opp_half       REAL,
    successful_dribbles          INTEGER,
    fouls_won                    INTEGER,
    fouls_conceded               INTEGER,
    penalties_conceded           INTEGER,
    yellow_cards                 INTEGER,
    red_cards                    INTEGER,
    PRIMARY KEY (snap_date, team_id, player_id),
    FOREIGN KEY (team_id)    REFERENCES teams(team_id),
    FOREIGN KEY (player_id)  REFERENCES players(player_id),
    FOREIGN KEY (snapshot_id) REFERENCES raw_snapshots(snapshot_id)
);

""")

# Let's verify the tables were created by querying SQLite's master table.
# sqlite_master is a built-in table that lists everything in the database.
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()
print(f"\nCreated {len(tables)} tables:")
for t in tables:
    print(f"  • {t[0]}")

# ================================================================
# DATA LOADING
# ================================================================
# Strategy: read each Excel file with pandas, clean it up, and use
# pandas' to_sql() method to insert rows into SQLite.
#
# Key pandas concepts:
#   pd.read_excel()  — reads an Excel file into a DataFrame
#   DataFrame        — a table in memory (rows and columns)
#   .rename()        — rename columns
#   .dropna()        — remove rows where everything is blank
#   .to_sql()        — write a DataFrame directly into a SQL table
#
# The tricky part with your files: most have a blank row 0 before
# the real header, and the columns are named "Unnamed: 0", etc.
# We handle that by using header=None and skiprows to get past it.

DATA_DIR = "."

# --- Helper function ---
# We'll reuse this pattern for every file, so let's make a function.
# A function is a reusable block of code you call by name.

def read_excel_clean(filename, skip=1):
    """
    Read an Excel file, skipping the junk rows at the top.
    
    Parameters:
        filename: name of the file in DATA_DIR
        skip: how many rows to skip before the header row
              (most of your files have 1 blank row to skip)
    
    Returns:
        A pandas DataFrame with clean column names.
    """
    path = f"{DATA_DIR}/{filename}"
    df = pd.read_excel(path, header=None, skiprows=skip)
    
    # Row 0 after skipping is the actual header row (column names).
    # We pull it out, set it as column names, then drop that row.
    df.columns = df.iloc[0]
    df = df.iloc[1:]          # Keep everything AFTER the header row
    df = df.reset_index(drop=True)  # Re-number rows from 0
    
    # Drop the unnamed index column if present (some files have it)
    first_col = df.columns[0]
    if first_col is None or pd.isna(first_col) or str(first_col).startswith('Unnamed'):
        df = df.iloc[:, 1:]   # Drop first column
    
    return df

# ================================================================
# LOAD STADIUMS (must go first — teams references it)
# ================================================================
print("\n--- Loading stadiums ---")
stadiums = read_excel_clean("stadiums.xlsx")
print(f"  Read {len(stadiums)} stadiums")
print(f"  Columns: {list(stadiums.columns)}")

# to_sql() is the pandas shortcut for inserting a whole DataFrame.
#   name        = target table name in SQLite
#   con         = our database connection
#   if_exists   = 'append' means add rows to the existing table
#                 (vs 'replace' which would DROP and recreate it,
#                  losing our carefully defined schema)
#   index=False = don't write pandas' row numbers as a column
stadiums.to_sql("stadiums", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(stadiums)} rows into stadiums")

# ================================================================
# LOAD TEAMS (split off season-specific columns)
# ================================================================
print("\n--- Loading teams ---")
teams_raw = read_excel_clean("teams.xlsx")
print(f"  Read {len(teams_raw)} teams")
print(f"  Columns: {list(teams_raw.columns)}")

# The raw teams table has columns we want to SPLIT OFF:
#   captains_2025 → goes into season_rosters (is_captain flag)
#   coach_2025    → goes into season_staff
#
# We'll handle those after loading the core team data.

# Select only the columns that belong in the clean teams table.
# This is pandas column selection: df[['col1', 'col2']] gives you
# a new DataFrame with just those columns.
teams_clean = teams_raw[['team_id', 'name', 'city', 'abbreviation',
                          'conference', 'member_since', 'stadium']].copy()

# Rename 'stadium' to 'stadium_id' to match our schema
teams_clean = teams_clean.rename(columns={'stadium': 'stadium_id'})

# Convert types — pandas may have read IDs as strings
teams_clean['team_id'] = teams_clean['team_id'].astype(int)
teams_clean['stadium_id'] = teams_clean['stadium_id'].astype(int)
teams_clean['member_since'] = teams_clean['member_since'].astype(int)

teams_clean.to_sql("teams", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(teams_clean)} rows into teams")

# --- Extract coaches into season_staff ---
# We iterate over each row of the original teams DataFrame.
# iterrows() gives us (index, row) pairs where row acts like
# a dictionary: row['column_name'] gets the value.
print("\n--- Extracting season_staff from teams ---")
staff_rows = []
for _, row in teams_raw.iterrows():
    if pd.notna(row.get('coach_2025')):
        staff_rows.append({
            'season': 2025,
            'team_id': int(row['team_id']),
            'role': 'Head Coach',
            'name': row['coach_2025']
        })

staff_df = pd.DataFrame(staff_rows)
staff_df.to_sql("season_staff", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(staff_df)} coaches into season_staff")

# ================================================================
# LOAD PLAYERS (split off team assignment + jersey into season_rosters)
# ================================================================
print("\n--- Loading players ---")
players_raw = read_excel_clean("players.xlsx")
# Same blank-row-0 format as the other files, so default skip=1 works.
print(f"  Read {len(players_raw)} players")
print(f"  Columns: {list(players_raw.columns)}")

# Clean players: just the permanent attributes
players_clean = players_raw[['player_id', 'name', 'dob', 'nation',
                              'position', 'dom_foot']].copy()
players_clean['player_id'] = players_clean['player_id'].astype(int)

# Convert date-of-birth to proper date strings.
# pandas reads Excel dates as Timestamps; SQLite wants 'YYYY-MM-DD'.
# pd.to_datetime() standardizes various date formats, then .dt.date
# extracts just the date portion.
players_clean['dob'] = pd.to_datetime(players_clean['dob'], errors='coerce').dt.date

# Drop any rows where the name is blank — these are empty/padding rows
# in the Excel file. .dropna(subset=['name']) removes rows where the
# 'name' column specifically is NaN/None.
players_clean = players_clean.dropna(subset=['name'])
print(f"  After removing blanks: {len(players_clean)} players")

players_clean.to_sql("players", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(players_clean)} rows into players")

# --- Build season_rosters ---
# This combines:
#   1. team_id + jersey_2025 from the players table (every player)
#   2. captains_2025 from the teams table (just the captains)
print("\n--- Building season_rosters ---")

roster_rows = []
for _, row in players_raw.iterrows():
    if pd.notna(row.get('team_id')):
        roster_rows.append({
            'season': 2025,
            'team_id': int(row['team_id']),
            'player_id': int(row['player_id']),
            'jersey_number': int(row['jersey_2025']) if pd.notna(row.get('jersey_2025')) else None,
            'is_captain': 0  # default; we'll update captains next
        })

roster_df = pd.DataFrame(roster_rows)

# Now flag captains. The teams table has a 'captains_2025' column
# that may list one or more names (comma-separated).
# We need to match these names back to player_ids.
#
# This is a common data task: "fuzzy matching" between two tables
# that don't share a key. We'll do a simple name-containment check.

# Build a lookup: player name → player_id (for name matching)
# .set_index() turns a column into the row labels (the index),
# then .to_dict() converts to {name: id} dictionary.
name_to_id = players_raw.set_index('name')['player_id'].to_dict()

captain_count = 0
for _, team_row in teams_raw.iterrows():
    captains_str = team_row.get('captains_2025')
    if pd.isna(captains_str):
        continue
    
    # Split on comma in case there are multiple captains
    captain_names = [c.strip() for c in str(captains_str).split(',')]
    team_id = int(team_row['team_id'])
    
    for cap_name in captain_names:
        # Search for a matching player on this team.
        # We check if the captain name appears IN the player's
        # "Last, First" formatted name. This handles slight
        # formatting differences.
        for player_name, pid in name_to_id.items():
            if player_name is None or cap_name is None:
                continue
            # Check both directions: "Phanuel Kavita" in "Kavita, Phanuel"
            # and vice versa
            cap_parts = cap_name.lower().split()
            player_lower = str(player_name).lower()
            if all(part in player_lower for part in cap_parts):
                # Verify this player is on the right team
                mask = (roster_df['player_id'] == int(pid)) & \
                       (roster_df['team_id'] == team_id)
                if mask.any():
                    roster_df.loc[mask, 'is_captain'] = 1
                    captain_count += 1
                    break

roster_df.to_sql("season_rosters", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(roster_df)} roster entries into season_rosters")
print(f"  ✓ Flagged {captain_count} captains")
print(f"  ⚠ Captain matching is approximate — review manually later")

# ================================================================
# LOAD MATCHES
# ================================================================
print("\n--- Loading matches ---")
matches_raw = read_excel_clean("matches.xlsx")
print(f"  Read {len(matches_raw)} matches")

# Select the columns matching our schema.
# Some columns may have mixed types (NaN for missing + numbers),
# so we convert carefully.
matches_clean = matches_raw[['match_id', 'date', 'home_team_id', 'away_team_id',
                              'home_score', 'away_score', 'competition',
                              'stadium_id', 'weather', 'attendance']].copy()

# pd.to_numeric() converts strings to numbers, with errors='coerce'
# turning anything unconvertible into NaN (rather than crashing).
for col in ['match_id', 'home_team_id', 'away_team_id', 'home_score',
            'away_score', 'stadium_id', 'attendance']:
    matches_clean[col] = pd.to_numeric(matches_clean[col], errors='coerce')

# Convert date column
matches_clean['date'] = pd.to_datetime(matches_clean['date'], errors='coerce').dt.date

# Drop any rows that don't have a valid match_id (guards against junk rows)
matches_clean = matches_clean.dropna(subset=['match_id'])
matches_clean['match_id'] = matches_clean['match_id'].astype(int)

# Filter out the header echo row if present (competition = 'competition')
matches_clean = matches_clean[matches_clean['competition'] != 'competition']

matches_clean.to_sql("matches", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(matches_clean)} matches")


# ================================================================
# LOAD APPEARANCES
# ================================================================
print("\n--- Loading appearances ---")
appearances_raw = read_excel_clean("appearances.xlsx")
print(f"  Read {len(appearances_raw)} appearance records")

appearances_clean = appearances_raw[['match_id', 'player_id', 'team_id',
    'minutes_played', 'is_starter', 'goals', 'shots', 'passes',
    'assists', 'interceptions', 'duels_won', 'yellow_cards', 'red_cards']].copy()

for col in appearances_clean.columns:
    if col not in ['is_starter']:  # keep is_starter as-is for now
        appearances_clean[col] = pd.to_numeric(appearances_clean[col], errors='coerce')

appearances_clean = appearances_clean.dropna(subset=['match_id', 'player_id'])
appearances_clean['match_id'] = appearances_clean['match_id'].astype(int)
appearances_clean['player_id'] = appearances_clean['player_id'].astype(int)
appearances_clean['team_id'] = appearances_clean['team_id'].astype(int)

appearances_clean.to_sql("appearances", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(appearances_clean)} appearance records")


# ================================================================
# LOAD PLAYER_SNAPS
# ================================================================
print("\n--- Loading player_snaps ---")
snaps_raw = read_excel_clean("player_snaps.xlsx")
print(f"  Read {len(snaps_raw)} snap records")
print(f"  Source columns: {list(snaps_raw.columns)}")

# Column mapping: Excel name → our schema name.
# A dictionary maps old names to new names. When column names don't
# match between source and target, explicit mapping prevents silent
# data misalignment — one of the most dangerous bugs in data work.
snap_column_map = {
    'snap_date':                          'snap_date',
    'team_id':                            'team_id',
    'player_id':                          'player_id',
    'games_played':                       'games_played',
    'mins_played':                        'mins_played',
    'starts':                             'starts',
    'subbed_on':                          'subbed_on',
    'subbed_off':                         'subbed_off',
    'goals_conceded':                     'goals_conceded',
    'saves':                              'saves',
    'catches':                            'catches',
    'punches':                            'punches',
    'goals':                              'goals',
    'penalties':                           'penalties',
    'mins_per_goal':                      'mins_per_goal',
    'shots_on_target':                    'shots_on_target',
    'shooting_accuracy':                  'shooting_accuracy',
    'successful_crosses':                 'successful_crosses',
    'crossing_accuracy':                  'crossing_accuracy',
    'assists':                            'assists',
    'key_passes':                         'key_passes',
    'penalties_won':                      'penalties_won',
    'offsides':                           'offsides',
    'tackles_won':                        'tackles_won',
    'tackles_success_rate':               'tackles_success_rate',
    'clearances':                         'clearances',
    'blocks':                             'blocks',
    'interceptions':                      'interceptions',
    'successful_passes':                  'successful_passes',
    'passing_accuracy':                   'passing_accuracy',
    'passing_accuracy_in_opponents_half': 'pass_accuracy_opp_half',
    'successful_dribbles':                'successful_dribbles',
    'fouls_won':                          'fouls_won',
    'fouls_conceded':                     'fouls_conceded',
    'penalties_conceded':                 'penalties_conceded',
    'yellow_cards':                       'yellow_cards',
    'red_cards':                          'red_cards',
}

# .rename(columns=...) applies the mapping to rename columns.
# We only keep the columns that appear in our mapping.
snaps_clean = snaps_raw.rename(columns=snap_column_map)
snaps_clean = snaps_clean[[v for v in snap_column_map.values()]].copy()

# Convert types
snaps_clean['snap_date'] = pd.to_datetime(snaps_clean['snap_date'], errors='coerce').dt.date
snaps_clean['team_id'] = pd.to_numeric(snaps_clean['team_id'], errors='coerce')
snaps_clean['player_id'] = pd.to_numeric(snaps_clean['player_id'], errors='coerce')

# Convert all numeric stat columns
for col in snaps_clean.columns:
    if col not in ['snap_date', 'team_id', 'player_id']:
        snaps_clean[col] = pd.to_numeric(snaps_clean[col], errors='coerce')

snaps_clean = snaps_clean.dropna(subset=['snap_date', 'team_id', 'player_id'])
snaps_clean['team_id'] = snaps_clean['team_id'].astype(int)
snaps_clean['player_id'] = snaps_clean['player_id'].astype(int)

# Check for any player_ids that don't exist in our players table.
# This is what foreign keys protect against — let's preview the
# problem before hitting the constraint.
cursor.execute("SELECT player_id FROM players")
valid_player_ids = {row[0] for row in cursor.fetchall()}
orphan_mask = ~snaps_clean['player_id'].isin(valid_player_ids)
orphan_count = orphan_mask.sum()
if orphan_count > 0:
    print(f"  ⚠ {orphan_count} snap rows reference player_ids not in players table")
    print(f"    Orphan IDs: {sorted(snaps_clean.loc[orphan_mask, 'player_id'].unique())}")
    # Remove orphans so the insert succeeds
    snaps_clean = snaps_clean[~orphan_mask]

# De-duplicate: if the same player appears twice for the same date
# and team, keep only the last occurrence. .drop_duplicates() with
# keep='last' does this. This happens when snapshot data has
# overlapping entries.
before_dedup = len(snaps_clean)
snaps_clean = snaps_clean.drop_duplicates(
    subset=['snap_date', 'team_id', 'player_id'], keep='last'
)
dupes_removed = before_dedup - len(snaps_clean)
if dupes_removed > 0:
    print(f"  ⚠ Removed {dupes_removed} duplicate rows")

snaps_clean.to_sql("player_snaps", conn, if_exists="append", index=False)
print(f"  ✓ Loaded {len(snaps_clean)} snap records")
print(f"    Teams covered: {sorted(snaps_clean['team_id'].unique())}")
print(f"    Date range: {snaps_clean['snap_date'].min()} to {snaps_clean['snap_date'].max()}")

# ================================================================
# CREATE VIEWS
# ================================================================
# A view is a saved query. It doesn't store data — it runs the
# query every time you SELECT from it. This means it's always
# up to date, unlike a separate table you'd have to maintain.

print("\n--- Creating views ---")

cursor.executescript("""

-- player_summaries: latest snapshot for each player
-- This replaces the empty player_summaries table entirely.
-- The subquery finds the max snap_date per player, then we
-- join back to get the full row.
CREATE VIEW IF NOT EXISTS v_player_summaries AS
SELECT ps.*
FROM player_snaps ps
INNER JOIN (
    SELECT player_id, MAX(snap_date) as max_date
    FROM player_snaps
    GROUP BY player_id
) latest ON ps.player_id = latest.player_id
       AND ps.snap_date = latest.max_date;

-- current_rosters: players on each team right now (2025)
-- Joins players, season_rosters, and teams for a convenient
-- "who's on which team" lookup.
CREATE VIEW IF NOT EXISTS v_current_rosters AS
SELECT
    sr.season,
    t.name AS team_name,
    t.abbreviation,
    p.player_id,
    p.name AS player_name,
    p.position,
    sr.jersey_number,
    sr.is_captain
FROM season_rosters sr
JOIN players p ON sr.player_id = p.player_id
JOIN teams t ON sr.team_id = t.team_id
WHERE sr.season = 2025
ORDER BY t.name, sr.jersey_number;

-- standings: win/draw/loss record derived from matches
CREATE VIEW IF NOT EXISTS v_standings AS
SELECT
    t.team_id,
    t.name,
    t.conference,
    COUNT(*) AS played,
    SUM(CASE
        WHEN (m.home_team_id = t.team_id AND m.home_score > m.away_score)
          OR (m.away_team_id = t.team_id AND m.away_score > m.home_score)
        THEN 1 ELSE 0 END) AS wins,
    SUM(CASE
        WHEN m.home_score = m.away_score THEN 1 ELSE 0 END) AS draws,
    SUM(CASE
        WHEN (m.home_team_id = t.team_id AND m.home_score < m.away_score)
          OR (m.away_team_id = t.team_id AND m.away_score < m.home_score)
        THEN 1 ELSE 0 END) AS losses,
    SUM(CASE
        WHEN m.home_team_id = t.team_id THEN m.home_score
        ELSE m.away_score END) AS goals_for,
    SUM(CASE
        WHEN m.home_team_id = t.team_id THEN m.away_score
        ELSE m.home_score END) AS goals_against,
    SUM(CASE
        WHEN (m.home_team_id = t.team_id AND m.home_score > m.away_score)
          OR (m.away_team_id = t.team_id AND m.away_score > m.home_score)
        THEN 3
        WHEN m.home_score = m.away_score THEN 1
        ELSE 0 END) AS points
FROM teams t
JOIN matches m ON t.team_id = m.home_team_id OR t.team_id = m.away_team_id
WHERE m.competition = 'League'
GROUP BY t.team_id
ORDER BY points DESC, goals_for - goals_against DESC;

""")

# List the views we just created
cursor.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name;")
views = cursor.fetchall()
print(f"Created {len(views)} views:")
for v in views:
    print(f"  • {v[0]}")

# ================================================================
# VALIDATION SUMMARY
# ================================================================
print("\n" + "=" * 60)
print("MIGRATION SUMMARY")
print("=" * 60)

# Query each table's row count. This is a common sanity check —
# after any data load, verify the counts match expectations.
cursor.execute("""
    SELECT name FROM sqlite_master
    WHERE type='table' AND name != 'sqlite_sequence'
    ORDER BY name
""")
for (table_name,) in cursor.fetchall():
    cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    count = cursor.fetchone()[0]
    status = "✓" if count > 0 else "○ (empty)"
    print(f"  {status} {table_name}: {count} rows")

# Test a view to make sure it works
cursor.execute("SELECT COUNT(*) FROM v_player_summaries")
summary_count = cursor.fetchone()[0]
print(f"\n  View test — v_player_summaries returns {summary_count} players")

cursor.execute("SELECT COUNT(*) FROM v_standings")
standings_count = cursor.fetchone()[0]
print(f"  View test — v_standings returns {standings_count} teams")

# Quick sample query: top 5 scorers
print("\n  Sample query — Top 5 goal scorers (from latest snapshots):")
cursor.execute("""
    SELECT p.name, t.abbreviation, ps.goals, ps.assists, ps.games_played
    FROM v_player_summaries ps
    JOIN players p ON ps.player_id = p.player_id
    JOIN teams t ON ps.team_id = t.team_id
    WHERE ps.goals > 0
    ORDER BY ps.goals DESC
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"    {row[0]} ({row[1]}): {row[2]}G {row[3]}A in {row[4]} games")


# ================================================================
# COMMIT AND CLOSE
# ================================================================
# CRITICAL: conn.commit() saves everything to disk. Without this,
# all the work above would be lost when the script ends. SQLite
# (and most databases) use "transactions" — changes are provisional
# until you commit them. This is a safety feature: if something
# goes wrong mid-script, nothing is half-written.
conn.commit()
conn.close()

print("\n✓ Database saved to: usl_championship.db")
print("  Open it with: sqlite3 usl_championship.db")
print("  Or connect from Python: sqlite3.connect('usl_championship.db')")