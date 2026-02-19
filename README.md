# USL Championship Database

A relational database and ingestion pipeline for tracking players, teams, matches, and performance statistics across the USL Championship soccer league.

## About

The USL Championship is the second division of men's professional soccer in the United States. This project collects and organizes season data — rosters, match results, and individual player statistics — into a normalized SQLite database designed for analysis. The data is sourced from the USL Championship website, where team-level player stat pages are captured as periodic snapshots throughout the season.

The raw website snapshots come in a transposed Excel format (players as columns, stat categories as rows), which makes direct analysis cumbersome. This project's core contribution is a migration pipeline that reshapes, validates, and loads that data into a properly structured relational database with enforced foreign keys, composite primary keys, and prebuilt SQL views for common queries.

## Database Schema

The database is organized into four tiers based on how frequently the data changes.

**Reference tables** store master data that rarely changes: `teams` (24 USL Championship clubs), `stadiums` (home venues), and `players` (biographical info like name, nationality, position, and date of birth). These tables contain no season-specific information, so they don't need to be restructured year over year.

**Season-specific tables** capture things that change annually. `season_rosters` tracks which players are on which teams in a given year, along with jersey numbers and captain designations. `season_staff` records coaching assignments. `season_team_stats` holds aggregate team-level numbers like goals for/against and possession averages. This separation means adding a new season is just inserting new rows — no schema changes required.

**Match-level tables** grow weekly during the season. `matches` stores results, venues, and attendance for each game. `appearances` records per-player per-match statistics (minutes played, goals, assists, cards, etc.) at the most granular level available.

**Snapshot tables** form the ingestion layer. `raw_snapshots` catalogs every website snapshot file that has been collected, tracking the source team, capture date, and when it was ingested. `player_snaps` holds the cumulative player statistics extracted from those snapshots — 34 stat columns covering everything from goals and assists to passing accuracy in the opponent's half.

Three SQL views are defined on top of these tables: `v_player_summaries` returns the latest snapshot for each player (replacing the need for a separate summary table), `v_current_rosters` joins players, rosters, and teams into a convenient lookup, and `v_standings` computes a full league table (wins, draws, losses, points) directly from match results.

### Entity Relationships

```
stadiums ←── teams ──→ season_staff
                │
                ├──→ season_rosters ←── players
                │                          │
                ├──→ matches               ├──→ appearances
                │                          │
                └──→ season_team_stats     └──→ player_snaps ──→ raw_snapshots
```

## Data Collection

The USL Championship website uses SportsEngine to render its statistics pages. Individual player stats are only available by selecting up to six players at a time and iterating through category tabs (Summary, Attacking, Defending, etc.) to build a complete stat line. The data loads dynamically via JavaScript and does not expose a stable API, which rules out conventional web scraping with tools like `requests` and `BeautifulSoup`.

To work around this, data collection uses Java `Robot` programs that automate the mouse and keyboard movements needed to select players, switch tabs, copy the rendered tables, and paste them into a preloaded Excel sheet. This produces one raw snapshot file per team per collection date.

### Collection programs

`USLCollect.java` handles a single team's stat page. It clicks through the category tabs in sequence, selecting and copying the stat table from each tab into an open Excel sheet. The copy targets are hardcoded pixel coordinates calibrated to a fullscreen browser window, and tab navigation uses the SportsEngine layout's fixed tab positions. Each run produces one transposed snapshot file where stat categories are rows and players are columns.

`USLRepop.java` handles the player-selection step that precedes collection. SportsEngine requires choosing which players to analyze from a dropdown, up to six at a time. This program accepts a "drop downs" count as a command-line argument (the number of presses needed to reach the next unselected player in the dropdown), then clicks through five selection slots to populate the comparison view. Once players are loaded, `USLCollect` can run to extract their stats.

`USLPosition.java` is a positioning utility. It reports the current mouse coordinates so that pixel targets in the other two programs can be recalibrated when screen resolution or browser layout changes.

### Collection workflow

A typical collection session for one team goes:

1. Open the team's USL Championship stats page in a fullscreen browser and an empty Excel sheet side by side.
2. Run `USLRepop` with the appropriate dropdown offset to select the first batch of up to six players.
3. Run `USLCollect` to copy each tab's stats into the Excel sheet.
4. Repeat steps 2–3 for remaining batches until all rostered players are captured.
5. Save the Excel file as `{team_id}_{MMDDYY}.xlsx` (e.g., `123_81625.xlsx` for team 123, captured August 16, 2025).

The resulting file is a raw transposed snapshot: row 1 contains player names (formatted as `"Name\nTeam"`), and rows 2+ contain one stat category per row with values across the player columns.

## Migration Pipeline

The `migration.py` script handles the full migration from raw Excel files to a populated SQLite database in a single run. It is written in Python using `pandas` for Excel I/O and the standard library `sqlite3` module for database operations.

### What it does

1. **Creates the SQLite database** with all 10 tables, enforcing foreign key constraints, `CHECK` constraints (e.g., conference must be `E` or `W`), and composite primary keys.

2. **Reads each source Excel file** using a helper function that handles the formatting quirks present in the raw data — blank header rows, unnamed index columns, and inconsistent type encoding.

3. **Splits season-specific data out of reference tables.** The original Excel files stored coaches and captains as columns on the teams table (`coach_2025`, `captains_2025`) and team/jersey assignments on the players table (`team_id`, `jersey_2025`). The migration extracts these into `season_staff` and `season_rosters` respectively, so the reference tables stay clean across seasons.

4. **Matches captain names to player IDs** by performing a fuzzy name lookup between the comma-separated captain strings in the teams file and the "Last, First" formatted names in the players file.

5. **Validates referential integrity before inserting.** For tables like `player_snaps` that reference `player_id`, the script pre-checks for orphaned foreign keys and removes them with a warning rather than failing mid-insert.

6. **Deduplicates** rows that share a composite primary key, keeping the last occurrence.

7. **Creates SQL views** for player summaries, current rosters, and league standings.

8. **Prints a validation summary** with row counts for every table and a sample query (top scorers) to confirm the views are functional.

### Running it

The script requires Python 3 with `pandas` and `openpyxl`:

```bash
pip install pandas openpyxl
```

Place `migration.py` in the same directory as the source Excel files, update the two path variables at the top of the script to match your local setup, and run:

```bash
python migration.py
```

This produces a `usl_championship.db` file that can be queried with any SQLite client, connected to from Python (`sqlite3.connect()`), or opened in tools like DB Browser for SQLite, Tableau, or R.

### Source files

| File | Contents |
|---|---|
| `teams.xlsx` | 24 clubs with city, conference, stadium, coach, and captain info |
| `stadiums.xlsx` | Venue names and cities (capacity and surface TBD) |
| `players.xlsx` | 604 players with biographical data and 2025 team assignments |
| `matches.xlsx` | 64 league matches with scores and venue |
| `appearances.xlsx` | Per-player per-match stats (31 records across 2 matches) |
| `player_snaps.xlsx` | Cumulative season stats for 444 player-snapshots across 17 teams |
| `season_team_stats.xlsx` | Schema defined, not yet populated |
| `{team_id}_{MMDDYY}.xlsx` | Raw USL website snapshots (transposed format) |

## Wikipedia Enrichment

The `wiki_scrape.py` script supplements the database with reference data from the [USL Championship Wikipedia page](https://en.wikipedia.org/wiki/USL_Championship). It pulls team and stadium information — capacity, surface type, head coach — that isn't available from the USL website's stats pages, and compares it against existing database records to generate targeted updates.

The script runs in two modes: preview mode (the default) prints what would change without touching the database, and `--update` mode applies the changes. It uses `pd.read_html()` to extract all tables from the Wikipedia page, scores each table against keyword sets to auto-detect the one containing team and stadium data, then walks each row to match against the database using normalized team name or city as a fallback.

For matched teams, the script checks capacity, surface, stadium name, and head coach against their current database values and generates `UPDATE` statements for anything that has changed or was previously empty. For unmatched rows — typically expansion teams not yet in the database — it generates `INSERT` statements for a new stadium, team, and coach record with auto-assigned IDs. Abbreviations for new teams are left blank and flagged for manual entry.

```bash
python wiki_scrape.py             # Preview changes
python wiki_scrape.py --update    # Apply changes to database
```

Requires `requests`, `beautifulsoup4`, and `lxml` in addition to `pandas`:

```bash
pip install requests beautifulsoup4 lxml
```

## Current Coverage

The database currently contains 2025 season data through mid-July, with player snapshots covering 17 of 24 teams. Match results, appearance records, and snapshot coverage are being expanded on an ongoing basis.

## Next Steps

The immediate priority is getting the database to a state where league-wide analysis can begin in R. The steps below are ordered by impact on that goal.

### 1. Build a snapshot ETL script

There is currently a manual gap between the raw transposed snapshot files produced by the Java Robots and the `player_snaps.xlsx` file that `migration.py` loads. A new `snapshot_etl.py` script will close this gap by reading raw snapshot files directly, transposing them into player-per-row format, matching player names to IDs in the database, and inserting the results into `player_snaps` and `raw_snapshots`. This is the single highest-value automation target in the project.

The script will scan a `raw_snapshots/` staging directory for any `{team_id}_{MMDDYY}.xlsx` files that haven't already been ingested (by checking the `raw_snapshots` table), parse the transposed format, and load them in one pass. Name matching will reuse the same fuzzy logic currently in `migration.py` for captain matching.

### 2. Extract shared utilities

`migration.py` and `wiki_scrape.py` both contain overlapping logic — the `normalize()` function for fuzzy name matching, Excel reading helpers, and similar cleanup patterns. These will be factored into a `utils.py` module that all three ingestion scripts import from. This also establishes a single source of truth for how player names are matched and stat columns are normalized, which matters as the database grows.

Planned project layout:

```
project/
├── utils.py              # normalize(), fuzzy_match_name(), read_excel_clean()
├── migration.py          # Full rebuild from Excel → DB (imports utils)
├── wiki_scrape.py        # Wikipedia enrichment (imports utils)
├── snapshot_etl.py       # Raw snapshot → player_snaps (imports utils)
├── raw_snapshots/        # Staging directory for Java Robot output
├── USLCollect.java       # Stat table collection automation
├── USLRepop.java         # Player selection automation
├── USLPosition.java      # Mouse coordinate utility
└── usl_championship.db
```

### 3. Complete league-wide snapshot coverage

Finish collecting snapshots for the remaining 7 of 24 teams. A full league cross-section at a single point in time is the minimum needed for meaningful comparative analysis — position-level stat distributions, team style profiles, and league-wide rankings.

Once all 24 teams have at least one snapshot, take a second round of snapshots for the 17 teams already collected. Two time points per team unlocks delta analysis: which players are improving, which teams are trending up or down, and how cumulative stats evolve over the season.

### 4. Backfill match results

Match scores can be collected from the USL schedule page or Wikipedia without the Robot workflow. Expanding the `matches` table to cover the full season will make the `v_standings` view functional and enable results-based analysis (home/away splits, goal distributions, form streaks) alongside the snapshot data.

### 5. Make migration.py incremental

The migration script currently does a full rebuild each run. As the database accumulates more snapshot data, it will need to support incremental loading — using `INSERT OR IGNORE` to skip existing records, checking which snapshots are already loaded before re-inserting, and separating schema creation from data loading so either can run independently.

### 6. Derive season_team_stats from existing data

Rather than populating `season_team_stats` manually, compute team-level aggregates from match results (goals for/against, clean sheets) and player snapshots (possession averages, pass accuracy) using a SQL script or a Python post-processing step. This keeps the table in sync with the underlying data and eliminates a manual maintenance burden.

## Tools

- **Python 3** with `pandas`, `openpyxl`, and `sqlite3` — data transformation and database operations
- **Java** (`java.awt.Robot`) — screen automation for USL website stat collection
- **SQLite** — storage and querying
- **R** — planned analysis environment (next phase)
- Source data from [USL Championship](https://www.uslchampionship.com/) and [Wikipedia](https://en.wikipedia.org/wiki/USL_Championship)
