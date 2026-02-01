"""Tests for target list functionality."""

import pytest
from src.database import Player, TargetPlayer
from src.targets import (
    add_target,
    remove_target,
    update_target,
    get_targets,
    get_target_player_ids,
    get_target_by_player_id,
    clear_all_targets,
    get_available_targets_below_value,
)


class TestAddTarget:
    """Tests for add_target function."""

    def test_add_target_basic(self, session, sample_hitter):
        """Test adding a player to targets with basic parameters."""
        target = add_target(session, sample_hitter.id, max_bid=30)

        assert target is not None
        assert target.player_id == sample_hitter.id
        assert target.max_bid == 30
        assert target.priority == 0
        assert target.notes is None

    def test_add_target_with_priority_and_notes(self, session, sample_hitter):
        """Test adding a target with priority and notes."""
        target = add_target(
            session,
            sample_hitter.id,
            max_bid=25,
            priority=2,
            notes="Great power upside"
        )

        assert target.max_bid == 25
        assert target.priority == 2
        assert target.notes == "Great power upside"

    def test_add_target_nonexistent_player(self, session):
        """Test adding a nonexistent player raises error."""
        with pytest.raises(ValueError, match="not found"):
            add_target(session, player_id=9999, max_bid=10)

    def test_add_target_already_targeted(self, session, sample_hitter):
        """Test adding the same player twice raises error."""
        add_target(session, sample_hitter.id, max_bid=30)

        with pytest.raises(ValueError, match="already on your target list"):
            add_target(session, sample_hitter.id, max_bid=25)


class TestRemoveTarget:
    """Tests for remove_target function."""

    def test_remove_target_success(self, session, sample_hitter):
        """Test removing an existing target."""
        add_target(session, sample_hitter.id, max_bid=30)

        result = remove_target(session, sample_hitter.id)

        assert result is True
        assert get_target_by_player_id(session, sample_hitter.id) is None

    def test_remove_target_not_found(self, session, sample_hitter):
        """Test removing a player not on target list."""
        result = remove_target(session, sample_hitter.id)

        assert result is False


class TestUpdateTarget:
    """Tests for update_target function."""

    def test_update_max_bid(self, session, sample_hitter):
        """Test updating the max bid."""
        add_target(session, sample_hitter.id, max_bid=30)

        target = update_target(session, sample_hitter.id, max_bid=35)

        assert target.max_bid == 35

    def test_update_priority(self, session, sample_hitter):
        """Test updating priority."""
        add_target(session, sample_hitter.id, max_bid=30, priority=0)

        target = update_target(session, sample_hitter.id, priority=2)

        assert target.priority == 2
        assert target.max_bid == 30  # Unchanged

    def test_update_notes(self, session, sample_hitter):
        """Test updating notes."""
        add_target(session, sample_hitter.id, max_bid=30)

        target = update_target(session, sample_hitter.id, notes="New note")

        assert target.notes == "New note"

    def test_update_clear_notes(self, session, sample_hitter):
        """Test clearing notes with empty string."""
        add_target(session, sample_hitter.id, max_bid=30, notes="Old note")

        target = update_target(session, sample_hitter.id, notes="")

        assert target.notes is None

    def test_update_nonexistent_target(self, session, sample_hitter):
        """Test updating a player not on target list raises error."""
        with pytest.raises(ValueError, match="not on your target list"):
            update_target(session, sample_hitter.id, max_bid=30)


class TestGetTargets:
    """Tests for get_targets function."""

    def test_get_targets_empty(self, session):
        """Test getting targets when none exist."""
        targets = get_targets(session)

        assert targets == []

    def test_get_targets_sorted_by_priority(self, session):
        """Test targets are sorted by priority (highest first)."""
        # Create multiple players
        player1 = Player(name="Player 1", player_type="hitter", dollar_value=20)
        player2 = Player(name="Player 2", player_type="hitter", dollar_value=25)
        player3 = Player(name="Player 3", player_type="hitter", dollar_value=15)
        session.add_all([player1, player2, player3])
        session.commit()

        # Add targets with different priorities
        add_target(session, player1.id, max_bid=20, priority=0)  # Low
        add_target(session, player2.id, max_bid=25, priority=2)  # High
        add_target(session, player3.id, max_bid=15, priority=1)  # Medium

        targets = get_targets(session)

        assert len(targets) == 3
        assert targets[0].player.name == "Player 2"  # High priority
        assert targets[1].player.name == "Player 3"  # Medium priority
        assert targets[2].player.name == "Player 1"  # Low priority

    def test_get_targets_excludes_drafted(self, session, sample_hitter):
        """Test that drafted players are excluded by default."""
        add_target(session, sample_hitter.id, max_bid=30)
        sample_hitter.is_drafted = True
        session.commit()

        targets = get_targets(session, include_drafted=False)

        assert len(targets) == 0

    def test_get_targets_includes_drafted(self, session, sample_hitter):
        """Test that drafted players can be included."""
        add_target(session, sample_hitter.id, max_bid=30)
        sample_hitter.is_drafted = True
        session.commit()

        targets = get_targets(session, include_drafted=True)

        assert len(targets) == 1


class TestGetTargetPlayerIds:
    """Tests for get_target_player_ids function."""

    def test_get_ids_empty(self, session):
        """Test getting IDs when no targets exist."""
        ids = get_target_player_ids(session)

        assert ids == set()

    def test_get_ids_multiple(self, session):
        """Test getting IDs for multiple targets."""
        player1 = Player(name="Player 1", player_type="hitter")
        player2 = Player(name="Player 2", player_type="hitter")
        session.add_all([player1, player2])
        session.commit()

        add_target(session, player1.id, max_bid=20)
        add_target(session, player2.id, max_bid=25)

        ids = get_target_player_ids(session)

        assert ids == {player1.id, player2.id}


class TestGetTargetByPlayerId:
    """Tests for get_target_by_player_id function."""

    def test_get_existing_target(self, session, sample_hitter):
        """Test getting an existing target."""
        add_target(session, sample_hitter.id, max_bid=30, notes="Test note")

        target = get_target_by_player_id(session, sample_hitter.id)

        assert target is not None
        assert target.max_bid == 30
        assert target.notes == "Test note"

    def test_get_nonexistent_target(self, session, sample_hitter):
        """Test getting a non-targeted player returns None."""
        target = get_target_by_player_id(session, sample_hitter.id)

        assert target is None


class TestClearAllTargets:
    """Tests for clear_all_targets function."""

    def test_clear_targets(self, session):
        """Test clearing all targets."""
        player1 = Player(name="Player 1", player_type="hitter")
        player2 = Player(name="Player 2", player_type="hitter")
        session.add_all([player1, player2])
        session.commit()

        add_target(session, player1.id, max_bid=20)
        add_target(session, player2.id, max_bid=25)

        count = clear_all_targets(session)

        assert count == 2
        assert len(get_targets(session)) == 0


class TestGetAvailableTargetsBelowValue:
    """Tests for get_available_targets_below_value function."""

    def test_bargain_targets(self, session):
        """Test finding targets where value is at or below max bid."""
        player1 = Player(name="Bargain", player_type="hitter", dollar_value=20)
        player2 = Player(name="Overpriced", player_type="hitter", dollar_value=40)
        session.add_all([player1, player2])
        session.commit()

        add_target(session, player1.id, max_bid=25)  # 5$ headroom
        add_target(session, player2.id, max_bid=30)  # Negative headroom

        bargains = get_available_targets_below_value(session)

        assert len(bargains) == 1
        assert bargains[0]["player"].name == "Bargain"
        assert bargains[0]["headroom"] == 5

    def test_excludes_drafted(self, session):
        """Test that drafted players are excluded from bargains."""
        player = Player(name="Drafted Bargain", player_type="hitter", dollar_value=20)
        session.add(player)
        session.commit()

        add_target(session, player.id, max_bid=30)
        player.is_drafted = True
        session.commit()

        bargains = get_available_targets_below_value(session)

        assert len(bargains) == 0

    def test_sorted_by_headroom(self, session):
        """Test bargains are sorted by headroom (most room first)."""
        player1 = Player(name="Small Headroom", player_type="hitter", dollar_value=28)
        player2 = Player(name="Big Headroom", player_type="hitter", dollar_value=20)
        session.add_all([player1, player2])
        session.commit()

        add_target(session, player1.id, max_bid=30)  # 2$ headroom
        add_target(session, player2.id, max_bid=30)  # 10$ headroom

        bargains = get_available_targets_below_value(session)

        assert len(bargains) == 2
        assert bargains[0]["player"].name == "Big Headroom"
        assert bargains[1]["player"].name == "Small Headroom"
