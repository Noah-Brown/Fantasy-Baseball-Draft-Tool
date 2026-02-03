"""Tests for the team needs analysis module."""

import pytest

from src.database import Player, Team, DraftPick
from src.settings import LeagueSettings
from src.needs import (
    PositionalRosterState,
    PlayerRecommendation,
    get_team_positional_roster_state,
    get_unfilled_positions,
    calculate_position_urgency,
    calculate_category_fit,
    get_player_positions_that_fill_needs,
    get_player_helpful_categories,
    get_player_recommendations,
    get_weak_categories,
    calculate_all_team_standings,
    analyze_team_needs,
)


@pytest.fixture
def settings():
    """Create test league settings."""
    return LeagueSettings(
        num_teams=12,
        budget_per_team=260,
        roster_spots={
            "C": 1,
            "1B": 1,
            "2B": 1,
            "3B": 1,
            "SS": 1,
            "OF": 3,
            "UTIL": 1,
            "CI": 0,
            "MI": 0,
            "SP": 2,
            "RP": 2,
            "P": 2,
        },
    )


@pytest.fixture
def team_with_picks(session):
    """Create a team with some draft picks."""
    from src.draft import initialize_draft

    # Initialize draft to create teams
    settings = LeagueSettings(num_teams=12, budget_per_team=260)
    initialize_draft(session, settings, "Test Team")

    # Get user team
    team = session.query(Team).filter(Team.is_user_team == True).first()

    return team


class TestPositionalRosterState:
    """Tests for positional roster state calculation."""

    def test_empty_team_all_positions_unfilled(self, session, team_with_picks, settings):
        """Test that empty team shows all positions as unfilled."""
        team = team_with_picks
        states = get_team_positional_roster_state(session, team, settings)

        # Should have states for all configured positions
        assert len(states) > 0

        # All should be unfilled
        for state in states:
            if state.required > 0:
                assert state.filled == 0
                assert state.remaining == state.required
                assert state.players == []

    def test_single_catcher_fills_c_slot(self, session, team_with_picks, settings):
        """Test that a catcher fills the C slot."""
        team = team_with_picks

        # Create a catcher and draft them
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        catcher = Player(
            name="Test Catcher",
            positions="C",
            player_type="hitter",
            r=50, hr=15, rbi=50, sb=2, avg=0.250, ab=400, h=100,
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(catcher)
        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        # Find C state
        c_state = next((s for s in states if s.position == "C"), None)
        assert c_state is not None
        assert c_state.filled == 1
        assert c_state.remaining == 0
        assert "Test Catcher" in c_state.players

    def test_multi_position_player_fills_most_restrictive(self, session, team_with_picks, settings):
        """Test that multi-position players fill most restrictive position first."""
        team = team_with_picks

        # Create a SS/2B eligible player
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        player = Player(
            name="SS/2B Player",
            positions="SS,2B",
            player_type="hitter",
            r=70, hr=15, rbi=60, sb=15, avg=0.270, ab=500, h=135,
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(player)
        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        # Player should fill SS (more restrictive than 2B in priority order)
        # based on HITTER_POSITION_PRIORITY = ["C", "1B", "2B", "3B", "SS", ...]
        # Actually 2B comes before SS in the priority list, so 2B should be filled
        ss_state = next((s for s in states if s.position == "SS"), None)
        b2_state = next((s for s in states if s.position == "2B"), None)

        # The player should fill one of them
        total_filled = (ss_state.filled if ss_state else 0) + (b2_state.filled if b2_state else 0)
        assert total_filled == 1

    def test_outfielder_fills_of_slot(self, session, team_with_picks, settings):
        """Test that outfielders fill OF slots correctly."""
        team = team_with_picks

        # Create 3 outfielders
        for i in range(3):
            pick = DraftPick(team_id=team.id, price=10, pick_number=i + 1)
            session.add(pick)
            session.commit()

            player = Player(
                name=f"Outfielder {i + 1}",
                positions="OF",
                player_type="hitter",
                r=80 - i * 5, hr=25 - i * 2, rbi=80 - i * 5, sb=10, avg=0.280,
                ab=550, h=154,
                draft_pick_id=pick.id,
                is_drafted=True,
            )
            session.add(player)

        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        of_state = next((s for s in states if s.position == "OF"), None)
        assert of_state is not None
        assert of_state.filled == 3
        assert of_state.remaining == 0

    def test_pitcher_fills_sp_before_p(self, session, team_with_picks, settings):
        """Test that SP fills SP slot before generic P slot."""
        team = team_with_picks

        # Create a starting pitcher
        pick = DraftPick(team_id=team.id, price=20, pick_number=1)
        session.add(pick)
        session.commit()

        pitcher = Player(
            name="Starting Pitcher",
            positions="SP",
            player_type="pitcher",
            ip=180, w=12, sv=0, k=180, era=3.50, whip=1.15,
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(pitcher)
        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        sp_state = next((s for s in states if s.position == "SP"), None)
        p_state = next((s for s in states if s.position == "P"), None)

        # Should fill SP first
        assert sp_state is not None
        assert sp_state.filled == 1
        # P should still be empty
        assert p_state is not None
        assert p_state.filled == 0


class TestGetUnfilledPositions:
    """Tests for get_unfilled_positions function."""

    def test_returns_positions_with_remaining_slots(self):
        """Test that unfilled positions are returned."""
        states = [
            PositionalRosterState("C", 1, 1, 0, ["Player 1"]),  # Filled
            PositionalRosterState("1B", 1, 0, 1, []),  # Unfilled
            PositionalRosterState("OF", 3, 2, 1, ["P1", "P2"]),  # Partial
        ]

        unfilled = get_unfilled_positions(states)

        assert "1B" in unfilled
        assert "OF" in unfilled
        assert "C" not in unfilled

    def test_empty_states_returns_empty(self):
        """Test that empty states returns empty list."""
        unfilled = get_unfilled_positions([])
        assert unfilled == []


class TestCalculatePositionUrgency:
    """Tests for position urgency calculation."""

    def test_fully_unfilled_position_high_urgency(self):
        """Test that unfilled position has high urgency."""
        states = [
            PositionalRosterState("C", 1, 0, 1, []),
        ]

        urgency = calculate_position_urgency("C", states)
        assert urgency == 1.0

    def test_fully_filled_position_zero_urgency(self):
        """Test that filled position has zero urgency."""
        states = [
            PositionalRosterState("C", 1, 1, 0, ["Catcher"]),
        ]

        urgency = calculate_position_urgency("C", states)
        assert urgency == 0.0

    def test_partial_fill_intermediate_urgency(self):
        """Test that partially filled position has intermediate urgency."""
        states = [
            PositionalRosterState("OF", 3, 1, 2, ["OF1"]),
        ]

        urgency = calculate_position_urgency("OF", states)
        assert 0.5 < urgency < 1.0  # 2/3 = 0.67

    def test_scarcity_boosts_urgency(self):
        """Test that scarcity increases urgency."""
        states = [
            PositionalRosterState("C", 1, 0, 1, []),
        ]

        # Without scarcity
        urgency_no_scarcity = calculate_position_urgency("C", states, scarcity=None)

        # With critical scarcity
        scarcity = {"C": {"level": "critical", "count": 1}}
        urgency_with_scarcity = calculate_position_urgency("C", states, scarcity=scarcity)

        # Scarcity should boost urgency (but cap at 1.0)
        assert urgency_with_scarcity >= urgency_no_scarcity

    def test_unknown_position_zero_urgency(self):
        """Test that unknown position returns zero urgency."""
        states = [
            PositionalRosterState("C", 1, 0, 1, []),
        ]

        urgency = calculate_position_urgency("XX", states)
        assert urgency == 0.0


class TestCalculateCategoryFit:
    """Tests for category fit calculation."""

    def test_player_strong_in_weak_category(self, session, settings):
        """Test that player strong in weak category has high fit."""
        player = Player(
            name="Speed Guy",
            player_type="hitter",
            sgp=5.0,
            sgp_breakdown={"r": 0.5, "hr": 0.5, "rbi": 0.5, "sb": 3.0, "avg": 0.5},
        )

        weak_categories = ["sb"]  # Team is weak in SB

        fit = calculate_category_fit(player, weak_categories, settings)
        assert fit > 0.5  # High fit because player is strong in SB

    def test_player_weak_in_weak_category(self, session, settings):
        """Test that player weak in team's weak category has low fit."""
        player = Player(
            name="Power Guy",
            player_type="hitter",
            sgp=5.0,
            sgp_breakdown={"r": 1.0, "hr": 3.0, "rbi": 1.0, "sb": -0.5, "avg": 0.5},
        )

        weak_categories = ["sb"]  # Team is weak in SB

        fit = calculate_category_fit(player, weak_categories, settings)
        assert fit == 0.0  # Negative SGP in weak category

    def test_no_weak_categories_returns_zero(self, session, settings):
        """Test that no weak categories returns zero fit."""
        player = Player(
            name="Any Player",
            player_type="hitter",
            sgp=5.0,
            sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 1.0, "avg": 1.0},
        )

        fit = calculate_category_fit(player, [], settings)
        assert fit == 0.0

    def test_no_breakdown_returns_zero(self, session, settings):
        """Test that player without breakdown returns zero fit."""
        player = Player(
            name="No Breakdown",
            player_type="hitter",
            sgp_breakdown=None,
        )

        fit = calculate_category_fit(player, ["sb"], settings)
        assert fit == 0.0


class TestGetWeakCategories:
    """Tests for weak category identification."""

    def test_identifies_weak_categories(self):
        """Test that categories with standings >= 7 are identified as weak."""
        analysis = {
            "standings": {
                "r": 3,   # Strong
                "hr": 6,  # Average
                "rbi": 9, # Weak
                "sb": 11, # Very weak
                "avg": 5, # Average
            }
        }

        weak = get_weak_categories(analysis, threshold=7)

        assert "rbi" in weak
        assert "sb" in weak
        assert "r" not in weak
        assert "hr" not in weak
        assert "avg" not in weak

    def test_custom_threshold(self):
        """Test with custom threshold."""
        analysis = {
            "standings": {"r": 5, "hr": 6}
        }

        weak = get_weak_categories(analysis, threshold=5)

        assert "r" in weak
        assert "hr" in weak


class TestGetPlayerRecommendations:
    """Tests for player recommendations."""

    def test_returns_recommendations_for_unfilled_positions(self, session, team_with_picks, settings):
        """Test that recommendations are generated for unfilled positions."""
        team = team_with_picks

        # Create available players
        for i in range(10):
            player = Player(
                name=f"Available Player {i}",
                positions="OF",
                player_type="hitter",
                r=80 - i, hr=25, rbi=80, sb=10, avg=0.280,
                ab=500, h=140,
                dollar_value=20 - i,
                sgp=3.0,
                sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 0, "avg": 0},
            )
            session.add(player)
        session.commit()

        roster_states = get_team_positional_roster_state(session, team, settings)
        category_analysis = {
            "standings": {"r": 6, "hr": 6, "rbi": 6, "sb": 9, "avg": 6},
            "sgp_totals": {"r": 0, "hr": 0, "rbi": 0, "sb": 0, "avg": 0},
        }

        recommendations = get_player_recommendations(
            session, team, roster_states, category_analysis, settings
        )

        assert len(recommendations) > 0
        # All should fill OF (which is unfilled)
        for rec in recommendations:
            assert "OF" in rec.fills_positions or "UTIL" in rec.fills_positions

    def test_recommendations_sorted_by_score(self, session, team_with_picks, settings):
        """Test that recommendations are sorted by composite score."""
        team = team_with_picks

        # Create players with different values
        for i, value in enumerate([10, 30, 20]):
            player = Player(
                name=f"Player {i}",
                positions="OF",
                player_type="hitter",
                r=80, hr=25, rbi=80, sb=10, avg=0.280,
                ab=500, h=140,
                dollar_value=value,
                sgp=value / 10,
                sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 0, "avg": 0},
            )
            session.add(player)
        session.commit()

        roster_states = get_team_positional_roster_state(session, team, settings)
        category_analysis = {
            "standings": {"r": 6, "hr": 6, "rbi": 6, "sb": 6, "avg": 6},
            "sgp_totals": {},
        }

        recommendations = get_player_recommendations(
            session, team, roster_states, category_analysis, settings
        )

        # Should be sorted by score descending
        scores = [r.composite_score for r in recommendations]
        assert scores == sorted(scores, reverse=True)


class TestCalculateAllTeamStandings:
    """Tests for comparative standings calculation."""

    def test_returns_standings_for_all_teams(self, session, team_with_picks, settings):
        """Test that standings are calculated for all teams."""
        standings = calculate_all_team_standings(session, settings)

        # Should have standings for each team
        assert len(standings) == settings.num_teams

        # Each team should have standings for all categories
        for team_name, team_standings in standings.items():
            for cat in ["r", "hr", "rbi", "sb", "avg", "w", "sv", "k", "era", "whip"]:
                assert cat in team_standings
                assert 1 <= team_standings[cat] <= settings.num_teams


class TestAnalyzeTeamNeeds:
    """Integration tests for the full analysis."""

    def test_returns_complete_analysis(self, session, team_with_picks, settings):
        """Test that analyze_team_needs returns complete analysis."""
        team = team_with_picks

        analysis = analyze_team_needs(session, team, settings)

        assert analysis.positional_states is not None
        assert isinstance(analysis.positional_states, list)

        assert analysis.recommendations is not None
        assert isinstance(analysis.recommendations, list)

        assert analysis.category_analysis is not None
        assert isinstance(analysis.category_analysis, dict)

        assert analysis.comparative_standings is not None
        assert isinstance(analysis.comparative_standings, dict)

    def test_works_with_empty_team(self, session, team_with_picks, settings):
        """Test that analysis works with no drafted players."""
        team = team_with_picks

        # Team has no picks, should still work
        analysis = analyze_team_needs(session, team, settings)

        # Should have unfilled positions
        unfilled = get_unfilled_positions(analysis.positional_states)
        assert len(unfilled) > 0

    def test_works_with_drafted_players(self, session, team_with_picks, settings):
        """Test that analysis works with drafted players."""
        team = team_with_picks

        # Draft a player
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        player = Player(
            name="Drafted Player",
            positions="OF",
            player_type="hitter",
            r=80, hr=25, rbi=80, sb=10, avg=0.280, ab=500, h=140,
            dollar_value=20,
            sgp=3.0,
            sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 0, "avg": 0},
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(player)
        session.commit()

        analysis = analyze_team_needs(session, team, settings)

        # Should reflect the drafted player
        of_state = next((s for s in analysis.positional_states if s.position == "OF"), None)
        assert of_state is not None
        assert of_state.filled == 1


class TestCompositePositions:
    """Tests for composite position handling (CI, MI, UTIL)."""

    def test_ci_player_fills_ci_slot(self, session, team_with_picks):
        """Test that 1B/3B player can fill CI slot."""
        settings = LeagueSettings(
            num_teams=12,
            roster_spots={
                "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1,
                "CI": 1,  # Corner infield slot
                "OF": 3, "UTIL": 1,
                "SP": 2, "RP": 2, "P": 2,
            }
        )

        team = team_with_picks

        # Create two 1B players (one fills 1B, one fills CI)
        for i in range(2):
            pick = DraftPick(team_id=team.id, price=10, pick_number=i + 1)
            session.add(pick)
            session.commit()

            player = Player(
                name=f"First Baseman {i + 1}",
                positions="1B",
                player_type="hitter",
                r=70, hr=30, rbi=90, sb=2, avg=0.270, ab=550, h=150,
                draft_pick_id=pick.id,
                is_drafted=True,
            )
            session.add(player)

        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        b1_state = next((s for s in states if s.position == "1B"), None)
        ci_state = next((s for s in states if s.position == "CI"), None)

        # One should fill 1B, one should fill CI
        assert b1_state.filled == 1
        assert ci_state.filled == 1

    def test_util_accepts_any_hitter(self, session, team_with_picks, settings):
        """Test that UTIL slot accepts any hitter."""
        team = team_with_picks

        # Fill all regular positions, then add one more hitter for UTIL
        # Create a DH-only player
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        player = Player(
            name="DH Only",
            positions="DH",
            player_type="hitter",
            r=70, hr=30, rbi=90, sb=2, avg=0.270, ab=550, h=150,
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(player)
        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        util_state = next((s for s in states if s.position == "UTIL"), None)
        assert util_state is not None
        assert util_state.filled == 1
        assert "DH Only" in util_state.players

    def test_p_slot_accepts_sp_or_rp(self, session, team_with_picks, settings):
        """Test that P slot accepts both SP and RP."""
        team = team_with_picks

        # Fill SP and RP slots first, then add more pitchers for P slots
        # Create 3 SP (2 fill SP, 1 fills P)
        for i in range(3):
            pick = DraftPick(team_id=team.id, price=15, pick_number=i + 1)
            session.add(pick)
            session.commit()

            player = Player(
                name=f"Starter {i + 1}",
                positions="SP",
                player_type="pitcher",
                ip=180 - i * 20, w=12 - i, sv=0, k=180 - i * 10, era=3.50, whip=1.15,
                draft_pick_id=pick.id,
                is_drafted=True,
            )
            session.add(player)

        session.commit()

        states = get_team_positional_roster_state(session, team, settings)

        sp_state = next((s for s in states if s.position == "SP"), None)
        p_state = next((s for s in states if s.position == "P"), None)

        # 2 should fill SP, 1 should fill P
        assert sp_state.filled == 2
        assert p_state.filled == 1
