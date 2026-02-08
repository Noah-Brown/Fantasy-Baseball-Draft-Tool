# Fantasy Baseball Auction Draft Tool

A Streamlit-based application for managing fantasy baseball auction drafts with Steamer projections.

## Features

- **Player Database**: Browse and search hitters and pitchers with projected stats
- **Steamer Projections**: Import projections directly from Fangraphs CSV exports
- **League Settings**: Configure teams, budgets, roster spots, and scoring categories
- **5x5 Scoring**: Standard rotisserie categories (R, HR, RBI, SB, AVG / W, SV, K, ERA, WHIP)
- **Draft Notes**: Add persistent free-text notes to any player (e.g., injury concerns, sleeper picks, avoid)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd Fantasy-Baseball-Draft-Tool
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the application:
   ```bash
   streamlit run app.py
   ```

2. Import projections:
   - Go to [Fangraphs Projections](https://www.fangraphs.com/projections)
   - Select **Steamer** as the projection system
   - Download hitter and pitcher CSV files (Requires Fangraphs subscription) 
   - Upload them via the "Import Projections" page

3. Browse players and configure league settings as needed.

## Project Structure

```
Fantasy-Baseball-Draft-Tool/
├── app.py              # Main Streamlit application
├── src/
│   ├── database.py     # SQLAlchemy models (Player, Team, DraftPick)
│   ├── projections.py  # CSV import and player queries
│   └── settings.py     # League configuration
├── requirements.txt    # Python dependencies
└── data/               # Uploaded projection files (created on import)
```

## Requirements

- Python 3.10+
- streamlit >= 1.28.0
- pandas >= 2.0.0
- sqlalchemy >= 2.0.0

## License

MIT
