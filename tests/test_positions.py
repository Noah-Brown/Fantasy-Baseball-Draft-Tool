"""Tests for position utilities."""

import pytest
from src.positions import (
    COMPOSITE_POSITIONS,
    HITTER_ROSTER_POSITIONS,
    PITCHER_ROSTER_POSITIONS,
    ALL_FILTER_POSITIONS,
    SCARCITY_POSITIONS,
    expand_position,
    can_player_fill_position,
)


class TestExpandPosition:
    """Tests for expand_position function."""

    def test_expand_ci_returns_1b_and_3b(self):
        """CI should expand to 1B and 3B."""
        result = expand_position("CI")
        assert result == ["1B", "3B"]

    def test_expand_mi_returns_2b_and_ss(self):
        """MI should expand to 2B and SS."""
        result = expand_position("MI")
        assert result == ["2B", "SS"]

    def test_expand_util_returns_empty(self):
        """UTIL is special-cased and returns empty list."""
        result = expand_position("UTIL")
        assert result == []

    def test_expand_p_returns_empty(self):
        """P is special-cased and returns empty list."""
        result = expand_position("P")
        assert result == []

    def test_expand_base_position_returns_single(self):
        """Base positions like 1B return themselves in a list."""
        assert expand_position("1B") == ["1B"]
        assert expand_position("SS") == ["SS"]
        assert expand_position("C") == ["C"]
        assert expand_position("OF") == ["OF"]
        assert expand_position("SP") == ["SP"]
        assert expand_position("RP") == ["RP"]


class TestCanPlayerFillPosition:
    """Tests for can_player_fill_position function."""

    def test_hitter_can_fill_util(self):
        """Any hitter can fill UTIL."""
        assert can_player_fill_position(["C"], "UTIL", "hitter") is True
        assert can_player_fill_position(["1B", "3B"], "UTIL", "hitter") is True
        assert can_player_fill_position(["OF"], "UTIL", "hitter") is True

    def test_pitcher_cannot_fill_util(self):
        """Pitchers cannot fill UTIL."""
        assert can_player_fill_position(["SP"], "UTIL", "pitcher") is False
        assert can_player_fill_position(["RP"], "UTIL", "pitcher") is False

    def test_pitcher_can_fill_p(self):
        """Any pitcher can fill P slot."""
        assert can_player_fill_position(["SP"], "P", "pitcher") is True
        assert can_player_fill_position(["RP"], "P", "pitcher") is True

    def test_hitter_cannot_fill_p(self):
        """Hitters cannot fill P slot."""
        assert can_player_fill_position(["1B"], "P", "hitter") is False

    def test_1b_can_fill_ci(self):
        """1B player can fill CI slot."""
        assert can_player_fill_position(["1B"], "CI", "hitter") is True

    def test_3b_can_fill_ci(self):
        """3B player can fill CI slot."""
        assert can_player_fill_position(["3B"], "CI", "hitter") is True

    def test_multi_position_1b_3b_can_fill_ci(self):
        """Player with both 1B and 3B can fill CI."""
        assert can_player_fill_position(["1B", "3B"], "CI", "hitter") is True

    def test_2b_cannot_fill_ci(self):
        """2B player cannot fill CI slot."""
        assert can_player_fill_position(["2B"], "CI", "hitter") is False

    def test_ss_cannot_fill_ci(self):
        """SS player cannot fill CI slot."""
        assert can_player_fill_position(["SS"], "CI", "hitter") is False

    def test_2b_can_fill_mi(self):
        """2B player can fill MI slot."""
        assert can_player_fill_position(["2B"], "MI", "hitter") is True

    def test_ss_can_fill_mi(self):
        """SS player can fill MI slot."""
        assert can_player_fill_position(["SS"], "MI", "hitter") is True

    def test_multi_position_2b_ss_can_fill_mi(self):
        """Player with both 2B and SS can fill MI."""
        assert can_player_fill_position(["2B", "SS"], "MI", "hitter") is True

    def test_1b_cannot_fill_mi(self):
        """1B player cannot fill MI slot."""
        assert can_player_fill_position(["1B"], "MI", "hitter") is False

    def test_3b_cannot_fill_mi(self):
        """3B player cannot fill MI slot."""
        assert can_player_fill_position(["3B"], "MI", "hitter") is False

    def test_base_position_match(self):
        """Player can fill their base position."""
        assert can_player_fill_position(["1B"], "1B", "hitter") is True
        assert can_player_fill_position(["SS"], "SS", "hitter") is True
        assert can_player_fill_position(["C"], "C", "hitter") is True
        assert can_player_fill_position(["OF"], "OF", "hitter") is True
        assert can_player_fill_position(["SP"], "SP", "pitcher") is True
        assert can_player_fill_position(["RP"], "RP", "pitcher") is True

    def test_base_position_no_match(self):
        """Player cannot fill position they don't have."""
        assert can_player_fill_position(["1B"], "2B", "hitter") is False
        assert can_player_fill_position(["SS"], "3B", "hitter") is False
        assert can_player_fill_position(["SP"], "RP", "pitcher") is False

    def test_multi_position_player(self):
        """Multi-position player can fill any of their positions."""
        # SS/2B player
        assert can_player_fill_position(["SS", "2B"], "SS", "hitter") is True
        assert can_player_fill_position(["SS", "2B"], "2B", "hitter") is True
        assert can_player_fill_position(["SS", "2B"], "MI", "hitter") is True
        assert can_player_fill_position(["SS", "2B"], "UTIL", "hitter") is True
        # Cannot fill CI
        assert can_player_fill_position(["SS", "2B"], "CI", "hitter") is False
        assert can_player_fill_position(["SS", "2B"], "1B", "hitter") is False


class TestPositionConstants:
    """Tests for position constant lists."""

    def test_composite_positions_has_ci_mi(self):
        """COMPOSITE_POSITIONS should include CI and MI."""
        assert "CI" in COMPOSITE_POSITIONS
        assert "MI" in COMPOSITE_POSITIONS
        assert COMPOSITE_POSITIONS["CI"] == ["1B", "3B"]
        assert COMPOSITE_POSITIONS["MI"] == ["2B", "SS"]

    def test_hitter_roster_positions_includes_ci_mi(self):
        """HITTER_ROSTER_POSITIONS should include CI and MI."""
        assert "CI" in HITTER_ROSTER_POSITIONS
        assert "MI" in HITTER_ROSTER_POSITIONS

    def test_all_filter_positions_includes_ci_mi(self):
        """ALL_FILTER_POSITIONS should include CI and MI."""
        assert "CI" in ALL_FILTER_POSITIONS
        assert "MI" in ALL_FILTER_POSITIONS

    def test_scarcity_positions_includes_ci_mi(self):
        """SCARCITY_POSITIONS should include CI and MI."""
        assert "CI" in SCARCITY_POSITIONS
        assert "MI" in SCARCITY_POSITIONS

    def test_pitcher_positions_unchanged(self):
        """Pitcher positions should not include CI or MI."""
        assert "CI" not in PITCHER_ROSTER_POSITIONS
        assert "MI" not in PITCHER_ROSTER_POSITIONS
