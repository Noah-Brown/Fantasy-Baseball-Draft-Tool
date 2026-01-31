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
    user_team_name: str = "My Team"
) -> DraftState:
    """
    Initialize a new draft.

    Creates teams based on league settings, marks user's team,
    creates DraftState, and resets all player drafted flags.

    Args:
        session: Database session
        settings: League settings (uses DEFAULT_SETTINGS if None)
        user_team_name: Name for the user's team

    Returns:
        The created DraftState
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    # Clear any existing draft data
    reset_draft(session)

    # Create teams
    for i in range(settings.num_teams):
        is_user = (i == 0)
        team_name = user_team_name if is_user else f"Team {i + 1}"
        team = Team(
            name=team_name,
            budget=settings.budget_per_team,
            is_user_team=is_user,
        )
        session.add(team)

    # Create draft state
    draft_state = DraftState(
        league_name=settings.name,
        num_teams=settings.num_teams,
        budget_per_team=settings.budget_per_team,
        current_pick=0,
        is_active=True,
        values_stale=False,
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
    price: int
) -> DraftPick:
    """
    Draft a player to a team.

    Args:
        session: Database session
        player_id: ID of the player to draft
        team_id: ID of the team drafting
        price: Auction price paid

    Returns:
        The created DraftPick

    Raises:
        ValueError: If player already drafted or team doesn't have budget
    """
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

    # Validate team has budget
    if price > team.remaining_budget:
        raise ValueError(
            f"{team.name} only has ${team.remaining_budget} remaining "
            f"(tried to spend ${price})"
        )

    if price < 1:
        raise ValueError("Price must be at least $1")

    # Increment pick number
    draft_state.current_pick += 1

    # Create draft pick
    pick = DraftPick(
        team_id=team_id,
        price=price,
        pick_number=draft_state.current_pick,
    )
    session.add(pick)
    session.flush()  # Get the pick ID

    # Update player
    player.is_drafted = True
    player.draft_pick_id = pick.id

    # Mark values as stale
    draft_state.values_stale = True

    session.commit()
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


def undo_pick(session: Session, pick_id: int) -> Player | None:
    """
    Undo a specific draft pick.

    Args:
        session: Database session
        pick_id: ID of the pick to undo

    Returns:
        The player who was undrafted, or None if pick not found
    """
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

    # Mark values as stale
    draft_state = get_draft_state(session)
    if draft_state:
        draft_state.values_stale = True

    session.commit()
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
