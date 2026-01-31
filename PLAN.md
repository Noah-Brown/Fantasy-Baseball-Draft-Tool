# Fantasy Baseball Auction Draft Tool - Implementation Plan

## Overview
A local webapp for managing fantasy baseball auction drafts with Steamer projections, SGP-based value calculations, and real-time draft tracking.

## Requirements Summary
- **Format**: Auction draft, Rotisserie 5x5 scoring
- **Projections**: Steamer (from Fangraphs)
- **Usage**: Solo tool, local deployment
- **Categories**: Standard 5x5 (R, HR, RBI, SB, AVG / W, SV, K, ERA, WHIP)

---

## Recommended Architecture: Python + Streamlit

**Why Streamlit?**
- Fast development for data-heavy apps
- Built-in tables, charts, filtering, search
- Single Python codebase (no frontend/backend split)
- Easy local deployment (`streamlit run app.py`)
- Great for statistical/projection work
- Can always migrate to FastAPI + React later if needed

**Tech Stack:**
- Python 3.11+
- Streamlit (UI)
- Pandas (data manipulation)
- SQLite (local database, persistent draft state)
- SQLAlchemy (ORM)

---

## Core Features

### 1. Player Database
- Import Steamer projections from CSV (downloadable from Fangraphs)
- Separate hitter and pitcher tables
- Store: Name, Team, Position(s), all projected stats

### 2. League Settings (Configurable)
- Number of teams (default: 12)
- Budget per team (default: $260)
- Roster spots: C, 1B, 2B, 3B, SS, OF (x3), UTIL, SP (x2), RP (x2), P (x2), BN
- Categories (standard 5x5, customizable)
- Minimum bid ($1)

### 3. Value Calculation Engine
- **SGP (Standings Gain Points)** method:
  - Calculate how much of each stat equals one standings point
  - Convert player projections to SGP
  - Sum SGP across categories = total value
  - Convert to dollar values based on league budget
- **Position scarcity adjustment**: Scale values by position depth
- **Split allocation**: ~68% hitters, 32% pitchers (configurable)

### 4. Draft Tracker
- Mark players drafted (team, price)
- Track per-team: budget remaining, roster slots filled
- **Live value recalculation**: Adjust remaining player values as pool shrinks
- Undo functionality for mistakes

### 5. User Interface
- **Main view**: Sortable/filterable player table with projections + values
- **Filters**: Position, availability, price range, stat thresholds
- **Search**: Find players by name
- **My Team tab**: Track your roster and remaining needs
- **All Teams tab**: See league-wide draft status
- **Value vs Price**: Highlight bargains/overpays

---

## Project Structure

```
Fantasy-Baseball-Draft-Tool/
├── app.py                 # Main Streamlit app
├── requirements.txt       # Dependencies
├── src/
│   ├── __init__.py
│   ├── database.py        # SQLite/SQLAlchemy models
│   ├── projections.py     # Import and process Steamer data
│   ├── values.py          # SGP calculation engine
│   ├── draft.py           # Draft state management
│   └── settings.py        # League configuration
├── data/
│   ├── steamer_hitters.csv    # User imports these
│   └── steamer_pitchers.csv
└── draft.db               # SQLite database (created at runtime)
```

---

## Implementation Phases

### Phase 1: Foundation
1. Set up project structure and dependencies
2. Create SQLAlchemy models (Player, DraftPick, Team, LeagueSettings)
3. Build Steamer CSV import functionality
4. Basic Streamlit app showing player list

### Phase 2: Value Engine
1. Implement SGP calculation for all categories
2. Build dollar value conversion
3. Add position scarcity adjustments
4. Display values in player table

### Phase 3: Draft Tracking
1. "Draft Player" functionality (assign to team + price)
2. Track team budgets and rosters
3. Recalculate values when players are drafted
4. Undo/edit draft picks

### Phase 4: Polish
1. Position filtering and search
2. "My Team" and "All Teams" views
3. Value vs price highlighting
4. Save/load draft state
5. Export functionality (CSV)

---

## Data Flow

```
Steamer CSV → Import → Player DB → SGP Calculation → Dollar Values
                                         ↓
                            Draft Pick → Recalculate → Updated Values
```

---

## Verification Plan
1. Import sample Steamer data and verify player counts
2. Test SGP calculations against known benchmarks
3. Run mock draft: draft players, verify budget/roster tracking
4. Test value recalculation after drafting top players
5. Verify persistence: restart app, confirm draft state preserved

---

## Future Enhancements (Not in v1)
- Multiple projection system support
- Head-to-head and points league formats
- Snake draft mode
- Player comparison tool
- Historical draft analysis
