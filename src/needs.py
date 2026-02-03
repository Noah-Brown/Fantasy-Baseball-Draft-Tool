"""Team needs analysis for fantasy baseball drafts.

Provides positional roster tracking, smart player recommendations,
and comparative team standings analysis.
"""

from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from .database import Player, Team, DraftPick
from .positions import can_player_fill_position, HITTER_ROSTER_POSITIONS, PITCHER_ROSTER_POSITIONS
from .settings import LeagueSettings, DEFAULT_SETTINGS


@dataclass
class PositionalRosterState:
    """State of a single roster position slot."""
    position: str       # e.g., "C", "1B", "CI"
    required: int       # Slots from roster_spots
    filled: int         # Players assigned to this slot
    remaining: int      # Slots still needed
    players: list       # Players filling this slot (player names/objects)


@dataclass
class PlayerRecommendation:
    """A recommended player with scoring breakdown."""
    player: Player
    composite_score: float
    position_urgency: float
    category_fit: float
    value_surplus: float
    fills_positions: list[str]  # Which needed positions this player fills
    helps_categories: list[str]  # Which weak categories this player helps


@dataclass
class TeamNeedsAnalysis:
    """Complete team needs analysis result."""
    positional_states: list[PositionalRosterState]
    recommendations: list[PlayerRecommendation]
    category_analysis: dict  # From analyze_team_category_balance
    comparative_standings: dict  # All teams x all categories


# Position restrictiveness order for greedy assignment
# Most restrictive (C) assigned first, least restrictive (UTIL) assigned last
HITTER_POSITION_PRIORITY = ["C", "1B", "2B", "3B", "SS", "OF", "CI", "MI", "UTIL"]
PITCHER_POSITION_PRIORITY = ["SP", "RP", "P"]


def get_team_players(session: Session, team: Team) -> list[Player]:
    """Get all drafted players for a team."""
    players = []
    for pick in team.draft_picks:
        player = session.query(Player).filter(Player.draft_pick_id == pick.id).first()
        if player:
            players.append(player)
    return players


def get_team_positional_roster_state(
    session: Session,
    team: Team,
    settings: LeagueSettings = None
) -> list[PositionalRosterState]:
    """
    Calculate positional roster state for a team using greedy assignment.

    Uses restrictiveness-based priority (C first, UTIL last) to assign
    players to their optimal roster slots.

    Args:
        session: Database session
        team: The team to analyze
        settings: League settings with roster configuration

    Returns:
        List of PositionalRosterState for each roster position
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Get all team's drafted players
    players = get_team_players(session, team)

    # Separate hitters and pitchers
    hitters = [p for p in players if p.player_type == "hitter"]
    pitchers = [p for p in players if p.player_type == "pitcher"]

    # Track which players have been assigned
    assigned_hitters = set()
    assigned_pitchers = set()

    # Build roster states
    states = []

    # Process hitter positions in priority order
    for position in HITTER_POSITION_PRIORITY:
        required = settings.roster_spots.get(position, 0)
        if required == 0:
            continue

        filled = 0
        slot_players = []

        # Find unassigned players who can fill this position
        for _ in range(required):
            for player in hitters:
                if player.id in assigned_hitters:
                    continue
                if can_player_fill_position(player.position_list, position, "hitter"):
                    assigned_hitters.add(player.id)
                    slot_players.append(player.name)
                    filled += 1
                    break

        states.append(PositionalRosterState(
            position=position,
            required=required,
            filled=filled,
            remaining=required - filled,
            players=slot_players,
        ))

    # Process pitcher positions in priority order
    for position in PITCHER_POSITION_PRIORITY:
        required = settings.roster_spots.get(position, 0)
        if required == 0:
            continue

        filled = 0
        slot_players = []

        # Find unassigned players who can fill this position
        for _ in range(required):
            for player in pitchers:
                if player.id in assigned_pitchers:
                    continue
                if can_player_fill_position(player.position_list, position, "pitcher"):
                    assigned_pitchers.add(player.id)
                    slot_players.append(player.name)
                    filled += 1
                    break

        states.append(PositionalRosterState(
            position=position,
            required=required,
            filled=filled,
            remaining=required - filled,
            players=slot_players,
        ))

    return states


def get_unfilled_positions(roster_states: list[PositionalRosterState]) -> list[str]:
    """Get list of positions that still need players."""
    return [state.position for state in roster_states if state.remaining > 0]


def calculate_position_urgency(
    position: str,
    roster_states: list[PositionalRosterState],
    scarcity: dict = None,
) -> float:
    """
    Calculate urgency score (0-1) for a position.

    Combines team need with league-wide scarcity.

    Args:
        position: Position code to evaluate
        roster_states: Current team roster states
        scarcity: Optional scarcity info from get_position_scarcity()

    Returns:
        Urgency score between 0 and 1
    """
    # Find roster state for this position
    state = None
    for s in roster_states:
        if s.position == position:
            state = s
            break

    if state is None or state.required == 0:
        return 0.0

    # Base urgency = remaining slots / required slots
    base_urgency = state.remaining / state.required

    # Boost for league-wide scarcity
    scarcity_boost = 0.0
    if scarcity and position in scarcity:
        level = scarcity[position].get('level', '')
        if level == 'critical':
            scarcity_boost = 0.3
        elif level == 'medium':
            scarcity_boost = 0.15
        elif level == 'low':
            scarcity_boost = 0.05

    # Combine with ceiling of 1.0
    return min(1.0, base_urgency + scarcity_boost)


def calculate_category_fit(
    player: Player,
    weak_categories: list[str],
    settings: LeagueSettings = None,
) -> float:
    """
    Calculate how well a player helps weak categories (0-1).

    Args:
        player: Player to evaluate
        weak_categories: List of weak category names (lowercase)
        settings: League settings

    Returns:
        Category fit score between 0 and 1
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    if not player.sgp_breakdown or not weak_categories:
        return 0.0

    # Sum player's SGP in weak categories
    weak_sgp = 0.0
    for cat in weak_categories:
        weak_sgp += player.sgp_breakdown.get(cat.lower(), 0)

    # Total player SGP (positive contribution only)
    total_positive = sum(max(0, v) for v in player.sgp_breakdown.values())

    if total_positive <= 0:
        return 0.0

    # Normalize: ratio of weak category contribution to total positive
    fit = weak_sgp / total_positive if weak_sgp > 0 else 0.0

    # Clamp to 0-1 range
    return max(0.0, min(1.0, fit))


def get_player_positions_that_fill_needs(
    player: Player,
    unfilled_positions: list[str],
) -> list[str]:
    """Get list of needed positions this player can fill."""
    fills = []
    for pos in unfilled_positions:
        if can_player_fill_position(player.position_list, pos, player.player_type):
            fills.append(pos)
    return fills


def get_player_helpful_categories(
    player: Player,
    weak_categories: list[str],
    threshold: float = 0.3,
) -> list[str]:
    """Get list of weak categories this player helps with."""
    if not player.sgp_breakdown:
        return []

    helps = []
    for cat in weak_categories:
        sgp = player.sgp_breakdown.get(cat.lower(), 0)
        if sgp >= threshold:
            helps.append(cat.upper())
    return helps


def get_player_recommendations(
    session: Session,
    team: Team,
    roster_states: list[PositionalRosterState],
    category_analysis: dict,
    settings: LeagueSettings = None,
    scarcity: dict = None,
    limit: int = 15,
) -> list[PlayerRecommendation]:
    """
    Generate smart player recommendations based on team needs.

    Scoring formula:
        composite_score = (
            position_urgency * 0.35 +
            category_fit * 0.35 +
            value_surplus * 0.30
        )

    Args:
        session: Database session
        team: The user's team
        roster_states: Current positional roster states
        category_analysis: Result from analyze_team_category_balance
        settings: League settings
        scarcity: Optional scarcity info from get_position_scarcity()
        limit: Maximum recommendations to return

    Returns:
        List of PlayerRecommendation sorted by composite score
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Get unfilled positions
    unfilled = get_unfilled_positions(roster_states)

    # Get weak categories (standings >= 7)
    weak_categories = get_weak_categories(category_analysis)

    # Get available players
    available = session.query(Player).filter(
        Player.is_drafted == False,
        Player.dollar_value.isnot(None)
    ).all()

    if not available:
        return []

    # Calculate max value for normalization
    max_value = max(p.dollar_value for p in available if p.dollar_value)

    recommendations = []

    for player in available:
        # Skip players that don't fill any needed position
        fills_positions = get_player_positions_that_fill_needs(player, unfilled)
        if not fills_positions:
            continue

        # Calculate position urgency (max across positions this player fills)
        position_urgency = 0.0
        for pos in fills_positions:
            urgency = calculate_position_urgency(pos, roster_states, scarcity)
            position_urgency = max(position_urgency, urgency)

        # Calculate category fit
        category_fit = calculate_category_fit(player, weak_categories, settings)

        # Calculate value surplus (normalized 0-1)
        value_surplus = (player.dollar_value or 0) / max_value if max_value > 0 else 0

        # Calculate composite score
        composite_score = (
            position_urgency * 0.35 +
            category_fit * 0.35 +
            value_surplus * 0.30
        )

        # Get helpful categories
        helps_categories = get_player_helpful_categories(player, weak_categories)

        recommendations.append(PlayerRecommendation(
            player=player,
            composite_score=composite_score,
            position_urgency=position_urgency,
            category_fit=category_fit,
            value_surplus=value_surplus,
            fills_positions=fills_positions,
            helps_categories=helps_categories,
        ))

    # Sort by composite score descending
    recommendations.sort(key=lambda r: r.composite_score, reverse=True)

    return recommendations[:limit]


def get_weak_categories(category_analysis: dict, threshold: int = 7) -> list[str]:
    """
    Get list of weak categories from analysis.

    Args:
        category_analysis: Result from analyze_team_category_balance
        threshold: Standings position at or above which category is "weak"

    Returns:
        List of weak category names (lowercase)
    """
    weak = []
    standings = category_analysis.get("standings", {})
    for cat, position in standings.items():
        if position >= threshold:
            weak.append(cat)
    return weak


def calculate_all_team_standings(
    session: Session,
    settings: LeagueSettings = None,
) -> dict[str, dict[str, int]]:
    """
    Calculate projected standings for all teams across all categories.

    Args:
        session: Database session
        settings: League settings

    Returns:
        Dict mapping team_name -> {category -> projected_position}
    """
    from .values import analyze_team_category_balance
    from .draft import get_all_teams

    if settings is None:
        settings = DEFAULT_SETTINGS

    teams = get_all_teams(session)

    if not teams:
        return {}

    all_standings = {}

    # Calculate SGP totals for each team
    team_sgps = {}
    for team in teams:
        analysis = analyze_team_category_balance(team.draft_picks, settings)
        team_sgps[team.name] = analysis["sgp_totals"]

    # For each category, rank teams by SGP
    hitting_cats = [c.lower() for c in settings.hitting_categories]
    pitching_cats = [c.lower() for c in settings.pitching_categories]
    all_cats = hitting_cats + pitching_cats

    for cat in all_cats:
        # Get all teams' SGP for this category
        team_scores = [(name, sgps.get(cat, 0)) for name, sgps in team_sgps.items()]

        # Sort by SGP descending (higher = better = lower rank)
        # For ratio stats (ERA, WHIP), SGP is already inverted
        team_scores.sort(key=lambda x: x[1], reverse=True)

        # Assign ranks
        for rank, (team_name, _) in enumerate(team_scores, start=1):
            if team_name not in all_standings:
                all_standings[team_name] = {}
            all_standings[team_name][cat] = rank

    return all_standings


def analyze_team_needs(
    session: Session,
    team: Team,
    settings: LeagueSettings = None,
) -> TeamNeedsAnalysis:
    """
    Main entry point for comprehensive team needs analysis.

    Args:
        session: Database session
        team: The team to analyze
        settings: League settings

    Returns:
        TeamNeedsAnalysis with positional states, recommendations,
        category analysis, and comparative standings
    """
    from .values import analyze_team_category_balance
    from .draft import get_position_scarcity

    if settings is None:
        settings = DEFAULT_SETTINGS

    # Get positional roster state
    positional_states = get_team_positional_roster_state(session, team, settings)

    # Get category analysis
    category_analysis = analyze_team_category_balance(team.draft_picks, settings)

    # Get position scarcity
    scarcity = get_position_scarcity(session, settings)

    # Get player recommendations
    recommendations = get_player_recommendations(
        session=session,
        team=team,
        roster_states=positional_states,
        category_analysis=category_analysis,
        settings=settings,
        scarcity=scarcity,
    )

    # Get comparative standings
    comparative_standings = calculate_all_team_standings(session, settings)

    return TeamNeedsAnalysis(
        positional_states=positional_states,
        recommendations=recommendations,
        category_analysis=category_analysis,
        comparative_standings=comparative_standings,
    )
