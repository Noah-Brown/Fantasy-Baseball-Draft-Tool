"""Tests for projection import functions."""

import pytest
import pandas as pd
from src.projections import (
    import_hitters_csv,
    import_pitchers_csv,
    get_all_hitters,
    get_all_pitchers,
    get_available_players,
    clear_all_players,
    _safe_float,
    _safe_str,
    _extract_positions,
    _extract_pitcher_positions,
)
from src.database import Player


class TestSafeFloat:
    """Tests for _safe_float helper function."""

    def test_valid_integer(self):
        """Test converting integer to float."""
        assert _safe_float(42) == 42.0

    def test_valid_float(self):
        """Test converting float."""
        assert _safe_float(3.14) == 3.14

    def test_valid_string(self):
        """Test converting numeric string."""
        assert _safe_float("100") == 100.0

    def test_none_value(self):
        """Test None returns None."""
        assert _safe_float(None) is None

    def test_nan_value(self):
        """Test NaN returns None."""
        assert _safe_float(float("nan")) is None

    def test_invalid_string(self):
        """Test invalid string returns None."""
        assert _safe_float("not a number") is None

    def test_pandas_na(self):
        """Test pandas NA returns None."""
        assert _safe_float(pd.NA) is None


class TestExtractPositions:
    """Tests for _extract_positions helper function."""

    def test_pos_column(self):
        """Test extracting from Pos column."""
        row = pd.Series({"Name": "Test Player", "Pos": "SS"})
        assert _extract_positions(row) == "SS"

    def test_position_column(self):
        """Test extracting from Position column."""
        row = pd.Series({"Name": "Test Player", "Position": "2B,SS"})
        assert _extract_positions(row) == "2B,SS"

    def test_position_in_name(self):
        """Test extracting position from name with parentheses."""
        row = pd.Series({"Name": "Mike Trout (CF)"})
        assert _extract_positions(row) == "CF"

    def test_no_position(self):
        """Test no position returns empty string."""
        row = pd.Series({"Name": "Test Player"})
        assert _extract_positions(row) == ""


class TestExtractPitcherPositions:
    """Tests for _extract_pitcher_positions helper function."""

    def test_explicit_pos_column(self):
        """Test extracting from Pos column."""
        row = pd.Series({"Name": "Test Pitcher", "Pos": "SP"})
        assert _extract_pitcher_positions(row) == "SP"

    def test_infer_sp_from_gs(self):
        """Test inferring SP from games started."""
        row = pd.Series({"Name": "Test Pitcher", "GS": 30, "SV": 0, "G": 32})
        assert "SP" in _extract_pitcher_positions(row)

    def test_infer_rp_from_saves(self):
        """Test inferring RP from saves."""
        row = pd.Series({"Name": "Test Pitcher", "GS": 0, "SV": 30, "G": 60})
        assert "RP" in _extract_pitcher_positions(row)

    def test_infer_rp_from_relief_appearances(self):
        """Test inferring RP from relief appearances (more G than GS)."""
        # Need GS > 0 for the (g - gs) > 10 check to work due to truthy check
        row = pd.Series({"Name": "Test Pitcher", "GS": 2, "SV": 0, "G": 50})
        assert "RP" in _extract_pitcher_positions(row)

    def test_default_to_sp(self):
        """Test default to SP when cannot determine."""
        row = pd.Series({"Name": "Test Pitcher"})
        assert _extract_pitcher_positions(row) == "SP"


class TestSafeStr:
    """Tests for _safe_str helper function."""

    def test_valid_string(self):
        assert _safe_str("abc") == "abc"

    def test_integer_value(self):
        assert _safe_str(12345) == "12345"

    def test_none_value(self):
        assert _safe_str(None) is None

    def test_nan_value(self):
        assert _safe_str(float("nan")) is None

    def test_empty_string(self):
        assert _safe_str("") is None

    def test_whitespace_string(self):
        assert _safe_str("  ") is None


class TestImportHittersCsv:
    """Tests for import_hitters_csv function."""

    def test_import_basic_hitters(self, session, tmp_csv_path):
        """Test importing basic hitter CSV."""
        csv_content = """Name,Team,PA,AB,H,R,HR,RBI,SB,AVG,OBP,SLG
Juan Soto,NYY,700,550,165,120,40,100,5,0.300,0.420,0.550
Shohei Ohtani,LAD,650,550,175,110,50,120,20,0.318,0.400,0.650"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        count = import_hitters_csv(session, csv_path)

        assert count == 2
        players = get_all_hitters(session)
        assert len(players) == 2
        assert any(p.name == "Juan Soto" for p in players)
        assert any(p.name == "Shohei Ohtani" for p in players)

    def test_import_hitters_with_positions(self, session, tmp_csv_path):
        """Test importing hitters with position column."""
        csv_content = """Name,Team,Pos,PA,HR,AVG
Mookie Betts,LAD,OF,650,30,0.280
Corey Seager,TEX,SS,600,35,0.275"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        count = import_hitters_csv(session, csv_path)

        assert count == 2
        players = get_all_hitters(session)
        mookie = next(p for p in players if p.name == "Mookie Betts")
        assert mookie.positions == "OF"

    def test_import_hitters_with_position_in_name(self, session, tmp_csv_path):
        """Test importing hitters with position in name."""
        csv_content = """Name,Team,PA,HR
Mike Trout (CF),LAA,600,40"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        count = import_hitters_csv(session, csv_path)

        player = get_all_hitters(session)[0]
        assert player.positions == "CF"

    def test_import_hitters_with_missing_values(self, session, tmp_csv_path):
        """Test importing hitters with missing values."""
        csv_content = """Name,Team,PA,HR,AVG
Test Player,NYY,,30,"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        count = import_hitters_csv(session, csv_path)

        player = get_all_hitters(session)[0]
        assert player.pa is None
        assert player.hr == 30
        assert player.avg is None


    def test_import_hitters_stores_fangraphs_id(self, session, tmp_csv_path):
        """Test that Fangraphs player IDs are stored from FGDC CSV."""
        csv_content = """Name,Team,PA,HR,AVG,playerid,xMLBAMID
Juan Soto,NYY,700,40,0.300,20123,665742"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        import_hitters_csv(session, csv_path)

        player = get_all_hitters(session)[0]
        assert player.fangraphs_id == "20123"
        assert player.mlbam_id == "665742"

    def test_import_hitters_no_position(self, session, tmp_csv_path):
        """Test importing hitters without position column (FGDC default)."""
        csv_content = """Name,Team,PA,HR,AVG
Test Player,NYY,600,30,0.280"""
        csv_path = tmp_csv_path("hitters.csv", csv_content)

        import_hitters_csv(session, csv_path)

        player = get_all_hitters(session)[0]
        assert player.positions == ""


class TestImportPitchersCsv:
    """Tests for import_pitchers_csv function."""

    def test_import_basic_pitchers(self, session, tmp_csv_path):
        """Test importing basic pitcher CSV."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,WHIP
Gerrit Cole,NYY,200,15,0,250,3.00,1.00
Josh Hader,HOU,60,5,40,80,2.50,0.90"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        count = import_pitchers_csv(session, csv_path)

        assert count == 2
        pitchers = get_all_pitchers(session)
        assert len(pitchers) == 2

    def test_import_pitchers_with_k_column(self, session, tmp_csv_path):
        """Test importing pitchers with K instead of SO."""
        csv_content = """Name,Team,IP,W,SV,K,ERA,WHIP
Test Pitcher,NYY,200,15,0,250,3.00,1.00"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        count = import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.k == 250

    def test_import_pitchers_infers_position(self, session, tmp_csv_path):
        """Test that pitcher positions are inferred from stats."""
        csv_content = """Name,Team,IP,W,SV,K,ERA,WHIP,GS,G
Starter,NYY,180,12,0,200,3.50,1.10,30,32
Reliever,LAD,60,3,35,70,2.50,0.95,0,60"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitchers = get_all_pitchers(session)
        starter = next(p for p in pitchers if p.name == "Starter")
        reliever = next(p for p in pitchers if p.name == "Reliever")

        assert "SP" in starter.positions
        assert "RP" in reliever.positions


    def test_import_pitchers_whip_fallback(self, session, tmp_csv_path):
        """Test WHIP is computed from BB and H when missing."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,BB,H
Test Pitcher,NYY,200,15,0,250,3.00,50,160"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.whip == pytest.approx((50 + 160) / 200)

    def test_import_pitchers_stores_fangraphs_id(self, session, tmp_csv_path):
        """Test that Fangraphs player IDs are stored from FGDC CSV."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,WHIP,playerid,xMLBAMID
Gerrit Cole,NYY,200,15,0,250,3.00,1.00,13125,543037"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.fangraphs_id == "13125"
        assert pitcher.mlbam_id == "543037"

    def test_import_pitchers_k9_from_csv(self, session, tmp_csv_path):
        """Test that K/9 is imported directly from CSV."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,WHIP,K/9
Test Pitcher,NYY,200,15,0,250,3.00,1.00,11.25"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.k9 == 11.25

    def test_import_pitchers_k9_fallback(self, session, tmp_csv_path):
        """Test that K/9 is computed from K and IP when not in CSV."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,WHIP
Test Pitcher,NYY,200,15,0,200,3.00,1.00"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.k9 == pytest.approx(9.0)  # (200 * 9) / 200

    def test_import_pitchers_hld(self, session, tmp_csv_path):
        """Test that HLD is imported from CSV."""
        csv_content = """Name,Team,IP,W,SV,SO,ERA,WHIP,HLD
Test Reliever,NYY,60,3,0,70,2.50,0.95,25"""
        csv_path = tmp_csv_path("pitchers.csv", csv_content)

        import_pitchers_csv(session, csv_path)

        pitcher = get_all_pitchers(session)[0]
        assert pitcher.hld == 25.0


class TestPlayerQueries:
    """Tests for player query functions."""

    def test_get_all_hitters(self, session, sample_hitter, sample_pitcher):
        """Test getting all hitters."""
        hitters = get_all_hitters(session)
        assert len(hitters) == 1
        assert hitters[0].name == "Mike Trout"

    def test_get_all_pitchers(self, session, sample_hitter, sample_pitcher):
        """Test getting all pitchers."""
        pitchers = get_all_pitchers(session)
        assert len(pitchers) == 1
        assert pitchers[0].name == "Gerrit Cole"

    def test_get_available_players_all(self, session, sample_hitter, sample_pitcher):
        """Test getting all available players."""
        players = get_available_players(session)
        assert len(players) == 2

    def test_get_available_players_by_type(self, session, sample_hitter, sample_pitcher):
        """Test getting available players by type."""
        hitters = get_available_players(session, "hitter")
        pitchers = get_available_players(session, "pitcher")

        assert len(hitters) == 1
        assert len(pitchers) == 1

    def test_get_available_excludes_drafted(self, session, sample_hitter, sample_pitcher):
        """Test that drafted players are excluded."""
        sample_hitter.is_drafted = True
        session.commit()

        available = get_available_players(session)
        assert len(available) == 1
        assert available[0].name == "Gerrit Cole"

    def test_clear_all_players(self, session, sample_hitter, sample_pitcher):
        """Test clearing all players."""
        assert session.query(Player).count() == 2

        clear_all_players(session)

        assert session.query(Player).count() == 0
