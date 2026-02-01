"""SGP calculation and dollar value conversion for fantasy baseball players."""

import statistics
from sqlalchemy.orm import Session

from .database import Player
from .projections import get_all_hitters, get_all_pitchers
from .settings import LeagueSettings, DEFAULT_SETTINGS


# Counting stats (higher is better)
HITTER_COUNTING_STATS = ["r", "hr", "rbi", "sb"]
PITCHER_COUNTING_STATS = ["w", "sv", "k"]

# Rate stats (weighted by plate appearances/innings)
HITTER_RATE_STATS = ["avg"]  # Weighted by AB

# Ratio stats (lower is better)
PITCHER_RATIO_STATS = ["era", "whip"]  # Weighted by IP


def calculate_all_player_values(session: Session, settings: LeagueSettings = None) -> int:
    """
    Main entry point - calculates and updates all player values.

    Args:
        session: Database session
        settings: League settings (uses DEFAULT_SETTINGS if None)

    Returns:
        Number of players with updated values
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    hitters = get_all_hitters(session)
    pitchers = get_all_pitchers(session)

    # Calculate values for each pool
    hitter_count = _calculate_pool_values(
        players=hitters,
        pool_size=settings.total_hitters_drafted,
        budget=settings.total_league_budget * settings.hitter_budget_pct,
        categories=settings.hitting_categories,
        player_type="hitter",
        min_bid=settings.min_bid,
    )

    pitcher_count = _calculate_pool_values(
        players=pitchers,
        pool_size=settings.total_pitchers_drafted,
        budget=settings.total_league_budget * (1 - settings.hitter_budget_pct),
        categories=settings.pitching_categories,
        player_type="pitcher",
        min_bid=settings.min_bid,
    )

    session.commit()
    return hitter_count + pitcher_count


def _calculate_pool_values(
    players: list[Player],
    pool_size: int,
    budget: float,
    categories: list[str],
    player_type: str,
    min_bid: int = 1,
) -> int:
    """
    Calculate SGP and dollar values for a pool of players (hitters or pitchers).

    Args:
        players: List of players in the pool
        pool_size: Number of players that will be drafted (replacement level)
        budget: Total budget allocated to this pool
        categories: Stat categories for this pool
        player_type: "hitter" or "pitcher"
        min_bid: Minimum dollar value

    Returns:
        Number of players with values calculated
    """
    if not players:
        return 0

    # Step 1: Calculate preliminary value to sort players
    preliminary_values = []
    for player in players:
        prelim = _calculate_preliminary_value(player, categories, player_type)
        preliminary_values.append((player, prelim))

    # Sort by preliminary value (descending)
    preliminary_values.sort(key=lambda x: x[1], reverse=True)

    # Step 2: Take top N players as the draftable pool
    draftable_pool = [p for p, _ in preliminary_values[:pool_size]]

    if len(draftable_pool) < pool_size:
        # Not enough players - use all available
        replacement_player = draftable_pool[-1] if draftable_pool else None
    else:
        # Replacement level is the Nth player
        replacement_player = draftable_pool[-1]

    if not replacement_player:
        return 0

    # Step 3: Calculate SGP denominators (std dev for each category)
    denominators = _calculate_sgp_denominators(draftable_pool, categories, player_type)

    # Step 4: Get replacement level stats
    replacement_stats = _get_player_stats(replacement_player, categories, player_type)

    # Step 5: Calculate SGP for each player in the pool
    player_sgps = []
    for player in draftable_pool:
        sgp, breakdown = _calculate_player_sgp(
            player,
            categories,
            player_type,
            replacement_stats,
            denominators
        )
        player.sgp = sgp
        player.sgp_breakdown = breakdown
        player_sgps.append((player, sgp))

    # Step 6: Calculate total positive SGP
    total_positive_sgp = sum(max(0, sgp) for _, sgp in player_sgps)

    if total_positive_sgp <= 0:
        # Edge case: no positive SGP values
        for player in draftable_pool:
            player.dollar_value = min_bid
        return len(draftable_pool)

    # Step 7: Calculate $/SGP
    # Adjust budget for minimum bids on negative SGP players
    negative_sgp_players = sum(1 for _, sgp in player_sgps if sgp <= 0)
    adjusted_budget = budget - (negative_sgp_players * min_bid)
    dollars_per_sgp = adjusted_budget / total_positive_sgp

    # Step 8: Assign dollar values
    for player, sgp in player_sgps:
        if sgp > 0:
            player.dollar_value = max(min_bid, sgp * dollars_per_sgp)
        else:
            player.dollar_value = min_bid

    # Players outside the draftable pool get minimum value and zero SGP
    for player, _ in preliminary_values[pool_size:]:
        player.sgp = 0
        player.dollar_value = min_bid
        player.sgp_breakdown = {cat.lower(): 0.0 for cat in categories}

    return len(players)


def _calculate_preliminary_value(
    player: Player,
    categories: list[str],
    player_type: str
) -> float:
    """
    Calculate a preliminary value for sorting players.
    Uses z-scores approximation based on typical stat ranges.
    """
    value = 0.0

    if player_type == "hitter":
        # Simple sum of normalized stats
        value += (getattr(player, "r", 0) or 0) / 100.0  # ~100 runs is good
        value += (getattr(player, "hr", 0) or 0) / 30.0  # ~30 HR is good
        value += (getattr(player, "rbi", 0) or 0) / 100.0  # ~100 RBI is good
        value += (getattr(player, "sb", 0) or 0) / 20.0  # ~20 SB is good

        # AVG contribution (above .250 baseline)
        avg = getattr(player, "avg", 0) or 0
        ab = getattr(player, "ab", 0) or 0
        if ab > 0:
            value += (avg - 0.250) * (ab / 500.0) * 10  # Scale by playing time
    else:
        # Pitcher preliminary value
        value += (getattr(player, "w", 0) or 0) / 15.0  # ~15 wins is good
        value += (getattr(player, "sv", 0) or 0) / 30.0  # ~30 saves is good
        value += (getattr(player, "k", 0) or 0) / 200.0  # ~200 K is good

        # ERA/WHIP contribution (below league average is good)
        era = getattr(player, "era", 0) or 0
        whip = getattr(player, "whip", 0) or 0
        ip = getattr(player, "ip", 0) or 0

        if ip > 0 and era > 0:
            value += (4.50 - era) * (ip / 200.0)  # Scale by innings
        if ip > 0 and whip > 0:
            value += (1.35 - whip) * (ip / 200.0) * 5  # Scale by innings

    return value


def _calculate_sgp_denominators(
    players: list[Player],
    categories: list[str],
    player_type: str
) -> dict[str, float]:
    """
    Calculate the SGP denominator (standard deviation) for each category.
    """
    denominators = {}

    for category in categories:
        cat_lower = category.lower()

        if player_type == "hitter" and cat_lower == "avg":
            # For AVG, use weighted hits
            values = []
            for p in players:
                ab = getattr(p, "ab", 0) or 0
                h = getattr(p, "h", 0) or 0
                if ab > 0:
                    values.append(h)
            if len(values) >= 2:
                denominators[cat_lower] = statistics.stdev(values)
            else:
                denominators[cat_lower] = 1.0

        elif player_type == "pitcher" and cat_lower in ["era", "whip"]:
            # For ratio stats, weight by IP
            values = []
            for p in players:
                ip = getattr(p, "ip", 0) or 0
                stat = getattr(p, cat_lower, 0) or 0
                if ip > 0 and stat > 0:
                    values.append(stat * ip)
            if len(values) >= 2:
                denominators[cat_lower] = statistics.stdev(values)
            else:
                denominators[cat_lower] = 1.0

        else:
            # Counting stats
            values = [getattr(p, cat_lower, 0) or 0 for p in players]
            if len(values) >= 2:
                denominators[cat_lower] = statistics.stdev(values)
            else:
                denominators[cat_lower] = 1.0

        # Ensure non-zero denominator
        if denominators[cat_lower] == 0:
            denominators[cat_lower] = 1.0

    return denominators


def _get_player_stats(
    player: Player,
    categories: list[str],
    player_type: str
) -> dict[str, float]:
    """Get the relevant stats for a player."""
    stats = {}

    for category in categories:
        cat_lower = category.lower()
        stats[cat_lower] = getattr(player, cat_lower, 0) or 0

    # Include AB/IP for rate stat calculations
    if player_type == "hitter":
        stats["ab"] = getattr(player, "ab", 0) or 0
        stats["h"] = getattr(player, "h", 0) or 0
    else:
        stats["ip"] = getattr(player, "ip", 0) or 0

    return stats


def _calculate_player_sgp(
    player: Player,
    categories: list[str],
    player_type: str,
    replacement_stats: dict[str, float],
    denominators: dict[str, float],
) -> tuple[float, dict[str, float]]:
    """
    Calculate total SGP for a player across all categories.

    Returns:
        Tuple of (total_sgp, breakdown_dict) where breakdown_dict maps
        category names to their individual SGP contributions.
    """
    total_sgp = 0.0
    breakdown = {}

    for category in categories:
        cat_lower = category.lower()
        player_stat = getattr(player, cat_lower, 0) or 0
        replacement_stat = replacement_stats.get(cat_lower, 0)
        denominator = denominators.get(cat_lower, 1.0)

        if player_type == "hitter" and cat_lower == "avg":
            # AVG: Compare weighted hits (player H vs expected H at replacement AVG)
            player_ab = getattr(player, "ab", 0) or 0
            player_h = getattr(player, "h", 0) or 0
            replacement_avg = replacement_stat

            if player_ab > 0 and replacement_avg > 0:
                expected_h = player_ab * replacement_avg
                sgp = (player_h - expected_h) / denominator
            else:
                sgp = 0

        elif player_type == "pitcher" and cat_lower in ["era", "whip"]:
            # ERA/WHIP: Lower is better, weight by IP
            player_ip = getattr(player, "ip", 0) or 0

            if player_ip > 0 and player_stat > 0:
                # Invert: replacement - player (so lower stat = positive SGP)
                sgp = (replacement_stat - player_stat) * player_ip / denominator
            else:
                sgp = 0

        else:
            # Counting stats: higher is better
            sgp = (player_stat - replacement_stat) / denominator

        breakdown[cat_lower] = sgp
        total_sgp += sgp

    return total_sgp, breakdown


def calculate_remaining_player_values(session: Session, settings: LeagueSettings = None) -> int:
    """
    Recalculate values for remaining undrafted players.

    Adjusts pool sizes based on remaining roster slots and uses
    remaining budget across all teams. Clears the values_stale flag
    after calculation.

    Args:
        session: Database session
        settings: League settings (uses DEFAULT_SETTINGS if None)

    Returns:
        Number of players with updated values
    """
    from .draft import get_draft_state, get_remaining_roster_slots, get_remaining_budget

    if settings is None:
        settings = DEFAULT_SETTINGS

    draft_state = get_draft_state(session)

    # Get remaining roster slots
    remaining_slots = get_remaining_roster_slots(session, settings)
    remaining_hitter_slots = remaining_slots["hitters"]
    remaining_pitcher_slots = remaining_slots["pitchers"]

    # Get remaining budget
    remaining_budget = get_remaining_budget(session)

    # Get undrafted players only
    hitters = get_available_hitters(session)
    pitchers = get_available_pitchers(session)

    # Calculate values for each pool with adjusted sizes and budgets
    hitter_budget = remaining_budget * settings.hitter_budget_pct
    pitcher_budget = remaining_budget * (1 - settings.hitter_budget_pct)

    hitter_count = _calculate_pool_values(
        players=hitters,
        pool_size=remaining_hitter_slots,
        budget=hitter_budget,
        categories=settings.hitting_categories,
        player_type="hitter",
        min_bid=settings.min_bid,
    )

    pitcher_count = _calculate_pool_values(
        players=pitchers,
        pool_size=remaining_pitcher_slots,
        budget=pitcher_budget,
        categories=settings.pitching_categories,
        player_type="pitcher",
        min_bid=settings.min_bid,
    )

    # Clear stale flag
    if draft_state:
        draft_state.values_stale = False

    session.commit()
    return hitter_count + pitcher_count


def get_available_hitters(session: Session) -> list[Player]:
    """Get all undrafted hitters."""
    return (
        session.query(Player)
        .filter(Player.player_type == "hitter", Player.is_drafted == False)
        .all()
    )


def get_available_pitchers(session: Session) -> list[Player]:
    """Get all undrafted pitchers."""
    return (
        session.query(Player)
        .filter(Player.player_type == "pitcher", Player.is_drafted == False)
        .all()
    )


def get_player_value_breakdown(
    player: Player,
    settings: LeagueSettings = None,
) -> dict:
    """
    Get a breakdown of a player's value by category.
    Useful for debugging and display.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    if player.player_type == "hitter":
        categories = settings.hitting_categories
    else:
        categories = settings.pitching_categories

    breakdown = {
        "name": player.name,
        "type": player.player_type,
        "total_sgp": player.sgp,
        "dollar_value": player.dollar_value,
        "categories": {},
    }

    for category in categories:
        cat_lower = category.lower()
        stat_value = getattr(player, cat_lower, 0) or 0
        breakdown["categories"][category] = stat_value

    return breakdown


def calculate_category_surplus(player: Player, price_paid: int) -> dict[str, float]:
    """
    Calculate surplus for each category using proportional allocation.

    The total surplus (dollar_value - price_paid) is distributed across
    categories proportionally to each category's SGP contribution.

    Args:
        player: Player with sgp_breakdown populated
        price_paid: The price paid for the player

    Returns:
        Dict mapping category names to their surplus values
    """
    if not player.sgp_breakdown:
        return {}

    if player.sgp is None:
        return {}

    total_surplus = (player.dollar_value or 0) - price_paid
    total_sgp = player.sgp

    if total_sgp == 0:
        # Distribute evenly if no SGP differentiation
        num_cats = len(player.sgp_breakdown)
        if num_cats == 0:
            return {}
        return {cat: total_surplus / num_cats for cat in player.sgp_breakdown}

    return {
        cat: (cat_sgp / total_sgp) * total_surplus
        for cat, cat_sgp in player.sgp_breakdown.items()
    }
