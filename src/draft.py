"""Draft state management and operations."""

from sqlalchemy.orm import Session

from .database import Player, Team, DraftPick, DraftState
from .settings import LeagueSettings, DEFAULT_SETTINGS


def get_draft_state(session: Session) -> DraftState | None:
    """Get the current draft state."""
    return session.query(DraftState).first()


def initialize_draft(
    session: Session,
    settings: LeagueSettings = None,
    user_team_name: str = "My Team",
    draft_order: list[int] = None,
) -> DraftState:
    """
    Initialize a new draft.

    Creates teams based on league settings, marks user's team,
    creates DraftState, and resets all player drafted flags.

    Args:
        session: Database session
        settings: League settings (uses DEFAULT_SETTINGS if None)
        user_team_name: Name for the user's team
        draft_order: For snake drafts, list of team IDs in first-round order.
                    If None for snake draft, teams are ordered by ID.

    Returns:
        The created DraftState
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Clear any existing draft data
    reset_draft(session)

    # Create teams
    team_ids = []
    for i in range(settings.num_teams):
        is_user = (i == 0)
        team_name = user_team_name if is_user else f"Team {i + 1}"
        team = Team(
            name=team_name,
            budget=settings.budget_per_team,
            is_user_team=is_user,
        )
        session.add(team)
        session.flush()  # Get the team ID
        team_ids.append(team.id)

    # For snake drafts, set up draft order
    if settings.draft_type == "snake":
        if draft_order is None:
            # Default: use team creation order
            draft_order = team_ids
        final_draft_order = draft_order
    else:
        final_draft_order = None

    # Create draft state
    draft_state = DraftState(
        league_name=settings.name,
        num_teams=settings.num_teams,
        budget_per_team=settings.budget_per_team,
        current_pick=0,
        is_active=True,
        values_stale=False,
        draft_type=settings.draft_type,
        draft_order=final_draft_order,
        current_round=1,
    )
    session.add(draft_state)

    # Reset all player drafted flags
    session.query(Player).update({Player.is_drafted: False, Player.draft_pick_id: None})

    session.commit()
    return draft_state


def draft_player(
    session: Session,
    player_id: int,
    team_id: int,
    price: int = None,
    settings: LeagueSettings = None
) -> DraftPick:
    """
    Draft a player to a team.

    Args:
        session: Database session
        player_id: ID of the player to draft
        team_id: ID of the team drafting
        price: Auction price paid (required for auction, ignored for snake)
        settings: League settings for auto-recalculation (uses DEFAULT_SETTINGS if None)

    Returns:
        The created DraftPick

    Raises:
        ValueError: If player already drafted, team doesn't have budget (auction),
                   or it's not this team's turn (snake)
    """
    from .values import calculate_remaining_player_values
    from .snake import get_current_drafter, get_pick_position

    if settings is None:
        settings = DEFAULT_SETTINGS

    # Get player and team
    player = session.get(Player, player_id)
    team = session.get(Team, team_id)
    draft_state = get_draft_state(session)

    if not player:
        raise ValueError(f"Player {player_id} not found")
    if not team:
        raise ValueError(f"Team {team_id} not found")
    if not draft_state or not draft_state.is_active:
        raise ValueError("No active draft")

    # Validate player not already drafted
    if player.is_drafted:
        raise ValueError(f"{player.name} has already been drafted")

    # Draft type specific validation
    is_snake = draft_state.draft_type == "snake"

    if is_snake:
        # Validate it's this team's turn
        current_drafter = get_current_drafter(draft_state)
        if current_drafter != team_id:
            # Find the team that should be picking
            current_team = session.get(Team, current_drafter) if current_drafter else None
            current_team_name = current_team.name if current_team else "Unknown"
            raise ValueError(f"It's {current_team_name}'s turn to pick, not {team.name}'s")

        # Get round/pick info for snake draft
        round_number, pick_in_round = get_pick_position(draft_state)
        pick_price = None  # No price in snake drafts
    else:
        # Auction validation
        if price is None:
            raise ValueError("Price is required for auction drafts")

        # Validate team has budget
        if price > team.remaining_budget:
            raise ValueError(
                f"{team.name} only has ${team.remaining_budget} remaining "
                f"(tried to spend ${price})"
            )

        if price < 1:
            raise ValueError("Price must be at least $1")

        round_number = None
        pick_in_round = None
        pick_price = price

    # Increment pick number
    draft_state.current_pick += 1

    # Update current round for snake draft
    if is_snake and draft_state.draft_order:
        num_teams = len(draft_state.draft_order)
        draft_state.current_round = ((draft_state.current_pick - 1) // num_teams) + 1

    # Create draft pick
    pick = DraftPick(
        team_id=team_id,
        price=pick_price,
        pick_number=draft_state.current_pick,
        round_number=round_number,
        pick_in_round=pick_in_round,
    )
    session.add(pick)
    session.flush()  # Get the pick ID

    # Update player
    player.is_drafted = True
    player.draft_pick_id = pick.id

    session.commit()

    # Auto-recalculate remaining player values
    calculate_remaining_player_values(session, settings)

    return pick


def undo_last_pick(session: Session) -> Player | None:
    """
    Undo the most recent draft pick.

    Returns:
        The player who was undrafted, or None if no picks exist
    """
    # Get the most recent pick
    pick = (
        session.query(DraftPick)
        .order_by(DraftPick.pick_number.desc())
        .first()
    )

    if not pick:
        return None

    return undo_pick(session, pick.id)


def undo_pick(session: Session, pick_id: int, settings: LeagueSettings = None) -> Player | None:
    """
    Undo a specific draft pick.

    Args:
        session: Database session
        pick_id: ID of the pick to undo
        settings: League settings for auto-recalculation (uses DEFAULT_SETTINGS if None)

    Returns:
        The player who was undrafted, or None if pick not found
    """
    from .values import calculate_remaining_player_values

    if settings is None:
        settings = DEFAULT_SETTINGS

    pick = session.get(DraftPick, pick_id)

    if not pick:
        return None

    # Find the player associated with this pick
    player = session.query(Player).filter(Player.draft_pick_id == pick_id).first()

    if player:
        player.is_drafted = False
        player.draft_pick_id = None

    # Delete the pick
    session.delete(pick)

    session.commit()

    # Auto-recalculate remaining player values
    calculate_remaining_player_values(session, settings)

    return player


def get_draft_history(session: Session, limit: int = None) -> list[dict]:
    """
    Get draft history with player and team info.

    Args:
        session: Database session
        limit: Maximum number of picks to return (None for all)

    Returns:
        List of dicts with pick info, ordered by most recent first
    """
    query = (
        session.query(DraftPick)
        .order_by(DraftPick.pick_number.desc())
    )

    if limit:
        query = query.limit(limit)

    picks = query.all()

    history = []
    for pick in picks:
        player = session.query(Player).filter(Player.draft_pick_id == pick.id).first()
        history.append({
            "pick_id": pick.id,
            "pick_number": pick.pick_number,
            "player_name": player.name if player else "Unknown",
            "player_id": player.id if player else None,
            "team_name": pick.team.name,
            "team_id": pick.team_id,
            "price": pick.price,
            "timestamp": pick.timestamp,
        })

    return history


def reset_draft(session: Session) -> None:
    """
    Reset all draft data.

    Clears teams, draft picks, draft state, and resets player flags.
    """
    # Reset player flags
    session.query(Player).update({Player.is_drafted: False, Player.draft_pick_id: None})

    # Delete draft picks
    session.query(DraftPick).delete()

    # Delete teams
    session.query(Team).delete()

    # Delete draft state
    session.query(DraftState).delete()

    session.commit()


def get_all_teams(session: Session) -> list[Team]:
    """Get all teams in the draft."""
    return session.query(Team).all()


def get_user_team(session: Session) -> Team | None:
    """Get the user's team."""
    return session.query(Team).filter(Team.is_user_team == True).first()


def get_on_the_clock_team(session: Session) -> Team | None:
    """
    Get the team that is currently on the clock in a snake draft.

    Returns:
        The Team object that should pick next, or None if not a snake draft
        or draft is complete
    """
    from .snake import get_current_drafter

    draft_state = get_draft_state(session)
    if not draft_state or draft_state.draft_type != "snake":
        return None

    team_id = get_current_drafter(draft_state)
    if team_id is None:
        return None

    return session.get(Team, team_id)


def get_remaining_roster_slots(session: Session, settings: LeagueSettings = None) -> dict:
    """
    Calculate remaining roster slots across all teams.

    Returns:
        Dict with 'hitters' and 'pitchers' counts
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    draft_state = get_draft_state(session)
    if not draft_state:
        return {
            "hitters": settings.total_hitters_drafted,
            "pitchers": settings.total_pitchers_drafted,
        }

    # Count drafted players by type
    drafted_hitters = (
        session.query(Player)
        .filter(Player.is_drafted == True, Player.player_type == "hitter")
        .count()
    )
    drafted_pitchers = (
        session.query(Player)
        .filter(Player.is_drafted == True, Player.player_type == "pitcher")
        .count()
    )

    return {
        "hitters": settings.total_hitters_drafted - drafted_hitters,
        "pitchers": settings.total_pitchers_drafted - drafted_pitchers,
    }


def get_remaining_budget(session: Session) -> int:
    """Get total remaining budget across all teams."""
    teams = get_all_teams(session)
    return sum(team.remaining_budget for team in teams)


def get_team_roster_needs(session: Session, team: Team, settings: LeagueSettings = None) -> dict:
    """
    Calculate remaining roster slots needed for a specific team.

    Args:
        session: Database session
        team: The team to check
        settings: League settings

    Returns:
        Dict with roster info including spots needed by type
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Count drafted players by type for this team
    drafted_hitters = 0
    drafted_pitchers = 0

    for pick in team.draft_picks:
        player = session.query(Player).filter(Player.draft_pick_id == pick.id).first()
        if player:
            if player.player_type == "hitter":
                drafted_hitters += 1
            elif player.player_type == "pitcher":
                drafted_pitchers += 1

    total_hitter_spots = settings.hitter_roster_spots
    total_pitcher_spots = settings.pitcher_roster_spots

    hitters_needed = max(0, total_hitter_spots - drafted_hitters)
    pitchers_needed = max(0, total_pitcher_spots - drafted_pitchers)
    total_needed = hitters_needed + pitchers_needed

    return {
        "hitters_drafted": drafted_hitters,
        "pitchers_drafted": drafted_pitchers,
        "hitters_needed": hitters_needed,
        "pitchers_needed": pitchers_needed,
        "total_needed": total_needed,
        "total_hitter_spots": total_hitter_spots,
        "total_pitcher_spots": total_pitcher_spots,
    }


def calculate_max_bid(
    session: Session,
    team: Team,
    settings: LeagueSettings = None
) -> dict:
    """
    Calculate the maximum affordable bid for a team.

    The max bid is calculated as:
        remaining_budget - (remaining_roster_slots - 1) * min_bid

    This ensures the team can fill remaining roster spots at minimum bid.

    Args:
        session: Database session
        team: The team to calculate for
        settings: League settings

    Returns:
        Dict with max bid info and breakdown
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    roster_needs = get_team_roster_needs(session, team, settings)
    remaining_budget = team.remaining_budget
    spots_needed = roster_needs["total_needed"]
    min_bid = settings.min_bid

    # If no spots needed, entire budget is available
    if spots_needed <= 0:
        max_bid = remaining_budget
        reserved_for_roster = 0
    else:
        # Reserve min_bid for each remaining spot after this one
        reserved_for_roster = (spots_needed - 1) * min_bid
        max_bid = remaining_budget - reserved_for_roster

    # Ensure max bid is at least min_bid (if they have budget)
    if max_bid < min_bid and remaining_budget >= min_bid:
        max_bid = min_bid

    # Can't bid more than remaining budget
    max_bid = min(max_bid, remaining_budget)

    # Can't bid less than 0
    max_bid = max(0, max_bid)

    return {
        "max_bid": max_bid,
        "remaining_budget": remaining_budget,
        "spots_needed": spots_needed,
        "reserved_for_roster": reserved_for_roster,
        "min_bid": min_bid,
        "hitters_needed": roster_needs["hitters_needed"],
        "pitchers_needed": roster_needs["pitchers_needed"],
    }


def calculate_bid_impact(
    session: Session,
    team: Team,
    bid_amount: int,
    settings: LeagueSettings = None
) -> dict:
    """
    Calculate the impact of a specific bid on a team's remaining capacity.

    Args:
        session: Database session
        team: The team considering the bid
        bid_amount: The proposed bid amount
        settings: League settings

    Returns:
        Dict with impact analysis
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    max_bid_info = calculate_max_bid(session, team, settings)
    roster_needs = get_team_roster_needs(session, team, settings)

    remaining_after_bid = team.remaining_budget - bid_amount
    spots_after_bid = roster_needs["total_needed"] - 1  # Assuming this bid wins

    if spots_after_bid > 0:
        avg_remaining_per_player = remaining_after_bid / spots_after_bid
        reserved_after = (spots_after_bid - 1) * settings.min_bid
        max_bid_after = remaining_after_bid - reserved_after
    else:
        avg_remaining_per_player = remaining_after_bid
        max_bid_after = remaining_after_bid

    return {
        "bid_amount": bid_amount,
        "is_affordable": bid_amount <= max_bid_info["max_bid"],
        "remaining_after": remaining_after_bid,
        "spots_after": spots_after_bid,
        "avg_per_player_after": round(avg_remaining_per_player, 1),
        "max_bid_after": max(0, max_bid_after),
        "over_max_by": max(0, bid_amount - max_bid_info["max_bid"]),
    }


def get_remaining_positional_needs(session: Session, settings: LeagueSettings = None) -> dict[str, int]:
    """
    Calculate remaining positional needs across the league.

    For each position, estimates how many more players at that position
    will be drafted based on remaining roster slots and drafted player positions.

    Args:
        session: Database session
        settings: League settings

    Returns:
        Dict mapping position codes to remaining demand count
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Get total positional demand
    total_demand = settings.get_positional_demand()

    # Count how many players at each position have been drafted
    drafted_players = session.query(Player).filter(Player.is_drafted == True).all()

    position_counts = {pos: 0 for pos in total_demand.keys()}
    for player in drafted_players:
        player_positions = player.position_list
        # Assign player to their primary (first) position for counting
        # This is a simplification - in reality draft positions are more complex
        if player_positions:
            primary_pos = player_positions[0]
            # Map OF variants to OF
            if primary_pos in ["LF", "CF", "RF"]:
                primary_pos = "OF"
            if primary_pos in position_counts:
                position_counts[primary_pos] += 1

    # Calculate remaining needs
    remaining_needs = {}
    for pos, demand in total_demand.items():
        drafted = position_counts.get(pos, 0)
        remaining_needs[pos] = max(0, demand - drafted)

    return remaining_needs


def get_position_scarcity(session: Session, settings: LeagueSettings = None, quality_threshold: int = 2):
    """
    Analyze positional scarcity for available players.

    Returns dict mapping position to scarcity info for positions
    with 3 or fewer quality players remaining.

    Args:
        session: Database session
        settings: League settings (unused but included for consistency)
        quality_threshold: Minimum dollar value for a player to be considered "quality"

    Returns:
        Dict mapping position to scarcity info:
        {
            'C': {
                'count': 2,
                'level': 'medium',
                'top_available': [Player, Player]
            },
            ...
        }
    """
    from sqlalchemy import or_
    from .positions import SCARCITY_POSITIONS, expand_position

    if settings is None:
        settings = DEFAULT_SETTINGS

    scarcity = {}

    for pos in SCARCITY_POSITIONS:
        base_positions = expand_position(pos)

        if base_positions and pos in ["CI", "MI"]:
            # Composite: OR logic across constituents
            position_filters = [Player.positions.contains(bp) for bp in base_positions]
            query = session.query(Player).filter(
                Player.is_drafted == False,
                Player.dollar_value >= quality_threshold,
                or_(*position_filters)
            )
        else:
            query = session.query(Player).filter(
                Player.is_drafted == False,
                Player.dollar_value >= quality_threshold,
                Player.positions.contains(pos)
            )

        quality_count = query.count()

        if quality_count <= 3:
            scarcity[pos] = {
                'count': quality_count,
                'level': 'critical' if quality_count <= 1 else
                         'medium' if quality_count == 2 else 'low',
                'top_available': query.order_by(Player.dollar_value.desc()).limit(3).all()
            }

    return scarcity


def get_team_positional_breakdown(
    session: Session,
    team: Team,
    settings: LeagueSettings = None
) -> dict:
    """
    Get a team's drafted players organized by their assigned position slots.

    Uses the greedy assignment from needs module to show which players
    are filling which roster slots.

    Args:
        session: Database session
        team: The team to analyze
        settings: League settings

    Returns:
        Dict with:
            - hitters: Dict mapping position -> list of player names
            - pitchers: Dict mapping position -> list of player names
            - unassigned: List of players who couldn't be assigned
    """
    from .needs import get_team_positional_roster_state

    if settings is None:
        settings = DEFAULT_SETTINGS

    roster_states = get_team_positional_roster_state(session, team, settings)

    hitters = {}
    pitchers = {}

    hitter_positions = ["C", "1B", "2B", "3B", "SS", "OF", "CI", "MI", "UTIL"]
    pitcher_positions = ["SP", "RP", "P"]

    for state in roster_states:
        if state.position in hitter_positions:
            hitters[state.position] = {
                "players": state.players,
                "filled": state.filled,
                "required": state.required,
                "remaining": state.remaining,
            }
        elif state.position in pitcher_positions:
            pitchers[state.position] = {
                "players": state.players,
                "filled": state.filled,
                "required": state.required,
                "remaining": state.remaining,
            }

    return {
        "hitters": hitters,
        "pitchers": pitchers,
    }
