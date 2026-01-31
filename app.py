"""Fantasy Baseball Auction Draft Tool - Main Streamlit App."""

import streamlit as st
import pandas as pd
from pathlib import Path

from src.database import init_db, get_session, Player, Team, DraftState
from src.projections import (
    import_hitters_csv,
    import_pitchers_csv,
    clear_all_players,
    get_available_players,
)
from src.settings import DEFAULT_SETTINGS
from src.values import calculate_all_player_values, calculate_remaining_player_values
from src.draft import (
    initialize_draft,
    draft_player,
    undo_pick,
    get_draft_history,
    reset_draft,
    get_draft_state,
    get_all_teams,
    get_user_team,
)

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
            ["Player Database", "Draft Room", "Import Projections", "League Settings"],
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
    elif page == "Draft Room":
        show_draft_room(session)
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


def show_draft_room(session):
    """Draft Room page for conducting the auction draft."""
    st.header("Draft Room")

    draft_state = get_draft_state(session)

    # Sidebar controls
    with st.sidebar:
        st.divider()

        if not draft_state or not draft_state.is_active:
            # Draft not initialized - show setup
            st.subheader("Start Draft")

            team_name = st.text_input(
                "Your Team Name",
                value="My Team",
                key="user_team_name",
            )

            if st.button("Start Draft", type="primary"):
                # Check if players exist
                player_count = session.query(Player).count()
                if player_count == 0:
                    st.error("Import players first before starting draft!")
                else:
                    initialize_draft(session, DEFAULT_SETTINGS, team_name)
                    st.success("Draft initialized!")
                    st.rerun()
        else:
            # Draft is active - show draft controls
            st.subheader("Draft Player")

            # Team selector with remaining budget
            teams = get_all_teams(session)
            team_options = {
                f"{t.name} (${t.remaining_budget})": t.id
                for t in teams
            }

            # Default to user team
            user_team = get_user_team(session)
            default_idx = 0
            if user_team:
                for idx, label in enumerate(team_options.keys()):
                    if user_team.name in label:
                        default_idx = idx
                        break

            selected_team_label = st.selectbox(
                "Team",
                options=list(team_options.keys()),
                index=default_idx,
                key="draft_team",
            )
            selected_team_id = team_options[selected_team_label]

            # Player search/selector
            available_players = get_available_players(session)
            # Sort by dollar value (descending)
            available_players.sort(
                key=lambda p: p.dollar_value if p.dollar_value else 0,
                reverse=True
            )

            if available_players:
                player_options = {
                    f"{p.name} (${p.dollar_value:.0f})" if p.dollar_value else p.name: p.id
                    for p in available_players
                }

                selected_player_label = st.selectbox(
                    "Player",
                    options=list(player_options.keys()),
                    key="draft_player",
                )
                selected_player_id = player_options[selected_player_label]

                # Get selected player for default price
                selected_player = session.get(Player, selected_player_id)
                default_price = int(selected_player.dollar_value) if selected_player.dollar_value else 1

                price = st.number_input(
                    "Price ($)",
                    min_value=1,
                    max_value=999,
                    value=default_price,
                    key="draft_price",
                )

                if st.button("DRAFT", type="primary", use_container_width=True):
                    try:
                        draft_player(session, selected_player_id, selected_team_id, price)
                        st.success(f"Drafted {selected_player.name} for ${price}!")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            else:
                st.info("No available players")

            # Team budgets summary
            st.divider()
            st.subheader("Team Budgets")

            for team in teams:
                col1, col2 = st.columns([2, 1])
                with col1:
                    label = team.name
                    if team.is_user_team:
                        label += " (You)"
                    st.text(label)
                with col2:
                    st.text(f"${team.remaining_budget}")

            # Reset draft button
            st.divider()
            if st.button("Reset Draft", type="secondary"):
                reset_draft(session)
                st.success("Draft reset!")
                st.rerun()

    # Main area
    if not draft_state or not draft_state.is_active:
        st.info("Set your team name in the sidebar and click 'Start Draft' to begin.")
        return

    # Recalculate values button with stale indicator
    col1, col2 = st.columns([3, 1])
    with col1:
        if draft_state.values_stale:
            st.warning("Player values are stale and need recalculation.")
    with col2:
        button_label = "Recalculate Values"
        if draft_state.values_stale:
            button_label = "⚠️ Recalculate Values"

        if st.button(button_label, type="primary" if draft_state.values_stale else "secondary"):
            try:
                count = calculate_remaining_player_values(session, DEFAULT_SETTINGS)
                st.success(f"Recalculated values for {count} available players!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Available players table
    st.subheader("Available Players")

    # Filters for available players
    col1, col2, col3 = st.columns(3)

    with col1:
        player_type = st.selectbox(
            "Player Type",
            ["All", "Hitters", "Pitchers"],
            key="avail_player_type",
        )

    with col2:
        position_filter = st.text_input(
            "Position Filter",
            placeholder="e.g., SS, OF, SP",
            key="avail_position",
        )

    with col3:
        search = st.text_input(
            "Search Player",
            placeholder="Player name...",
            key="avail_search",
        )

    # Build query for available players
    query = session.query(Player).filter(Player.is_drafted == False)

    if player_type == "Hitters":
        query = query.filter(Player.player_type == "hitter")
    elif player_type == "Pitchers":
        query = query.filter(Player.player_type == "pitcher")

    if position_filter:
        query = query.filter(Player.positions.contains(position_filter.upper()))

    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))

    # Sort by dollar value descending
    query = query.order_by(Player.dollar_value.desc())

    available = query.limit(100).all()

    if available:
        df = pd.DataFrame([
            {
                "Name": p.name,
                "Team": p.team or "",
                "Type": p.player_type.title() if p.player_type else "",
                "Pos": p.positions or "",
                "Value": f"${p.dollar_value:.0f}" if p.dollar_value else "-",
            }
            for p in available
        ])

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Showing top {len(available)} available players by value")
    else:
        st.info("No available players match the current filters.")

    # Draft history
    st.divider()
    st.subheader("Draft History")

    history = get_draft_history(session, limit=20)

    if history:
        for pick in history:
            col1, col2, col3, col4 = st.columns([1, 3, 2, 1])

            with col1:
                st.text(f"#{pick['pick_number']}")

            with col2:
                st.text(pick['player_name'])

            with col3:
                st.text(f"{pick['team_name']} - ${pick['price']}")

            with col4:
                if st.button("Undo", key=f"undo_{pick['pick_id']}"):
                    player = undo_pick(session, pick['pick_id'])
                    if player:
                        st.success(f"Undid pick: {player.name}")
                    st.rerun()

        if len(history) >= 20:
            st.caption("Showing last 20 picks")
    else:
        st.info("No picks yet. Start drafting!")


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

    # Calculate Values section
    st.divider()
    st.subheader("Calculate Player Values")

    # Check if we have players to calculate values for
    total_players = session.query(Player).count()

    if total_players > 0:
        st.markdown("""
        Calculate SGP (Standings Gain Points) and dollar values for all players.
        This uses the standard deviation method to determine how much each player
        contributes to your standings in each category.
        """)

        if st.button("Calculate Values", type="primary"):
            try:
                count = calculate_all_player_values(session, DEFAULT_SETTINGS)
                st.success(f"Calculated values for {count} players!")
                st.rerun()
            except Exception as e:
                st.error(f"Error calculating values: {e}")

        # Show summary of current values
        players_with_values = session.query(Player).filter(Player.dollar_value.isnot(None)).count()
        if players_with_values > 0:
            st.info(f"{players_with_values} players currently have calculated values.")
    else:
        st.warning("Import players first before calculating values.")


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
