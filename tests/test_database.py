"""Tests for database models."""

import pytest
from src.database import Player, Team, DraftPick, init_db, get_session, get_engine


class TestPlayer:
    """Tests for the Player model."""

    def test_create_hitter(self, session):
        """Test creating a hitter."""
        player = Player(
            name="Mookie Betts",
            team="LAD",
            positions="OF,2B",
            player_type="hitter",
            hr=30,
            avg=0.280,
        )
        session.add(player)
        session.commit()

        assert player.id is not None
        assert player.name == "Mookie Betts"
        assert player.player_type == "hitter"

    def test_create_pitcher(self, session):
        """Test creating a pitcher."""
        player = Player(
            name="Spencer Strider",
            team="ATL",
            positions="SP",
            player_type="pitcher",
            ip=180,
            k=220,
            era=2.80,
        )
        session.add(player)
        session.commit()

        assert player.id is not None
        assert player.player_type == "pitcher"

    def test_position_list(self, session):
        """Test position_list property."""
        player = Player(name="Test", positions="SS,2B,3B")
        assert player.position_list == ["SS", "2B", "3B"]

    def test_position_list_empty(self, session):
        """Test position_list with no positions."""
        player = Player(name="Test", positions=None)
        assert player.position_list == []

    def test_position_list_single(self, session):
        """Test position_list with single position."""
        player = Player(name="Test", positions="CF")
        assert player.position_list == ["CF"]

    def test_can_play_exact_position(self, sample_hitter):
        """Test can_play with exact position match."""
        assert sample_hitter.can_play("CF") is True
        assert sample_hitter.can_play("SS") is False

    def test_can_play_util(self, sample_hitter):
        """Test that hitters can play UTIL."""
        assert sample_hitter.can_play("UTIL") is True

    def test_can_play_pitcher(self, sample_pitcher):
        """Test that pitchers can play P."""
        assert sample_pitcher.can_play("P") is True
        assert sample_pitcher.can_play("UTIL") is False

    def test_player_repr(self, sample_hitter):
        """Test Player string representation."""
        assert "Mike Trout" in repr(sample_hitter)
        assert "CF" in repr(sample_hitter)


class TestTeam:
    """Tests for the Team model."""

    def test_create_team(self, session):
        """Test creating a team."""
        team = Team(name="My Team", budget=260)
        session.add(team)
        session.commit()

        assert team.id is not None
        assert team.name == "My Team"
        assert team.budget == 260

    def test_team_spent_empty(self, sample_team):
        """Test spent with no draft picks."""
        assert sample_team.spent == 0

    def test_team_remaining_budget(self, sample_team):
        """Test remaining budget calculation."""
        assert sample_team.remaining_budget == 260

    def test_team_roster_count_empty(self, sample_team):
        """Test roster count with no picks."""
        assert sample_team.roster_count == 0

    def test_team_with_draft_picks(self, session, sample_team, sample_hitter):
        """Test team with draft picks."""
        pick = DraftPick(
            team_id=sample_team.id,
            price=45,
            pick_number=1,
        )
        session.add(pick)
        sample_hitter.draft_pick = pick
        sample_hitter.is_drafted = True
        session.commit()

        assert sample_team.spent == 45
        assert sample_team.remaining_budget == 215
        assert sample_team.roster_count == 1

    def test_team_repr(self, sample_team):
        """Test Team string representation."""
        assert "Test Team" in repr(sample_team)


class TestDraftPick:
    """Tests for the DraftPick model."""

    def test_create_draft_pick(self, session, sample_team, sample_hitter):
        """Test creating a draft pick."""
        pick = DraftPick(
            team_id=sample_team.id,
            price=50,
            pick_number=1,
        )
        session.add(pick)
        sample_hitter.draft_pick = pick
        session.commit()

        assert pick.id is not None
        assert pick.price == 50
        assert pick.team.name == "Test Team"

    def test_draft_pick_repr(self, session, sample_team, sample_hitter):
        """Test DraftPick string representation."""
        pick = DraftPick(
            team_id=sample_team.id,
            price=35,
            pick_number=1,
        )
        session.add(pick)
        sample_hitter.draft_pick = pick
        session.commit()

        repr_str = repr(pick)
        assert "Mike Trout" in repr_str
        assert "Test Team" in repr_str
        assert "$35" in repr_str


class TestDatabaseFunctions:
    """Tests for database utility functions."""

    def test_get_engine(self, tmp_path):
        """Test creating a database engine."""
        db_path = tmp_path / "test.db"
        engine = get_engine(str(db_path))
        assert engine is not None

    def test_init_db(self, tmp_path):
        """Test database initialization."""
        db_path = tmp_path / "test.db"
        engine = init_db(str(db_path))
        assert engine is not None
        assert db_path.exists()

    def test_get_session(self, engine):
        """Test creating a session."""
        session = get_session(engine)
        assert session is not None
        session.close()
