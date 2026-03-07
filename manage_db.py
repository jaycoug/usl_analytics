#!/usr/bin/env python3
"""
manage_db.py — CLI for adding and deleting players and teams in a USL analytics SQLite database.

Usage:
    python3 manage_db.py --db <path> <command> [options]

Run with --help or <command> --help for details.
"""

import argparse
import sqlite3
import sys


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def connect(db_path):
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        print(f"Error: Could not open database at '{db_path}': {e}")
        sys.exit(1)


def fetch_one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def confirm(prompt):
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer == "y"


# ---------------------------------------------------------------------------
# add-player
# ---------------------------------------------------------------------------

def cmd_add_player(args):
    # Validate: season and team-id must be provided together
    if (args.team_id is None) != (args.season is None):
        print("Error: --team-id and --season must be provided together.")
        sys.exit(1)

    conn = connect(args.db)
    add_roster = args.team_id is not None

    if add_roster:
        team = fetch_one(conn, "SELECT name FROM teams WHERE team_id = ?", (args.team_id,))
        if not team:
            print(f"Error: No team found with team_id {args.team_id}.")
            conn.close()
            sys.exit(1)

    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO players (name, dob, nation, position, dom_foot) VALUES (?, ?, ?, ?, ?)",
                (args.name, args.dob, args.nation, args.position, args.dom_foot),
            )
            player_id = cur.lastrowid
            print(f"Added player '{args.name}' with player_id {player_id}.")

            if add_roster:
                conn.execute(
                    "INSERT INTO season_rosters "
                    "(season, team_id, player_id, jersey_number, is_captain) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (args.season, args.team_id, player_id, args.jersey),
                )
                print(
                    f"Added to {args.season} roster for team_id {args.team_id}"
                    + (f" (jersey #{args.jersey})" if args.jersey else "") + "."
                )
    except sqlite3.IntegrityError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# delete-player
# ---------------------------------------------------------------------------

def cmd_delete_player(args):
    conn = connect(args.db)

    row = fetch_one(conn, "SELECT name FROM players WHERE player_id = ?", (args.player_id,))
    if not row:
        print(f"Error: No player found with player_id {args.player_id}.")
        conn.close()
        sys.exit(1)

    name = row[0]
    roster_count     = fetch_one(conn, "SELECT COUNT(*) FROM season_rosters    WHERE player_id = ?", (args.player_id,))[0]
    appearance_count = fetch_one(conn, "SELECT COUNT(*) FROM appearances        WHERE player_id = ?", (args.player_id,))[0]
    snap_count       = fetch_one(conn, "SELECT COUNT(*) FROM player_snaps      WHERE player_id = ?", (args.player_id,))[0]
    top_scorer_count = fetch_one(conn, "SELECT COUNT(*) FROM season_team_stats WHERE top_scorer_id = ?", (args.player_id,))[0]

    print(f"Player to delete: '{name}' (player_id {args.player_id})")
    print(f"  season_rosters rows:   {roster_count}")
    print(f"  appearances rows:      {appearance_count}")
    print(f"  player_snaps rows:     {snap_count}")
    print(f"  top_scorer references: {top_scorer_count}  (will be set to NULL)")

    if not args.yes and not confirm("Permanently delete this player and all related records?"):
        print("Aborted.")
        conn.close()
        return

    try:
        with conn:
            conn.execute("DELETE FROM season_rosters    WHERE player_id = ?",          (args.player_id,))
            conn.execute("DELETE FROM appearances        WHERE player_id = ?",          (args.player_id,))
            conn.execute("DELETE FROM player_snaps      WHERE player_id = ?",          (args.player_id,))
            conn.execute("UPDATE season_team_stats SET top_scorer_id = NULL WHERE top_scorer_id = ?", (args.player_id,))
            conn.execute("DELETE FROM players           WHERE player_id = ?",          (args.player_id,))
        print(f"Deleted player '{name}' (player_id {args.player_id}) and all related records.")
    except sqlite3.Error as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# add-team
# ---------------------------------------------------------------------------

def cmd_add_team(args):
    conn = connect(args.db)

    if args.stadium_id is not None:
        stadium = fetch_one(conn, "SELECT name FROM stadiums WHERE stadium_id = ?", (args.stadium_id,))
        if not stadium:
            print(f"Error: No stadium found with stadium_id {args.stadium_id}.")
            conn.close()
            sys.exit(1)

    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO teams (name, city, abbreviation, conference, member_since, stadium_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (args.name, args.city, args.abbr, args.conference, args.member_since, args.stadium_id),
            )
            team_id = cur.lastrowid
            print(f"Added team '{args.name}' with team_id {team_id}.")
    except sqlite3.IntegrityError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# delete-team
# ---------------------------------------------------------------------------

def cmd_delete_team(args):
    conn = connect(args.db)

    row = fetch_one(conn, "SELECT name FROM teams WHERE team_id = ?", (args.team_id,))
    if not row:
        print(f"Error: No team found with team_id {args.team_id}.")
        conn.close()
        sys.exit(1)

    name = row[0]
    roster_count     = fetch_one(conn, "SELECT COUNT(*) FROM season_rosters  WHERE team_id = ?",      (args.team_id,))[0]
    appearance_count = fetch_one(conn, "SELECT COUNT(*) FROM appearances      WHERE team_id = ?",      (args.team_id,))[0]
    snap_count       = fetch_one(conn, "SELECT COUNT(*) FROM player_snaps    WHERE team_id = ?",      (args.team_id,))[0]
    snapshot_count   = fetch_one(conn, "SELECT COUNT(*) FROM raw_snapshots   WHERE team_id = ?",      (args.team_id,))[0]
    stats_count      = fetch_one(conn, "SELECT COUNT(*) FROM season_team_stats WHERE team_id = ?",    (args.team_id,))[0]
    staff_count      = fetch_one(conn, "SELECT COUNT(*) FROM season_staff    WHERE team_id = ?",      (args.team_id,))[0]
    home_count       = fetch_one(conn, "SELECT COUNT(*) FROM matches         WHERE home_team_id = ?", (args.team_id,))[0]
    away_count       = fetch_one(conn, "SELECT COUNT(*) FROM matches         WHERE away_team_id = ?", (args.team_id,))[0]

    print(f"Team to delete: '{name}' (team_id {args.team_id})")
    print(f"  season_rosters rows:   {roster_count}")
    print(f"  appearances rows:      {appearance_count}")
    print(f"  player_snaps rows:     {snap_count}")
    print(f"  raw_snapshots rows:    {snapshot_count}")
    print(f"  season_team_stats:     {stats_count}")
    print(f"  season_staff rows:     {staff_count}")
    print(f"  matches (home):        {home_count}  (home_team_id will be set to NULL)")
    print(f"  matches (away):        {away_count}  (away_team_id will be set to NULL)")

    if not args.yes and not confirm("Permanently delete this team and all related records?"):
        print("Aborted.")
        conn.close()
        return

    try:
        with conn:
            conn.execute("DELETE FROM season_rosters   WHERE team_id = ?",      (args.team_id,))
            conn.execute("DELETE FROM appearances       WHERE team_id = ?",      (args.team_id,))
            conn.execute("DELETE FROM player_snaps     WHERE team_id = ?",      (args.team_id,))
            conn.execute("DELETE FROM raw_snapshots    WHERE team_id = ?",      (args.team_id,))
            conn.execute("DELETE FROM season_team_stats WHERE team_id = ?",     (args.team_id,))
            conn.execute("DELETE FROM season_staff     WHERE team_id = ?",      (args.team_id,))
            conn.execute("UPDATE matches SET home_team_id = NULL WHERE home_team_id = ?", (args.team_id,))
            conn.execute("UPDATE matches SET away_team_id = NULL WHERE away_team_id = ?", (args.team_id,))
            conn.execute("DELETE FROM teams            WHERE team_id = ?",      (args.team_id,))
        print(f"Deleted team '{name}' (team_id {args.team_id}) and all related records.")
    except sqlite3.Error as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# add-roster
# ---------------------------------------------------------------------------

def cmd_add_roster(args):
    conn = connect(args.db)

    player = fetch_one(conn, "SELECT name FROM players WHERE player_id = ?", (args.player_id,))
    if not player:
        print(f"Error: No player found with player_id {args.player_id}.")
        conn.close()
        sys.exit(1)

    team = fetch_one(conn, "SELECT name FROM teams WHERE team_id = ?", (args.team_id,))
    if not team:
        print(f"Error: No team found with team_id {args.team_id}.")
        conn.close()
        sys.exit(1)

    try:
        with conn:
            conn.execute(
                "INSERT INTO season_rosters "
                "(season, team_id, player_id, jersey_number, is_captain) "
                "VALUES (?, ?, ?, ?, ?)",
                (args.season, args.team_id, args.player_id, args.jersey, 1 if args.captain else 0),
            )
        print(
            f"Added '{player[0]}' to {args.season} roster for '{team[0]}'"
            + (f" (jersey #{args.jersey})" if args.jersey else "")
            + (" [captain]" if args.captain else "") + "."
        )
    except sqlite3.IntegrityError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# remove-roster
# ---------------------------------------------------------------------------

def cmd_remove_roster(args):
    conn = connect(args.db)

    row = fetch_one(
        conn,
        "SELECT p.name, t.name FROM season_rosters sr "
        "JOIN players p ON p.player_id = sr.player_id "
        "JOIN teams   t ON t.team_id   = sr.team_id "
        "WHERE sr.player_id = ? AND sr.team_id = ? AND sr.season = ?",
        (args.player_id, args.team_id, args.season),
    )
    if not row:
        print(
            f"Error: No roster entry found for player_id {args.player_id}, "
            f"team_id {args.team_id}, season {args.season}."
        )
        conn.close()
        sys.exit(1)

    player_name, team_name = row

    if not args.yes and not confirm(
        f"Remove '{player_name}' from '{team_name}' {args.season} roster?"
    ):
        print("Aborted.")
        conn.close()
        return

    with conn:
        conn.execute(
            "DELETE FROM season_rosters WHERE player_id = ? AND team_id = ? AND season = ?",
            (args.player_id, args.team_id, args.season),
        )
    print(f"Removed '{player_name}' from '{team_name}' {args.season} roster.")
    conn.close()


# ---------------------------------------------------------------------------
# list-players
# ---------------------------------------------------------------------------

def cmd_list_players(args):
    conn = connect(args.db)

    if args.team_id is not None:
        if args.season is not None:
            sql = (
                "SELECT p.player_id, p.name, p.position, sr.jersey_number, sr.season, t.name "
                "FROM players p "
                "JOIN season_rosters sr ON p.player_id = sr.player_id "
                "JOIN teams t ON t.team_id = sr.team_id "
                "WHERE sr.team_id = ? AND sr.season = ? ORDER BY p.name"
            )
            rows = conn.execute(sql, (args.team_id, args.season)).fetchall()
            header = f"Players — team_id {args.team_id}, season {args.season}"
        else:
            sql = (
                "SELECT p.player_id, p.name, p.position, sr.jersey_number, sr.season, t.name "
                "FROM players p "
                "JOIN season_rosters sr ON p.player_id = sr.player_id "
                "JOIN teams t ON t.team_id = sr.team_id "
                "WHERE sr.team_id = ? ORDER BY sr.season, p.name"
            )
            rows = conn.execute(sql, (args.team_id,)).fetchall()
            header = f"Players — team_id {args.team_id} (all seasons)"
        col_headers = ("ID", "Name", "Position", "Jersey", "Season", "Team")
    else:
        sql = "SELECT player_id, name, position, dob, nation FROM players ORDER BY name"
        rows = conn.execute(sql).fetchall()
        header = "All players"
        col_headers = ("ID", "Name", "Position", "DOB", "Nation")

    print(f"\n{header}")
    print("-" * 72)
    widths = [6, 24, 10, 8, 8, 20]
    print("  ".join(f"{h:<{w}}" for h, w in zip(col_headers, widths)))
    print("-" * 72)
    for row in rows:
        print("  ".join(f"{str(v) if v is not None else '':<{w}}" for v, w in zip(row, widths)))
    print(f"\n{len(rows)} row(s).")
    conn.close()


# ---------------------------------------------------------------------------
# list-teams
# ---------------------------------------------------------------------------

def cmd_list_teams(args):
    conn = connect(args.db)
    sql = (
        "SELECT team_id, name, abbreviation, city, conference, member_since "
        "FROM teams ORDER BY name"
    )
    rows = conn.execute(sql).fetchall()

    print("\nAll teams")
    print("-" * 72)
    print(f"{'ID':<6}  {'Name':<28}  {'Abbr':<6}  {'City':<18}  {'Conf':<5}  Since")
    print("-" * 72)
    for team_id, name, abbr, city, conf, since in rows:
        print(
            f"{team_id:<6}  {name:<28}  {(abbr or ''):<6}  "
            f"{(city or ''):<18}  {(conf or ''):<5}  {since or ''}"
        )
    print(f"\n{len(rows)} team(s).")
    conn.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="manage_db.py",
        description="Add and delete players and teams in a USL analytics SQLite database.",
    )
    parser.add_argument(
        "--db", required=True, metavar="PATH",
        help="Path to the SQLite database file.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── add-player ──────────────────────────────────────────────────────────
    p = sub.add_parser("add-player", help="Add a new player (optionally to a season roster).")
    p.add_argument("--name",      required=True, help="Player name, format: 'Last, First'.")
    p.add_argument("--position",  help="Position abbreviation (e.g. GK, DEF, MID, FWD).")
    p.add_argument("--dob",       help="Date of birth in YYYY-MM-DD format.")
    p.add_argument("--nation",    help="Nationality / country code.")
    p.add_argument("--dom-foot",  dest="dom_foot", help="Dominant foot (L or R).")
    p.add_argument("--team-id",   dest="team_id", type=int,
                   help="team_id to add player to a season roster (requires --season).")
    p.add_argument("--season",    type=int,
                   help="Season year for the roster entry (requires --team-id).")
    p.add_argument("--jersey",    type=int, help="Jersey number for the roster entry.")

    # ── delete-player ───────────────────────────────────────────────────────
    p = sub.add_parser("delete-player", help="Delete a player and all their related records.")
    p.add_argument("--player-id", dest="player_id", required=True, type=int,
                   help="player_id of the player to delete.")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    # ── add-team ────────────────────────────────────────────────────────────
    p = sub.add_parser("add-team", help="Add a new team.")
    p.add_argument("--name",         required=True, help="Full team name.")
    p.add_argument("--city",         help="City.")
    p.add_argument("--abbr",         help="Abbreviation (e.g. LOU, TBF).")
    p.add_argument("--conference",   choices=["E", "W"], help="Conference: E or W.")
    p.add_argument("--member-since", dest="member_since", type=int,
                   help="Year the team joined the league.")
    p.add_argument("--stadium-id",   dest="stadium_id", type=int,
                   help="stadium_id from the stadiums table.")

    # ── delete-team ─────────────────────────────────────────────────────────
    p = sub.add_parser("delete-team", help="Delete a team and all their related records.")
    p.add_argument("--team-id", dest="team_id", required=True, type=int,
                   help="team_id of the team to delete.")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    # ── add-roster ──────────────────────────────────────────────────────────
    p = sub.add_parser("add-roster", help="Add an existing player to a season roster.")
    p.add_argument("--player-id", dest="player_id", required=True, type=int)
    p.add_argument("--team-id",   dest="team_id",   required=True, type=int)
    p.add_argument("--season",    required=True, type=int)
    p.add_argument("--jersey",    type=int, help="Jersey number.")
    p.add_argument("--captain",   action="store_true", help="Mark as team captain.")

    # ── remove-roster ───────────────────────────────────────────────────────
    p = sub.add_parser("remove-roster",
                       help="Remove a player from a specific season roster only.")
    p.add_argument("--player-id", dest="player_id", required=True, type=int)
    p.add_argument("--team-id",   dest="team_id",   required=True, type=int)
    p.add_argument("--season",    required=True, type=int)
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")

    # ── list-players ────────────────────────────────────────────────────────
    p = sub.add_parser("list-players",
                       help="List players, optionally filtered by team and/or season.")
    p.add_argument("--team-id", dest="team_id", type=int,
                   help="Filter by team_id (shows all their seasons unless --season is given).")
    p.add_argument("--season",  type=int, help="Filter by season year (requires --team-id).")

    # ── list-teams ──────────────────────────────────────────────────────────
    sub.add_parser("list-teams", help="List all teams with their IDs.")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "add-player":    cmd_add_player,
    "delete-player": cmd_delete_player,
    "add-team":      cmd_add_team,
    "delete-team":   cmd_delete_team,
    "add-roster":    cmd_add_roster,
    "remove-roster": cmd_remove_roster,
    "list-players":  cmd_list_players,
    "list-teams":    cmd_list_teams,
}

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    COMMANDS[args.command](args)
