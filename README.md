# Fantasy Baseball Draft Tool

A Streamlit-based application for managing fantasy baseball auction and snake drafts using Fangraphs Depth Charts (FGDC) projections with Yahoo Fantasy position eligibility.

## Features

- **Player Database**: Browse and search hitters and pitchers with projected stats
- **FGDC Projections**: Auto-imports Fangraphs Depth Charts projections from CSV files
- **Yahoo Positions**: Fetches position eligibility from Yahoo Fantasy Baseball API
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

## Setup

### 1. Download FGDC Projections

1. Go to [Fangraphs Projections](https://www.fangraphs.com/projections) (requires Fangraphs subscription)
2. Select **Depth Charts** as the projection system
3. Download hitter and pitcher CSV exports
4. Rename the files so they contain "hitter" or "batter" and "pitcher" in the filename (e.g., `fgdc_hitters.csv`, `fgdc_pitchers.csv`)
5. Place them in the `data/` folder

### 2. Set Up Yahoo Fantasy API (for position data)

The FGDC projections don't include position eligibility, so we pull that from Yahoo Fantasy.

1. Go to [Yahoo Developer Apps](https://developer.yahoo.com/apps/) and sign in
2. Click **Create an App**
3. Fill in the form:
   - **Application Name**: anything you like (e.g., "Fantasy Draft Tool")
   - **Application Type**: **Installed Application**
   - **Homepage URL**: `https://localhost`
   - **Redirect URI(s)**: leave blank (or `oob` if required)
   - **API Permissions**: check **Fantasy Sports** with **Read** access
4. Click **Create App**
5. Copy your **Client ID (Consumer Key)** and **Client Secret (Consumer Secret)**
6. Create `oauth2.json` in the project root:
   ```json
   {
     "consumer_key": "YOUR_CLIENT_ID_HERE",
     "consumer_secret": "YOUR_CLIENT_SECRET_HERE"
   }
   ```

This file is gitignored and will never be committed.

### 3. Fetch Yahoo Position Data

After placing your FGDC CSVs in `data/` and starting the app once (to import projections), run:

```bash
# Preview matches without writing to database
python scripts/fetch_yahoo_positions.py --league-id 388.l.XXXXX --dry-run

# Write position data to database
python scripts/fetch_yahoo_positions.py --league-id 388.l.XXXXX
```

Find your league ID in your Yahoo Fantasy league URL (e.g., `https://baseball.fantasysports.yahoo.com/b2/XXXXX`). The full league key format is `{game_key}.l.{league_id}`.

On the first run, a browser window will open asking you to authorize the app. After approving, the tokens are saved to `oauth2.json` for future use.

## Usage

1. Start the application:
   ```bash
   streamlit run app.py
   ```

2. The app auto-imports any FGDC CSV files in `data/` on first startup.

3. Browse players, configure league settings, and manage your draft.

## Project Structure

```
Fantasy-Baseball-Draft-Tool/
├── app.py                  # Main Streamlit application
├── src/
│   ├── database.py         # SQLAlchemy models (Player, Team, DraftPick)
│   ├── projections.py      # FGDC CSV import and player queries
│   ├── values.py           # SGP valuation engine
│   ├── draft.py            # Draft lifecycle management
│   ├── settings.py         # League configuration
│   ├── needs.py            # Team roster needs analysis
│   ├── positions.py        # Position eligibility utilities
│   └── targets.py          # Target list CRUD
├── scripts/
│   └── fetch_yahoo_positions.py  # Yahoo API position fetch CLI
├── tests/                  # Test suite
├── requirements.txt        # Python dependencies
├── oauth2.json             # Yahoo API credentials (gitignored)
└── data/                   # FGDC projection CSV files
```

## Requirements

- Python 3.10+
- streamlit >= 1.37.0
- pandas >= 2.0.0
- sqlalchemy >= 2.0.0
- yahoo_oauth >= 1.1.0
- yahoo_fantasy_api >= 2.12.0

## Docker Deployment

Start all containers (app instances + nginx):

```bash
docker-compose up -d
```

Rebuild after code changes:

```bash
docker-compose up -d --build
```

Restart a specific service:

```bash
docker-compose restart nginx
docker-compose restart app-noah
```

Stop all containers:

```bash
docker-compose down
```

View logs:

```bash
docker-compose logs -f          # all services
docker-compose logs -f app-noah # single service
```

## Changing the HTTP Auth Password

The app is protected by HTTP Basic Auth at the nginx level. The `.htpasswd` file lives in the project root and is mounted into the nginx container.

To add or update a user's password:

```bash
# Install htpasswd if needed (usually in apache2-utils)
sudo apt install apache2-utils

# Add a new user or update an existing user's password
htpasswd .htpasswd <username>

# Restart nginx to pick up the change
docker-compose restart nginx
```

To remove a user:

```bash
htpasswd -D .htpasswd <username>
docker-compose restart nginx
```

## License

MIT
