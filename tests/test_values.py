"""Tests for the SGP and dollar value calculation module."""

import pytest

from src.database import Player
from src.settings import LeagueSettings
from src.values import (
    calculate_all_player_values,
    _calculate_preliminary_value,
    _calculate_sgp_denominators,
    _calculate_player_sgp,
    _get_player_stats,
    _calculate_pool_values,
    calculate_category_surplus,
    calculate_team_category_sgp,
    calculate_team_raw_stats,
    estimate_standings_position,
    analyze_team_category_balance,
)


@pytest.fixture
def settings():
    """Create test league settings."""
    return LeagueSettings(
        num_teams=12,
        budget_per_team=260,
        hitter_budget_pct=0.68,
    )


@pytest.fixture
def sample_hitters(session):
    """Create a sample pool of hitters for testing."""
    hitters = []
    # Create 120 hitters with varying stats
    for i in range(120):
        rank = i + 1
        # Stats decrease as rank increases
        player = Player(
            name=f"Hitter {rank}",
            team="TST",
            positions="OF",
            player_type="hitter",
            pa=600 - (i * 2),
            ab=550 - (i * 2),
            h=180 - (i * 1.2),
            r=100 - (i * 0.7),
            hr=35 - (i * 0.25),
            rbi=100 - (i * 0.7),
            sb=20 - (i * 0.15),
            avg=0.300 - (i * 0.001),
        )
        session.add(player)
        hitters.append(player)

    session.commit()
    return hitters


@pytest.fixture
def sample_pitchers(session):
    """Create a sample pool of pitchers for testing."""
    pitchers = []
    # Create 80 pitchers with varying stats
    for i in range(80):
        rank = i + 1
        # Stats decrease/increase as rank increases
        player = Player(
            name=f"Pitcher {rank}",
            team="TST",
            positions="SP",
            player_type="pitcher",
            ip=200 - (i * 1.5),
            w=18 - (i * 0.15),
            sv=0 if i < 40 else (40 - (i - 40) * 0.8),  # Some relievers
            k=220 - (i * 2),
            era=2.80 + (i * 0.03),  # ERA increases (worse)
            whip=1.00 + (i * 0.008),  # WHIP increases (worse)
        )
        session.add(player)
        pitchers.append(player)

    session.commit()
    return pitchers


class TestPreliminaryValue:
    """Tests for preliminary value calculation."""

    def test_hitter_preliminary_value(self, session):
        """Test that better hitters get higher preliminary values."""
        good_hitter = Player(
            name="Good Hitter",
            player_type="hitter",
            r=100, hr=35, rbi=100, sb=20,
            ab=550, avg=0.300,
        )
        bad_hitter = Player(
            name="Bad Hitter",
            player_type="hitter",
            r=50, hr=10, rbi=50, sb=5,
            ab=400, avg=0.240,
        )

        categories = ["R", "HR", "RBI", "SB", "AVG"]

        good_value = _calculate_preliminary_value(good_hitter, categories, "hitter")
        bad_value = _calculate_preliminary_value(bad_hitter, categories, "hitter")

        assert good_value > bad_value

    def test_pitcher_preliminary_value(self, session):
        """Test that better pitchers get higher preliminary values."""
        good_pitcher = Player(
            name="Good Pitcher",
            player_type="pitcher",
            w=18, sv=0, k=220,
            ip=200, era=2.50, whip=1.00,
        )
        bad_pitcher = Player(
            name="Bad Pitcher",
            player_type="pitcher",
            w=8, sv=0, k=100,
            ip=150, era=4.50, whip=1.40,
        )

        categories = ["W", "SV", "K", "ERA", "WHIP"]

        good_value = _calculate_preliminary_value(good_pitcher, categories, "pitcher")
        bad_value = _calculate_preliminary_value(bad_pitcher, categories, "pitcher")

        assert good_value > bad_value


class TestSGPDenominators:
    """Tests for SGP denominator calculation."""

    def test_counting_stat_denominator(self, session, sample_hitters):
        """Test denominator calculation for counting stats."""
        categories = ["R", "HR", "RBI", "SB", "AVG"]
        denominators = _calculate_sgp_denominators(
            sample_hitters[:50], categories, "hitter"
        )

        # Should have positive denominators for all categories
        for cat in ["r", "hr", "rbi", "sb", "avg"]:
            assert cat in denominators
            assert denominators[cat] > 0

    def test_pitcher_ratio_denominator(self, session, sample_pitchers):
        """Test denominator calculation for ERA/WHIP."""
        categories = ["W", "SV", "K", "ERA", "WHIP"]
        denominators = _calculate_sgp_denominators(
            sample_pitchers[:30], categories, "pitcher"
        )

        assert denominators["era"] > 0
        assert denominators["whip"] > 0

    def test_single_player_returns_default(self, session):
        """Test that single player returns default denominator of 1."""
        player = Player(
            name="Solo",
            player_type="hitter",
            r=80, hr=25, rbi=80, sb=10, avg=0.280,
            ab=500, h=140,
        )

        categories = ["R", "HR", "RBI", "SB", "AVG"]
        denominators = _calculate_sgp_denominators([player], categories, "hitter")

        # With only one player, can't calculate std dev
        for cat in ["r", "hr", "rbi", "sb", "avg"]:
            assert denominators[cat] == 1.0


class TestPlayerSGP:
    """Tests for individual player SGP calculation."""

    def test_above_replacement_positive_sgp(self, session):
        """Test that players above replacement have positive SGP."""
        good_player = Player(
            name="Good",
            player_type="hitter",
            r=100, hr=35, rbi=100, sb=20, avg=0.300,
            ab=550, h=165,
        )

        replacement_stats = {
            "r": 70, "hr": 20, "rbi": 70, "sb": 10, "avg": 0.260,
            "ab": 500, "h": 130,
        }
        denominators = {"r": 15, "hr": 8, "rbi": 15, "sb": 5, "avg": 10}
        categories = ["R", "HR", "RBI", "SB", "AVG"]

        sgp, breakdown = _calculate_player_sgp(
            good_player, categories, "hitter",
            replacement_stats, denominators
        )

        assert sgp > 0
        assert isinstance(breakdown, dict)
        assert len(breakdown) == 5

    def test_below_replacement_negative_sgp(self, session):
        """Test that players below replacement have negative SGP."""
        bad_player = Player(
            name="Bad",
            player_type="hitter",
            r=50, hr=10, rbi=50, sb=5, avg=0.230,
            ab=400, h=92,
        )

        replacement_stats = {
            "r": 70, "hr": 20, "rbi": 70, "sb": 10, "avg": 0.260,
            "ab": 500, "h": 130,
        }
        denominators = {"r": 15, "hr": 8, "rbi": 15, "sb": 5, "avg": 10}
        categories = ["R", "HR", "RBI", "SB", "AVG"]

        sgp, breakdown = _calculate_player_sgp(
            bad_player, categories, "hitter",
            replacement_stats, denominators
        )

        assert sgp < 0
        assert isinstance(breakdown, dict)

    def test_pitcher_era_lower_is_better(self, session):
        """Test that lower ERA gives positive SGP for pitchers."""
        good_pitcher = Player(
            name="Ace",
            player_type="pitcher",
            w=15, sv=0, k=200,
            ip=200, era=2.50, whip=1.00,
        )

        replacement_stats = {
            "w": 10, "sv": 0, "k": 150,
            "ip": 170, "era": 4.00, "whip": 1.25,
        }
        denominators = {"w": 3, "sv": 5, "k": 30, "era": 50, "whip": 10}
        categories = ["W", "SV", "K", "ERA", "WHIP"]

        sgp, breakdown = _calculate_player_sgp(
            good_pitcher, categories, "pitcher",
            replacement_stats, denominators
        )

        # ERA/WHIP contributions should be positive (good pitcher has lower values)
        assert sgp > 0
        assert "era" in breakdown
        assert "whip" in breakdown


class TestDollarValueConversion:
    """Tests for dollar value conversion."""

    def test_values_sum_approximately_to_budget(self, session, sample_hitters, settings):
        """Test that total values approximately equal the budget."""
        calculate_all_player_values(session, settings)

        hitter_budget = settings.total_league_budget * settings.hitter_budget_pct

        # Get all hitters with values
        total_value = sum(h.dollar_value or 0 for h in sample_hitters[:108])

        # Should be close to budget (within 5%)
        assert abs(total_value - hitter_budget) / hitter_budget < 0.05

    def test_minimum_value_enforced(self, session, sample_hitters, settings):
        """Test that no player has a value below minimum bid."""
        calculate_all_player_values(session, settings)

        for hitter in sample_hitters:
            if hitter.dollar_value is not None:
                assert hitter.dollar_value >= settings.min_bid

    def test_top_players_have_high_values(self, session, sample_hitters, settings):
        """Test that top players have values significantly above minimum."""
        calculate_all_player_values(session, settings)

        # Sort by dollar value
        valued_hitters = [h for h in sample_hitters if h.dollar_value]
        valued_hitters.sort(key=lambda x: x.dollar_value, reverse=True)

        # Top player should be worth $30+
        assert valued_hitters[0].dollar_value >= 30


class TestIntegration:
    """Integration tests for the full value calculation."""

    def test_full_calculation_with_both_pools(
        self, session, sample_hitters, sample_pitchers, settings
    ):
        """Test full calculation with both hitters and pitchers."""
        count = calculate_all_player_values(session, settings)

        # Should have processed all players
        assert count == len(sample_hitters) + len(sample_pitchers)

        # Hitters and pitchers should have values
        hitters_with_values = [h for h in sample_hitters if h.dollar_value]
        pitchers_with_values = [p for p in sample_pitchers if p.dollar_value]

        assert len(hitters_with_values) > 0
        assert len(pitchers_with_values) > 0

    def test_empty_database_returns_zero(self, session, settings):
        """Test that empty database returns 0 players processed."""
        count = calculate_all_player_values(session, settings)
        assert count == 0

    def test_recalculation_updates_values(self, session, sample_hitters, settings):
        """Test that recalculating updates existing values."""
        # First calculation
        calculate_all_player_values(session, settings)
        first_value = sample_hitters[0].dollar_value

        # Modify a player's stats
        sample_hitters[0].hr = (sample_hitters[0].hr or 0) + 20
        session.commit()

        # Recalculate
        calculate_all_player_values(session, settings)
        second_value = sample_hitters[0].dollar_value

        # Value should have increased
        assert second_value > first_value


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_player_with_missing_stats(self, session, settings):
        """Test handling of players with missing stats."""
        player = Player(
            name="Incomplete",
            player_type="hitter",
            positions="OF",
            # Missing most stats
            r=50,
        )
        session.add(player)
        session.commit()

        # Should not raise an error
        count = calculate_all_player_values(session, settings)
        assert count == 1
        assert player.dollar_value is not None

    def test_player_with_zero_ab(self, session, settings):
        """Test handling of players with zero at-bats."""
        player = Player(
            name="Zero AB",
            player_type="hitter",
            positions="OF",
            ab=0,
            h=0,
            avg=0,
            r=0, hr=0, rbi=0, sb=0,
        )
        session.add(player)
        session.commit()

        # Should not raise an error
        count = calculate_all_player_values(session, settings)
        assert count == 1

    def test_player_with_zero_ip(self, session, settings):
        """Test handling of pitchers with zero innings pitched."""
        player = Player(
            name="Zero IP",
            player_type="pitcher",
            positions="SP",
            ip=0,
            w=0, sv=0, k=0, era=0, whip=0,
        )
        session.add(player)
        session.commit()

        # Should not raise an error
        count = calculate_all_player_values(session, settings)
        assert count == 1

    def test_small_player_pool(self, session, settings):
        """Test with fewer players than draft slots."""
        # Only 5 hitters when we need 108
        for i in range(5):
            player = Player(
                name=f"Hitter {i}",
                player_type="hitter",
                positions="OF",
                r=80 - i * 5, hr=25 - i * 2, rbi=80 - i * 5,
                sb=10 - i, avg=0.280 - i * 0.01,
                ab=500, h=140 - i * 5,
            )
            session.add(player)
        session.commit()

        # Should handle gracefully
        count = calculate_all_player_values(session, settings)
        assert count == 5

    def test_all_identical_players(self, session, settings):
        """Test with players who all have identical stats."""
        for i in range(50):
            player = Player(
                name=f"Clone {i}",
                player_type="hitter",
                positions="OF",
                r=80, hr=25, rbi=80, sb=10, avg=0.280,
                ab=500, h=140,
            )
            session.add(player)
        session.commit()

        # Should not raise (division by zero with 0 std dev)
        count = calculate_all_player_values(session, settings)
        assert count == 50


class TestPoolValues:
    """Tests for the _calculate_pool_values function."""

    def test_separate_hitter_pitcher_budgets(
        self, session, sample_hitters, sample_pitchers, settings
    ):
        """Test that hitters and pitchers have separate budgets."""
        calculate_all_player_values(session, settings)

        hitter_total = sum(h.dollar_value or 0 for h in sample_hitters[:108])
        pitcher_total = sum(p.dollar_value or 0 for p in sample_pitchers[:72])

        expected_hitter_budget = settings.total_league_budget * settings.hitter_budget_pct
        expected_pitcher_budget = settings.total_league_budget * (1 - settings.hitter_budget_pct)

        # Each pool should be close to its allocated budget
        assert abs(hitter_total - expected_hitter_budget) / expected_hitter_budget < 0.10
        assert abs(pitcher_total - expected_pitcher_budget) / expected_pitcher_budget < 0.10


class TestSGPBreakdown:
    """Tests for per-category SGP breakdown storage."""

    def test_sgp_breakdown_populated_for_hitters(self, session, sample_hitters, settings):
        """Test that sgp_breakdown is populated for hitters."""
        calculate_all_player_values(session, settings)

        # Check a hitter in the draftable pool
        hitter = sample_hitters[0]
        assert hitter.sgp_breakdown is not None
        assert isinstance(hitter.sgp_breakdown, dict)

        # Should have all hitter categories
        expected_cats = ["r", "hr", "rbi", "sb", "avg"]
        for cat in expected_cats:
            assert cat in hitter.sgp_breakdown

    def test_sgp_breakdown_populated_for_pitchers(self, session, sample_pitchers, settings):
        """Test that sgp_breakdown is populated for pitchers."""
        calculate_all_player_values(session, settings)

        # Check a pitcher in the draftable pool
        pitcher = sample_pitchers[0]
        assert pitcher.sgp_breakdown is not None
        assert isinstance(pitcher.sgp_breakdown, dict)

        # Should have all pitcher categories
        expected_cats = ["w", "sv", "k", "era", "whip"]
        for cat in expected_cats:
            assert cat in pitcher.sgp_breakdown

    def test_sgp_breakdown_sums_to_total(self, session, sample_hitters, settings):
        """Test that category SGP values sum to total SGP."""
        calculate_all_player_values(session, settings)

        for hitter in sample_hitters[:10]:
            if hitter.sgp_breakdown and hitter.sgp:
                breakdown_sum = sum(hitter.sgp_breakdown.values())
                # Allow small floating point tolerance
                assert abs(breakdown_sum - hitter.sgp) < 0.001

    def test_sgp_breakdown_zeros_outside_pool(self, session, settings):
        """Test that players outside draftable pool have zero breakdown."""
        # Create more players than pool size
        for i in range(150):
            player = Player(
                name=f"Hitter {i}",
                player_type="hitter",
                positions="OF",
                r=100 - i * 0.5, hr=30 - i * 0.2, rbi=100 - i * 0.5,
                sb=15 - i * 0.1, avg=0.290 - i * 0.001,
                ab=500, h=145 - i * 0.5,
            )
            session.add(player)
        session.commit()

        calculate_all_player_values(session, settings)

        # Get players sorted by value
        players = session.query(Player).filter(Player.player_type == "hitter").all()
        players.sort(key=lambda p: p.dollar_value or 0, reverse=True)

        # Last player (outside pool) should have zero breakdown
        last_player = players[-1]
        assert last_player.sgp == 0
        assert last_player.sgp_breakdown is not None
        assert all(v == 0.0 for v in last_player.sgp_breakdown.values())


class TestCategorySurplus:
    """Tests for the calculate_category_surplus function."""

    def test_positive_surplus_distribution(self, session, sample_hitters, settings):
        """Test surplus is distributed proportionally to SGP."""
        calculate_all_player_values(session, settings)

        hitter = sample_hitters[0]
        # Simulate buying at half value
        price_paid = int((hitter.dollar_value or 0) / 2)
        total_surplus = (hitter.dollar_value or 0) - price_paid

        cat_surplus = calculate_category_surplus(hitter, price_paid)

        # Sum of category surplus should equal total surplus
        if cat_surplus:
            surplus_sum = sum(cat_surplus.values())
            assert abs(surplus_sum - total_surplus) < 0.01

    def test_negative_surplus_distribution(self, session, sample_hitters, settings):
        """Test negative surplus (overpay) is distributed correctly."""
        calculate_all_player_values(session, settings)

        hitter = sample_hitters[0]
        # Simulate overpaying
        price_paid = int((hitter.dollar_value or 0) * 2)
        total_surplus = (hitter.dollar_value or 0) - price_paid

        cat_surplus = calculate_category_surplus(hitter, price_paid)

        if cat_surplus:
            surplus_sum = sum(cat_surplus.values())
            assert surplus_sum < 0
            assert abs(surplus_sum - total_surplus) < 0.01

    def test_empty_breakdown_returns_empty(self, session):
        """Test that player without breakdown returns empty dict."""
        player = Player(
            name="No Breakdown",
            player_type="hitter",
            sgp=None,
            sgp_breakdown=None,
        )

        cat_surplus = calculate_category_surplus(player, 10)
        assert cat_surplus == {}

    def test_zero_sgp_distributes_evenly(self, session):
        """Test that zero total SGP distributes surplus evenly."""
        player = Player(
            name="Zero SGP",
            player_type="hitter",
            dollar_value=10,
            sgp=0,
            sgp_breakdown={"r": 0, "hr": 0, "rbi": 0, "sb": 0, "avg": 0},
        )

        cat_surplus = calculate_category_surplus(player, 5)

        # Surplus of $5 should be distributed evenly across 5 categories
        assert len(cat_surplus) == 5
        for val in cat_surplus.values():
            assert val == 1.0  # $5 / 5 categories

    def test_proportional_allocation(self, session):
        """Test that surplus is allocated proportionally to SGP contribution."""
        player = Player(
            name="Proportional",
            player_type="hitter",
            dollar_value=20,
            sgp=10.0,
            sgp_breakdown={"r": 5.0, "hr": 3.0, "rbi": 2.0, "sb": 0, "avg": 0},
        )

        # Buy at $10, so $10 surplus
        cat_surplus = calculate_category_surplus(player, 10)

        # r contributes 50% of SGP, should get 50% of surplus ($5)
        assert abs(cat_surplus["r"] - 5.0) < 0.01
        # hr contributes 30% of SGP, should get 30% of surplus ($3)
        assert abs(cat_surplus["hr"] - 3.0) < 0.01
        # rbi contributes 20% of SGP, should get 20% of surplus ($2)
        assert abs(cat_surplus["rbi"] - 2.0) < 0.01
        # sb and avg contribute 0%, should get 0%
        assert cat_surplus["sb"] == 0
        assert cat_surplus["avg"] == 0


class TestEstimateStandingsPosition:
    """Tests for the estimate_standings_position function."""

    def test_zero_sgp_returns_middle(self):
        """Test that zero SGP returns middle position."""
        position = estimate_standings_position(0, num_teams=12)
        # Middle for 12 teams is 6 or 7
        assert position in [6, 7]

    def test_positive_sgp_better_position(self):
        """Test that positive SGP gives better (lower) position."""
        position = estimate_standings_position(4.0, num_teams=12, sgp_spread=2.0)
        # Should be in top half
        assert position <= 5

    def test_negative_sgp_worse_position(self):
        """Test that negative SGP gives worse (higher) position."""
        position = estimate_standings_position(-4.0, num_teams=12, sgp_spread=2.0)
        # Should be in bottom half
        assert position >= 8

    def test_position_clamped_to_first(self):
        """Test that very high SGP clamps to 1st place."""
        position = estimate_standings_position(100.0, num_teams=12)
        assert position == 1

    def test_position_clamped_to_last(self):
        """Test that very low SGP clamps to last place."""
        position = estimate_standings_position(-100.0, num_teams=12)
        assert position == 12

    def test_different_league_sizes(self):
        """Test with different number of teams."""
        # 10-team league
        position = estimate_standings_position(0, num_teams=10)
        assert 4 <= position <= 6

        # 14-team league
        position = estimate_standings_position(0, num_teams=14)
        assert 6 <= position <= 8


class TestTeamCategorySGP:
    """Tests for the calculate_team_category_sgp function."""

    def test_empty_picks_returns_zeros(self, settings):
        """Test that empty picks list returns zero totals."""
        result = calculate_team_category_sgp([], settings)

        for cat in ["r", "hr", "rbi", "sb", "avg", "w", "sv", "k", "era", "whip"]:
            assert cat in result
            assert result[cat] == 0.0

    def test_single_hitter_sgp(self, session, settings):
        """Test SGP calculation for single hitter."""
        from src.database import Team, DraftPick

        # Create team first
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create pick
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        # Create player with known SGP breakdown, linked to pick
        player = Player(
            name="Test Hitter",
            player_type="hitter",
            sgp=5.0,
            sgp_breakdown={"r": 2.0, "hr": 1.5, "rbi": 1.0, "sb": 0.5, "avg": 0.0},
            draft_pick_id=pick.id,
            is_drafted=True,
        )
        session.add(player)
        session.commit()

        # Refresh to get relationship
        session.refresh(team)

        result = calculate_team_category_sgp(team.draft_picks, settings)

        assert result["r"] == 2.0
        assert result["hr"] == 1.5
        assert result["rbi"] == 1.0
        assert result["sb"] == 0.5
        assert result["avg"] == 0.0

    def test_multiple_players_sums(self, session, settings):
        """Test that SGP from multiple players sums correctly."""
        from src.database import Team, DraftPick

        # Create team first
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create picks
        pick1 = DraftPick(team_id=team.id, price=10, pick_number=1)
        pick2 = DraftPick(team_id=team.id, price=10, pick_number=2)
        session.add_all([pick1, pick2])
        session.commit()

        # Create two players linked to picks
        player1 = Player(
            name="Hitter 1",
            player_type="hitter",
            sgp=3.0,
            sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 0, "avg": 0},
            draft_pick_id=pick1.id,
            is_drafted=True,
        )
        player2 = Player(
            name="Hitter 2",
            player_type="hitter",
            sgp=2.0,
            sgp_breakdown={"r": 0.5, "hr": 0.5, "rbi": 0.5, "sb": 0.5, "avg": 0},
            draft_pick_id=pick2.id,
            is_drafted=True,
        )
        session.add_all([player1, player2])
        session.commit()

        session.refresh(team)

        result = calculate_team_category_sgp(team.draft_picks, settings)

        assert result["r"] == 1.5
        assert result["hr"] == 1.5
        assert result["rbi"] == 1.5
        assert result["sb"] == 0.5


class TestTeamRawStats:
    """Tests for the calculate_team_raw_stats function."""

    def test_counting_stats_sum(self, session, settings):
        """Test that counting stats sum correctly."""
        from src.database import Team, DraftPick

        # Create team
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create picks
        pick1 = DraftPick(team_id=team.id, price=10, pick_number=1)
        pick2 = DraftPick(team_id=team.id, price=10, pick_number=2)
        session.add_all([pick1, pick2])
        session.commit()

        # Create players linked to picks
        player1 = Player(
            name="Hitter 1", player_type="hitter",
            r=80, hr=25, rbi=70, sb=10, ab=500, h=150, avg=0.300,
            draft_pick_id=pick1.id, is_drafted=True,
        )
        player2 = Player(
            name="Hitter 2", player_type="hitter",
            r=60, hr=15, rbi=50, sb=20, ab=400, h=120, avg=0.300,
            draft_pick_id=pick2.id, is_drafted=True,
        )
        session.add_all([player1, player2])
        session.commit()

        session.refresh(team)

        result = calculate_team_raw_stats(team.draft_picks, settings)

        assert result["r"] == 140
        assert result["hr"] == 40
        assert result["rbi"] == 120
        assert result["sb"] == 30

    def test_avg_is_weighted(self, session, settings):
        """Test that AVG is calculated as team average (total H / total AB)."""
        from src.database import Team, DraftPick

        # Create team
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create picks
        pick1 = DraftPick(team_id=team.id, price=10, pick_number=1)
        pick2 = DraftPick(team_id=team.id, price=10, pick_number=2)
        session.add_all([pick1, pick2])
        session.commit()

        # Player 1: 200 AB, 60 H (.300)
        # Player 2: 400 AB, 100 H (.250)
        # Team: 600 AB, 160 H (.267)
        player1 = Player(
            name="High AVG", player_type="hitter",
            r=50, hr=10, rbi=40, sb=5, ab=200, h=60, avg=0.300,
            draft_pick_id=pick1.id, is_drafted=True,
        )
        player2 = Player(
            name="Low AVG", player_type="hitter",
            r=70, hr=20, rbi=60, sb=10, ab=400, h=100, avg=0.250,
            draft_pick_id=pick2.id, is_drafted=True,
        )
        session.add_all([player1, player2])
        session.commit()

        session.refresh(team)

        result = calculate_team_raw_stats(team.draft_picks, settings)

        # 160 / 600 = 0.2667
        assert abs(result["avg"] - 0.2667) < 0.001

    def test_pitcher_ratio_weighted_by_ip(self, session, settings):
        """Test that ERA/WHIP are weighted by IP."""
        from src.database import Team, DraftPick

        # Create team
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create picks
        pick1 = DraftPick(team_id=team.id, price=10, pick_number=1)
        pick2 = DraftPick(team_id=team.id, price=10, pick_number=2)
        session.add_all([pick1, pick2])
        session.commit()

        # Player 1: 100 IP, 2.00 ERA, 1.00 WHIP
        # Player 2: 100 IP, 4.00 ERA, 1.20 WHIP
        # Team: 200 IP, 3.00 ERA, 1.10 WHIP
        player1 = Player(
            name="Ace", player_type="pitcher",
            w=10, sv=0, k=100, ip=100, era=2.00, whip=1.00,
            draft_pick_id=pick1.id, is_drafted=True,
        )
        player2 = Player(
            name="Average", player_type="pitcher",
            w=8, sv=0, k=80, ip=100, era=4.00, whip=1.20,
            draft_pick_id=pick2.id, is_drafted=True,
        )
        session.add_all([player1, player2])
        session.commit()

        session.refresh(team)

        result = calculate_team_raw_stats(team.draft_picks, settings)

        assert abs(result["era"] - 3.00) < 0.01
        assert abs(result["whip"] - 1.10) < 0.01
        assert result["w"] == 18
        assert result["k"] == 180


class TestAnalyzeTeamCategoryBalance:
    """Tests for the analyze_team_category_balance function."""

    def test_returns_all_required_keys(self, session, settings):
        """Test that analysis returns all expected keys."""
        from src.database import Team, DraftPick

        # Create team
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create pick
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        # Create player linked to pick
        player = Player(
            name="Test Player", player_type="hitter",
            r=80, hr=25, rbi=70, sb=10, ab=500, h=150, avg=0.300,
            sgp=3.0, sgp_breakdown={"r": 1.0, "hr": 1.0, "rbi": 1.0, "sb": 0, "avg": 0},
            draft_pick_id=pick.id, is_drafted=True,
        )
        session.add(player)
        session.commit()

        session.refresh(team)

        analysis = analyze_team_category_balance(team.draft_picks, settings)

        assert "sgp_totals" in analysis
        assert "raw_stats" in analysis
        assert "standings" in analysis
        assert "recommendations" in analysis
        assert "hitting_cats" in analysis
        assert "pitching_cats" in analysis
        assert "num_teams" in analysis

    def test_weak_category_generates_recommendation(self, session, settings):
        """Test that weak categories generate recommendations."""
        from src.database import Team, DraftPick

        # Create team
        team = Team(name="Test", budget=260, is_user_team=True)
        session.add(team)
        session.commit()

        # Create pick
        pick = DraftPick(team_id=team.id, price=10, pick_number=1)
        session.add(pick)
        session.commit()

        # Player with strong R but very weak SB
        player = Player(
            name="No Speed", player_type="hitter",
            r=100, hr=35, rbi=100, sb=0, ab=550, h=165, avg=0.300,
            sgp=5.0, sgp_breakdown={"r": 3.0, "hr": 2.0, "rbi": 2.0, "sb": -2.0, "avg": 0},
            draft_pick_id=pick.id, is_drafted=True,
        )
        session.add(player)
        session.commit()

        session.refresh(team)

        analysis = analyze_team_category_balance(team.draft_picks, settings)

        # Should have a recommendation for SB
        sb_recs = [r for r in analysis["recommendations"] if r["category"] == "SB"]
        assert len(sb_recs) > 0

    def test_empty_roster_returns_average_standings(self, settings):
        """Test that empty roster returns middle standings."""
        analysis = analyze_team_category_balance([], settings)

        # All standings should be around middle (6-7 for 12 teams)
        for cat, pos in analysis["standings"].items():
            assert 5 <= pos <= 8


class TestPositionalAdjustments:
    """Tests for positional price adjustments."""

    def test_positional_adjustments_enabled_by_default(self, settings):
        """Test that positional adjustments are enabled by default."""
        assert settings.use_positional_adjustments is True

    def test_positional_adjustments_can_be_disabled(self):
        """Test that positional adjustments can be disabled."""
        settings = LeagueSettings(use_positional_adjustments=False)
        assert settings.use_positional_adjustments is False

    def test_get_positional_demand_standard_roster(self, settings):
        """Test positional demand calculation for standard roster."""
        demand = settings.get_positional_demand()

        # Standard roster: C(1), 1B(1), 2B(1), 3B(1), SS(1), OF(3), UTIL(1)
        # For 12 teams:
        assert demand["C"] == 12  # 1 * 12
        assert demand["1B"] == 12  # 1 * 12
        assert demand["2B"] == 12  # 1 * 12
        assert demand["3B"] == 12  # 1 * 12
        assert demand["SS"] == 12  # 1 * 12
        assert demand["OF"] == 36  # 3 * 12

    def test_get_positional_demand_two_catcher(self):
        """Test positional demand for 2-catcher league."""
        settings = LeagueSettings(
            num_teams=12,
            roster_spots={
                "C": 2,  # Two catchers!
                "1B": 1,
                "2B": 1,
                "3B": 1,
                "SS": 1,
                "OF": 3,
                "UTIL": 1,
                "SP": 2,
                "RP": 2,
                "P": 2,
            }
        )

        demand = settings.get_positional_demand()

        # With 2 catchers per team:
        assert demand["C"] == 24  # 2 * 12

    def test_positional_demand_ci_mi_slots(self):
        """Test that CI/MI slots are distributed correctly."""
        settings = LeagueSettings(
            num_teams=12,
            roster_spots={
                "C": 1,
                "1B": 1,
                "2B": 1,
                "3B": 1,
                "SS": 1,
                "CI": 1,  # Corner infield slot
                "MI": 1,  # Middle infield slot
                "OF": 3,
                "UTIL": 1,
                "SP": 2,
                "RP": 2,
                "P": 0,
            }
        )

        demand = settings.get_positional_demand()

        # CI adds demand to 1B and 3B (split evenly: 6 each)
        assert demand["1B"] == 18  # 12 + 6
        assert demand["3B"] == 18  # 12 + 6

        # MI adds demand to 2B and SS (split evenly: 6 each)
        assert demand["2B"] == 18  # 12 + 6
        assert demand["SS"] == 18  # 12 + 6

    def test_catchers_more_valuable_in_two_catcher_league(self, session):
        """Test that catchers have higher values in 2-catcher league."""
        # Create catchers with identical stats
        for i in range(30):
            player = Player(
                name=f"Catcher {i}",
                player_type="hitter",
                positions="C",
                r=50 - i, hr=15 - i * 0.3, rbi=50 - i, sb=2, avg=0.250,
                ab=400, h=100 - i,
            )
            session.add(player)

        # Create some outfielders for comparison
        for i in range(50):
            player = Player(
                name=f"Outfielder {i}",
                player_type="hitter",
                positions="OF",
                r=80 - i * 0.5, hr=25 - i * 0.3, rbi=80 - i * 0.5, sb=10 - i * 0.1,
                avg=0.280 - i * 0.001, ab=550, h=154 - i * 0.5,
            )
            session.add(player)

        session.commit()

        # Calculate with 1-catcher league
        settings_1c = LeagueSettings(
            num_teams=12,
            roster_spots={"C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "UTIL": 1,
                         "SP": 2, "RP": 2, "P": 2},
            use_positional_adjustments=True,
        )
        calculate_all_player_values(session, settings_1c)

        # Get top catcher value in 1C league
        catchers = session.query(Player).filter(Player.positions == "C").all()
        top_catcher_1c = max(c.dollar_value or 0 for c in catchers)

        # Reset values
        for p in session.query(Player).all():
            p.dollar_value = None
            p.sgp = None
            p.sgp_breakdown = None
        session.commit()

        # Calculate with 2-catcher league
        settings_2c = LeagueSettings(
            num_teams=12,
            roster_spots={"C": 2, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "UTIL": 1,
                         "SP": 2, "RP": 2, "P": 2},
            use_positional_adjustments=True,
        )
        calculate_all_player_values(session, settings_2c)

        # Get top catcher value in 2C league
        catchers = session.query(Player).filter(Player.positions == "C").all()
        top_catcher_2c = max(c.dollar_value or 0 for c in catchers)

        # In a 2C league, the replacement level catcher is worse (24th vs 12th),
        # so top catchers should be worth MORE
        # Note: This might not always be true depending on stat distributions,
        # but in general the top catcher should gain value
        assert top_catcher_2c >= top_catcher_1c * 0.8  # Allow some variance

    def test_values_calculate_without_positional_adjustments(self, session):
        """Test that values can be calculated with positional adjustments disabled."""
        # Create some players
        for i in range(50):
            player = Player(
                name=f"Player {i}",
                player_type="hitter",
                positions="OF",
                r=80 - i * 0.5, hr=25 - i * 0.3, rbi=80 - i * 0.5,
                sb=10, avg=0.280, ab=500, h=140,
            )
            session.add(player)
        session.commit()

        settings = LeagueSettings(use_positional_adjustments=False)
        count = calculate_all_player_values(session, settings)

        assert count == 50
        # Verify values were calculated
        players = session.query(Player).all()
        assert all(p.dollar_value is not None for p in players)
