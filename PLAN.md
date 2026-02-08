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

### Value Calculation Enhancements

21. **Positional Price Adjustments** - Adjust player values based on positional scarcity using replacement level methodology. Critical for leagues with non-standard roster configurations (e.g., 2-catcher leagues). See detailed section below.

---

### Priority

**Highest impact for draft day**: Target List (#1), Max Bid Calculator (#7), Quick Search (#10), and Category Balance Dashboard (#5). These address the most common draft-day pain points: tracking targets, avoiding overbidding, finding players fast, and building a balanced team.

---

### Implementation Status

- [x] 1. Target List / Watchlist
- [x] 2. Positional Scarcity Indicator
- [x] 3. Best Available by Position
- [x] 4. Inflation/Deflation Tracker
- [x] 5. Category Balance Dashboard
- [x] 6. Team Needs Analysis
- [x] 7. Max Affordable Bid Calculator
- [ ] 8. Opponent Needs Tracker
- [ ] 9. Budget Pressure Alerts
- [x] 10. Quick Search / Hotkey
- [ ] 11. Nomination Queue
- [x] 12. One-Click Draft
- [ ] 13. Sound/Visual Alerts
- [ ] 14. Player Comparison Tool
- [ ] 15. Draft Replay / History Analysis
- [ ] 16. Tier-Based Grouping
- [ ] 17. Dark Mode
- [ ] 18. Mobile/Tablet View
- [x] 19. Draft Notes
- [ ] 20. Undo with Confirmation
- [x] 21. Positional Price Adjustments

---

## Positional Price Adjustments (Future Feature)

### Overview

Positional price adjustments modify player values based on the scarcity of quality players at each position. In a two-catcher league, for example, catchers become more valuable because:
- More catchers are drafted (24 instead of 12 in a 12-team league)
- The replacement level catcher is significantly less productive
- Good catchers have more "value above replacement"

### Adjustment Methodologies

There are four main approaches to positional adjustments:

1. **Meritocracy Theory** - No position adjustments. Players are valued purely on projected stats regardless of position.

2. **Apples-to-Apples Theory** - Compare players against others at their position rather than against all hitters. A player's value is based on how they compare to their positional peers.

3. **Replacement Level Theory** (Most Common) - Adjust values so that the last rosterable player at each position is worth exactly $1. This naturally boosts scarce positions where the drop-off is steeper.

4. **Communist Theory** - Distribute budget equally across all positions. Each position gets the same total dollar allocation.

### Replacement Level Implementation

The Replacement Level approach (used by FanGraphs Auction Calculator) works as follows:

1. **Determine replacement level per position**: For each position, identify the Nth-ranked player where N = (teams × roster spots at that position)
   - 1C league, 12 teams: 12th-best catcher is replacement level
   - 2C league, 12 teams: 24th-best catcher is replacement level

2. **Calculate Points/SGP Above Replacement**: Instead of using overall replacement level, subtract the positional replacement level stats:
   ```
   Positional SGP = (Player Stat - Replacement Stat at Position) / SGP Denominator
   ```

3. **The adjustment happens automatically**: Players at shallow positions (C, SS, 2B) gain value because their replacement level is lower. Players at deep positions (OF, 1B) lose some value.

### Example: Two-Catcher League Impact

In a standard 1C league vs 2C league for a 12-team format:

| Position | 1C League Replacement | 2C League Replacement | Value Change |
|----------|----------------------|----------------------|--------------|
| C        | 12th catcher         | 24th catcher         | +$10-15      |
| 1B       | ~18th ranked         | ~18th ranked         | No change    |
| OF       | ~40th ranked         | ~40th ranked         | No change    |

Top catchers can gain 2-3 rounds of draft value (or $10-15 in auction) in a 2C league.

### Implementation Plan

To add positional adjustments to this tool:

1. **Add roster position counts to settings**: Track how many of each position are drafted league-wide
2. **Calculate positional replacement levels**: Find the Nth player at each position
3. **Modify SGP calculation**: Subtract positional replacement stats instead of overall replacement
4. **Handle multi-position eligibility**: Players eligible at multiple positions get the most favorable adjustment
5. **Allow toggle between methods**: Let users choose Meritocracy vs Replacement Level

### Configuration Options

```python
# Example settings additions
roster_slots_by_position = {
    "C": 2,   # 2-catcher league
    "1B": 1,
    "2B": 1,
    "SS": 1,
    "3B": 1,
    "OF": 3,
    "UTIL": 1,
    # etc.
}

position_adjustment_method = "replacement_level"  # or "none", "apples_to_apples"
```

### Sources

- [Smart Fantasy Baseball - Replacement Level & Position Scarcity](https://www.smartfantasybaseball.com/2013/03/create-your-own-fantasy-baseball-rankings-part-6-accounting-for-replacement-level-and-position-scarcity/)
- [Razzball - Position Adjustments](https://razzball.com/position-adjustments/)
- [FanGraphs Auction Calculator](https://www.fangraphs.com/fantasy-tools/auction-calculator)
- [Mastersball Valuation Theory](https://www.mastersball.com/index.php?option=com_content&view=article&id=5581:mastersball-valuation-theory-and-methodolgy)

---

## Future Integrations

### Yahoo Fantasy API Integration
- Connect to Yahoo Fantasy Sports API for live league data
- Potential features:
  - Import league settings automatically (roster spots, categories, teams)
  - Sync draft picks in real-time during live drafts
  - Pull actual league standings and stats post-draft
  - Import keeper values and auction budgets
- Requires OAuth authentication setup
- Documentation: https://developer.yahoo.com/fantasysports/guide/

---

## Version History

- **v0.0** - Initial development release with core functionality
