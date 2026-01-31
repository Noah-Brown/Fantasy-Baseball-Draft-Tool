"""Shared test fixtures."""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base, Player, Team, DraftPick


@pytest.fixture
def engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_hitter(session):
    """Create a sample hitter for testing."""
    player = Player(
        name="Mike Trout",
        team="LAA",
        positions="CF",
        player_type="hitter",
        pa=600,
        ab=550,
        h=165,
        r=100,
        hr=40,
        rbi=100,
        sb=10,
        avg=0.300,
        obp=0.400,
        slg=0.600,
    )
    session.add(player)
    session.commit()
    return player


@pytest.fixture
def sample_pitcher(session):
    """Create a sample pitcher for testing."""
    player = Player(
        name="Gerrit Cole",
        team="NYY",
        positions="SP",
        player_type="pitcher",
        ip=200,
        w=15,
        sv=0,
        k=250,
        era=3.00,
        whip=1.00,
    )
    session.add(player)
    session.commit()
    return player


@pytest.fixture
def sample_team(session):
    """Create a sample team for testing."""
    team = Team(
        name="Test Team",
        budget=260,
        is_user_team=True,
    )
    session.add(team)
    session.commit()
    return team


@pytest.fixture
def tmp_csv_path(tmp_path):
    """Return a factory for creating temporary CSV files."""
    def _create_csv(filename: str, content: str) -> Path:
        csv_path = tmp_path / filename
        csv_path.write_text(content)
        return csv_path
    return _create_csv
