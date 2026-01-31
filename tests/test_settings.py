"""Tests for league settings."""

import pytest
from src.settings import LeagueSettings, DEFAULT_SETTINGS


class TestLeagueSettings:
    """Tests for LeagueSettings dataclass."""

    def test_default_values(self):
        """Test default settings values."""
        settings = LeagueSettings()

        assert settings.name == "My League"
        assert settings.num_teams == 12
        assert settings.budget_per_team == 260
        assert settings.min_bid == 1

    def test_custom_values(self):
        """Test custom settings values."""
        settings = LeagueSettings(
            name="Custom League",
            num_teams=10,
            budget_per_team=300,
            min_bid=2,
        )

        assert settings.name == "Custom League"
        assert settings.num_teams == 10
        assert settings.budget_per_team == 300
        assert settings.min_bid == 2

    def test_total_league_budget(self):
        """Test total league budget calculation."""
        settings = LeagueSettings(num_teams=12, budget_per_team=260)
        assert settings.total_league_budget == 3120

        settings = LeagueSettings(num_teams=10, budget_per_team=300)
        assert settings.total_league_budget == 3000

    def test_hitter_roster_spots(self):
        """Test hitter roster spots calculation."""
        settings = LeagueSettings()
        # Default: C(1) + 1B(1) + 2B(1) + 3B(1) + SS(1) + OF(3) + UTIL(1) = 9
        assert settings.hitter_roster_spots == 9

    def test_pitcher_roster_spots(self):
        """Test pitcher roster spots calculation."""
        settings = LeagueSettings()
        # Default: SP(2) + RP(2) + P(2) = 6
        assert settings.pitcher_roster_spots == 6

    def test_total_roster_spots(self):
        """Test total roster spots calculation."""
        settings = LeagueSettings()
        # 9 hitters + 6 pitchers = 15
        assert settings.total_roster_spots == 15

    def test_total_hitters_drafted(self):
        """Test total hitters drafted across league."""
        settings = LeagueSettings(num_teams=12)
        # 9 hitter spots * 12 teams = 108
        assert settings.total_hitters_drafted == 108

    def test_total_pitchers_drafted(self):
        """Test total pitchers drafted across league."""
        settings = LeagueSettings(num_teams=12)
        # 6 pitcher spots * 12 teams = 72
        assert settings.total_pitchers_drafted == 72

    def test_custom_roster_spots(self):
        """Test custom roster configuration."""
        custom_roster = {
            "C": 2,
            "1B": 1,
            "2B": 1,
            "3B": 1,
            "SS": 1,
            "OF": 5,
            "UTIL": 2,
            "SP": 3,
            "RP": 3,
            "P": 0,
            "BN": 5,
        }
        settings = LeagueSettings(roster_spots=custom_roster)

        # 2 + 1 + 1 + 1 + 1 + 5 + 2 = 13 hitters
        assert settings.hitter_roster_spots == 13
        # 3 + 3 + 0 = 6 pitchers
        assert settings.pitcher_roster_spots == 6

    def test_hitting_categories(self):
        """Test default hitting categories."""
        settings = LeagueSettings()
        assert settings.hitting_categories == ["R", "HR", "RBI", "SB", "AVG"]

    def test_pitching_categories(self):
        """Test default pitching categories."""
        settings = LeagueSettings()
        assert settings.pitching_categories == ["W", "SV", "K", "ERA", "WHIP"]

    def test_custom_categories(self):
        """Test custom scoring categories."""
        settings = LeagueSettings(
            hitting_categories=["R", "HR", "RBI", "SB", "OBP"],
            pitching_categories=["W", "SV", "K", "ERA", "WHIP", "QS"],
        )

        assert "OBP" in settings.hitting_categories
        assert "QS" in settings.pitching_categories

    def test_hitter_budget_pct(self):
        """Test default hitter budget percentage."""
        settings = LeagueSettings()
        assert settings.hitter_budget_pct == 0.68


class TestDefaultSettings:
    """Tests for DEFAULT_SETTINGS instance."""

    def test_default_settings_exists(self):
        """Test that DEFAULT_SETTINGS is available."""
        assert DEFAULT_SETTINGS is not None
        assert isinstance(DEFAULT_SETTINGS, LeagueSettings)

    def test_default_settings_values(self):
        """Test DEFAULT_SETTINGS has expected values."""
        assert DEFAULT_SETTINGS.num_teams == 12
        assert DEFAULT_SETTINGS.budget_per_team == 260
        assert DEFAULT_SETTINGS.total_league_budget == 3120
