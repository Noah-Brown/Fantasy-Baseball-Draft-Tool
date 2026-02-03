"""Tests for snake draft functionality."""

import pytest
from src.database import Player, Team, DraftPick, DraftState
from src.snake import (
    get_serpentine_pick_order,
    get_current_drafter,
    get_pick_position,
    get_team_next_pick,
    is_teams_turn,
    get_overall_pick_number,
    format_pick_display,
)
from src.draft import (
    initialize_draft,
    draft_player,
    get_draft_state,
    get_all_teams,
    get_user_team,
    get_on_the_clock_team,
)
from src.settings import LeagueSettings


@pytest.fixture
def snake_settings():
    """Create test league settings for snake draft."""
    return LeagueSettings(
        name="Test Snake League",
        num_teams=4,
        budget_per_team=260,  # Not used in snake but required
        draft_type="snake",
        rounds_per_team=5,
    )


@pytest.fixture
def auction_settings():
    """Create test league settings for auction draft."""
    return LeagueSettings(
        name="Test Auction League",
        num_teams=4,
        budget_per_team=100,
        draft_type="auction",
    )


@pytest.fixture
def populated_db(session):
    """Create a database with some players."""
    players = [
        Player(name="Mike Trout", team="LAA", positions="CF", player_type="hitter",
               pa=600, r=100, hr=40, rbi=100, sb=10, avg=0.300, dollar_value=50, sgp=10.0),
        Player(name="Mookie Betts", team="LAD", positions="OF,2B", player_type="hitter",
               pa=580, r=95, hr=30, rbi=85, sb=15, avg=0.280, dollar_value=40, sgp=8.0),
        Player(name="Juan Soto", team="NYY", positions="OF", player_type="hitter",
               pa=620, r=90, hr=35, rbi=95, sb=5, avg=0.290, dollar_value=45, sgp=9.0),
        Player(name="Gerrit Cole", team="NYY", positions="SP", player_type="pitcher",
               ip=200, w=15, sv=0, k=250, era=3.00, whip=1.00, dollar_value=35, sgp=7.0),
        Player(name="Spencer Strider", team="ATL", positions="SP", player_type="pitcher",
               ip=180, w=14, sv=0, k=230, era=2.80, whip=0.95, dollar_value=32, sgp=6.5),
        Player(name="Corey Seager", team="TEX", positions="SS", player_type="hitter",
               pa=550, r=85, hr=30, rbi=90, sb=3, avg=0.275, dollar_value=35, sgp=7.5),
        Player(name="Ronald Acuna", team="ATL", positions="OF", player_type="hitter",
               pa=640, r=110, hr=35, rbi=80, sb=40, avg=0.285, dollar_value=55, sgp=12.0),
        Player(name="Shohei Ohtani", team="LAD", positions="DH", player_type="hitter",
               pa=600, r=100, hr=45, rbi=100, sb=15, avg=0.290, dollar_value=60, sgp=13.0),
    ]
    for p in players:
        session.add(p)
    session.commit()
    return players


class TestSerpentinePickOrder:
    """Tests for serpentine pick order generation."""

    def test_serpentine_4_teams_3_rounds(self):
        """Test serpentine order for 4 teams, 3 rounds."""
        draft_order = [1, 2, 3, 4]  # Team IDs
        picks = get_serpentine_pick_order(draft_order, 3)

        # Round 1: 1, 2, 3, 4
        # Round 2: 4, 3, 2, 1
        # Round 3: 1, 2, 3, 4
        expected = [
            (1, 1, 1), (1, 2, 2), (1, 3, 3), (1, 4, 4),  # Round 1
            (2, 1, 4), (2, 2, 3), (2, 3, 2), (2, 4, 1),  # Round 2
            (3, 1, 1), (3, 2, 2), (3, 3, 3), (3, 4, 4),  # Round 3
        ]
        assert picks == expected

    def test_serpentine_total_picks(self):
        """Test that total picks equals teams * rounds."""
        draft_order = [10, 20, 30]
        picks = get_serpentine_pick_order(draft_order, 5)

        assert len(picks) == 15  # 3 teams * 5 rounds

    def test_serpentine_single_round(self):
        """Test single round order."""
        draft_order = [1, 2, 3]
        picks = get_serpentine_pick_order(draft_order, 1)

        expected = [(1, 1, 1), (1, 2, 2), (1, 3, 3)]
        assert picks == expected

    def test_serpentine_preserves_order_odd_rounds(self):
        """Test that odd rounds maintain original order."""
        draft_order = [100, 200, 300, 400]
        picks = get_serpentine_pick_order(draft_order, 3)

        # Check round 1 (odd)
        round_1 = [p[2] for p in picks if p[0] == 1]
        assert round_1 == [100, 200, 300, 400]

        # Check round 3 (odd)
        round_3 = [p[2] for p in picks if p[0] == 3]
        assert round_3 == [100, 200, 300, 400]

    def test_serpentine_reverses_even_rounds(self):
        """Test that even rounds reverse the order."""
        draft_order = [100, 200, 300, 400]
        picks = get_serpentine_pick_order(draft_order, 2)

        # Check round 2 (even)
        round_2 = [p[2] for p in picks if p[0] == 2]
        assert round_2 == [400, 300, 200, 100]


class TestCurrentDrafter:
    """Tests for determining current drafter."""

    def test_first_pick(self, session, populated_db, snake_settings):
        """Test that first pick goes to first team in order."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        current = get_current_drafter(draft_state)
        assert current == teams[0].id

    def test_second_pick(self, session, populated_db, snake_settings):
        """Test that second pick goes to second team."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        # Make first pick
        draft_player(session, populated_db[0].id, teams[0].id, settings=snake_settings)

        draft_state = get_draft_state(session)
        current = get_current_drafter(draft_state)
        assert current == teams[1].id

    def test_snake_turn_after_round(self, session, populated_db, snake_settings):
        """Test that order reverses after first round."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        # Draft all 4 picks in round 1
        for i in range(4):
            draft_state = get_draft_state(session)
            current_team_id = get_current_drafter(draft_state)
            draft_player(session, populated_db[i].id, current_team_id, settings=snake_settings)

        # Now round 2 should start with last team
        draft_state = get_draft_state(session)
        current = get_current_drafter(draft_state)
        assert current == teams[3].id  # Team 4 picks first in round 2

    def test_non_snake_returns_none(self, session, populated_db, auction_settings):
        """Test that auction draft returns None."""
        initialize_draft(session, auction_settings, "My Team")
        draft_state = get_draft_state(session)

        current = get_current_drafter(draft_state)
        assert current is None


class TestPickPosition:
    """Tests for getting current pick position."""

    def test_initial_position(self, session, populated_db, snake_settings):
        """Test initial position is round 1, pick 1."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)

        round_num, pick_in_round = get_pick_position(draft_state)
        assert round_num == 1
        assert pick_in_round == 1

    def test_mid_round_position(self, session, populated_db, snake_settings):
        """Test position after a few picks."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        # Make 2 picks
        draft_player(session, populated_db[0].id, teams[0].id, settings=snake_settings)
        draft_player(session, populated_db[1].id, teams[1].id, settings=snake_settings)

        draft_state = get_draft_state(session)
        round_num, pick_in_round = get_pick_position(draft_state)
        assert round_num == 1
        assert pick_in_round == 3

    def test_new_round_position(self, session, populated_db, snake_settings):
        """Test position at start of new round."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        # Complete round 1 (4 picks)
        for i in range(4):
            draft_state = get_draft_state(session)
            current_team_id = get_current_drafter(draft_state)
            draft_player(session, populated_db[i].id, current_team_id, settings=snake_settings)

        draft_state = get_draft_state(session)
        round_num, pick_in_round = get_pick_position(draft_state)
        assert round_num == 2
        assert pick_in_round == 1


class TestTeamNextPick:
    """Tests for calculating when a team picks next."""

    def test_on_clock_returns_zero(self, session, populated_db, snake_settings):
        """Test that team on clock gets 0 picks away."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        picks_away = get_team_next_pick(draft_state, teams[0].id)
        assert picks_away == 0

    def test_second_team_picks_away(self, session, populated_db, snake_settings):
        """Test second team is 1 pick away at start."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        picks_away = get_team_next_pick(draft_state, teams[1].id)
        assert picks_away == 1

    def test_last_team_picks_away(self, session, populated_db, snake_settings):
        """Test last team is N-1 picks away at start."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        picks_away = get_team_next_pick(draft_state, teams[3].id)
        assert picks_away == 3

    def test_invalid_team_returns_none(self, session, populated_db, snake_settings):
        """Test that invalid team ID returns None."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)

        picks_away = get_team_next_pick(draft_state, 99999)
        assert picks_away is None


class TestSnakeDraftValidation:
    """Tests for snake draft turn validation."""

    def test_wrong_team_pick_fails(self, session, populated_db, snake_settings):
        """Test that drafting out of turn fails."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        # Try to draft with team 2 (should be team 1's turn)
        with pytest.raises(ValueError, match="turn"):
            draft_player(session, populated_db[0].id, teams[1].id, settings=snake_settings)

    def test_correct_team_pick_succeeds(self, session, populated_db, snake_settings):
        """Test that drafting in turn succeeds."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        # Draft with correct team
        pick = draft_player(session, populated_db[0].id, teams[0].id, settings=snake_settings)
        assert pick is not None
        assert pick.team_id == teams[0].id

    def test_snake_pick_no_price(self, session, populated_db, snake_settings):
        """Test that snake draft picks have no price."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        pick = draft_player(session, populated_db[0].id, teams[0].id, settings=snake_settings)
        assert pick.price is None

    def test_snake_pick_records_round_info(self, session, populated_db, snake_settings):
        """Test that snake draft picks record round information."""
        initialize_draft(session, snake_settings, "My Team")
        teams = get_all_teams(session)

        pick = draft_player(session, populated_db[0].id, teams[0].id, settings=snake_settings)
        assert pick.round_number == 1
        assert pick.pick_in_round == 1


class TestIsTeamsTurn:
    """Tests for is_teams_turn helper."""

    def test_correct_team(self, session, populated_db, snake_settings):
        """Test returns True for correct team."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        assert is_teams_turn(draft_state, teams[0].id) is True

    def test_wrong_team(self, session, populated_db, snake_settings):
        """Test returns False for wrong team."""
        initialize_draft(session, snake_settings, "My Team")
        draft_state = get_draft_state(session)
        teams = get_all_teams(session)

        assert is_teams_turn(draft_state, teams[1].id) is False


class TestOnTheClockTeam:
    """Tests for get_on_the_clock_team helper in draft.py."""

    def test_snake_returns_team(self, session, populated_db, snake_settings):
        """Test snake draft returns on-clock team."""
        initialize_draft(session, snake_settings, "My Team")

        team = get_on_the_clock_team(session)
        assert team is not None
        assert team.name == "My Team"

    def test_auction_returns_none(self, session, populated_db, auction_settings):
        """Test auction draft returns None."""
        initialize_draft(session, auction_settings, "My Team")

        team = get_on_the_clock_team(session)
        assert team is None


class TestHelperFunctions:
    """Tests for helper formatting functions."""

    def test_get_overall_pick_number(self):
        """Test overall pick calculation."""
        assert get_overall_pick_number(1, 1, 12) == 1
        assert get_overall_pick_number(1, 12, 12) == 12
        assert get_overall_pick_number(2, 1, 12) == 13
        assert get_overall_pick_number(3, 5, 12) == 29

    def test_format_pick_display(self):
        """Test pick display formatting."""
        display = format_pick_display(1, 1, 12)
        assert "Round 1" in display
        assert "Pick 1" in display
        assert "1st overall" in display

        display = format_pick_display(2, 5, 12)
        assert "Round 2" in display
        assert "Pick 5" in display
        assert "17th overall" in display

    def test_ordinal_suffixes(self):
        """Test ordinal number suffixes."""
        # Test 1st, 2nd, 3rd
        assert "1st" in format_pick_display(1, 1, 10)
        assert "2nd" in format_pick_display(1, 2, 10)
        assert "3rd" in format_pick_display(1, 3, 10)

        # Test 11th, 12th, 13th (special cases)
        assert "11th" in format_pick_display(2, 1, 10)
        assert "12th" in format_pick_display(2, 2, 10)
        assert "13th" in format_pick_display(2, 3, 10)

        # Test 21st, 22nd, 23rd
        assert "21st" in format_pick_display(3, 1, 10)
        assert "22nd" in format_pick_display(3, 2, 10)
        assert "23rd" in format_pick_display(3, 3, 10)
