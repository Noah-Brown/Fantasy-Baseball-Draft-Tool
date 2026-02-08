"""Database models for the fantasy baseball draft tool."""

from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Player(Base):
    """A baseball player with projected stats."""

    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    team = Column(String)
    positions = Column(String)  # Comma-separated list: "SS,2B"
    player_type = Column(String)  # "hitter" or "pitcher"

    # Hitter stats
    pa = Column(Float)  # Plate appearances
    ab = Column(Float)  # At bats
    h = Column(Float)   # Hits
    r = Column(Float)   # Runs
    hr = Column(Float)  # Home runs
    rbi = Column(Float) # RBIs
    sb = Column(Float)  # Stolen bases
    avg = Column(Float) # Batting average
    obp = Column(Float) # On-base percentage
    slg = Column(Float) # Slugging percentage

    # Pitcher stats
    ip = Column(Float)  # Innings pitched
    w = Column(Float)   # Wins
    sv = Column(Float)  # Saves
    k = Column(Float)   # Strikeouts
    era = Column(Float) # ERA
    whip = Column(Float) # WHIP

    # Calculated values (populated by value engine)
    sgp = Column(Float)          # Total standings gain points
    dollar_value = Column(Float) # Auction dollar value
    sgp_breakdown = Column(JSON) # {"r": 1.5, "hr": 2.1, ...} per-category SGP

    # Draft status
    is_drafted = Column(Boolean, default=False)
    draft_pick_id = Column(Integer, ForeignKey("draft_picks.id"), nullable=True)
    draft_pick = relationship("DraftPick", back_populates="player")

    # User annotations
    note = Column(String)  # Free-text draft note (e.g., "injury", "sleeper", "avoid")

    def __repr__(self):
        return f"<Player {self.name} ({self.positions})>"

    @property
    def position_list(self) -> list[str]:
        """Return positions as a list."""
        if not self.positions:
            return []
        return [p.strip() for p in self.positions.split(",")]

    def can_play(self, position: str) -> bool:
        """Check if player is eligible for a position."""
        from .positions import can_player_fill_position
        return can_player_fill_position(self.position_list, position, self.player_type)


class Team(Base):
    """A fantasy team in the draft."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    budget = Column(Integer, default=260)
    is_user_team = Column(Boolean, default=False)

    draft_picks = relationship("DraftPick", back_populates="team")

    def __repr__(self):
        return f"<Team {self.name}>"

    @property
    def spent(self) -> int:
        """Total amount spent on drafted players."""
        return sum(pick.price or 0 for pick in self.draft_picks)

    @property
    def remaining_budget(self) -> int:
        """Budget remaining for future picks."""
        return self.budget - self.spent

    @property
    def roster_count(self) -> int:
        """Number of players drafted."""
        return len(self.draft_picks)


class DraftPick(Base):
    """A single draft pick."""

    __tablename__ = "draft_picks"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    price = Column(Integer, nullable=True)  # Nullable for snake drafts
    pick_number = Column(Integer)  # Order in which player was drafted
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Snake draft specific fields
    round_number = Column(Integer, nullable=True)  # Which round (1-based)
    pick_in_round = Column(Integer, nullable=True)  # Pick position within round (1-based)

    team = relationship("Team", back_populates="draft_picks")
    player = relationship("Player", back_populates="draft_pick", uselist=False)

    def __repr__(self):
        player_name = self.player.name if self.player else "Unknown"
        return f"<DraftPick {player_name} to {self.team.name} for ${self.price}>"


class DraftState(Base):
    """Global draft state and settings."""

    __tablename__ = "draft_state"

    id = Column(Integer, primary_key=True)
    league_name = Column(String, default="My League")
    num_teams = Column(Integer, default=12)
    budget_per_team = Column(Integer, default=260)
    current_pick = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    values_stale = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Snake draft specific fields
    draft_type = Column(String, default="auction")  # "auction" or "snake"
    draft_order = Column(JSON, nullable=True)  # List of team_ids in first-round order
    current_round = Column(Integer, default=1)  # Current round number for snake drafts


class TargetPlayer(Base):
    """A player the user wants to target in the draft."""

    __tablename__ = "target_players"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, unique=True)
    max_bid = Column(Integer, nullable=False)  # Maximum price willing to pay
    priority = Column(Integer, default=0)  # Higher = more important (for sorting)
    notes = Column(String)  # Optional notes about the player
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    player = relationship("Player", backref="target")

    def __repr__(self):
        return f"<TargetPlayer {self.player.name if self.player else 'Unknown'} max=${self.max_bid}>"


def get_engine(db_path: str = "draft.db"):
    """Create database engine."""
    return create_engine(f"sqlite:///{db_path}")


def init_db(db_path: str = "draft.db"):
    """Initialize the database with all tables."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Create a new database session."""
    Session = sessionmaker(bind=engine)
    return Session()
