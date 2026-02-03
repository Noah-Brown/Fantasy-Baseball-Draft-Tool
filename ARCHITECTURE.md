# Fantasy Baseball Draft Tool - Architecture Documentation

This document provides comprehensive technical documentation of the Fantasy Baseball Draft Tool's architecture, data flows, module dependencies, and key algorithms.

## Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Module Architecture](#module-architecture)
4. [Data Models](#data-models)
5. [Data Flow](#data-flow)
6. [Key Algorithms](#key-algorithms)
7. [Configuration](#configuration)
8. [API Reference](#api-reference)

---

## System Overview

The Fantasy Baseball Draft Tool is a local Streamlit application for managing fantasy baseball auction drafts. It uses Standings Gain Points (SGP) methodology to calculate player values and dynamically recalculates values throughout the draft as the player pool shrinks.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Streamlit UI (app.py)                       │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐ │
│  │  Player  │ │  Draft   │ │   My    │ │   All   │ │   League    │ │
│  │ Database │ │   Room   │ │  Team   │ │  Teams  │ │  Settings   │ │
│  └────┬─────┘ └────┬─────┘ └────┬────┘ └────┬────┘ └──────┬──────┘ │
└───────┼────────────┼────────────┼───────────┼─────────────┼────────┘
        │            │            │           │             │
        v            v            v           v             v
┌─────────────────────────────────────────────────────────────────────┐
│                        Core Modules (src/)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ projections │  │    draft    │  │   values    │  │ settings  │  │
│  │   .py       │  │    .py      │  │    .py      │  │   .py     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │
│         │                │                │                │        │
│         │         ┌──────┴──────┐         │                │        │
│         │         │   needs.py  │◄────────┘                │        │
│         │         │             │                          │        │
│         │         └──────┬──────┘                          │        │
│         │                │                │                │        │
│         └────────────────┴────────────────┴────────────────┘        │
│                                  │                                  │
│                                  v                                  │
│                        ┌─────────────────┐                          │
│                        │   database.py   │                          │
│                        │  (SQLAlchemy)   │                          │
│                        └────────┬────────┘                          │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │
                                  v
                         ┌────────────────┐
                         │   draft.db     │
                         │   (SQLite)     │
                         └────────────────┘
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| UI Framework | Streamlit >= 1.28.0 | Web interface and user interaction |
| Data Processing | Pandas >= 2.0.0 | CSV parsing and data manipulation |
| ORM | SQLAlchemy >= 2.0.0 | Database abstraction layer |
| Database | SQLite | Local persistent storage |
| Language | Python 3.10+ | Application runtime |

### External Data Sources

- **Fangraphs Steamer Projections**: CSV exports (requires subscription)
  - Hitter projections: PA, AB, H, R, HR, RBI, SB, AVG, OBP, SLG
  - Pitcher projections: IP, W, SV, K, ERA, WHIP

---

## Module Architecture

### Dependency Graph

```
                    ┌─────────────┐
                    │   app.py    │
                    │   (main)    │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         v                 v                 v
┌────────────────┐ ┌──────────────┐ ┌────────────────┐
│ projections.py │ │   draft.py   │ │  settings.py   │
│                │ │              │ │                │
│ - CSV import   │ │ - Draft mgmt │ │ - League config│
│ - Player query │ │ - Team mgmt  │ │ - Roster spots │
└───────┬────────┘ └──────┬───────┘ └───────┬────────┘
        │                 │                 │
        │    ┌────────────┴────────────┐    │
        │    │                         │    │
        v    v                         v    v
┌────────────────┐             ┌──────────────┐
│  database.py   │◄────────────│   values.py  │
│                │             │              │
│ - ORM models   │             │ - SGP calc   │
│ - DB session   │             │ - Dollar val │
└───────┬────────┘             └──────────────┘
        │
        v
┌────────────────┐
│  positions.py  │
│                │
│ - CI/MI logic  │
│ - Eligibility  │
└────────────────┘
```

### Module Responsibilities

| Module | File | Responsibilities |
|--------|------|------------------|
| **Database** | `src/database.py` | SQLAlchemy ORM models, database initialization, session management |
| **Projections** | `src/projections.py` | CSV import/parsing, player CRUD operations, position extraction |
| **Settings** | `src/settings.py` | League configuration dataclass, roster structure, budget allocation |
| **Draft** | `src/draft.py` | Draft state management, team operations, pick tracking, undo functionality |
| **Values** | `src/values.py` | SGP calculation engine, dollar value conversion, value recalculation |
| **Positions** | `src/positions.py` | Position constants, composite position handling (CI/MI), eligibility checking |
| **Needs** | `src/needs.py` | Team needs analysis, positional roster tracking, player recommendations |
| **App** | `app.py` | Streamlit UI, page routing, session state management |

---

## Data Models

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Player                                  │
├─────────────────────────────────────────────────────────────────────┤
│ PK  id: Integer                                                      │
│     name: String                                                     │
│     team: String (MLB team)                                          │
│     positions: String (comma-separated)                              │
│     player_type: Enum (hitter | pitcher)                             │
│     ─────────── Hitter Stats ───────────                             │
│     pa, ab, h, r, hr, rbi, sb: Integer                               │
│     avg, obp, slg: Float                                             │
│     ─────────── Pitcher Stats ──────────                             │
│     ip, w, sv, k: Integer/Float                                      │
│     era, whip: Float                                                 │
│     ─────────── Calculated ─────────────                             │
│     sgp: Float                                                       │
│     dollar_value: Float                                              │
│     sgp_breakdown: JSON                                              │
│     is_drafted: Boolean                                              │
│ FK  draft_pick_id: Integer ─────────────────────┐                    │
└─────────────────────────────────────────────────┼────────────────────┘
                                                  │
                                                  │ 1:1
                                                  │
┌─────────────────────────────────────────────────┼────────────────────┐
│                           DraftPick             │                    │
├─────────────────────────────────────────────────┼────────────────────┤
│ PK  id: Integer ◄───────────────────────────────┘                    │
│ FK  team_id: Integer ───────────────────────────┐                    │
│     price: Integer                              │                    │
│     pick_number: Integer                        │                    │
│     timestamp: DateTime                         │                    │
└─────────────────────────────────────────────────┼────────────────────┘
                                                  │
                                                  │ N:1
                                                  │
┌─────────────────────────────────────────────────┼────────────────────┐
│                              Team               │                    │
├─────────────────────────────────────────────────┼────────────────────┤
│ PK  id: Integer ◄───────────────────────────────┘                    │
│     name: String                                                     │
│     budget: Integer                                                  │
│     is_user_team: Boolean                                            │
│     ─────────── Computed Properties ────────────                     │
│     spent: Integer (sum of draft_pick prices)                        │
│     remaining_budget: Integer (budget - spent)                       │
│     roster_count: Integer (len(draft_picks))                         │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                           DraftState                                 │
├──────────────────────────────────────────────────────────────────────┤
│ PK  id: Integer                                                      │
│     league_name: String                                              │
│     num_teams: Integer                                               │
│     budget_per_team: Integer                                         │
│     is_active: Boolean                                               │
│     values_stale: Boolean                                            │
└──────────────────────────────────────────────────────────────────────┘
```

### LeagueSettings (Dataclass)

```python
@dataclass
class LeagueSettings:
    name: str = "My League"
    num_teams: int = 12
    budget_per_team: int = 260
    min_bid: int = 1
    roster_spots: dict = {
        "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1,
        "CI": 0,   # Corner Infielder (1B/3B)
        "MI": 0,   # Middle Infielder (2B/SS)
        "OF": 3, "UTIL": 1,
        "SP": 2, "RP": 2, "P": 2, "BN": 3
    }
    hitting_categories: list = ["R", "HR", "RBI", "SB", "AVG"]
    pitching_categories: list = ["W", "SV", "K", "ERA", "WHIP"]
    hitter_budget_pct: float = 0.68  # 68% hitters, 32% pitchers
```

---

## Data Flow

### Application Startup Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Application Startup                          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  streamlit run app.py │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │    init_db("draft.db")│
                    │  Create tables if new │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │   auto_load_data()    │
                    │   Check /data folder  │
                    └───────────┬───────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
                v                               v
    ┌─────────────────────┐         ┌─────────────────────┐
    │ CSV files exist?    │   No    │ Skip auto-import    │
    │ Database empty?     │────────►│                     │
    └──────────┬──────────┘         └─────────────────────┘
               │ Yes
               v
    ┌─────────────────────┐
    │ import_hitters_csv()│
    │ import_pitchers_csv │
    └──────────┬──────────┘
               │
               v
    ┌─────────────────────┐
    │ calculate_all_      │
    │ player_values()     │
    └──────────┬──────────┘
               │
               v
    ┌─────────────────────┐
    │ Initialize session  │
    │ state, render UI    │
    └─────────────────────┘
```

### CSV Import Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CSV Import Process                           │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │   Read CSV with       │
                    │   pandas.read_csv()   │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Column Mapping       │
                    │  ───────────────────  │
                    │  Hitters: Name, Team, │
                    │  PA, AB, H, R, HR,    │
                    │  RBI, SB, AVG, OBP,   │
                    │  SLG                  │
                    │  ───────────────────  │
                    │  Pitchers: Name, Team,│
                    │  IP, W, SV, K/SO,     │
                    │  ERA, WHIP            │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  _extract_positions() │
                    │  Parse "Pos" column   │
                    │  or name parentheses  │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Calculate derived    │
                    │  stats if missing     │
                    │  - AB from PA         │
                    │  - H from AB * AVG    │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Create Player()      │
                    │  objects, bulk insert │
                    │  to database          │
                    └─────────────────────────┘
```

### Draft Operation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Draft Player Flow                            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  User selects:        │
                    │  - Player             │
                    │  - Team               │
                    │  - Price              │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  draft_player()       │
                    │  Validation:          │
                    │  - Player not drafted │
                    │  - Team has budget    │
                    └───────────┬───────────┘
                                │
               ┌────────────────┴────────────────┐
               │                                 │
               v                                 v
    ┌─────────────────────┐           ┌─────────────────────┐
    │  Create DraftPick   │           │  Update Player      │
    │  - team_id          │           │  - is_drafted=True  │
    │  - price            │           │  - draft_pick_id    │
    │  - pick_number      │           │                     │
    │  - timestamp        │           │                     │
    └──────────┬──────────┘           └──────────┬──────────┘
               │                                 │
               └────────────────┬────────────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  calculate_remaining_ │
                    │  player_values()      │
                    │  ─────────────────────│
                    │  1. Get remaining     │
                    │     roster slots      │
                    │  2. Get remaining     │
                    │     budget            │
                    │  3. Recalculate SGP   │
                    │     for undrafted     │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  UI refreshes with    │
                    │  updated values       │
                    └─────────────────────────┘
```

### Value Calculation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SGP Value Calculation Flow                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  calculate_all_       │
                    │  player_values()      │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Step 1: Preliminary  │
                    │  Sort                 │
                    │  Quick value estimate │
                    │  to identify pool     │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Step 2: Define Pool  │
                    │  Top N players where  │
                    │  N = roster_slots *   │
                    │  num_teams            │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Step 3: Replacement  │
                    │  Level                │
                    │  Nth player's stats   │
                    │  become baseline      │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Step 4: SGP          │
                    │  Denominators         │
                    │  StdDev per category  │
                    │  across pool          │
                    └───────────┬───────────┘
                                │
                                v
              ┌─────────────────┴─────────────────┐
              │                                   │
              v                                   v
┌─────────────────────────┐         ┌─────────────────────────┐
│   Counting Stats        │         │   Rate/Ratio Stats      │
│   (R, HR, RBI, SB,      │         │   (AVG, ERA, WHIP)      │
│    W, SV, K)            │         │                         │
│   ──────────────────────│         │   ──────────────────────│
│   SGP = (Stat - Repl)   │         │   AVG: Weighted by AB   │
│         / StdDev        │         │   ERA/WHIP: Lower=better│
│                         │         │   weighted by IP         │
└───────────┬─────────────┘         └───────────┬─────────────┘
            │                                   │
            └─────────────────┬─────────────────┘
                              │
                              v
                    ┌───────────────────────┐
                    │  Step 5: Dollar       │
                    │  Conversion           │
                    │  ─────────────────────│
                    │  Total Positive SGP   │
                    │  $/SGP = Budget /     │
                    │          Total SGP    │
                    │  Value = max($1,      │
                    │          SGP * $/SGP) │
                    └───────────┬───────────┘
                                │
                                v
                    ┌───────────────────────┐
                    │  Store in Player:     │
                    │  - sgp                │
                    │  - dollar_value       │
                    │  - sgp_breakdown JSON │
                    └─────────────────────────┘
```

---

## Key Algorithms

### SGP (Standings Gain Points) Calculation

The SGP method converts raw statistics into standings points, then to dollar values.

#### Formula for Counting Stats

```
SGP = (Player_Stat - Replacement_Stat) / Category_StdDev
```

Where:
- `Player_Stat`: Player's projected value for the category
- `Replacement_Stat`: The Nth-ranked player's stat (N = total roster spots)
- `Category_StdDev`: Standard deviation of that stat across the draftable pool

#### Formula for Rate Stats (AVG)

```
Expected_Hits = Replacement_AVG * Player_AB
Hits_Above_Replacement = Player_H - Expected_Hits
SGP = Hits_Above_Replacement / Category_StdDev
```

This weights AVG contribution by playing time (AB).

#### Formula for Ratio Stats (ERA, WHIP)

```
Expected_Stat = Replacement_ERA * Player_IP  (for ERA)
Stat_Below_Replacement = Expected_Stat - (Player_ERA * Player_IP)
SGP = Stat_Below_Replacement / Category_StdDev
```

Lower is better, so the formula is inverted and weighted by IP.

#### Dollar Value Conversion

```
Total_Positive_SGP = sum(max(0, player.sgp) for player in pool)
Dollars_Per_SGP = League_Budget / Total_Positive_SGP
Player_Value = max(Min_Bid, Player_SGP * Dollars_Per_SGP)
```

### Category Surplus Allocation

When a player is drafted, surplus (or deficit) is distributed across categories:

```
Total_Surplus = Dollar_Value - Price_Paid
Category_Surplus[cat] = (Category_SGP[cat] / Total_SGP) * Total_Surplus
```

### Dynamic Value Recalculation

After each draft pick, values are recalculated:

1. **Remaining Pool**: Only undrafted players
2. **Remaining Budget**: League budget minus total spent
3. **Remaining Roster Spots**: Total spots minus picks made
4. **New Replacement Level**: Nth player in remaining pool

This ensures values reflect current scarcity and budget conditions.

---

## Configuration

### League Settings Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `num_teams` | 12 | 4-20 | Number of teams in the league |
| `budget_per_team` | 260 | 100-500 | Auction budget per team ($) |
| `min_bid` | 1 | 1-5 | Minimum bid allowed ($) |
| `hitter_budget_pct` | 0.68 | 0.5-0.8 | Percentage of budget for hitters |

### Roster Configuration

| Position | Default Spots | Type | Description |
|----------|---------------|------|-------------|
| C | 1 | Hitter | Catcher |
| 1B | 1 | Hitter | First Base |
| 2B | 1 | Hitter | Second Base |
| 3B | 1 | Hitter | Third Base |
| SS | 1 | Hitter | Shortstop |
| CI | 0 | Hitter | Corner Infielder (1B or 3B eligible) |
| MI | 0 | Hitter | Middle Infielder (2B or SS eligible) |
| OF | 3 | Hitter | Outfielder |
| UTIL | 1 | Hitter | Utility (any hitter) |
| SP | 2 | Pitcher | Starting Pitcher |
| RP | 2 | Pitcher | Relief Pitcher |
| P | 2 | Pitcher | Pitcher (any pitcher) |
| BN | 3 | Either | Bench |

### Scoring Categories

**Hitting (5x5)**: R, HR, RBI, SB, AVG

**Pitching (5x5)**: W, SV, K, ERA, WHIP

---

## API Reference

### database.py

```python
def init_db(db_path: str = "draft.db") -> Engine
    """Initialize database and create tables."""

def get_session(engine: Engine) -> Session
    """Get a new database session."""

class Player(Base):
    """SQLAlchemy model for baseball players."""

class Team(Base):
    """SQLAlchemy model for fantasy teams."""

class DraftPick(Base):
    """SQLAlchemy model for draft picks."""

class DraftState(Base):
    """SQLAlchemy model for draft state."""
```

### projections.py

```python
def import_hitters_csv(session: Session, file_path: str) -> int
    """Import hitters from CSV. Returns count imported."""

def import_pitchers_csv(session: Session, file_path: str) -> int
    """Import pitchers from CSV. Returns count imported."""

def get_all_hitters(session: Session) -> list[Player]
    """Get all hitter records."""

def get_all_pitchers(session: Session) -> list[Player]
    """Get all pitcher records."""

def get_available_players(session: Session, player_type: str = None) -> list[Player]
    """Get undrafted players, optionally filtered by type."""

def clear_all_players(session: Session) -> None
    """Delete all player records."""
```

### settings.py

```python
@dataclass
class LeagueSettings:
    """League configuration dataclass."""

    @property
    def total_league_budget(self) -> int
        """Total budget across all teams."""

    @property
    def hitter_roster_spots(self) -> int
        """Total hitter roster slots per team."""

    @property
    def pitcher_roster_spots(self) -> int
        """Total pitcher roster slots per team."""

    @property
    def total_hitters_drafted(self) -> int
        """Total hitters drafted league-wide."""

    @property
    def total_pitchers_drafted(self) -> int
        """Total pitchers drafted league-wide."""
```

### draft.py

```python
def initialize_draft(session: Session, settings: LeagueSettings) -> DraftState
    """Initialize draft: create teams, reset player flags."""

def draft_player(
    session: Session,
    player_id: int,
    team_id: int,
    price: int,
    settings: LeagueSettings
) -> DraftPick
    """Draft a player to a team at given price."""

def undo_pick(session: Session, pick_id: int) -> None
    """Undo a specific draft pick."""

def undo_last_pick(session: Session) -> DraftPick | None
    """Undo the most recent draft pick."""

def get_draft_history(session: Session) -> list[dict]
    """Get all draft picks with metadata."""

def reset_draft(session: Session) -> None
    """Clear all draft data (picks, teams, state)."""

def get_all_teams(session: Session) -> list[Team]
    """Get all fantasy teams."""

def get_user_team(session: Session) -> Team | None
    """Get the user's team (is_user_team=True)."""

def get_remaining_roster_slots(
    session: Session,
    settings: LeagueSettings
) -> dict[str, int]
    """Calculate unfilled roster positions."""

def get_remaining_budget(session: Session) -> int
    """Get total unspent budget across all teams."""
```

### values.py

```python
def calculate_all_player_values(
    session: Session,
    settings: LeagueSettings
) -> None
    """Calculate SGP and dollar values for all players."""

def calculate_remaining_player_values(
    session: Session,
    settings: LeagueSettings
) -> None
    """Recalculate values for undrafted players only."""

def calculate_category_surplus(
    player: Player,
    price_paid: int
) -> dict[str, float]
    """Distribute surplus across categories proportionally."""

def get_category_weak_points(
    analysis: dict,
    threshold: int = 7
) -> list[dict]
    """Identify weak categories from team analysis."""
```

### needs.py

```python
@dataclass
class PositionalRosterState:
    """State of a single roster position slot."""
    position: str       # e.g., "C", "1B", "CI"
    required: int       # Slots from roster_spots
    filled: int         # Players assigned to this slot
    remaining: int      # Slots still needed
    players: list       # Players filling this slot

@dataclass
class PlayerRecommendation:
    """A recommended player with scoring breakdown."""
    player: Player
    composite_score: float
    position_urgency: float
    category_fit: float
    value_surplus: float
    fills_positions: list[str]
    helps_categories: list[str]

@dataclass
class TeamNeedsAnalysis:
    """Complete team needs analysis result."""
    positional_states: list[PositionalRosterState]
    recommendations: list[PlayerRecommendation]
    category_analysis: dict
    comparative_standings: dict

def get_team_positional_roster_state(
    session: Session,
    team: Team,
    settings: LeagueSettings
) -> list[PositionalRosterState]
    """Get positional fill status using greedy slot assignment."""

def analyze_team_needs(
    session: Session,
    team: Team,
    settings: LeagueSettings
) -> TeamNeedsAnalysis
    """Perform complete team needs analysis."""

def get_player_recommendations(
    session: Session,
    team: Team,
    settings: LeagueSettings,
    limit: int = 10
) -> list[PlayerRecommendation]
    """Get smart player recommendations based on needs."""

def calculate_all_team_standings(
    session: Session,
    settings: LeagueSettings
) -> dict[str, dict[str, int]]
    """Calculate comparative standings for all teams."""
```

### positions.py

```python
# Position Constants
COMPOSITE_POSITIONS = {
    "CI": ["1B", "3B"],    # Corner Infielder
    "MI": ["2B", "SS"],    # Middle Infielder
    "UTIL": None,          # Any hitter (special handling)
    "P": None,             # Any pitcher (special handling)
}

HITTER_ROSTER_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "UTIL"]
PITCHER_ROSTER_POSITIONS = ["SP", "RP", "P"]
ALL_FILTER_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "UTIL", "SP", "RP"]
SCARCITY_POSITIONS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "SP", "RP"]

def expand_position(position: str) -> list[str]
    """Expand composite position to constituent base positions.
    CI -> ["1B", "3B"], MI -> ["2B", "SS"], base positions -> [position]"""

def can_player_fill_position(
    player_positions: list[str],
    roster_position: str,
    player_type: str
) -> bool
    """Check if a player with given positions can fill a roster slot.
    Handles UTIL, P, CI, MI, and base position eligibility."""
```

---

## File Structure

```
Fantasy-Baseball-Draft-Tool/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── README.md                 # User documentation
├── PLAN.md                   # Development roadmap
├── ARCHITECTURE.md           # This file
├── src/
│   ├── __init__.py
│   ├── database.py           # SQLAlchemy ORM models
│   ├── projections.py        # CSV import logic
│   ├── settings.py           # League configuration
│   ├── draft.py              # Draft management
│   ├── values.py             # SGP calculation engine
│   ├── positions.py          # Position constants and CI/MI utilities
│   └── needs.py              # Team needs analysis and recommendations
├── data/                     # CSV data storage (gitignored)
│   └── .gitkeep
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_database.py      # Database model tests
│   ├── test_draft.py         # Draft operation tests
│   ├── test_projections.py   # CSV import tests
│   ├── test_settings.py      # Settings tests
│   ├── test_values.py        # SGP calculation tests
│   ├── test_positions.py     # Position utilities tests
│   └── test_needs.py         # Team needs analysis tests
└── draft.db                  # SQLite database (created at runtime)
```

---

## Testing

Run the test suite:

```bash
pytest tests/ -v
```

Test coverage by module:
- `test_database.py`: ORM model behavior, relationships
- `test_draft.py`: Draft operations, undo functionality
- `test_projections.py`: CSV parsing, column mapping
- `test_settings.py`: Configuration validation
- `test_values.py`: SGP calculations, edge cases
- `test_positions.py`: Position expansion, CI/MI eligibility, composite positions
- `test_needs.py`: Team needs analysis, positional roster state, recommendations

---

## Glossary

| Term | Definition |
|------|------------|
| **SGP** | Standings Gain Points - methodology for converting stats to value |
| **Replacement Level** | The baseline player (last draftable) against which others are measured |
| **Counting Stat** | Statistics that accumulate (R, HR, RBI, SB, W, SV, K) |
| **Rate Stat** | Statistics that are ratios/averages (AVG, OBP, SLG) |
| **Ratio Stat** | Statistics where lower is better (ERA, WHIP) |
| **5x5** | Standard rotisserie format with 5 hitting and 5 pitching categories |
| **Surplus** | The difference between a player's calculated value and draft price |
| **CI** | Corner Infielder - composite position accepting 1B or 3B eligible players |
| **MI** | Middle Infielder - composite position accepting 2B or SS eligible players |
| **Composite Position** | A roster slot that accepts multiple base positions (CI, MI, UTIL, P) |
