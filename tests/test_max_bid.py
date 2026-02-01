"""Tests for max bid calculator functionality."""

import pytest
from src.database import Player, Team, DraftPick, DraftState
from src.draft import (
    calculate_max_bid,
    get_team_roster_needs,
    calculate_bid_impact,
    initialize_draft,
    draft_player,
)
from src.settings import LeagueSettings


@pytest.fixture
def settings():
    """Create test league settings."""
    return LeagueSettings(
        num_teams=2,
        budget_per_team=100,
        min_bid=1,
        roster_spots={
            "C": 1,
            "1B": 1,
            "2B": 1,
            "3B": 1,
            "SS": 1,
            "OF": 3,
            "UTIL": 1,
            "SP": 2,
            "RP": 2,
            "P": 1,
        }
    )


@pytest.fixture
def draft_with_teams(session, settings):
    """Initialize a draft with teams."""
    initialize_draft(session, settings, "Test Team")
    return session.query(Team).filter(Team.is_user_team == True).first()


class TestGetTeamRosterNeeds:
    """Tests for get_team_roster_needs function."""

    def test_empty_roster(self, session, draft_with_teams, settings):
        """Test roster needs with no players drafted."""
        team = draft_with_teams
        needs = get_team_roster_needs(session, team, settings)

        assert needs["hitters_drafted"] == 0
        assert needs["pitchers_drafted"] == 0
        assert needs["hitters_needed"] == settings.hitter_roster_spots
        assert needs["pitchers_needed"] == settings.pitcher_roster_spots
        assert needs["total_needed"] == settings.hitter_roster_spots + settings.pitcher_roster_spots

    def test_partial_roster(self, session, draft_with_teams, settings):
        """Test roster needs with some players drafted."""
        team = draft_with_teams

        # Create and draft a hitter
        hitter = Player(name="Test Hitter", player_type="hitter", dollar_value=10)
        session.add(hitter)
        session.commit()

        draft_player(session, hitter.id, team.id, 10, settings)

        needs = get_team_roster_needs(session, team, settings)

        assert needs["hitters_drafted"] == 1
        assert needs["pitchers_drafted"] == 0
        assert needs["hitters_needed"] == settings.hitter_roster_spots - 1

    def test_full_roster(self, session, draft_with_teams, settings):
        """Test roster needs when roster is full."""
        team = draft_with_teams

        # Draft enough players to fill roster
        for i in range(settings.hitter_roster_spots):
            hitter = Player(name=f"Hitter {i}", player_type="hitter", dollar_value=5)
            session.add(hitter)
            session.commit()
            draft_player(session, hitter.id, team.id, 1, settings)

        for i in range(settings.pitcher_roster_spots):
            pitcher = Player(name=f"Pitcher {i}", player_type="pitcher", dollar_value=5)
            session.add(pitcher)
            session.commit()
            draft_player(session, pitcher.id, team.id, 1, settings)

        needs = get_team_roster_needs(session, team, settings)

        assert needs["hitters_needed"] == 0
        assert needs["pitchers_needed"] == 0
        assert needs["total_needed"] == 0


class TestCalculateMaxBid:
    """Tests for calculate_max_bid function."""

    def test_full_budget_empty_roster(self, session, draft_with_teams, settings):
        """Test max bid with full budget and empty roster."""
        team = draft_with_teams
        result = calculate_max_bid(session, team, settings)

        total_spots = settings.hitter_roster_spots + settings.pitcher_roster_spots
        expected_reserved = (total_spots - 1) * settings.min_bid
        expected_max = settings.budget_per_team - expected_reserved

        assert result["max_bid"] == expected_max
        assert result["remaining_budget"] == settings.budget_per_team
        assert result["spots_needed"] == total_spots
        assert result["reserved_for_roster"] == expected_reserved

    def test_partial_budget_partial_roster(self, session, draft_with_teams, settings):
        """Test max bid after drafting some players."""
        team = draft_with_teams

        # Draft one player for $20
        hitter = Player(name="Expensive Hitter", player_type="hitter", dollar_value=20)
        session.add(hitter)
        session.commit()
        draft_player(session, hitter.id, team.id, 20, settings)

        result = calculate_max_bid(session, team, settings)

        remaining = settings.budget_per_team - 20
        total_spots = settings.hitter_roster_spots + settings.pitcher_roster_spots
        spots_left = total_spots - 1
        expected_reserved = (spots_left - 1) * settings.min_bid
        expected_max = remaining - expected_reserved

        assert result["max_bid"] == expected_max
        assert result["remaining_budget"] == remaining
        assert result["spots_needed"] == spots_left

    def test_low_budget_forces_min_bids(self, session, draft_with_teams, settings):
        """Test max bid when budget only allows min bids."""
        team = draft_with_teams

        total_spots = settings.hitter_roster_spots + settings.pitcher_roster_spots

        # Spend most of budget leaving only enough for min bids
        hitter = Player(name="Star Player", player_type="hitter", dollar_value=50)
        session.add(hitter)
        session.commit()

        # Spend so we have exactly total_spots dollars left
        spend_amount = settings.budget_per_team - total_spots
        draft_player(session, hitter.id, team.id, spend_amount, settings)

        result = calculate_max_bid(session, team, settings)

        # With exactly total_spots-1 spots left and total_spots dollars,
        # max bid should be slightly more than $1
        assert result["max_bid"] >= settings.min_bid

    def test_full_roster_all_budget_available(self, session, draft_with_teams, settings):
        """Test that full roster means entire remaining budget is available."""
        team = draft_with_teams

        # Fill the entire roster at $1 each
        for i in range(settings.hitter_roster_spots):
            hitter = Player(name=f"Hitter {i}", player_type="hitter", dollar_value=5)
            session.add(hitter)
            session.commit()
            draft_player(session, hitter.id, team.id, 1, settings)

        for i in range(settings.pitcher_roster_spots):
            pitcher = Player(name=f"Pitcher {i}", player_type="pitcher", dollar_value=5)
            session.add(pitcher)
            session.commit()
            draft_player(session, pitcher.id, team.id, 1, settings)

        result = calculate_max_bid(session, team, settings)

        # No more spots needed, so max_bid equals remaining budget
        assert result["spots_needed"] == 0
        assert result["reserved_for_roster"] == 0
        assert result["max_bid"] == result["remaining_budget"]


class TestCalculateBidImpact:
    """Tests for calculate_bid_impact function."""

    def test_affordable_bid(self, session, draft_with_teams, settings):
        """Test impact of an affordable bid."""
        team = draft_with_teams
        max_info = calculate_max_bid(session, team, settings)

        # Test a bid at half the max
        test_bid = max_info["max_bid"] // 2
        impact = calculate_bid_impact(session, team, test_bid, settings)

        assert impact["is_affordable"] is True
        assert impact["over_max_by"] == 0
        assert impact["remaining_after"] == settings.budget_per_team - test_bid

    def test_unaffordable_bid(self, session, draft_with_teams, settings):
        """Test impact of a bid that exceeds max."""
        team = draft_with_teams
        max_info = calculate_max_bid(session, team, settings)

        # Test a bid $10 over max
        test_bid = max_info["max_bid"] + 10
        impact = calculate_bid_impact(session, team, test_bid, settings)

        assert impact["is_affordable"] is False
        assert impact["over_max_by"] == 10

    def test_exact_max_bid(self, session, draft_with_teams, settings):
        """Test impact of bidding exactly the max."""
        team = draft_with_teams
        max_info = calculate_max_bid(session, team, settings)

        impact = calculate_bid_impact(session, team, max_info["max_bid"], settings)

        assert impact["is_affordable"] is True
        assert impact["over_max_by"] == 0

    def test_spots_decrement(self, session, draft_with_teams, settings):
        """Test that spots_after decrements correctly."""
        team = draft_with_teams
        total_spots = settings.hitter_roster_spots + settings.pitcher_roster_spots

        impact = calculate_bid_impact(session, team, 10, settings)

        assert impact["spots_after"] == total_spots - 1

    def test_average_per_player_calculation(self, session, draft_with_teams, settings):
        """Test average remaining per player calculation."""
        team = draft_with_teams
        total_spots = settings.hitter_roster_spots + settings.pitcher_roster_spots

        test_bid = 50
        impact = calculate_bid_impact(session, team, test_bid, settings)

        remaining = settings.budget_per_team - test_bid
        spots_after = total_spots - 1
        expected_avg = remaining / spots_after

        assert impact["avg_per_player_after"] == round(expected_avg, 1)


class TestMaxBidEdgeCases:
    """Tests for edge cases in max bid calculations."""

    def test_zero_remaining_budget(self, session, settings):
        """Test max bid when budget is exhausted."""
        initialize_draft(session, settings, "Test Team")
        team = session.query(Team).filter(Team.is_user_team == True).first()

        # Spend entire budget
        team.budget = 0
        session.commit()

        # Create a team manually with 0 budget for testing
        zero_budget_team = Team(name="Broke Team", budget=0)
        session.add(zero_budget_team)
        session.commit()

        result = calculate_max_bid(session, zero_budget_team, settings)

        assert result["max_bid"] == 0
        assert result["remaining_budget"] == 0

    def test_min_bid_enforcement(self, session, draft_with_teams, settings):
        """Test that max bid is at least min_bid when budget allows."""
        team = draft_with_teams

        # With any reasonable budget and roster, max should be >= min_bid
        result = calculate_max_bid(session, team, settings)

        if result["remaining_budget"] >= settings.min_bid:
            assert result["max_bid"] >= settings.min_bid

    def test_different_min_bid_values(self, session):
        """Test max bid calculation with different min_bid settings."""
        settings_5 = LeagueSettings(
            num_teams=2,
            budget_per_team=100,
            min_bid=5,  # Higher min bid
        )

        initialize_draft(session, settings_5, "Test Team")
        team = session.query(Team).filter(Team.is_user_team == True).first()

        result = calculate_max_bid(session, team, settings_5)

        total_spots = settings_5.hitter_roster_spots + settings_5.pitcher_roster_spots
        expected_reserved = (total_spots - 1) * 5  # Using $5 min bid
        expected_max = settings_5.budget_per_team - expected_reserved

        assert result["max_bid"] == expected_max
        assert result["min_bid"] == 5
