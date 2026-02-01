"""Position constants and utilities for fantasy baseball."""

# Composite positions mapped to their constituent base positions
COMPOSITE_POSITIONS = {
    "CI": ["1B", "3B"],    # Corner Infielder
    "MI": ["2B", "SS"],    # Middle Infielder
    "UTIL": None,          # Any hitter (special handling)
    "P": None,             # Any pitcher (special handling)
}

# All hitter roster positions (for settings configuration)
HITTER_ROSTER_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "UTIL"]

# All pitcher roster positions
PITCHER_ROSTER_POSITIONS = ["SP", "RP", "P"]

# Positions for UI filters
ALL_FILTER_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "UTIL", "SP", "RP"]

# Positions for scarcity analysis
SCARCITY_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "SP", "RP"]


def expand_position(position: str) -> list[str]:
    """Expand composite position to constituent base positions.

    Args:
        position: A position code (e.g., "CI", "1B", "SP")

    Returns:
        List of base positions. For composite positions like CI, returns
        constituent positions (["1B", "3B"]). For base positions, returns
        a single-element list. For UTIL/P, returns empty list (special handling).
    """
    if position in COMPOSITE_POSITIONS:
        constituents = COMPOSITE_POSITIONS[position]
        return constituents if constituents else []
    return [position]


def can_player_fill_position(player_positions: list[str], roster_position: str, player_type: str) -> bool:
    """Check if a player with given positions can fill a roster slot.

    Args:
        player_positions: List of positions the player is eligible for
        roster_position: The roster slot to check (e.g., "CI", "1B", "UTIL")
        player_type: Either "hitter" or "pitcher"

    Returns:
        True if the player can fill the roster position
    """
    if roster_position == "UTIL" and player_type == "hitter":
        return True
    if roster_position == "P" and player_type == "pitcher":
        return True
    if roster_position in COMPOSITE_POSITIONS:
        constituents = COMPOSITE_POSITIONS[roster_position]
        if constituents:
            return any(pos in player_positions for pos in constituents)
    return roster_position in player_positions
