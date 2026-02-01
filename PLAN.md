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

## Future Enhancements - Feature Roadmap

### Real-Time Decision Support

1. **Target List / Watchlist** - Let users mark players they want with max bid prices. Highlight when a target is nominated and show if current price is below your limit.

2. **Positional Scarcity Indicator** - Show a "danger zone" warning when only 2-3 quality players remain at a position. Help avoid getting stuck with replacement-level options.

3. **Best Available by Position** - Quick tab/view showing top 5 available players at each position, sorted by value. Faster than filtering the main table.

4. **Inflation/Deflation Tracker** - Track whether actual draft prices are running above or below projected values. Show a running "inflation factor" (e.g., +8% over projections) to adjust bidding strategy.

### Team Building Assistance

5. **Category Balance Dashboard** - Visual display (bar chart or radar chart) showing your team's projected standings in each category. Highlight weak categories to target.

6. **Team Needs Analysis** - After each pick, suggest which positions/categories to prioritize next based on remaining budget and roster holes.

7. **Max Affordable Bid Calculator** - Given remaining budget and roster spots to fill, calculate the maximum you can bid on a player while still filling your roster at minimum bids.

### Opponent Intelligence

8. **Opponent Needs Tracker** - Show what positions each team still needs. Predict who might bid aggressively on certain players.

9. **Budget Pressure Alerts** - Flag teams running low on budget who may be forced to let bargains pass.

### Speed & Usability

10. **Quick Search / Hotkey** - Keyboard shortcut (Ctrl+F or `/`) to instantly search for a player by name when they're nominated. Jump straight to their row.

11. **Nomination Queue** - Track whose turn to nominate and optionally queue your upcoming nominations.

12. **One-Click Draft** - For players you're tracking, draft them with one click at the current price without re-selecting from dropdowns.

13. **Sound/Visual Alerts** - Optional audio ping when a target player is available below your max price, or when it's your turn to nominate.

### Analysis & Strategy

14. **Player Comparison Tool** - Side-by-side comparison of 2-3 players showing stats, values, and category contributions.

15. **Draft Replay / History Analysis** - After the draft, review all picks with analysis of bargains and overpays across the league.

16. **Tier-Based Grouping** - Group players into value tiers (e.g., $30+, $20-29, $10-19) to quickly see when tiers are depleted.

### Quality of Life

17. **Dark Mode** - Easier on the eyes during a long draft.

18. **Mobile/Tablet View** - Responsive layout for following along on a second device.

19. **Draft Notes** - Add notes to players (injury concerns, sleeper pick, avoid, etc.) that persist through the draft.

20. **Undo with Confirmation** - Batch undo or "correct last N picks" for fixing entry mistakes quickly.

---

### Priority

**Highest impact for draft day**: Target List (#1), Max Bid Calculator (#7), Quick Search (#10), and Category Balance Dashboard (#5). These address the most common draft-day pain points: tracking targets, avoiding overbidding, finding players fast, and building a balanced team.

---

### Implementation Status

- [x] 1. Target List / Watchlist
- [ ] 2. Positional Scarcity Indicator
- [ ] 3. Best Available by Position
- [ ] 4. Inflation/Deflation Tracker
- [x] 5. Category Balance Dashboard
- [ ] 6. Team Needs Analysis
- [x] 7. Max Affordable Bid Calculator
- [ ] 8. Opponent Needs Tracker
- [ ] 9. Budget Pressure Alerts
- [x] 10. Quick Search / Hotkey
- [ ] 11. Nomination Queue
- [ ] 12. One-Click Draft
- [ ] 13. Sound/Visual Alerts
- [ ] 14. Player Comparison Tool
- [ ] 15. Draft Replay / History Analysis
- [ ] 16. Tier-Based Grouping
- [ ] 17. Dark Mode
- [ ] 18. Mobile/Tablet View
- [ ] 19. Draft Notes
- [ ] 20. Undo with Confirmation
