"""League settings and configuration."""

from dataclasses import dataclass, field


@dataclass
class LeagueSettings:
    """Configuration for a fantasy baseball league."""

    name: str = "My League"
    num_teams: int = 12
    budget_per_team: int = 260
    min_bid: int = 1

    # Roster configuration
    roster_spots: dict = field(default_factory=lambda: {
        "C": 1,
        "1B": 1,
        "2B": 1,
        "3B": 1,
        "SS": 1,
        "OF": 3,
        "UTIL": 1,
        "SP": 2,
        "RP": 2,
        "P": 2,
        "BN": 3,
    })

    # Standard 5x5 categories
    hitting_categories: list = field(default_factory=lambda: [
        "R", "HR", "RBI", "SB", "AVG"
    ])

    pitching_categories: list = field(default_factory=lambda: [
        "W", "SV", "K", "ERA", "WHIP"
    ])

    # Budget split between hitters and pitchers
    hitter_budget_pct: float = 0.68

    @property
    def total_league_budget(self) -> int:
        """Total dollars available across all teams."""
        return self.num_teams * self.budget_per_team

    @property
    def hitter_roster_spots(self) -> int:
        """Number of hitter roster spots per team."""
        hitter_positions = ["C", "1B", "2B", "3B", "SS", "OF", "UTIL"]
        return sum(self.roster_spots.get(pos, 0) for pos in hitter_positions)

    @property
    def pitcher_roster_spots(self) -> int:
        """Number of pitcher roster spots per team."""
        pitcher_positions = ["SP", "RP", "P"]
        return sum(self.roster_spots.get(pos, 0) for pos in pitcher_positions)

    @property
    def total_roster_spots(self) -> int:
        """Total roster spots per team (excluding bench)."""
        return self.hitter_roster_spots + self.pitcher_roster_spots

    @property
    def total_hitters_drafted(self) -> int:
        """Total hitters drafted across the league."""
        return self.hitter_roster_spots * self.num_teams

    @property
    def total_pitchers_drafted(self) -> int:
        """Total pitchers drafted across the league."""
        return self.pitcher_roster_spots * self.num_teams


# Default settings instance
DEFAULT_SETTINGS = LeagueSettings()
