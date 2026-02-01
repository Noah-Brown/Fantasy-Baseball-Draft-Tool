"""Fantasy Baseball Auction Draft Tool - Main Streamlit App."""

import streamlit as st
import pandas as pd
from pathlib import Path

from src.database import init_db, get_session, Player, Team, DraftState, TargetPlayer
from src.projections import (
    import_hitters_csv,
    import_pitchers_csv,
    clear_all_players,
    get_available_players,
)
from src.settings import DEFAULT_SETTINGS, LeagueSettings
from src.values import calculate_all_player_values, calculate_remaining_player_values, calculate_category_surplus
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
from src.targets import (
    add_target,
    remove_target,
    update_target,
    get_targets,
    get_target_player_ids,
    get_target_by_player_id,
    clear_all_targets,
    get_available_targets_below_value,
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


def auto_load_data(session) -> bool:
    """
    Auto-load CSV data from the data folder if database is empty.

    Looks for hitter and pitcher CSVs in the data folder and imports them
    if the database has no players. Also calculates values after import.

    Returns:
        True if data was auto-loaded, False otherwise
    """
    # Skip if already checked this session
    if st.session_state.get("data_auto_loaded"):
        return False

    # Check if database already has players
    player_count = session.query(Player).count()
    if player_count > 0:
        st.session_state.data_auto_loaded = True
        return False

    # Look for CSV files in data folder
    data_dir = Path("data")
    if not data_dir.exists():
        st.session_state.data_auto_loaded = True
        return False

    # Find hitter and pitcher CSV files
    hitter_csv = None
    pitcher_csv = None

    for csv_file in data_dir.glob("*.csv"):
        name_lower = csv_file.name.lower()
        if "batter" in name_lower or "hitter" in name_lower:
            hitter_csv = csv_file
        elif "pitcher" in name_lower:
            pitcher_csv = csv_file

    if not hitter_csv and not pitcher_csv:
        st.session_state.data_auto_loaded = True
        return False

    # Import the data
    imported = False

    if hitter_csv:
        try:
            count = import_hitters_csv(session, hitter_csv)
            st.toast(f"Auto-loaded {count} hitters from {hitter_csv.name}")
            imported = True
        except Exception as e:
            st.warning(f"Failed to auto-load hitters: {e}")

    if pitcher_csv:
        try:
            count = import_pitchers_csv(session, pitcher_csv)
            st.toast(f"Auto-loaded {count} pitchers from {pitcher_csv.name}")
            imported = True
        except Exception as e:
            st.warning(f"Failed to auto-load pitchers: {e}")

    # Calculate values if we imported data
    if imported:
        try:
            settings = get_current_settings()
            calculate_all_player_values(session, settings)
            st.toast("Calculated player values")
        except Exception as e:
            st.warning(f"Failed to calculate values: {e}")

    st.session_state.data_auto_loaded = True
    return imported


def get_current_settings() -> LeagueSettings:
    """
    Get current league settings from session state.

    Initializes session state from DEFAULT_SETTINGS if not present.
    Returns a LeagueSettings instance with current session values.
    """
    # Initialize from defaults if not present
    if "league_settings" not in st.session_state:
        st.session_state.league_settings = {
            "num_teams": DEFAULT_SETTINGS.num_teams,
            "budget_per_team": DEFAULT_SETTINGS.budget_per_team,
            "min_bid": DEFAULT_SETTINGS.min_bid,
            "roster_spots": dict(DEFAULT_SETTINGS.roster_spots),
        }

    # Build LeagueSettings from session state
    state = st.session_state.league_settings
    return LeagueSettings(
        num_teams=state["num_teams"],
        budget_per_team=state["budget_per_team"],
        min_bid=state["min_bid"],
        roster_spots=state["roster_spots"],
    )


def main():
    """Main application."""
    engine = get_db()
    session = get_session(engine)

    # Auto-load data from CSVs in data folder if database is empty
    auto_load_data(session)

    st.title("⚾ Fantasy Baseball Auction Draft Tool")

    # Sidebar for navigation and settings
    with st.sidebar:
        st.header("Navigation")
        page = st.radio(
            "Select Page",
            ["Player Database", "Draft Room", "My Targets", "My Team", "All Teams", "Import Projections", "League Settings"],
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
    elif page == "My Targets":
        show_my_targets(session)
    elif page == "My Team":
        show_my_team(session)
    elif page == "All Teams":
        show_all_teams(session)
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
        positions = st.multiselect(
            "Positions",
            ["C", "1B", "2B", "3B", "SS", "OF", "UTIL", "SP", "RP"],
            default=[],
            key="position_filter",
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

    if positions:
        # Filter for players matching ANY of the selected positions
        from sqlalchemy import or_
        position_filters = [Player.positions.contains(pos) for pos in positions]
        query = query.filter(or_(*position_filters))

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
        width='stretch',
        hide_index=True,
    )

    st.caption(f"Showing {len(players)} players")

    # Quick add to targets
    st.divider()
    st.subheader("Quick Add to Targets")

    target_ids = get_target_player_ids(session)
    # Filter to only show players not already targeted and not drafted
    targetable_players = [p for p in players if p.id not in target_ids and not p.is_drafted]

    if targetable_players:
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            player_options = {
                f"{p.name} ({p.positions}) - ${p.dollar_value:.0f}" if p.dollar_value else f"{p.name} ({p.positions})": p.id
                for p in targetable_players[:100]
            }
            selected_label = st.selectbox(
                "Select Player to Target",
                options=list(player_options.keys()),
                key="db_target_player",
            )
            selected_id = player_options[selected_label]

        selected_player = session.get(Player, selected_id)
        default_bid = int(selected_player.dollar_value) if selected_player.dollar_value else 1

        with col2:
            max_bid = st.number_input(
                "Max Bid ($)",
                min_value=1,
                max_value=999,
                value=default_bid,
                key="db_target_max_bid",
            )

        with col3:
            st.write("")  # Spacer
            st.write("")  # Spacer
            if st.button("Add to Targets", key="db_add_target"):
                try:
                    add_target(session, selected_id, max_bid)
                    st.success(f"Added {selected_player.name} to targets!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    else:
        st.info("All displayed players are either already targeted or drafted.")


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
                    initialize_draft(session, get_current_settings(), team_name)
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

                if st.button("DRAFT", type="primary", width='stretch'):
                    try:
                        draft_player(session, selected_player_id, selected_team_id, price, get_current_settings())
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

    # Target alerts - show bargains at the top
    bargains = get_available_targets_below_value(session)
    if bargains:
        with st.container():
            st.success(f"🎯 **{len(bargains)} TARGET ALERT{'S' if len(bargains) > 1 else ''}** - Players available at or below your max bid!")
            cols = st.columns(min(len(bargains), 4))
            for i, b in enumerate(bargains[:4]):  # Show up to 4
                player = b["player"]
                with cols[i]:
                    st.markdown(f"**{player.name}**")
                    st.caption(f"Value: ${b['value']:.0f} | Max: ${b['max_bid']} | +${b['headroom']:.0f} headroom")
            if len(bargains) > 4:
                st.caption(f"... and {len(bargains) - 4} more. See My Targets for full list.")
        st.divider()

    # Manual recalculate values button (backup option - values auto-update after each pick)
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Recalculate Values", type="secondary"):
            try:
                count = calculate_remaining_player_values(session, get_current_settings())
                st.success(f"Recalculated values for {count} available players!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # Available players table
    st.subheader("Available Players")

    # Filters for available players
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        player_type = st.selectbox(
            "Player Type",
            ["All", "Hitters", "Pitchers"],
            key="avail_player_type",
        )

    with col2:
        positions = st.multiselect(
            "Positions",
            ["C", "1B", "2B", "3B", "SS", "OF", "UTIL", "SP", "RP"],
            default=[],
            key="avail_position",
        )

    with col3:
        search = st.text_input(
            "Search Player",
            placeholder="Player name...",
            key="avail_search",
        )

    with col4:
        show_category_sgp = st.checkbox(
            "Show Category SGP",
            key="show_category_sgp",
            disabled=(player_type == "All"),
            help="Available when viewing Hitters or Pitchers only",
        )
        show_raw_stats = st.checkbox(
            "Show Raw Stats",
            key="show_raw_stats",
            disabled=(player_type == "All"),
            help="Show projected stats (R, HR, etc.) alongside values",
        )

    # Build query for available players
    query = session.query(Player).filter(Player.is_drafted == False)

    if player_type == "Hitters":
        query = query.filter(Player.player_type == "hitter")
    elif player_type == "Pitchers":
        query = query.filter(Player.player_type == "pitcher")

    if positions:
        # Filter for players matching ANY of the selected positions
        from sqlalchemy import or_
        position_filters = [Player.positions.contains(pos) for pos in positions]
        query = query.filter(or_(*position_filters))

    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))

    # Sort by dollar value descending
    query = query.order_by(Player.dollar_value.desc())

    available = query.limit(100).all()

    # Get target info for highlighting
    target_ids = get_target_player_ids(session)
    target_info = {t.player_id: t for t in get_targets(session, include_drafted=False)}

    if available:
        rows = []
        target_rows = []  # Track which rows are targets for styling
        for idx, p in enumerate(available):
            # Check if player is targeted
            is_target = p.id in target_ids
            target = target_info.get(p.id)

            # Build target indicator
            if is_target and target:
                value = p.dollar_value or 0
                if value <= target.max_bid:
                    target_display = f"🎯 ${target.max_bid}"  # Bargain - at/below max
                else:
                    target_display = f"⭐ ${target.max_bid}"  # Target but above max
            else:
                target_display = ""

            row = {
                "Target": target_display,
                "Name": p.name,
                "Team": p.team or "",
                "Type": p.player_type.title() if p.player_type else "",
                "Pos": p.positions or "",
                "Value": f"${p.dollar_value:.0f}" if p.dollar_value else "-",
            }

            # Add raw stats columns if toggle is enabled and not viewing "All"
            if show_raw_stats and player_type != "All":
                if player_type == "Hitters":
                    row["R"] = int(p.r or 0)
                    row["HR"] = int(p.hr or 0)
                    row["RBI"] = int(p.rbi or 0)
                    row["SB"] = int(p.sb or 0)
                    row["AVG"] = f"{p.avg:.3f}" if p.avg else ".000"
                elif player_type == "Pitchers":
                    row["W"] = int(p.w or 0)
                    row["SV"] = int(p.sv or 0)
                    row["K"] = int(p.k or 0)
                    row["ERA"] = round(p.era, 2) if p.era else 0.00
                    row["WHIP"] = round(p.whip, 2) if p.whip else 0.00

            # Add category SGP columns if toggle is enabled and not viewing "All"
            if show_category_sgp and player_type != "All" and p.sgp_breakdown:
                if player_type == "Hitters":
                    for cat in ["r", "hr", "rbi", "sb", "avg"]:
                        row[f"{cat.upper()} SGP"] = round(p.sgp_breakdown.get(cat, 0), 2)
                elif player_type == "Pitchers":
                    for cat in ["w", "sv", "k", "era", "whip"]:
                        row[f"{cat.upper()} SGP"] = round(p.sgp_breakdown.get(cat, 0), 2)

            rows.append(row)
            if is_target:
                target_rows.append(idx)

        df = pd.DataFrame(rows)

        # Style function to highlight target rows
        def highlight_targets(row):
            if row.name in target_rows:
                # Check if it's a bargain (🎯) or just a target (⭐)
                if "🎯" in str(row.get("Target", "")):
                    return ["background-color: #c8e6c9"] * len(row)  # Light green for bargains
                else:
                    return ["background-color: #fff9c4"] * len(row)  # Light yellow for targets
            return [""] * len(row)

        styled_df = df.style.apply(highlight_targets, axis=1)

        st.dataframe(
            styled_df,
            width='stretch',
            hide_index=True,
        )

        # Legend
        st.caption(f"Showing top {len(available)} available players by value")
        if target_ids:
            st.caption("🎯 = Target at/below max bid (bargain!) | ⭐ = Target above max bid")

        # Export available players
        csv = df.to_csv(index=False)
        st.download_button(
            label="Export Available Players to CSV",
            data=csv,
            file_name="available_players.csv",
            mime="text/csv",
        )
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
                    player = undo_pick(session, pick['pick_id'], get_current_settings())
                    if player:
                        st.success(f"Undid pick: {player.name}")
                    st.rerun()

        if len(history) >= 20:
            st.caption("Showing last 20 picks")

        # Export draft history - get full history for export
        full_history = get_draft_history(session)
        history_rows = []
        for pick in full_history:
            player = session.get(Player, pick['player_id']) if pick['player_id'] else None
            value = player.dollar_value if player and player.dollar_value else 0
            surplus = value - pick['price']
            history_rows.append({
                "Pick #": pick['pick_number'],
                "Player": pick['player_name'],
                "Team": pick['team_name'],
                "Pos": player.positions if player else "",
                "Price": pick['price'],
                "Value": round(value, 0),
                "Surplus": round(surplus, 0),
            })

        if history_rows:
            history_df = pd.DataFrame(history_rows)
            csv = history_df.to_csv(index=False)
            st.download_button(
                label="Export Draft History to CSV",
                data=csv,
                file_name="draft_history.csv",
                mime="text/csv",
            )
    else:
        st.info("No picks yet. Start drafting!")


def show_my_targets(session):
    """Display and manage the user's target list."""
    st.header("My Targets")

    st.markdown("""
    Build your target list before the draft. Set maximum bid prices for players you want,
    and they'll be highlighted in the Draft Room when available.
    """)

    # Get current targets
    target_ids = get_target_player_ids(session)

    # Bargain alerts - targets available at or below max bid
    bargains = get_available_targets_below_value(session)
    if bargains:
        st.success(f"🎯 {len(bargains)} target(s) available at or below your max bid!")
        with st.expander("View Bargain Targets", expanded=True):
            for b in bargains:
                player = b["player"]
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"**{player.name}** ({player.positions})")
                with col2:
                    st.write(f"Value: ${b['value']:.0f}")
                with col3:
                    st.write(f"Max Bid: ${b['max_bid']}")
                with col4:
                    st.write(f"Headroom: +${b['headroom']:.0f}")

    st.divider()

    # Add new target section
    st.subheader("Add Target")

    # Get available players not already targeted
    available_players = session.query(Player).filter(
        Player.is_drafted == False,
        ~Player.id.in_(target_ids) if target_ids else True
    ).order_by(Player.dollar_value.desc()).all()

    if available_players:
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            player_options = {
                f"{p.name} ({p.positions}) - ${p.dollar_value:.0f}" if p.dollar_value else f"{p.name} ({p.positions})": p.id
                for p in available_players[:200]  # Limit for performance
            }
            selected_player_label = st.selectbox(
                "Select Player",
                options=list(player_options.keys()),
                key="target_player_select",
            )
            selected_player_id = player_options[selected_player_label]

        # Get selected player for default max bid
        selected_player = session.get(Player, selected_player_id)
        default_max = int(selected_player.dollar_value) if selected_player.dollar_value else 1

        with col2:
            max_bid = st.number_input(
                "Max Bid ($)",
                min_value=1,
                max_value=999,
                value=default_max,
                key="target_max_bid",
            )

        with col3:
            priority = st.selectbox(
                "Priority",
                options=[("High", 2), ("Medium", 1), ("Low", 0)],
                format_func=lambda x: x[0],
                key="target_priority",
            )

        notes = st.text_input(
            "Notes (optional)",
            placeholder="e.g., Great SB upside, injury risk...",
            key="target_notes",
        )

        if st.button("Add to Targets", type="primary"):
            try:
                add_target(session, selected_player_id, max_bid, priority[1], notes if notes else None)
                st.success(f"Added {selected_player.name} to targets!")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        st.info("No available players to target. Import players first.")

    st.divider()

    # Current targets list
    st.subheader("Current Targets")

    targets = get_targets(session, include_drafted=True)

    if not targets:
        st.info("No targets yet. Add players above to build your target list.")
        return

    # Summary stats
    available_targets = [t for t in targets if not t.player.is_drafted]
    drafted_targets = [t for t in targets if t.player.is_drafted]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Targets", len(targets))
    col2.metric("Still Available", len(available_targets))
    col3.metric("Already Drafted", len(drafted_targets))

    st.divider()

    # Display targets
    for target in targets:
        player = target.player
        is_drafted = player.is_drafted
        value = player.dollar_value or 0

        # Determine status and styling
        if is_drafted:
            status = "🔴 Drafted"
            container_style = "background-color: #ffebee;"
        elif value <= target.max_bid:
            status = "🟢 Bargain!"
            container_style = "background-color: #e8f5e9;"
        else:
            status = "🟡 Available"
            container_style = ""

        # Priority label
        priority_labels = {0: "Low", 1: "Medium", 2: "High"}
        priority_label = priority_labels.get(target.priority, "Medium")

        with st.container():
            col1, col2, col3, col4, col5, col6 = st.columns([3, 1, 1, 1, 1, 1])

            with col1:
                name_display = f"~~{player.name}~~" if is_drafted else f"**{player.name}**"
                st.markdown(f"{name_display} ({player.positions})")
                if target.notes:
                    st.caption(f"📝 {target.notes}")

            with col2:
                st.write(f"Value: ${value:.0f}")

            with col3:
                st.write(f"Max: ${target.max_bid}")

            with col4:
                st.write(priority_label)

            with col5:
                st.write(status)

            with col6:
                if not is_drafted:
                    if st.button("Remove", key=f"remove_target_{player.id}"):
                        remove_target(session, player.id)
                        st.rerun()

        # Edit section (collapsible)
        if not is_drafted:
            with st.expander(f"Edit {player.name}", expanded=False):
                edit_col1, edit_col2, edit_col3 = st.columns([1, 1, 2])

                with edit_col1:
                    new_max = st.number_input(
                        "New Max Bid",
                        min_value=1,
                        max_value=999,
                        value=target.max_bid,
                        key=f"edit_max_{player.id}",
                    )

                with edit_col2:
                    new_priority = st.selectbox(
                        "New Priority",
                        options=[("High", 2), ("Medium", 1), ("Low", 0)],
                        format_func=lambda x: x[0],
                        index=2 - target.priority,  # Reverse index since High=2
                        key=f"edit_priority_{player.id}",
                    )

                with edit_col3:
                    new_notes = st.text_input(
                        "New Notes",
                        value=target.notes or "",
                        key=f"edit_notes_{player.id}",
                    )

                if st.button("Save Changes", key=f"save_target_{player.id}"):
                    update_target(session, player.id, new_max, new_priority[1], new_notes)
                    st.success("Updated!")
                    st.rerun()

    st.divider()

    # Clear all targets button
    if targets:
        if st.button("Clear All Targets", type="secondary"):
            count = clear_all_targets(session)
            st.success(f"Removed {count} targets")
            st.rerun()


def style_surplus(val):
    """Apply color styling based on surplus value."""
    if pd.isna(val):
        return ''
    if val >= 5:
        return 'background-color: #90EE90'  # Light green (great deal)
    elif val >= 1:
        return 'background-color: #98FB98'  # Pale green (good deal)
    elif val >= -4:
        return 'background-color: #FFFFE0'  # Light yellow (fair/slight overpay)
    else:
        return 'background-color: #FFB6C1'  # Light pink/red (significant overpay)


def show_my_team(session):
    """Display the user's team roster and stats."""
    st.header("My Team")

    draft_state = get_draft_state(session)
    if not draft_state or not draft_state.is_active:
        st.info("Start a draft first to see your team. Go to Draft Room to begin.")
        return

    user_team = get_user_team(session)
    if not user_team:
        st.warning("No user team found.")
        return

    # Summary metrics at top
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    col1.metric("Spent", f"${user_team.spent}")
    col2.metric("Remaining", f"${user_team.remaining_budget}")
    col3.metric("Players", user_team.roster_count)
    with col4:
        show_category_surplus = st.checkbox(
            "Show Category Surplus",
            key="my_team_category_surplus",
        )

    st.divider()

    # Get drafted players via DraftPick relationship
    picks = user_team.draft_picks
    if not picks:
        st.info("No players drafted yet. Go to Draft Room to start drafting!")
        return

    # Build dataframe with player info + value/price comparison
    rows = []
    category_surplus_totals = {"r": 0, "hr": 0, "rbi": 0, "sb": 0, "avg": 0, "w": 0, "sv": 0, "k": 0, "era": 0, "whip": 0}
    for pick in picks:
        player = pick.player
        if player:
            value = player.dollar_value or 0
            surplus = value - pick.price
            row = {
                "Name": player.name,
                "Pos": player.positions or "",
                "MLB Team": player.team or "",
                "Price": pick.price,
                "Value": round(value, 0),
                "Surplus": round(surplus, 0),
            }

            # Add category surplus columns if toggle is enabled
            if show_category_surplus:
                cat_surplus = calculate_category_surplus(player, pick.price)
                if player.player_type == "hitter":
                    for cat in ["r", "hr", "rbi", "sb", "avg"]:
                        val = cat_surplus.get(cat, 0)
                        row[f"{cat.upper()} +/-"] = round(val, 1)
                        category_surplus_totals[cat] += val
                elif player.player_type == "pitcher":
                    for cat in ["w", "sv", "k", "era", "whip"]:
                        val = cat_surplus.get(cat, 0)
                        row[f"{cat.upper()} +/-"] = round(val, 1)
                        category_surplus_totals[cat] += val

            rows.append(row)

    if rows:
        df = pd.DataFrame(rows)

        # Apply styling to Surplus column and category surplus columns
        surplus_cols = ['Surplus']
        if show_category_surplus:
            surplus_cols += [col for col in df.columns if col.endswith('+/-')]

        styled_df = df.style.applymap(style_surplus, subset=[c for c in surplus_cols if c in df.columns])

        st.dataframe(
            styled_df,
            width='stretch',
            hide_index=True,
        )

        # Export button
        csv = df.to_csv(index=False)
        st.download_button(
            label="Export My Team to CSV",
            data=csv,
            file_name="my_team.csv",
            mime="text/csv",
        )

        # Summary stats
        st.divider()
        total_value = df['Value'].sum()
        total_spent = df['Price'].sum()
        total_surplus = df['Surplus'].sum()

        st.subheader("Team Summary")
        scol1, scol2, scol3 = st.columns(3)
        scol1.metric("Total Value", f"${total_value:.0f}")
        scol2.metric("Total Spent", f"${total_spent:.0f}")
        scol3.metric("Total Surplus", f"${total_surplus:+.0f}")

        # Category surplus totals
        if show_category_surplus:
            st.divider()
            st.subheader("Category Surplus Totals")

            # Hitter categories
            hitter_cats = ["r", "hr", "rbi", "sb", "avg"]
            hitter_totals = {cat: category_surplus_totals[cat] for cat in hitter_cats}
            if any(v != 0 for v in hitter_totals.values()):
                st.markdown("**Hitting**")
                hcols = st.columns(5)
                for i, cat in enumerate(hitter_cats):
                    val = hitter_totals[cat]
                    hcols[i].metric(cat.upper(), f"{val:+.1f}")

            # Pitcher categories
            pitcher_cats = ["w", "sv", "k", "era", "whip"]
            pitcher_totals = {cat: category_surplus_totals[cat] for cat in pitcher_cats}
            if any(v != 0 for v in pitcher_totals.values()):
                st.markdown("**Pitching**")
                pcols = st.columns(5)
                for i, cat in enumerate(pitcher_cats):
                    val = pitcher_totals[cat]
                    pcols[i].metric(cat.upper(), f"{val:+.1f}")


def show_all_teams(session):
    """Display all teams and their rosters."""
    st.header("All Teams")

    draft_state = get_draft_state(session)
    if not draft_state or not draft_state.is_active:
        st.info("Start a draft first to see teams. Go to Draft Room to begin.")
        return

    teams = get_all_teams(session)
    if not teams:
        st.warning("No teams found.")
        return

    # Toggle for category surplus display
    show_category_surplus = st.checkbox(
        "Show Category Surplus",
        key="all_teams_category_surplus",
    )

    # Summary table - include category surplus totals if enabled
    summary_data = []
    all_team_cat_totals = {}  # {team_id: {cat: total}}

    for t in teams:
        team_label = t.name
        if t.is_user_team:
            team_label += " (You)"

        row = {
            "Team": team_label,
            "Spent": f"${t.spent}",
            "Remaining": f"${t.remaining_budget}",
            "Players": t.roster_count,
        }

        # Calculate category totals for this team
        if show_category_surplus:
            team_cat_totals = {"r": 0, "hr": 0, "rbi": 0, "sb": 0, "avg": 0, "w": 0, "sv": 0, "k": 0, "era": 0, "whip": 0}
            for pick in t.draft_picks:
                player = pick.player
                if player:
                    cat_surplus = calculate_category_surplus(player, pick.price)
                    for cat, val in cat_surplus.items():
                        team_cat_totals[cat] += val
            all_team_cat_totals[t.id] = team_cat_totals

        summary_data.append(row)

    summary_df = pd.DataFrame(summary_data)
    st.dataframe(summary_df, width='stretch', hide_index=True)

    # League-wide category surplus comparison table
    if show_category_surplus and all_team_cat_totals:
        st.divider()
        st.subheader("League Category Surplus Comparison")

        comparison_rows = []
        for t in teams:
            if t.id in all_team_cat_totals:
                team_label = t.name
                if t.is_user_team:
                    team_label += " (You)"
                cat_totals = all_team_cat_totals[t.id]
                row = {"Team": team_label}
                # Hitting categories
                for cat in ["r", "hr", "rbi", "sb", "avg"]:
                    row[cat.upper()] = round(cat_totals[cat], 1)
                # Pitching categories
                for cat in ["w", "sv", "k", "era", "whip"]:
                    row[cat.upper()] = round(cat_totals[cat], 1)
                comparison_rows.append(row)

        if comparison_rows:
            comparison_df = pd.DataFrame(comparison_rows)
            # Style positive/negative values
            cat_cols = ["R", "HR", "RBI", "SB", "AVG", "W", "SV", "K", "ERA", "WHIP"]
            styled_comparison = comparison_df.style.applymap(
                style_surplus,
                subset=[c for c in cat_cols if c in comparison_df.columns]
            )
            st.dataframe(styled_comparison, width='stretch', hide_index=True)

    st.divider()

    # Expandable detail sections for each team
    for team in teams:
        header_label = f"{team.name}"
        if team.is_user_team:
            header_label += " (You)"
        header_label += f" - {team.roster_count} players"

        with st.expander(header_label, expanded=team.is_user_team):
            picks = team.draft_picks
            if not picks:
                st.info("No players drafted yet.")
                continue

            # Build roster dataframe
            rows = []
            for pick in picks:
                player = pick.player
                if player:
                    value = player.dollar_value or 0
                    surplus = value - pick.price
                    row = {
                        "Name": player.name,
                        "Pos": player.positions or "",
                        "MLB Team": player.team or "",
                        "Price": pick.price,
                        "Value": round(value, 0),
                        "Surplus": round(surplus, 0),
                    }

                    # Add category surplus columns if toggle is enabled
                    if show_category_surplus:
                        cat_surplus = calculate_category_surplus(player, pick.price)
                        if player.player_type == "hitter":
                            for cat in ["r", "hr", "rbi", "sb", "avg"]:
                                row[f"{cat.upper()} +/-"] = round(cat_surplus.get(cat, 0), 1)
                        elif player.player_type == "pitcher":
                            for cat in ["w", "sv", "k", "era", "whip"]:
                                row[f"{cat.upper()} +/-"] = round(cat_surplus.get(cat, 0), 1)

                    rows.append(row)

            if rows:
                df = pd.DataFrame(rows)

                # Apply styling to surplus columns
                surplus_cols = ['Surplus']
                if show_category_surplus:
                    surplus_cols += [col for col in df.columns if col.endswith('+/-')]

                styled_df = df.style.applymap(style_surplus, subset=[c for c in surplus_cols if c in df.columns])
                st.dataframe(
                    styled_df,
                    width='stretch',
                    hide_index=True,
                )

                # Team totals
                total_value = df['Value'].sum()
                total_surplus = df['Surplus'].sum()
                st.caption(f"Total Value: ${total_value:.0f} | Total Surplus: ${total_surplus:+.0f}")


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
                count = calculate_all_player_values(session, get_current_settings())
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

    # Get current settings from session state
    settings = get_current_settings()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("League Structure")
        num_teams = st.number_input(
            "Number of Teams",
            min_value=4,
            max_value=20,
            value=st.session_state.league_settings["num_teams"],
            key="settings_num_teams",
        )
        budget = st.number_input(
            "Budget per Team ($)",
            min_value=100,
            max_value=500,
            value=st.session_state.league_settings["budget_per_team"],
            key="settings_budget",
        )
        min_bid = st.number_input(
            "Minimum Bid ($)",
            min_value=1,
            max_value=5,
            value=st.session_state.league_settings["min_bid"],
            key="settings_min_bid",
        )

        # Update session state when values change
        st.session_state.league_settings["num_teams"] = num_teams
        st.session_state.league_settings["budget_per_team"] = budget
        st.session_state.league_settings["min_bid"] = min_bid

    with col2:
        st.subheader("Scoring Categories")
        st.markdown("**Hitting (5x5)**")
        st.text(", ".join(settings.hitting_categories))

        st.markdown("**Pitching (5x5)**")
        st.text(", ".join(settings.pitching_categories))

    st.divider()

    st.subheader("Roster Spots")

    # Hitter positions
    st.markdown("**Hitters**")
    hitter_cols = st.columns(4)
    hitter_positions = ["C", "1B", "2B", "3B", "SS", "OF", "UTIL"]

    for i, pos in enumerate(hitter_positions):
        with hitter_cols[i % 4]:
            current_val = st.session_state.league_settings["roster_spots"].get(pos, 0)
            new_val = st.number_input(
                pos,
                min_value=0,
                max_value=10,
                value=current_val,
                key=f"roster_{pos}",
            )
            st.session_state.league_settings["roster_spots"][pos] = new_val

    # Pitcher positions
    st.markdown("**Pitchers**")
    pitcher_cols = st.columns(4)
    pitcher_positions = ["SP", "RP", "P"]

    for i, pos in enumerate(pitcher_positions):
        with pitcher_cols[i % 4]:
            current_val = st.session_state.league_settings["roster_spots"].get(pos, 0)
            new_val = st.number_input(
                pos,
                min_value=0,
                max_value=10,
                value=current_val,
                key=f"roster_{pos}",
            )
            st.session_state.league_settings["roster_spots"][pos] = new_val

    # Bench
    st.markdown("**Bench**")
    bench_col = st.columns(4)
    with bench_col[0]:
        current_bn = st.session_state.league_settings["roster_spots"].get("BN", 0)
        new_bn = st.number_input(
            "BN",
            min_value=0,
            max_value=10,
            value=current_bn,
            key="roster_BN",
        )
        st.session_state.league_settings["roster_spots"]["BN"] = new_bn

    st.divider()

    # Reset to defaults button
    if st.button("Reset to Defaults", type="secondary"):
        st.session_state.league_settings = {
            "num_teams": DEFAULT_SETTINGS.num_teams,
            "budget_per_team": DEFAULT_SETTINGS.budget_per_team,
            "min_bid": DEFAULT_SETTINGS.min_bid,
            "roster_spots": dict(DEFAULT_SETTINGS.roster_spots),
        }
        st.rerun()

    st.divider()

    # Summary - recalculate from current session state
    current_settings = get_current_settings()
    st.subheader("League Summary")
    total_budget = current_settings.num_teams * current_settings.budget_per_team
    st.write(f"**Total League Budget:** ${total_budget:,}")
    st.write(f"**Hitters Drafted:** {current_settings.total_hitters_drafted}")
    st.write(f"**Pitchers Drafted:** {current_settings.total_pitchers_drafted}")


if __name__ == "__main__":
    main()
