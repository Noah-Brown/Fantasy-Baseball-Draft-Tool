# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
streamlit run app.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_values.py -v

# Run tests matching a pattern
pytest tests/ -k "test_sgp" -v

# Install dependencies
pip install -r requirements.txt

# Docker deployment
docker-compose up -d
```

There is no linter, formatter, or type checker configured for this project.

## Architecture

Streamlit single-page app (`app.py`) for managing fantasy baseball auction and snake drafts using Fangraphs Steamer projections. Python 3.10+, SQLAlchemy 2.0+, SQLite (`draft.db`), Pandas, Altair.

### Core Modules (`src/`)

- **`database.py`** - SQLAlchemy ORM models: `Player`, `Team`, `DraftPick`, `DraftState`, `TargetPlayer`. All tables created via `Base.metadata.create_all()`.
- **`values.py`** - SGP (Standings Gain Points) valuation engine. Two modes: positional replacement level (default, FanGraphs methodology) and pool-based. Converts raw projections into dollar values relative to replacement level.
- **`draft.py`** - Draft lifecycle: `initialize_draft()`, `draft_player()`, `undo_last_pick()`. Handles both auction (price-based) and snake (round-based). Auto-recalculates remaining player values after each pick.
- **`snake.py`** - Serpentine draft order generation and pick tracking.
- **`projections.py`** - Fangraphs Steamer CSV import with column mapping fallbacks and stat estimation (e.g., AB from PA).
- **`settings.py`** - `LeagueSettings` dataclass with computed properties for budget splits, roster totals, and positional demand.
- **`needs.py`** - Team positional roster state (greedy assignment to most restrictive position first) and category weakness analysis.
- **`targets.py`** - Target list CRUD operations.
- **`positions.py`** - Position eligibility, composite position expansion (CI -> 1B/3B, MI -> 2B/SS).
- **`components.py`** - UI keyboard shortcut injection.

### Data Flow

CSV import (`projections.py`) -> Player records in SQLite -> SGP calculation (`values.py`) -> Dollar values stored on Player -> Draft operations (`draft.py`) update DraftPick/Team/Player state -> Values recalculated for remaining players.

### Key Conventions

- **Positions** stored as comma-separated strings: `"SS,2B"`. Composite positions: CI (1B/3B), MI (2B/SS), UTIL, DH.
- **Player types**: `"hitter"` or `"pitcher"`. Pitcher subtypes inferred from stats (SP vs RP).
- **Budget split**: 68% hitters / 32% pitchers by default (`hitter_budget_pct`).
- **SGP breakdown** stored as JSON dict on Player: `{"r": 1.5, "hr": 2.1, ...}`.
- **Rate stats** (AVG, ERA, WHIP) use weighted SGP calculation (by PA or IP). ERA/WHIP are inverted (lower = better).
- **Database sessions**: Each page function gets a fresh SQLAlchemy session. `@st.cache_resource` used for engine/session factory.
- **Auto-load**: App checks for CSV files in `data/` folder on startup; imports automatically if DB is empty.
- **Authentication**: HTTP Basic Auth at nginx level only (`.htpasswd`), not in the application. Single-league shared tool, not multi-tenant.

### Testing

Tests use in-memory SQLite via fixtures in `conftest.py` (`engine`, `session`, `sample_hitter`, `sample_pitcher`, `sample_team`, `tmp_csv_path`).
