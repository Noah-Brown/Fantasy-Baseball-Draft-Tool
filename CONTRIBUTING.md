# Contributing Guide

This guide covers development setup, coding standards, and how to contribute to the Fantasy Baseball Draft Tool.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- A virtual environment tool (venv, virtualenv, or conda)

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd Fantasy-Baseball-Draft-Tool

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov
```

### Running the Application

```bash
streamlit run app.py
```

The application will be available at `http://localhost:8501`.

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_values.py -v

# Run tests matching a pattern
pytest tests/ -k "test_sgp" -v
```

---

## Project Structure

```
Fantasy-Baseball-Draft-Tool/
├── app.py                    # Main Streamlit application
├── src/                      # Core modules
│   ├── database.py           # SQLAlchemy ORM models
│   ├── projections.py        # CSV import/export
│   ├── settings.py           # League configuration
│   ├── draft.py              # Draft state management
│   └── values.py             # SGP calculation engine
├── tests/                    # Test suite
│   ├── conftest.py           # Shared fixtures
│   └── test_*.py             # Test modules
├── data/                     # CSV data (gitignored)
└── docs/                     # Documentation
```

---

## Coding Standards

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use descriptive variable names

### Docstrings

Use Google-style docstrings for all public functions:

```python
def calculate_player_value(player: Player, settings: LeagueSettings) -> float:
    """Calculate the dollar value for a player.

    Args:
        player: The Player object with projected stats.
        settings: League configuration including budget and roster spots.

    Returns:
        The calculated dollar value, minimum of $1.

    Raises:
        ValueError: If player has no projected stats.
    """
```

### Testing

- Write tests for all new functionality
- Test edge cases and error conditions
- Use pytest fixtures for common setup
- Aim for high coverage on calculation-heavy modules

Example test structure:

```python
def test_sgp_calculation_counting_stat():
    """SGP for counting stats should increase with higher values."""
    # Arrange
    player = create_test_player(hr=30)
    settings = create_test_settings()

    # Act
    result = calculate_sgp(player, settings)

    # Assert
    assert result > 0
```

---

## Module Guidelines

### database.py

- Keep ORM models simple and focused
- Use relationships for related data
- Computed properties for derived values
- No business logic in models

### projections.py

- Handle various CSV formats gracefully
- Provide clear error messages for parsing failures
- Support common column name variations
- Calculate derived stats when source data is incomplete

### settings.py

- Use dataclasses for configuration
- Provide sensible defaults
- Validate inputs where appropriate
- Use properties for computed values

### draft.py

- Maintain transaction integrity
- Provide clear undo functionality
- Validate all operations before committing
- Trigger value recalculation when needed

### values.py

- Document all formulas clearly
- Handle edge cases (zero denominators, empty pools)
- Support both initial and recalculation scenarios
- Store breakdown data for analysis

### app.py

- Keep UI code separate from business logic
- Use session state for user preferences
- Provide clear user feedback
- Support filtering and export

---

## Adding New Features

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Implement the Feature

1. Start with tests (TDD approach recommended)
2. Implement the core logic in `src/`
3. Add UI components in `app.py`
4. Update documentation as needed

### 3. Test Thoroughly

```bash
# Run full test suite
pytest tests/ -v

# Check for regressions
pytest tests/ --tb=short
```

### 4. Update Documentation

- Update ARCHITECTURE.md if adding new modules or data flows
- Update README.md if adding user-facing features
- Update PLAN.md to mark features complete

### 5. Submit a Pull Request

- Provide a clear description of changes
- Reference any related issues
- Ensure all tests pass

---

## Common Development Tasks

### Adding a New Stat Category

1. Update `LeagueSettings` in `settings.py`:
   ```python
   hitting_categories: list = ["R", "HR", "RBI", "SB", "AVG", "OPS"]
   ```

2. Update CSV parsing in `projections.py` to import the stat

3. Add SGP calculation in `values.py`:
   ```python
   # For counting stats
   if category == "OPS":
       sgp = (player.ops - replacement.ops) / stddev

   # For rate stats (weighted)
   if category == "OPS":
       expected = replacement.ops * player.pa
       actual = player.ops * player.pa
       sgp = (actual - expected) / stddev
   ```

4. Add tests in `test_values.py`

### Adding a New UI Page

1. Create the page function in `app.py`:
   ```python
   def page_new_feature():
       st.header("New Feature")
       # Page content
   ```

2. Add to navigation:
   ```python
   pages = {
       "Player Database": page_player_database,
       "New Feature": page_new_feature,
       # ...
   }
   ```

### Modifying the Database Schema

1. Update models in `database.py`
2. Handle migrations (for development, delete `draft.db` to recreate)
3. Update any queries that use the modified tables
4. Add/update tests

---

## Troubleshooting

### Common Issues

**"Module not found" errors**
```bash
# Ensure you're in the virtual environment
source venv/bin/activate
pip install -r requirements.txt
```

**Database schema errors**
```bash
# Delete and recreate the database
rm draft.db
streamlit run app.py
```

**Test failures after changes**
```bash
# Run with verbose output to see details
pytest tests/ -v --tb=long
```

**Streamlit caching issues**
- Clear cache: `st.cache_data.clear()` in the app
- Or restart the Streamlit server

---

## Release Process

1. Update version number (if applicable)
2. Run full test suite
3. Update CHANGELOG (if maintained)
4. Create a release tag:
   ```bash
   git tag -a v1.0.0 -m "Release version 1.0.0"
   git push origin v1.0.0
   ```

---

## Getting Help

- Check existing issues on GitHub
- Review the ARCHITECTURE.md for system understanding
- Review the PLAN.md for feature roadmap
- Create an issue for bugs or feature requests
