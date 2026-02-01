"""Target list management for the fantasy baseball draft tool."""

from sqlalchemy.orm import Session
from .database import Player, TargetPlayer


def add_target(session: Session, player_id: int, max_bid: int, priority: int = 0, notes: str = None) -> TargetPlayer:
    """
    Add a player to the target list.

    Args:
        session: Database session
        player_id: ID of the player to target
        max_bid: Maximum price willing to pay
        priority: Priority level (higher = more important)
        notes: Optional notes about the player

    Returns:
        The created TargetPlayer object

    Raises:
        ValueError: If player doesn't exist or is already targeted
    """
    # Check if player exists
    player = session.get(Player, player_id)
    if not player:
        raise ValueError(f"Player with ID {player_id} not found")

    # Check if already targeted
    existing = session.query(TargetPlayer).filter(TargetPlayer.player_id == player_id).first()
    if existing:
        raise ValueError(f"{player.name} is already on your target list")

    target = TargetPlayer(
        player_id=player_id,
        max_bid=max_bid,
        priority=priority,
        notes=notes,
    )
    session.add(target)
    session.commit()
    return target


def remove_target(session: Session, player_id: int) -> bool:
    """
    Remove a player from the target list.

    Args:
        session: Database session
        player_id: ID of the player to remove

    Returns:
        True if removed, False if not found
    """
    target = session.query(TargetPlayer).filter(TargetPlayer.player_id == player_id).first()
    if target:
        session.delete(target)
        session.commit()
        return True
    return False


def update_target(session: Session, player_id: int, max_bid: int = None, priority: int = None, notes: str = None) -> TargetPlayer:
    """
    Update a target's max bid, priority, or notes.

    Args:
        session: Database session
        player_id: ID of the targeted player
        max_bid: New maximum bid (optional)
        priority: New priority level (optional)
        notes: New notes (optional, pass empty string to clear)

    Returns:
        The updated TargetPlayer object

    Raises:
        ValueError: If player is not on target list
    """
    target = session.query(TargetPlayer).filter(TargetPlayer.player_id == player_id).first()
    if not target:
        raise ValueError("Player is not on your target list")

    if max_bid is not None:
        target.max_bid = max_bid
    if priority is not None:
        target.priority = priority
    if notes is not None:
        target.notes = notes if notes else None

    session.commit()
    return target


def get_targets(session: Session, include_drafted: bool = False) -> list[TargetPlayer]:
    """
    Get all targeted players.

    Args:
        session: Database session
        include_drafted: If True, include players that have been drafted

    Returns:
        List of TargetPlayer objects sorted by priority (desc) then value (desc)
    """
    query = session.query(TargetPlayer).join(Player)

    if not include_drafted:
        query = query.filter(Player.is_drafted == False)

    # Sort by priority descending, then by dollar value descending
    targets = query.all()
    targets.sort(key=lambda t: (t.priority, t.player.dollar_value or 0), reverse=True)
    return targets


def get_target_player_ids(session: Session) -> set[int]:
    """
    Get a set of player IDs that are on the target list.

    Useful for quickly checking if a player is targeted.

    Returns:
        Set of player IDs
    """
    targets = session.query(TargetPlayer.player_id).all()
    return {t[0] for t in targets}


def get_target_by_player_id(session: Session, player_id: int) -> TargetPlayer | None:
    """
    Get target info for a specific player.

    Args:
        session: Database session
        player_id: ID of the player

    Returns:
        TargetPlayer object or None if not targeted
    """
    return session.query(TargetPlayer).filter(TargetPlayer.player_id == player_id).first()


def clear_all_targets(session: Session) -> int:
    """
    Remove all players from the target list.

    Returns:
        Number of targets removed
    """
    count = session.query(TargetPlayer).delete()
    session.commit()
    return count


def get_available_targets_below_value(session: Session) -> list[dict]:
    """
    Get available targets where current value is at or below max bid.

    These are "bargain" targets that the user should consider bidding on.

    Returns:
        List of dicts with target info and bargain amount
    """
    targets = get_targets(session, include_drafted=False)
    bargains = []

    for target in targets:
        player = target.player
        if player and not player.is_drafted and player.dollar_value:
            if player.dollar_value <= target.max_bid:
                bargains.append({
                    "player": player,
                    "target": target,
                    "value": player.dollar_value,
                    "max_bid": target.max_bid,
                    "headroom": target.max_bid - player.dollar_value,
                })

    # Sort by headroom (most room to bid first)
    bargains.sort(key=lambda x: x["headroom"], reverse=True)
    return bargains
