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
        "CI": 0,   # Corner Infielder (1B/3B)
        "MI": 0,   # Middle Infielder (2B/SS)
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

    # Positional adjustment settings
    use_positional_adjustments: bool = True  # Enable replacement-level positional adjustments

    @property
    def total_league_budget(self) -> int:
        """Total dollars available across all teams."""
        return self.num_teams * self.budget_per_team

    @property
    def hitter_roster_spots(self) -> int:
        """Number of hitter roster spots per team."""
        from .positions import HITTER_ROSTER_POSITIONS
        return sum(self.roster_spots.get(pos, 0) for pos in HITTER_ROSTER_POSITIONS)

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

    def get_positional_demand(self) -> dict[str, int]:
        """
        Calculate how many players at each position will be drafted league-wide.

        This accounts for composite positions (CI, MI, UTIL) by distributing
        their demand to constituent positions. For example:
        - CI slots increase demand for both 1B and 3B
        - UTIL slots increase overall hitter demand (distributed proportionally)

        Returns:
            Dict mapping position codes to number of players needed
        """
        from .positions import COMPOSITE_POSITIONS

        demand = {}

        # Start with direct position slots (C, 1B, 2B, 3B, SS, OF, SP, RP)
        direct_positions = ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP"]
        for pos in direct_positions:
            demand[pos] = int(self.roster_spots.get(pos, 0) * self.num_teams)

        # Handle CI (Corner Infield) - splits demand between 1B and 3B
        ci_slots = int(self.roster_spots.get("CI", 0) * self.num_teams)
        if ci_slots > 0:
            # Distribute CI demand to 1B and 3B (half each, rounded)
            demand["1B"] = demand.get("1B", 0) + ci_slots // 2
            demand["3B"] = demand.get("3B", 0) + (ci_slots - ci_slots // 2)

        # Handle MI (Middle Infield) - splits demand between 2B and SS
        mi_slots = int(self.roster_spots.get("MI", 0) * self.num_teams)
        if mi_slots > 0:
            # Distribute MI demand to 2B and SS (half each, rounded)
            demand["2B"] = demand.get("2B", 0) + mi_slots // 2
            demand["SS"] = demand.get("SS", 0) + (mi_slots - mi_slots // 2)

        # Handle UTIL - increases overall hitter pool demand
        # We don't add UTIL to specific positions; it's handled in overall pool sizing
        # UTIL players are valued at their primary position

        # Handle P (generic pitcher) - splits between SP and RP
        p_slots = int(self.roster_spots.get("P", 0) * self.num_teams)
        if p_slots > 0:
            # Distribute P demand to SP and RP (half each, rounded)
            demand["SP"] = demand.get("SP", 0) + p_slots // 2
            demand["RP"] = demand.get("RP", 0) + (p_slots - p_slots // 2)

        return demand


# Default settings instance
DEFAULT_SETTINGS = LeagueSettings()
