"""Fantasy Baseball Auction Draft Tool - Main Streamlit App."""

import streamlit as st
import pandas as pd
from pathlib import Path

from src.database import init_db, get_session, Player, Team, DraftState
from src.projections import (
    import_hitters_csv,
    import_pitchers_csv,
    clear_all_players,
)
from src.settings import DEFAULT_SETTINGS

# Page configuration
st.set_page_config(
    page_title="Fantasy Baseball Draft Tool",
    page_icon="⚾",
    layout="wide",
)

# Initialize database
@st.cache_resource
def get_db():
    """Initialize and cache database connection."""
    engine = init_db("draft.db")
    return engine


def main():
    """Main application."""
    engine = get_db()
    session = get_session(engine)

    st.title("⚾ Fantasy Baseball Auction Draft Tool")

    # Sidebar for navigation and settings
    with st.sidebar:
        st.header("Navigation")
        page = st.radio(
            "Select Page",
            ["Player Database", "Import Projections", "League Settings"],
            label_visibility="collapsed",
        )

        st.divider()

        # Quick stats
        hitter_count = session.query(Player).filter(Player.player_type == "hitter").count()
        pitcher_count = session.query(Player).filter(Player.player_type == "pitcher").count()

        st.metric("Hitters", hitter_count)
        st.metric("Pitchers", pitcher_count)

    # Page routing
    if page == "Player Database":
        show_player_database(session)
    elif page == "Import Projections":
        show_import_page(session)
    elif page == "League Settings":
        show_settings_page(session)

    session.close()


def show_player_database(session):
    """Display the player database with projections."""
    st.header("Player Database")

    # Check if we have players
    total_players = session.query(Player).count()

    if total_players == 0:
        st.warning("No players in database. Go to 'Import Projections' to add players.")
        return

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        player_type = st.selectbox(
            "Player Type",
            ["All", "Hitters", "Pitchers"],
        )

    with col2:
        position_filter = st.text_input(
            "Position Filter",
            placeholder="e.g., SS, OF, SP",
        )

    with col3:
        search = st.text_input(
            "Search Player",
            placeholder="Player name...",
        )

    # Build query
    query = session.query(Player)

    if player_type == "Hitters":
        query = query.filter(Player.player_type == "hitter")
    elif player_type == "Pitchers":
        query = query.filter(Player.player_type == "pitcher")

    if position_filter:
        query = query.filter(Player.positions.contains(position_filter.upper()))

    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))

    players = query.all()

    if not players:
        st.info("No players match the current filters.")
        return

    # Convert to DataFrame for display
    if player_type == "Pitchers":
        df = pd.DataFrame([
            {
                "Name": p.name,
                "Team": p.team or "",
                "Pos": p.positions or "",
                "IP": p.ip or 0,
                "W": p.w or 0,
                "SV": p.sv or 0,
                "K": p.k or 0,
                "ERA": round(p.era, 2) if p.era else 0,
                "WHIP": round(p.whip, 2) if p.whip else 0,
                "Value": f"${p.dollar_value:.0f}" if p.dollar_value else "-",
            }
            for p in players
        ])
    elif player_type == "Hitters":
        df = pd.DataFrame([
            {
                "Name": p.name,
                "Team": p.team or "",
                "Pos": p.positions or "",
                "PA": p.pa or 0,
                "R": p.r or 0,
                "HR": p.hr or 0,
                "RBI": p.rbi or 0,
                "SB": p.sb or 0,
                "AVG": f"{p.avg:.3f}" if p.avg else ".000",
                "Value": f"${p.dollar_value:.0f}" if p.dollar_value else "-",
            }
            for p in players
        ])
    else:
        # All players - show basic info
        df = pd.DataFrame([
            {
                "Name": p.name,
                "Team": p.team or "",
                "Type": p.player_type.title() if p.player_type else "",
                "Pos": p.positions or "",
                "Value": f"${p.dollar_value:.0f}" if p.dollar_value else "-",
            }
            for p in players
        ])

    # Display table
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"Showing {len(players)} players")


def show_import_page(session):
    """Page for importing Steamer projections."""
    st.header("Import Projections")

    st.markdown("""
    ### How to get Steamer projections:
    1. Go to [Fangraphs Projections](https://www.fangraphs.com/projections)
    2. Select **Steamer** as the projection system
    3. Choose **Hitters** or **Pitchers**
    4. Click **Export Data** to download CSV
    5. Upload the files below
    """)

    # Check for existing data
    existing_hitters = session.query(Player).filter(Player.player_type == "hitter").count()
    existing_pitchers = session.query(Player).filter(Player.player_type == "pitcher").count()

    if existing_hitters or existing_pitchers:
        st.info(f"Current database: {existing_hitters} hitters, {existing_pitchers} pitchers")

        if st.button("Clear All Players", type="secondary"):
            clear_all_players(session)
            st.success("All players cleared!")
            st.rerun()

    st.divider()

    # File uploaders
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Hitters")
        hitter_file = st.file_uploader(
            "Upload Steamer Hitters CSV",
            type=["csv"],
            key="hitters",
        )

        if hitter_file is not None:
            if st.button("Import Hitters", type="primary"):
                # Save to temp file and import
                temp_path = Path("data/steamer_hitters.csv")
                temp_path.parent.mkdir(exist_ok=True)
                temp_path.write_bytes(hitter_file.getvalue())

                try:
                    count = import_hitters_csv(session, temp_path)
                    st.success(f"Imported {count} hitters!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error importing: {e}")

    with col2:
        st.subheader("Pitchers")
        pitcher_file = st.file_uploader(
            "Upload Steamer Pitchers CSV",
            type=["csv"],
            key="pitchers",
        )

        if pitcher_file is not None:
            if st.button("Import Pitchers", type="primary"):
                temp_path = Path("data/steamer_pitchers.csv")
                temp_path.parent.mkdir(exist_ok=True)
                temp_path.write_bytes(pitcher_file.getvalue())

                try:
                    count = import_pitchers_csv(session, temp_path)
                    st.success(f"Imported {count} pitchers!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error importing: {e}")


def show_settings_page(session):
    """Page for configuring league settings."""
    st.header("League Settings")

    settings = DEFAULT_SETTINGS

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("League Structure")
        num_teams = st.number_input(
            "Number of Teams",
            min_value=4,
            max_value=20,
            value=settings.num_teams,
        )
        budget = st.number_input(
            "Budget per Team ($)",
            min_value=100,
            max_value=500,
            value=settings.budget_per_team,
        )
        min_bid = st.number_input(
            "Minimum Bid ($)",
            min_value=1,
            max_value=5,
            value=settings.min_bid,
        )

    with col2:
        st.subheader("Scoring Categories")
        st.markdown("**Hitting (5x5)**")
        st.text(", ".join(settings.hitting_categories))

        st.markdown("**Pitching (5x5)**")
        st.text(", ".join(settings.pitching_categories))

    st.divider()

    st.subheader("Roster Spots")
    roster_cols = st.columns(4)

    positions = list(settings.roster_spots.items())
    for i, (pos, count) in enumerate(positions):
        with roster_cols[i % 4]:
            st.metric(pos, count)

    st.divider()

    # Summary
    st.subheader("League Summary")
    total_budget = num_teams * budget
    st.write(f"**Total League Budget:** ${total_budget:,}")
    st.write(f"**Hitters Drafted:** {settings.total_hitters_drafted}")
    st.write(f"**Pitchers Drafted:** {settings.total_pitchers_drafted}")

    st.info("Settings customization will be available in a future update.")


if __name__ == "__main__":
    main()
