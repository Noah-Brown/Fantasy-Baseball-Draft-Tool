"""Tests for Yahoo position fetch script utilities."""

import pytest
from scripts.fetch_yahoo_positions import normalize_name, match_players, format_positions
from src.database import Player


class TestNormalizeName:
    """Tests for name normalization."""

    def test_basic_name(self):
        assert normalize_name("Mike Trout") == "mike trout"

    def test_accented_characters(self):
        assert normalize_name("José Ramírez") == "jose ramirez"

    def test_jr_suffix(self):
        assert normalize_name("Fernando Tatis Jr.") == "fernando tatis"

    def test_iii_suffix(self):
        assert normalize_name("Ronald Acuna III") == "ronald acuna"

    def test_parenthetical(self):
        assert normalize_name("Shohei Ohtani (Hitter)") == "shohei ohtani"

    def test_periods_removed(self):
        assert normalize_name("J.T. Realmuto") == "jt realmuto"

    def test_extra_whitespace(self):
        assert normalize_name("  Juan   Soto  ") == "juan soto"


class TestFormatPositions:
    """Tests for Yahoo position formatting."""

    def test_basic_positions(self):
        assert format_positions(["C", "1B"]) == "C,1B"

    def test_filters_meta_positions(self):
        assert format_positions(["SS", "Util", "BN"]) == "SS"

    def test_outfield_consolidation(self):
        result = format_positions(["LF", "CF", "RF", "Util"])
        assert result == "OF"

    def test_outfield_with_other_positions(self):
        result = format_positions(["CF", "DH", "Util"])
        assert "OF" in result
        assert "DH" in result
        assert "Util" not in result

    def test_empty_list(self):
        assert format_positions([]) == ""

    def test_util_only_kept_as_util(self):
        assert format_positions(["Util"]) == "UTIL"

    def test_other_meta_positions_filtered(self):
        assert format_positions(["BN", "IL"]) == ""

    def test_pitcher_positions(self):
        assert format_positions(["SP", "RP"]) == "SP,RP"


class TestMatchPlayers:
    """Tests for player matching logic."""

    def test_exact_match(self, session):
        player = Player(name="Mike Trout", team="LAA", player_type="hitter")
        session.add(player)
        session.commit()

        yahoo_players = {
            "123": {"player_id": "123", "name": "Mike Trout",
                    "eligible_positions": ["CF"], "position_type": "B"}
        }

        matched, unmatched = match_players(yahoo_players, [player])
        assert len(matched) == 1
        assert matched[0][2] == 1.0  # exact match score
        assert len(unmatched) == 0

    def test_fuzzy_match_accents(self, session):
        player = Player(name="Jose Ramirez", team="CLE", player_type="hitter")
        session.add(player)
        session.commit()

        yahoo_players = {
            "456": {"player_id": "456", "name": "José Ramírez",
                    "eligible_positions": ["3B"], "position_type": "B"}
        }

        matched, unmatched = match_players(yahoo_players, [player])
        assert len(matched) == 1
        assert len(unmatched) == 0

    def test_split_player_match(self, session):
        """Test that split players (e.g., Ohtani) match by type."""
        hitter = Player(name="Shohei Ohtani", team="LAD", player_type="hitter")
        pitcher = Player(name="Shohei Ohtani", team="LAD", player_type="pitcher")
        session.add_all([hitter, pitcher])
        session.commit()

        yahoo_players = {
            "100": {"player_id": "100", "name": "Shohei Ohtani (Hitter)",
                    "eligible_positions": ["DH", "OF"], "position_type": "B"},
            "200": {"player_id": "200", "name": "Shohei Ohtani (Pitcher)",
                    "eligible_positions": ["SP"], "position_type": "P"},
        }

        matched, unmatched = match_players(yahoo_players, [hitter, pitcher])
        assert len(matched) == 2
        assert len(unmatched) == 0
        # Verify correct type mapping
        hitter_match = next(m for m in matched if m[0].player_type == "hitter")
        pitcher_match = next(m for m in matched if m[0].player_type == "pitcher")
        assert hitter_match[1]["player_id"] == "100"
        assert pitcher_match[1]["player_id"] == "200"

    def test_no_match(self, session):
        player = Player(name="Fake Player", team="XXX", player_type="hitter")
        session.add(player)
        session.commit()

        yahoo_players = {
            "789": {"player_id": "789", "name": "Real Player",
                    "eligible_positions": ["1B"], "position_type": "B"}
        }

        matched, unmatched = match_players(yahoo_players, [player])
        assert len(matched) == 0
        assert len(unmatched) == 1
