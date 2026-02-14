"""Import and process FGDC (Fangraphs Depth Charts) projections."""

import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session

from .database import Player


# Column mappings from Fangraphs FGDC CSV to our database
HITTER_COLUMN_MAP = {
    "Name": "name",
    "Team": "team",
    "PA": "pa",
    "AB": "ab",
    "H": "h",
    "R": "r",
    "HR": "hr",
    "RBI": "rbi",
    "SB": "sb",
    "AVG": "avg",
    "OBP": "obp",
    "SLG": "slg",
}

PITCHER_COLUMN_MAP = {
    "Name": "name",
    "Team": "team",
    "IP": "ip",
    "W": "w",
    "SV": "sv",
    "SO": "k",  # Fangraphs uses SO for strikeouts
    "K": "k",   # Some exports use K
    "ERA": "era",
    "WHIP": "whip",
    "BB": "bb",
    "HLD": "hld",
    "K/9": "k9",
}


def import_hitters_csv(session: Session, csv_path: str | Path) -> int:
    """
    Import hitter projections from a FGDC CSV file.

    Args:
        session: Database session
        csv_path: Path to the CSV file

    Returns:
        Number of players imported
    """
    df = pd.read_csv(csv_path)

    # Normalize column names
    df.columns = df.columns.str.strip()

    count = 0
    for _, row in df.iterrows():
        pa = _safe_float(row.get("PA"))
        ab = _safe_float(row.get("AB"))
        h = _safe_float(row.get("H"))
        avg = _safe_float(row.get("AVG"))

        # If AB is not provided, estimate from PA (typical walk/HBP/sac rate is ~14%)
        if ab is None and pa is not None:
            ab = pa * 0.86

        # If H is not provided, calculate from AB and AVG
        if h is None and ab is not None and avg is not None:
            h = ab * avg

        player = Player(
            name=row.get("Name", ""),
            team=row.get("Team", ""),
            positions=_extract_positions(row),
            player_type="hitter",
            fangraphs_id=_safe_str(row.get("playerid") or row.get("PlayerId")),
            mlbam_id=_safe_str(row.get("xMLBAMID") or row.get("MLBAMID")),
            pa=pa,
            ab=ab,
            h=h,
            r=_safe_float(row.get("R")),
            hr=_safe_float(row.get("HR")),
            rbi=_safe_float(row.get("RBI")),
            sb=_safe_float(row.get("SB")),
            avg=avg,
            obp=_safe_float(row.get("OBP")),
            slg=_safe_float(row.get("SLG")),
        )
        session.add(player)
        count += 1

    session.commit()
    return count


def import_pitchers_csv(session: Session, csv_path: str | Path) -> int:
    """
    Import pitcher projections from a FGDC CSV file.

    Args:
        session: Database session
        csv_path: Path to the CSV file

    Returns:
        Number of players imported
    """
    df = pd.read_csv(csv_path)

    # Normalize column names
    df.columns = df.columns.str.strip()

    count = 0
    for _, row in df.iterrows():
        # Determine if SP or RP based on various indicators
        positions = _extract_pitcher_positions(row)

        # Use SO if K not present
        k_value = row.get("K") if "K" in df.columns else row.get("SO")

        # WHIP fallback: compute from (BB + H) / IP if not in CSV
        whip = _safe_float(row.get("WHIP"))
        if whip is None:
            bb = _safe_float(row.get("BB")) or 0
            h_val = _safe_float(row.get("H")) or 0
            ip = _safe_float(row.get("IP"))
            if ip and ip > 0:
                whip = (bb + h_val) / ip

        # K/9 fallback: compute from (K * 9) / IP if not in CSV
        k9 = _safe_float(row.get("K/9"))
        if k9 is None:
            k_val = _safe_float(k_value)
            ip = _safe_float(row.get("IP"))
            if k_val and ip and ip > 0:
                k9 = (k_val * 9) / ip

        player = Player(
            name=row.get("Name", ""),
            team=row.get("Team", ""),
            positions=positions,
            player_type="pitcher",
            fangraphs_id=_safe_str(row.get("playerid") or row.get("PlayerId")),
            mlbam_id=_safe_str(row.get("xMLBAMID") or row.get("MLBAMID")),
            ip=_safe_float(row.get("IP")),
            w=_safe_float(row.get("W")),
            sv=_safe_float(row.get("SV")),
            k=_safe_float(k_value),
            era=_safe_float(row.get("ERA")),
            whip=whip,
            k9=k9,
            hld=_safe_float(row.get("HLD")),
        )
        session.add(player)
        count += 1

    session.commit()
    return count


def _extract_positions(row) -> str:
    """Extract position eligibility from a row."""
    # Fangraphs includes position in various columns
    # Check for explicit position columns (case-insensitive search)
    for col in row.index:
        col_lower = col.lower().strip()
        if col_lower in ("pos", "position", "positions"):
            val = row[col]
            if pd.notna(val) and str(val).strip():
                return str(val).strip()

    # Some exports have position in the name like "Mike Trout (CF)"
    name = str(row.get("Name", ""))
    if "(" in name and ")" in name:
        start = name.rfind("(") + 1
        end = name.rfind(")")
        return name[start:end]

    # Check for minpos column (Fangraphs uses this sometimes)
    if "minpos" in [c.lower() for c in row.index]:
        for col in row.index:
            if col.lower() == "minpos":
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    return str(val).strip()

    return ""


def _extract_pitcher_positions(row) -> str:
    """Determine if a pitcher is SP, RP, or both."""
    positions = []

    # Check for explicit position
    if "Pos" in row.index:
        return str(row["Pos"])

    # Infer from stats
    gs = _safe_float(row.get("GS", 0))  # Games started
    sv = _safe_float(row.get("SV", 0))  # Saves
    g = _safe_float(row.get("G", 0))    # Total games

    if gs and gs > 5:
        positions.append("SP")
    if sv and sv > 0:
        positions.append("RP")
    elif g and gs and (g - gs) > 10:
        positions.append("RP")

    # Default to SP if we can't determine
    if not positions:
        positions.append("SP")

    return ",".join(positions)


def _safe_float(value) -> float | None:
    """Safely convert a value to float."""
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_str(value) -> str | None:
    """Safely convert a value to string, returning None for missing values."""
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def get_all_hitters(session: Session) -> list[Player]:
    """Get all hitters from the database."""
    return session.query(Player).filter(Player.player_type == "hitter").all()


def get_all_pitchers(session: Session) -> list[Player]:
    """Get all pitchers from the database."""
    return session.query(Player).filter(Player.player_type == "pitcher").all()


def get_available_players(session: Session, player_type: str = None) -> list[Player]:
    """Get all undrafted players."""
    query = session.query(Player).filter(Player.is_drafted == False)
    if player_type:
        query = query.filter(Player.player_type == player_type)
    return query.all()


def clear_all_players(session: Session):
    """Remove all players from the database."""
    session.query(Player).delete()
    session.commit()
