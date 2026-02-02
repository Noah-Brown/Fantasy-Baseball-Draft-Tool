"""Tests for draft functionality."""

import pytest
from src.database import Player, Team, DraftPick, DraftState
from src.draft import (
    initialize_draft,
    draft_player,
    undo_last_pick,
    undo_pick,
    get_draft_history,
    reset_draft,
    get_draft_state,
    get_all_teams,
    get_user_team,
    get_remaining_roster_slots,
    get_remaining_budget,
    get_best_available_by_position,
)
from src.settings import LeagueSettings


@pytest.fixture
def test_settings():
    """Create test league settings with smaller values."""
    return LeagueSettings(
        name="Test League",
        num_teams=4,
        budget_per_team=100,
    )


@pytest.fixture
def populated_db(session):
    """Create a database with some players."""
    players = [
        Player(name="Mike Trout", team="LAA", positions="CF", player_type="hitter",
               pa=600, r=100, hr=40, rbi=100, sb=10, avg=0.300, dollar_value=50),
        Player(name="Mookie Betts", team="LAD", positions="OF,2B", player_type="hitter",
               pa=580, r=95, hr=30, rbi=85, sb=15, avg=0.280, dollar_value=40),
        Player(name="Juan Soto", team="NYY", positions="OF", player_type="hitter",
               pa=620, r=90, hr=35, rbi=95, sb=5, avg=0.290, dollar_value=45),
        Player(name="Gerrit Cole", team="NYY", positions="SP", player_type="pitcher",
               ip=200, w=15, sv=0, k=250, era=3.00, whip=1.00, dollar_value=35),
        Player(name="Spencer Strider", team="ATL", positions="SP", player_type="pitcher",
               ip=180, w=14, sv=0, k=230, era=2.80, whip=0.95, dollar_value=32),
    ]
    for p in players:
        session.add(p)
    session.commit()
    return players


class TestInitializeDraft:
    """Tests for draft initialization."""

    def test_initialize_draft_creates_teams(self, session, populated_db, test_settings):
        """Test that initializing draft creates correct number of teams."""
        initialize_draft(session, test_settings, "My Team")

        teams = get_all_teams(session)
        assert len(teams) == 4

    def test_initialize_draft_marks_user_team(self, session, populated_db, test_settings):
        """Test that user's team is marked correctly."""
        initialize_draft(session, test_settings, "Champions")

        user_team = get_user_team(session)
        assert user_team is not None
        assert user_team.name == "Champions"
        assert user_team.is_user_team is True

    def test_initialize_draft_creates_draft_state(self, session, populated_db, test_settings):
        """Test that draft state is created."""
        initialize_draft(session, test_settings, "My Team")

        state = get_draft_state(session)
        assert state is not None
        assert state.is_active is True
        assert state.num_teams == 4
        assert state.budget_per_team == 100
        assert state.values_stale is False

    def test_initialize_draft_resets_player_flags(self, session, test_settings):
        """Test that player drafted flags are reset."""
        # Create a player marked as drafted
        player = Player(name="Test Player", player_type="hitter", is_drafted=True)
        session.add(player)
        session.commit()

        initialize_draft(session, test_settings, "My Team")

        # Refresh the player
        session.refresh(player)
        assert player.is_drafted is False

    def test_initialize_draft_clears_existing_draft(self, session, populated_db, test_settings):
        """Test that initializing clears existing draft data."""
        # Initialize once
        initialize_draft(session, test_settings, "First Team")

        # Initialize again
        initialize_draft(session, test_settings, "Second Team")

        # Should only have new teams
        teams = get_all_teams(session)
        assert len(teams) == 4

        user_team = get_user_team(session)
        assert user_team.name == "Second Team"


class TestDraftPlayer:
    """Tests for drafting players."""

    def test_draft_player_success(self, session, populated_db, test_settings):
        """Test successful player draft."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        team = teams[0]
        player = populated_db[0]  # Mike Trout

        pick = draft_player(session, player.id, team.id, 45)

        assert pick is not None
        assert pick.price == 45
        assert pick.team_id == team.id
        assert pick.pick_number == 1

        # Verify player is marked as drafted
        session.refresh(player)
        assert player.is_drafted is True
        assert player.draft_pick_id == pick.id

    def test_draft_player_updates_budget(self, session, populated_db, test_settings):
        """Test that drafting updates team budget."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        team = teams[0]
        player = populated_db[0]

        draft_player(session, player.id, team.id, 30)

        session.refresh(team)
        assert team.remaining_budget == 70

    def test_draft_player_auto_recalculates_values(self, session, populated_db, test_settings):
        """Test that drafting auto-recalculates values (values_stale is False)."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]

        draft_player(session, player.id, teams[0].id, 25)

        # Values should not be stale because auto-recalculation happens
        state = get_draft_state(session)
        assert state.values_stale is False

    def test_draft_player_already_drafted_fails(self, session, populated_db, test_settings):
        """Test that drafting already-drafted player fails."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]

        # Draft once
        draft_player(session, player.id, teams[0].id, 25)

        # Try to draft again
        with pytest.raises(ValueError, match="already been drafted"):
            draft_player(session, player.id, teams[1].id, 20)

    def test_draft_player_insufficient_budget_fails(self, session, populated_db, test_settings):
        """Test that drafting with insufficient budget fails."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]

        # Try to spend more than budget
        with pytest.raises(ValueError, match="only has"):
            draft_player(session, player.id, teams[0].id, 150)

    def test_draft_player_minimum_price(self, session, populated_db, test_settings):
        """Test that minimum price is enforced."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]

        with pytest.raises(ValueError, match="at least"):
            draft_player(session, player.id, teams[0].id, 0)

    def test_draft_player_increments_pick_number(self, session, populated_db, test_settings):
        """Test that pick numbers increment correctly."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        pick1 = draft_player(session, populated_db[0].id, teams[0].id, 10)
        pick2 = draft_player(session, populated_db[1].id, teams[1].id, 10)
        pick3 = draft_player(session, populated_db[2].id, teams[0].id, 10)

        assert pick1.pick_number == 1
        assert pick2.pick_number == 2
        assert pick3.pick_number == 3


class TestUndoFunctionality:
    """Tests for undo operations."""

    def test_undo_last_pick(self, session, populated_db, test_settings):
        """Test undoing the last pick."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]

        draft_player(session, player.id, teams[0].id, 30)

        undone_player = undo_last_pick(session)

        assert undone_player.id == player.id
        session.refresh(player)
        assert player.is_drafted is False
        assert player.draft_pick_id is None

    def test_undo_last_pick_restores_budget(self, session, populated_db, test_settings):
        """Test that undo restores team budget."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        team = teams[0]

        draft_player(session, populated_db[0].id, team.id, 30)
        assert team.remaining_budget == 70

        undo_last_pick(session)

        session.refresh(team)
        assert team.remaining_budget == 100

    def test_undo_specific_pick(self, session, populated_db, test_settings):
        """Test undoing a specific pick."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        pick1 = draft_player(session, populated_db[0].id, teams[0].id, 10)
        pick2 = draft_player(session, populated_db[1].id, teams[1].id, 10)

        # Undo the first pick specifically
        undone_player = undo_pick(session, pick1.id)

        assert undone_player.id == populated_db[0].id
        session.refresh(populated_db[0])
        assert populated_db[0].is_drafted is False

        # Second pick should still exist
        session.refresh(populated_db[1])
        assert populated_db[1].is_drafted is True

    def test_undo_auto_recalculates_values(self, session, populated_db, test_settings):
        """Test that undo auto-recalculates values (values_stale is False)."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        draft_player(session, populated_db[0].id, teams[0].id, 25)

        undo_last_pick(session)

        # Values should not be stale because auto-recalculation happens
        state = get_draft_state(session)
        assert state.values_stale is False

    def test_undo_no_picks_returns_none(self, session, populated_db, test_settings):
        """Test that undo with no picks returns None."""
        initialize_draft(session, test_settings, "My Team")

        result = undo_last_pick(session)
        assert result is None


class TestDraftHistory:
    """Tests for draft history retrieval."""

    def test_get_draft_history(self, session, populated_db, test_settings):
        """Test getting draft history."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        draft_player(session, populated_db[0].id, teams[0].id, 30)
        draft_player(session, populated_db[1].id, teams[1].id, 25)

        history = get_draft_history(session)

        assert len(history) == 2
        # Should be ordered most recent first
        assert history[0]["player_name"] == "Mookie Betts"
        assert history[1]["player_name"] == "Mike Trout"

    def test_get_draft_history_with_limit(self, session, populated_db, test_settings):
        """Test getting draft history with limit."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        draft_player(session, populated_db[0].id, teams[0].id, 30)
        draft_player(session, populated_db[1].id, teams[1].id, 25)
        draft_player(session, populated_db[2].id, teams[0].id, 20)

        history = get_draft_history(session, limit=2)

        assert len(history) == 2
        assert history[0]["player_name"] == "Juan Soto"

    def test_get_draft_history_empty(self, session, populated_db, test_settings):
        """Test getting draft history with no picks."""
        initialize_draft(session, test_settings, "My Team")

        history = get_draft_history(session)
        assert history == []

    def test_draft_history_includes_pick_info(self, session, populated_db, test_settings):
        """Test that history includes all expected fields."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        draft_player(session, populated_db[0].id, teams[0].id, 42)

        history = get_draft_history(session)

        assert len(history) == 1
        pick = history[0]
        assert "pick_id" in pick
        assert "pick_number" in pick
        assert "player_name" in pick
        assert "player_id" in pick
        assert "team_name" in pick
        assert "team_id" in pick
        assert "price" in pick
        assert "timestamp" in pick
        assert pick["price"] == 42


class TestResetDraft:
    """Tests for draft reset."""

    def test_reset_draft_clears_teams(self, session, populated_db, test_settings):
        """Test that reset clears all teams."""
        initialize_draft(session, test_settings, "My Team")

        reset_draft(session)

        teams = get_all_teams(session)
        assert len(teams) == 0

    def test_reset_draft_clears_picks(self, session, populated_db, test_settings):
        """Test that reset clears all draft picks."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        draft_player(session, populated_db[0].id, teams[0].id, 25)

        reset_draft(session)

        picks = session.query(DraftPick).all()
        assert len(picks) == 0

    def test_reset_draft_clears_state(self, session, populated_db, test_settings):
        """Test that reset clears draft state."""
        initialize_draft(session, test_settings, "My Team")

        reset_draft(session)

        state = get_draft_state(session)
        assert state is None

    def test_reset_draft_resets_player_flags(self, session, populated_db, test_settings):
        """Test that reset resets player drafted flags."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)
        player = populated_db[0]
        draft_player(session, player.id, teams[0].id, 25)

        reset_draft(session)

        session.refresh(player)
        assert player.is_drafted is False
        assert player.draft_pick_id is None


class TestRemainingCalculations:
    """Tests for remaining roster slots and budget calculations."""

    def test_get_remaining_roster_slots_initial(self, session, populated_db, test_settings):
        """Test remaining slots before any picks."""
        initialize_draft(session, test_settings, "My Team")

        slots = get_remaining_roster_slots(session, test_settings)

        assert slots["hitters"] == test_settings.total_hitters_drafted
        assert slots["pitchers"] == test_settings.total_pitchers_drafted

    def test_get_remaining_roster_slots_after_draft(self, session, populated_db, test_settings):
        """Test remaining slots after drafting."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        # Draft 2 hitters
        draft_player(session, populated_db[0].id, teams[0].id, 10)
        draft_player(session, populated_db[1].id, teams[1].id, 10)

        slots = get_remaining_roster_slots(session, test_settings)

        assert slots["hitters"] == test_settings.total_hitters_drafted - 2

    def test_get_remaining_budget_initial(self, session, populated_db, test_settings):
        """Test remaining budget before any picks."""
        initialize_draft(session, test_settings, "My Team")

        budget = get_remaining_budget(session)

        # 4 teams * $100 each
        assert budget == 400

    def test_get_remaining_budget_after_draft(self, session, populated_db, test_settings):
        """Test remaining budget after drafting."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        draft_player(session, populated_db[0].id, teams[0].id, 30)
        draft_player(session, populated_db[1].id, teams[1].id, 25)

        budget = get_remaining_budget(session)

        # 400 - 30 - 25 = 345
        assert budget == 345


class TestGetBestAvailableByPosition:
    """Tests for get_best_available_by_position."""

    def test_returns_dict_with_all_positions(self, session, populated_db, test_settings):
        """Test that function returns dict with all scarcity positions."""
        initialize_draft(session, test_settings, "My Team")

        best_available = get_best_available_by_position(session)

        from src.positions import SCARCITY_POSITIONS
        for pos in SCARCITY_POSITIONS:
            assert pos in best_available

    def test_returns_top_n_players(self, session, populated_db, test_settings):
        """Test that function returns up to top_n players per position."""
        initialize_draft(session, test_settings, "My Team")

        # With default top_n=5
        best_available = get_best_available_by_position(session, top_n=5)

        # Check each position has at most 5 players
        for pos, players in best_available.items():
            assert len(players) <= 5

    def test_excludes_drafted_players(self, session, populated_db, test_settings):
        """Test that drafted players are excluded."""
        initialize_draft(session, test_settings, "My Team")
        teams = get_all_teams(session)

        # Get best available before draft
        best_before = get_best_available_by_position(session)

        # Draft the first player (a hitter with position 1B,3B)
        draft_player(session, populated_db[0].id, teams[0].id, 30)

        # Get best available after draft
        best_after = get_best_available_by_position(session)

        # The drafted player should not be in any position list
        drafted_player = populated_db[0]
        for pos, players in best_after.items():
            player_ids = [p.id for p in players]
            assert drafted_player.id not in player_ids

    def test_players_sorted_by_value_descending(self, session, populated_db, test_settings):
        """Test that players are sorted by dollar value (highest first)."""
        initialize_draft(session, test_settings, "My Team")

        best_available = get_best_available_by_position(session)

        for pos, players in best_available.items():
            if len(players) >= 2:
                for i in range(len(players) - 1):
                    current_value = players[i].dollar_value or 0
                    next_value = players[i + 1].dollar_value or 0
                    assert current_value >= next_value
