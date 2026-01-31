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

        sgp = _calculate_player_sgp(
            good_player, categories, "hitter",
            replacement_stats, denominators
        )

        assert sgp > 0

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

        sgp = _calculate_player_sgp(
            bad_player, categories, "hitter",
            replacement_stats, denominators
        )

        assert sgp < 0

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

        sgp = _calculate_player_sgp(
            good_pitcher, categories, "pitcher",
            replacement_stats, denominators
        )

        # ERA/WHIP contributions should be positive (good pitcher has lower values)
        assert sgp > 0


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
