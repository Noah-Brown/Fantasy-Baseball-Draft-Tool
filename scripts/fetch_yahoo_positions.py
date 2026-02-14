#!/usr/bin/env python3
"""Fetch player position eligibility from Yahoo Fantasy Baseball API.

Usage:
    python scripts/fetch_yahoo_positions.py --league-id 388.l.12345

First-time setup:
    1. Register an app at https://developer.yahoo.com/apps/
    2. Select "Installed Application" type
    3. Request "Read" access to "Fantasy Sports"
    4. Create oauth2.json in project root with:
       {"consumer_key": "YOUR_KEY", "consumer_secret": "YOUR_SECRET"}
    5. On first run, a browser window opens for Yahoo authorization
"""

import argparse
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

# Add project root to path so we can import src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

from src.database import Player, get_engine, get_session


# Positions to query for free agents (covers all Yahoo baseball positions)
YAHOO_POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF",
                    "DH", "SP", "RP", "P"]

# Yahoo positions to exclude from stored eligibility (not real positions)
YAHOO_META_POSITIONS = {"Util", "BN", "DL", "IL", "IL+", "NA"}


def normalize_name(name: str) -> str:
    """Normalize a player name for matching.

    Strips accents, lowercases, removes suffixes like Jr./III/II,
    and strips parenthetical notes.
    """
    # Remove parenthetical suffixes like "(Hitter)" or "(SP)"
    if "(" in name:
        name = name[:name.index("(")]

    # Strip accents/diacritics
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    # Lowercase and strip
    name = name.lower().strip()

    # Remove common suffixes
    for suffix in [" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()

    # Remove periods and extra spaces
    name = name.replace(".", "")
    name = " ".join(name.split())

    return name


def match_players(yahoo_players: dict[str, dict], db_players: list[Player],
                  threshold: float = 0.85) -> list[tuple[Player, dict, float]]:
    """Match database players to Yahoo players by name.

    Returns list of (db_player, yahoo_data, score) tuples.
    """
    matched = []
    unmatched_db = []

    # Build normalized name lookup for Yahoo players
    yahoo_by_norm = {}
    for yp in yahoo_players.values():
        norm = normalize_name(yp["name"])
        yahoo_by_norm[norm] = yp

    for player in db_players:
        norm_name = normalize_name(player.name)

        # Exact normalized match
        if norm_name in yahoo_by_norm:
            matched.append((player, yahoo_by_norm[norm_name], 1.0))
            continue

        # Fuzzy match
        best_score = 0
        best_yahoo = None
        for yahoo_norm, yp in yahoo_by_norm.items():
            score = SequenceMatcher(None, norm_name, yahoo_norm).ratio()
            if score > best_score:
                best_score = score
                best_yahoo = yp

        if best_score >= threshold and best_yahoo is not None:
            matched.append((player, best_yahoo, best_score))
        else:
            unmatched_db.append(player)

    return matched, unmatched_db


def format_positions(eligible_positions: list[str]) -> str:
    """Convert Yahoo eligible_positions list to comma-separated string.

    Filters out meta-positions like Util, BN, IL.
    """
    positions = [p for p in eligible_positions if p not in YAHOO_META_POSITIONS]

    # Normalize OF positions: LF/CF/RF -> OF
    outfield = {"LF", "CF", "RF"}
    if any(p in outfield for p in positions):
        positions = [p for p in positions if p not in outfield]
        if "OF" not in positions:
            positions.append("OF")

    return ",".join(positions) if positions else ""


def fetch_yahoo_players(league) -> dict[str, dict]:
    """Fetch all players from a Yahoo league with their position data.

    Returns dict keyed by player_id with name and eligible_positions.
    """
    all_players = {}

    # Fetch free agents for each position
    for pos in YAHOO_POSITIONS:
        print(f"  Fetching free agents: {pos}...")
        try:
            fas = league.free_agents(pos)
            for p in fas:
                pid = str(p["player_id"])
                if pid not in all_players:
                    all_players[pid] = {
                        "player_id": pid,
                        "name": p["name"],
                        "eligible_positions": p.get("eligible_positions", []),
                        "position_type": p.get("position_type", ""),
                    }
        except Exception as e:
            print(f"  Warning: failed to fetch {pos} free agents: {e}")

    # Fetch taken (rostered) players
    print("  Fetching rostered players...")
    try:
        taken = league.taken_players()
        for p in taken:
            pid = str(p["player_id"])
            if pid not in all_players:
                all_players[pid] = {
                    "player_id": pid,
                    "name": p["name"],
                    "eligible_positions": p.get("eligible_positions", []),
                    "position_type": p.get("position_type", ""),
                }
    except Exception as e:
        print(f"  Warning: failed to fetch rostered players: {e}")

    return all_players


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Yahoo Fantasy Baseball position data and update the draft database."
    )
    parser.add_argument(
        "--league-id",
        required=True,
        help="Yahoo league ID (e.g., 388.l.12345). Find this in your league URL.",
    )
    parser.add_argument(
        "--db-path",
        default="draft.db",
        help="Path to SQLite database (default: draft.db)",
    )
    parser.add_argument(
        "--oauth-file",
        default="oauth2.json",
        help="Path to Yahoo OAuth credentials file (default: oauth2.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show matches without writing to database",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match threshold 0-1 (default: 0.85)",
    )
    args = parser.parse_args()

    # Validate oauth file exists
    oauth_path = Path(args.oauth_file)
    if not oauth_path.exists():
        print(f"Error: OAuth file not found: {oauth_path}")
        print("Create it with: {\"consumer_key\": \"YOUR_KEY\", \"consumer_secret\": \"YOUR_SECRET\"}")
        sys.exit(1)

    # Connect to Yahoo
    print("Connecting to Yahoo Fantasy API...")
    sc = OAuth2(None, None, from_file=str(oauth_path))
    if not sc.token_is_valid():
        sc.refresh_access_token()

    gm = yfa.Game(sc, "mlb")
    lg = gm.to_league(args.league_id)
    print(f"Connected to league: {args.league_id}")

    # Fetch Yahoo players
    print("Fetching players from Yahoo...")
    yahoo_players = fetch_yahoo_players(lg)
    print(f"Found {len(yahoo_players)} players on Yahoo")

    # Load database players
    print("Loading database players...")
    engine = get_engine(args.db_path)
    session = get_session(engine)
    db_players = session.query(Player).all()
    print(f"Found {len(db_players)} players in database")

    if not db_players:
        print("Error: No players in database. Import FGDC projections first.")
        session.close()
        sys.exit(1)

    # Match players
    print(f"Matching players (threshold: {args.threshold})...")
    matched, unmatched_db = match_players(yahoo_players, db_players, args.threshold)

    # Report results
    print(f"\nResults:")
    print(f"  Matched: {len(matched)}")
    print(f"  Unmatched (DB): {len(unmatched_db)}")

    # Show fuzzy matches (non-exact) for review
    fuzzy_matches = [(p, y, s) for p, y, s in matched if s < 1.0]
    if fuzzy_matches:
        print(f"\nFuzzy matches ({len(fuzzy_matches)}):")
        for player, yahoo, score in sorted(fuzzy_matches, key=lambda x: x[2]):
            print(f"  {player.name} -> {yahoo['name']} (score: {score:.2f})")

    # Show unmatched players
    if unmatched_db:
        print(f"\nUnmatched database players ({len(unmatched_db)}):")
        for player in unmatched_db[:20]:
            print(f"  {player.name} ({player.team})")
        if len(unmatched_db) > 20:
            print(f"  ... and {len(unmatched_db) - 20} more")

    # Write to database
    if args.dry_run:
        print("\nDry run - no changes written to database.")
        # Show what would be written
        print("\nSample updates:")
        for player, yahoo, score in matched[:10]:
            positions = format_positions(yahoo["eligible_positions"])
            print(f"  {player.name}: positions={positions}, yahoo_id={yahoo['player_id']}")
    else:
        print("\nWriting to database...")
        updated = 0
        for player, yahoo, score in matched:
            player.yahoo_id = yahoo["player_id"]
            player.positions = format_positions(yahoo["eligible_positions"])
            updated += 1

        session.commit()
        print(f"Updated {updated} players with Yahoo position data.")

    session.close()


if __name__ == "__main__":
    main()
