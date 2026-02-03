"""Snake draft logic and utilities."""

from sqlalchemy.orm import Session

from .database import DraftState, Team


def get_serpentine_pick_order(draft_order: list[int], num_rounds: int) -> list[tuple[int, int, int]]:
    """
    Generate the complete serpentine (snake) draft pick order.

    In a snake draft, odd rounds go in order (1, 2, 3...) and even rounds
    go in reverse order (...3, 2, 1).

    Args:
        draft_order: List of team_ids in first-round order
        num_rounds: Total number of rounds in the draft

    Returns:
        List of tuples: (round_number, pick_in_round, team_id)
        where round_number and pick_in_round are 1-based
    """
    picks = []
    num_teams = len(draft_order)

    for round_num in range(1, num_rounds + 1):
        if round_num % 2 == 1:
            # Odd round: normal order
            for pick_in_round, team_id in enumerate(draft_order, start=1):
                picks.append((round_num, pick_in_round, team_id))
        else:
            # Even round: reverse order
            for pick_in_round, team_id in enumerate(reversed(draft_order), start=1):
                picks.append((round_num, pick_in_round, team_id))

    return picks


def get_current_drafter(draft_state: DraftState) -> int | None:
    """
    Determine which team is currently on the clock in a snake draft.

    Args:
        draft_state: Current draft state

    Returns:
        team_id of the team that should pick next, or None if draft is complete
    """
    if not draft_state or draft_state.draft_type != "snake":
        return None

    if not draft_state.draft_order:
        return None

    num_teams = len(draft_state.draft_order)
    total_picks_made = draft_state.current_pick

    # Calculate current round and position
    current_round = (total_picks_made // num_teams) + 1
    pick_in_round = (total_picks_made % num_teams) + 1

    # Check if draft is complete (this would need rounds_per_team from settings)
    # For now, we assume the draft continues until all rounds are done

    if current_round % 2 == 1:
        # Odd round: normal order (1-indexed)
        team_idx = pick_in_round - 1
    else:
        # Even round: reverse order
        team_idx = num_teams - pick_in_round

    if team_idx < 0 or team_idx >= num_teams:
        return None

    return draft_state.draft_order[team_idx]


def get_pick_position(draft_state: DraftState) -> tuple[int, int]:
    """
    Get the current round and pick position within that round.

    Args:
        draft_state: Current draft state

    Returns:
        Tuple of (round_number, pick_in_round), both 1-based
    """
    if not draft_state or draft_state.draft_type != "snake":
        return (1, 1)

    if not draft_state.draft_order:
        return (1, 1)

    num_teams = len(draft_state.draft_order)
    total_picks_made = draft_state.current_pick

    current_round = (total_picks_made // num_teams) + 1
    pick_in_round = (total_picks_made % num_teams) + 1

    return (current_round, pick_in_round)


def get_team_next_pick(draft_state: DraftState, team_id: int) -> int | None:
    """
    Calculate how many picks until a specific team picks again.

    Args:
        draft_state: Current draft state
        team_id: The team to check

    Returns:
        Number of picks until team picks (0 if they're on the clock),
        or None if team not found or draft is complete
    """
    if not draft_state or draft_state.draft_type != "snake":
        return None

    if not draft_state.draft_order:
        return None

    if team_id not in draft_state.draft_order:
        return None

    num_teams = len(draft_state.draft_order)
    total_picks_made = draft_state.current_pick

    # Find the team's position in draft order (0-indexed)
    team_position = draft_state.draft_order.index(team_id)

    # Calculate current round and pick position
    current_round = (total_picks_made // num_teams) + 1
    pick_in_round = total_picks_made % num_teams  # 0-indexed for calculation

    # Look ahead to find when team picks next
    picks_away = 0
    search_round = current_round
    search_pick = pick_in_round

    # Limit search to prevent infinite loop
    max_search = num_teams * 2 + 1

    while picks_away < max_search:
        # Determine who picks at this position
        if search_round % 2 == 1:
            # Odd round: normal order
            picking_team_idx = search_pick
        else:
            # Even round: reverse order
            picking_team_idx = num_teams - 1 - search_pick

        if picking_team_idx == team_position:
            return picks_away

        picks_away += 1
        search_pick += 1

        if search_pick >= num_teams:
            search_pick = 0
            search_round += 1

    return None


def is_teams_turn(draft_state: DraftState, team_id: int) -> bool:
    """
    Check if it's a specific team's turn to pick.

    Args:
        draft_state: Current draft state
        team_id: The team to check

    Returns:
        True if it's this team's turn, False otherwise
    """
    current_drafter = get_current_drafter(draft_state)
    return current_drafter == team_id


def get_overall_pick_number(round_number: int, pick_in_round: int, num_teams: int) -> int:
    """
    Convert round/pick to overall pick number.

    Args:
        round_number: 1-based round number
        pick_in_round: 1-based pick within round
        num_teams: Number of teams in draft

    Returns:
        Overall pick number (1-based)
    """
    return (round_number - 1) * num_teams + pick_in_round


def format_pick_display(round_number: int, pick_in_round: int, num_teams: int) -> str:
    """
    Format a pick for display (e.g., "Round 3, Pick 7 (31st overall)").

    Args:
        round_number: 1-based round number
        pick_in_round: 1-based pick within round
        num_teams: Number of teams in draft

    Returns:
        Formatted string for display
    """
    overall = get_overall_pick_number(round_number, pick_in_round, num_teams)

    # Determine suffix for ordinal
    if 11 <= overall % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(overall % 10, "th")

    return f"Round {round_number}, Pick {pick_in_round} ({overall}{suffix} overall)"
