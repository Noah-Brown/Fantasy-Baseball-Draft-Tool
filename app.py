"""Fantasy Baseball Auction Draft Tool - Main Streamlit App."""

import streamlit as st
import pandas as pd
import altair as alt
from pathlib import Path

from src.database import init_db, get_session, Player, Team, DraftState, TargetPlayer
from src.projections import (
    import_hitters_csv,
    import_pitchers_csv,
    clear_all_players,
    get_available_players,
)
from src.settings import DEFAULT_SETTINGS, LeagueSettings
from src.values import (
    calculate_all_player_values,
    calculate_remaining_player_values,
    calculate_category_surplus,
    analyze_team_category_balance,
)
from src.draft import (
    initialize_draft,
    draft_player,
    undo_pick,
    get_draft_history,
    reset_draft,
    get_draft_state,
    get_all_teams,
    get_user_team,
    get_on_the_clock_team,
    calculate_max_bid,
    get_team_roster_needs,
    calculate_bid_impact,
    get_position_scarcity,
)
from src.snake import (
    get_current_drafter,
    get_pick_position,
    get_team_next_pick,
    format_pick_display,
)
from src.values import get_player_ranks
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
from src.components import inject_keyboard_shortcuts, inject_keyboard_hint
from src.positions import (
    ALL_FILTER_POSITIONS,
    HITTER_ROSTER_POSITIONS,
    expand_position,
)
from src.needs import (
    analyze_team_needs,
    get_team_positional_roster_state,
)

# Page configuration
st.set_page_config(
    page_title="Fantasy Baseball Draft Tool",
    page_icon="⚾",
    layout="wide",
)

# Inject keyboard shortcuts for quick search
inject_keyboard_shortcuts()
inject_keyboard_hint()

# Initialize database
@st.cache_resource
def get_db():
    """Initialize and cache database connection."""
    engine = init_db("data/draft.db")
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
            "use_positional_adjustments": DEFAULT_SETTINGS.use_positional_adjustments,
            "draft_type": DEFAULT_SETTINGS.draft_type,
            "rounds_per_team": DEFAULT_SETTINGS.rounds_per_team,
        }

    # Ensure use_positional_adjustments exists (for existing sessions)
    if "use_positional_adjustments" not in st.session_state.league_settings:
        st.session_state.league_settings["use_positional_adjustments"] = DEFAULT_SETTINGS.use_positional_adjustments

    # Ensure draft_type and rounds_per_team exist (for existing sessions)
    if "draft_type" not in st.session_state.league_settings:
        st.session_state.league_settings["draft_type"] = DEFAULT_SETTINGS.draft_type
    if "rounds_per_team" not in st.session_state.league_settings:
        st.session_state.league_settings["rounds_per_team"] = DEFAULT_SETTINGS.rounds_per_team

    # Build category lists from core + optional
    state = st.session_state.league_settings
    hitting_categories = ["R", "HR", "RBI", "SB", "AVG"] + state.get("optional_hitting_cats", [])
    pitching_categories = ["W", "SV", "K", "ERA", "WHIP"] + state.get("optional_pitching_cats", [])

    # Build LeagueSettings from session state
    return LeagueSettings(
        num_teams=state["num_teams"],
        budget_per_team=state["budget_per_team"],
        min_bid=state["min_bid"],
        roster_spots=state["roster_spots"],
        hitting_categories=hitting_categories,
        pitching_categories=pitching_categories,
        use_positional_adjustments=state.get("use_positional_adjustments", True),
        draft_type=state.get("draft_type", "auction"),
        rounds_per_team=state.get("rounds_per_team", 23),
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
            ["Home", "Player Database", "Draft Room", "My Targets", "My Team", "All Teams", "League Settings"],
            label_visibility="collapsed",
        )

        st.divider()

        # Quick stats
        hitter_count = session.query(Player).filter(Player.player_type == "hitter").count()
        pitcher_count = session.query(Player).filter(Player.player_type == "pitcher").count()

        st.metric("Hitters", hitter_count)
        st.metric("Pitchers", pitcher_count)

    # Page routing
    if page == "Home":
        show_home_page(session)
    elif page == "Player Database":
        show_player_database(session)
    elif page == "Draft Room":
        show_draft_room(session)
    elif page == "My Targets":
        show_my_targets(session)
    elif page == "My Team":
        show_my_team(session)
    elif page == "All Teams":
        show_all_teams(session)
    elif page == "League Settings":
        show_settings_page(session)

    session.close()


def show_home_page(session):
    """Display the welcome/home page with overview and status dashboard."""
    st.header("Welcome to Fantasy Baseball Draft Tool")

    st.markdown(
        "A draft assistant powered by **SGP (Standings Gain Points)** valuations "
        "from FanGraphs Depth Charts (FGDC) projections. Supports both **auction** "
        "and **snake** draft formats."
    )

    st.divider()

    # Status dashboard
    st.subheader("Dashboard")

    hitter_count = session.query(Player).filter(Player.player_type == "hitter").count()
    pitcher_count = session.query(Player).filter(Player.player_type == "pitcher").count()
    drafted_count = session.query(Player).filter(Player.is_drafted == True).count()  # noqa: E712
    team_count = session.query(Team).count()
    target_count = session.query(TargetPlayer).count()

    draft_state = session.query(DraftState).first()
    if draft_state and draft_state.is_active:
        draft_status = f"{drafted_count} picks made"
    elif drafted_count > 0:
        draft_status = f"Complete ({drafted_count} picks)"
    else:
        draft_status = "Not started"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Hitters", hitter_count)
    col2.metric("Pitchers", pitcher_count)
    col3.metric("Draft", draft_status)
    col4.metric("Targets", target_count)

    st.divider()

    # Quick start guide
    st.subheader("Getting Started")

    st.markdown("""
1. **League Settings** — Configure your league size, budget, roster spots, and scoring categories
2. **Player Database** — Browse player projections and SGP-based dollar values
3. **My Targets** — Build a watchlist of players you want to draft with max bid prices
4. **Draft Room** — Run your draft with live value updates as players come off the board
""")

    st.divider()

    # Page guide
    st.subheader("Pages")

    pages = {
        "Player Database": "Browse all players with projections, values, and rankings. Filter by position, search by name, and sort by any stat.",
        "Draft Room": "The main draft interface. Draft players, track spending, and see real-time value adjustments as the player pool shrinks.",
        "My Targets": "Build a watchlist of players you're targeting. Set max bid prices and notes to stay organized during the draft.",
        "My Team": "View your drafted roster, positional coverage, and category strengths/weaknesses.",
        "All Teams": "See every team's roster and compare across the league.",
        "League Settings": "Configure league parameters: team count, budget, roster spots, scoring categories, and draft type.",
    }

    for name, desc in pages.items():
        st.markdown(f"**{name}** — {desc}")


def show_player_database(session):
    """Display the player database with projections."""
    st.header("Player Database")

    # Check if we have players
    total_players = session.query(Player).count()

    if total_players == 0:
        st.warning("No players in database. Place FGDC CSV files in the data/ folder and restart the app.")
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
            ALL_FILTER_POSITIONS,
            default=[],
            key="position_filter",
        )

    with col3:
        search = st.text_input(
            "Search Player",
            placeholder="Player name...",
            key="db_search",
        )

    # Build query
    query = session.query(Player)

    if player_type == "Hitters":
        query = query.filter(Player.player_type == "hitter")
    elif player_type == "Pitchers":
        query = query.filter(Player.player_type == "pitcher")

    if positions:
        # Filter for players matching ANY of the selected positions
        # Expand CI/MI to constituent positions for filtering
        from sqlalchemy import or_
        expanded = set()
        for pos in positions:
            expanded.update(expand_position(pos) or [pos])
        position_filters = [Player.positions.contains(p) for p in expanded]
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


@st.dialog("Draft Player")
def draft_player_dialog(player, session, settings, draft_state):
    """Dialog for confirming a player draft from the available players table."""
    is_snake = draft_state.draft_type == "snake"

    st.markdown(f"### {player.name}")
    st.caption(f"{player.positions} | {player.team or 'FA'} | {player.player_type.title()}")

    if is_snake:
        if player.sgp:
            st.metric("SGP", f"{player.sgp:.1f}")
    else:
        if player.dollar_value:
            st.metric("Value", f"${player.dollar_value:.0f}")

    # Show existing note
    if player.note:
        st.info(f"Note: {player.note}")

    # Edit note
    new_note = st.text_input(
        "Draft Note",
        value=player.note or "",
        placeholder="e.g., injury concern, sleeper, avoid...",
        key="dialog_note",
    )
    if new_note != (player.note or ""):
        if st.button("Save Note", key="dialog_save_note"):
            player.note = new_note if new_note else None
            session.commit()
            st.success("Note saved!")
            st.rerun()

    st.divider()

    if is_snake:
        on_clock_team = get_on_the_clock_team(session)
        if not on_clock_team:
            st.error("No team on the clock. Draft may be complete.")
            return

        st.info(f"Drafting for: **{on_clock_team.name}**")

        if st.button("Confirm Draft Pick", type="primary", use_container_width=True):
            try:
                draft_player(session, player.id, on_clock_team.id, settings=settings)
                st.success(f"Drafted {player.name}!")
                if "available_players_table" in st.session_state:
                    del st.session_state["available_players_table"]
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    else:
        teams = get_all_teams(session)
        user_team = get_user_team(session)

        team_options = {
            f"{t.name} (${t.remaining_budget})": t.id
            for t in teams
        }

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
            key="dialog_draft_team",
        )
        selected_team_id = team_options[selected_team_label]

        default_price = int(player.dollar_value) if player.dollar_value else 1
        price = st.number_input(
            "Price ($)",
            min_value=1,
            max_value=999,
            value=default_price,
            key="dialog_draft_price",
        )

        selected_team = session.get(Team, selected_team_id)
        if selected_team:
            max_bid_info = calculate_max_bid(session, selected_team, settings)
            st.caption(f"Max affordable bid: **${max_bid_info['max_bid']}**")

            if price > max_bid_info['max_bid']:
                st.warning(f"Over max by ${price - max_bid_info['max_bid']}!")

        if st.button("Confirm Draft", type="primary", use_container_width=True):
            try:
                draft_player(session, player.id, selected_team_id, price, settings)
                st.success(f"Drafted {player.name} for ${price}!")
                if "available_players_table" in st.session_state:
                    del st.session_state["available_players_table"]
                st.rerun()
            except ValueError as e:
                st.error(str(e))


def show_draft_room(session):
    """Draft Room page for conducting the auction or snake draft."""
    st.header("Draft Room")

    draft_state = get_draft_state(session)
    settings = get_current_settings()

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

            # Show draft type from settings
            st.caption(f"Draft Type: **{settings.draft_type.title()}**")
            if settings.draft_type == "snake":
                st.caption(f"Rounds: {settings.rounds_per_team}")

            if st.button("Start Draft", type="primary"):
                # Check if players exist
                player_count = session.query(Player).count()
                if player_count == 0:
                    st.error("Import players first before starting draft!")
                else:
                    initialize_draft(session, settings, team_name)
                    st.success("Draft initialized!")
                    st.rerun()
        else:
            # Draft is active - show draft controls
            is_snake = draft_state.draft_type == "snake"
            teams = get_all_teams(session)
            user_team = get_user_team(session)

            if is_snake:
                # Snake draft controls
                st.subheader("Snake Draft")

                # Show current pick info
                round_num, pick_in_round = get_pick_position(draft_state)
                num_teams = len(draft_state.draft_order) if draft_state.draft_order else settings.num_teams
                pick_display = format_pick_display(round_num, pick_in_round, num_teams)
                st.markdown(f"**{pick_display}**")

                # Show who's on the clock
                on_clock_team = get_on_the_clock_team(session)
                if on_clock_team:
                    if on_clock_team.is_user_team:
                        st.success(f"🎯 **YOU'RE ON THE CLOCK!**")
                    else:
                        st.info(f"On the clock: **{on_clock_team.name}**")

                st.divider()
                st.subheader("Make Pick")

                # In snake, automatically select the on-clock team
                if on_clock_team:
                    selected_team_id = on_clock_team.id
                    st.caption(f"Picking for: **{on_clock_team.name}**")
                else:
                    selected_team_id = None
                    st.warning("Draft may be complete")

                # Player search/selector - sorted by SGP for snake
                available_players = get_available_players(session)
                available_players.sort(
                    key=lambda p: p.sgp if p.sgp else 0,
                    reverse=True
                )

                if available_players and selected_team_id:
                    # Get ranks for display
                    player_ranks = get_player_ranks(session)

                    player_options = {
                        f"#{player_ranks.get(p.id, '?')} {p.name} ({p.positions})": p.id
                        for p in available_players
                    }

                    selected_player_label = st.selectbox(
                        "Player",
                        options=list(player_options.keys()),
                        key="draft_player",
                    )
                    selected_player_id = player_options[selected_player_label]
                    selected_player = session.get(Player, selected_player_id)

                    if st.button("DRAFT", type="primary", use_container_width=True):
                        try:
                            draft_player(session, selected_player_id, selected_team_id, settings=settings)
                            st.success(f"Drafted {selected_player.name}!")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                elif not available_players:
                    st.info("No available players")

                # Draft progress
                st.divider()
                st.subheader("Draft Progress")

                total_picks = settings.rounds_per_team * num_teams
                picks_made = draft_state.current_pick
                progress = picks_made / total_picks if total_picks > 0 else 0

                st.progress(progress, text=f"Pick {picks_made + 1} of {total_picks}")
                st.caption(f"Round {round_num} of {settings.rounds_per_team}")

                # Show teams and their next pick
                st.divider()
                st.subheader("Pick Order")
                for team in teams:
                    picks_away = get_team_next_pick(draft_state, team.id)
                    label = team.name
                    if team.is_user_team:
                        label += " ⭐"

                    if picks_away == 0:
                        st.markdown(f"**{label}** - 🎯 NOW")
                    elif picks_away is not None:
                        st.caption(f"{label} - {picks_away} picks away")
                    else:
                        st.caption(f"{label}")

            else:
                # Auction draft controls (existing code)
                st.subheader("Draft Player")

                # Team selector with remaining budget
                team_options = {
                    f"{t.name} (${t.remaining_budget})": t.id
                    for t in teams
                }

                # Default to user team
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

                    # Max bid calculator for selected team
                    selected_team = session.get(Team, selected_team_id)
                    if selected_team:
                        max_bid_info = calculate_max_bid(session, selected_team, settings)

                        # Show max affordable bid
                        st.caption(f"💰 Max affordable bid: **${max_bid_info['max_bid']}**")

                        # Show warning if price exceeds max bid
                        if price > max_bid_info['max_bid']:
                            st.warning(f"⚠️ Over max by ${price - max_bid_info['max_bid']}!")
                        elif price == max_bid_info['max_bid']:
                            st.info("This is your max affordable bid")

                        # Show roster needs
                        if max_bid_info['spots_needed'] > 0:
                            st.caption(
                                f"Roster: {max_bid_info['hitters_needed']}H + "
                                f"{max_bid_info['pitchers_needed']}P needed"
                            )

                    if st.button("DRAFT", type="primary", use_container_width=True):
                        try:
                            draft_player(session, selected_player_id, selected_team_id, price, settings)
                            st.success(f"Drafted {selected_player.name} for ${price}!")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                else:
                    st.info("No available players")

                # Team budgets summary with max bids
                st.divider()
                st.subheader("Team Budgets")

                for team in teams:
                    max_info = calculate_max_bid(session, team, settings)
                    roster_info = get_team_roster_needs(session, team, settings)

                    label = team.name
                    if team.is_user_team:
                        label += " ⭐"

                    with st.container():
                        st.markdown(f"**{label}**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.caption(f"${team.remaining_budget}")
                        with col2:
                            st.caption(f"Max: ${max_info['max_bid']}")
                        with col3:
                            spots = roster_info['total_needed']
                            st.caption(f"{spots} left")

            # Reset draft button (common to both types)
            st.divider()
            if st.button("Reset Draft", type="secondary"):
                reset_draft(session)
                st.success("Draft reset!")
                st.rerun()

    # Main area
    if not draft_state or not draft_state.is_active:
        st.info("Set your team name in the sidebar and click 'Start Draft' to begin.")
        return

    is_snake = draft_state.draft_type == "snake"

    # Target alerts - show bargains at the top (auction only shows price-based alerts)
    bargains = get_available_targets_below_value(session)
    if bargains and not is_snake:
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

    # Positional scarcity warnings
    scarcity = get_position_scarcity(session, settings)
    if scarcity:
        critical = {p: s for p, s in scarcity.items() if s['level'] == 'critical'}
        medium = {p: s for p, s in scarcity.items() if s['level'] == 'medium'}
        low = {p: s for p, s in scarcity.items() if s['level'] == 'low'}

        with st.container():
            if critical:
                positions_str = ", ".join(critical.keys())
                st.error(f"🚨 **SCARCITY ALERT**: Only 0-1 quality players left at: {positions_str}")
            if medium:
                positions_str = ", ".join(medium.keys())
                st.warning(f"⚠️ **Position Warning**: Only 2 quality players left at: {positions_str}")
            if low:
                positions_str = ", ".join(low.keys())
                st.info(f"📊 **Getting Thin**: Only 3 quality players left at: {positions_str}")

            # Expandable detail showing top available at scarce positions
            with st.expander("View Scarce Position Details", expanded=False):
                for pos, info in scarcity.items():
                    st.markdown(f"**{pos}** ({info['count']} quality remaining)")
                    for player in info['top_available']:
                        if is_snake:
                            st.caption(f"  • {player.name} (SGP: {player.sgp:.1f})")
                        else:
                            st.caption(f"  • {player.name} - ${player.dollar_value:.0f}")
        st.divider()

    # Max Bid Calculator and Recalculate button row (auction only)
    if not is_snake:
        col1, col2 = st.columns([3, 1])

        with col1:
            # Expandable max bid calculator
            with st.expander("💰 Max Bid Calculator", expanded=False):
                user_team = get_user_team(session)
                if user_team:
                    max_info = calculate_max_bid(session, user_team, settings)
                    roster_info = get_team_roster_needs(session, user_team, settings)

                    # Summary metrics
                    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
                    mcol1.metric("Max Bid", f"${max_info['max_bid']}")
                    mcol2.metric("Budget Left", f"${max_info['remaining_budget']}")
                    mcol3.metric("Spots Needed", max_info['spots_needed'])
                    mcol4.metric("Reserved", f"${max_info['reserved_for_roster']}")

                    st.caption(
                        f"Roster needs: {max_info['hitters_needed']} hitters, "
                        f"{max_info['pitchers_needed']} pitchers"
                    )

                    st.divider()

                    # Bid impact calculator
                    st.markdown("**What-If Calculator**")
                    test_bid = st.number_input(
                        "Test bid amount",
                        min_value=1,
                        max_value=max_info['remaining_budget'],
                        value=min(max_info['max_bid'], max_info['remaining_budget']),
                        key="test_bid_amount",
                    )

                    impact = calculate_bid_impact(session, user_team, test_bid, settings)

                    if impact['is_affordable']:
                        st.success(f"✅ ${test_bid} is affordable")
                    else:
                        st.error(f"❌ ${test_bid} exceeds max by ${impact['over_max_by']}")

                    icol1, icol2, icol3 = st.columns(3)
                    icol1.metric("Budget After", f"${impact['remaining_after']}")
                    icol2.metric("Spots After", impact['spots_after'])
                    icol3.metric("Avg/Player After", f"${impact['avg_per_player_after']}")

                    if impact['spots_after'] > 0:
                        st.caption(f"Max bid for next player: ${impact['max_bid_after']}")

        with col2:
            if st.button("Recalculate Values", type="secondary"):
                try:
                    count = calculate_remaining_player_values(session, settings)
                    st.success(f"Recalculated values for {count} available players!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    else:
        # Snake draft - just show recalculate button
        if st.button("Recalculate Rankings", type="secondary"):
            try:
                count = calculate_remaining_player_values(session, settings)
                st.success(f"Recalculated rankings for {count} available players!")
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
            ALL_FILTER_POSITIONS,
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
        # Expand CI/MI to constituent positions for filtering
        from sqlalchemy import or_
        expanded = set()
        for pos in positions:
            expanded.update(expand_position(pos) or [pos])
        position_filters = [Player.positions.contains(p) for p in expanded]
        query = query.filter(or_(*position_filters))

    if search:
        query = query.filter(Player.name.ilike(f"%{search}%"))

    # Sort by dollar value descending
    query = query.order_by(Player.dollar_value.desc())

    available = query.limit(100).all()

    # Get target info for highlighting
    target_ids = get_target_player_ids(session)
    target_info = {t.player_id: t for t in get_targets(session, include_drafted=False)}

    # Get player ranks for snake draft
    if is_snake:
        player_ranks = get_player_ranks(session)

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
                if is_snake:
                    target_display = "⭐"  # Just show star for snake drafts
                elif value <= target.max_bid:
                    target_display = f"🎯 ${target.max_bid}"  # Bargain - at/below max
                else:
                    target_display = f"⭐ ${target.max_bid}"  # Target but above max
            else:
                target_display = ""

            # Build note display
            note_display = ""
            if p.note:
                note_display = p.note if len(p.note) <= 30 else p.note[:30] + "..."

            row = {
                "_player_id": p.id,
                "Target": target_display,
                "Name": p.name,
                "Team": p.team or "",
                "Type": p.player_type.title() if p.player_type else "",
                "Pos": p.positions or "",
                "Note": note_display,
            }

            # Show Rank for snake, Value for auction
            if is_snake:
                rank = player_ranks.get(p.id, "-")
                row["Rank"] = rank
                row["SGP"] = f"{p.sgp:.1f}" if p.sgp else "-"
            else:
                row["Value"] = f"${p.dollar_value:.0f}" if p.dollar_value else "-"

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

        # For snake drafts, sort by rank
        if is_snake:
            query = query.order_by(Player.sgp.desc())

        df = pd.DataFrame(rows)

        # Build column config: hide _player_id, format SGP columns
        column_config = {"_player_id": None}
        sgp_cols = []
        if show_category_sgp and player_type != "All":
            if player_type == "Hitters":
                sgp_cols = [f"{cat.upper()} SGP" for cat in ["r", "hr", "rbi", "sb", "avg"]]
            elif player_type == "Pitchers":
                sgp_cols = [f"{cat.upper()} SGP" for cat in ["w", "sv", "k", "era", "whip"]]
            sgp_cols = [c for c in sgp_cols if c in df.columns]
            for col in sgp_cols:
                column_config[col] = st.column_config.NumberColumn(col, format="%.2f")

        selection = st.dataframe(
            df,
            width='stretch',
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            key="available_players_table",
            column_config=column_config,
        )

        # Open draft dialog when a row is selected
        if selection and selection.selection and selection.selection.rows:
            selected_row_idx = selection.selection.rows[0]
            selected_player_id = int(df.iloc[selected_row_idx]["_player_id"])
            selected_player = session.get(Player, selected_player_id)
            if selected_player and not selected_player.is_drafted:
                draft_player_dialog(selected_player, session, settings, draft_state)

        # Legend
        st.caption("Click a row to draft that player")
        if is_snake:
            st.caption(f"Showing top {len(available)} available players by rank")
        else:
            st.caption(f"Showing top {len(available)} available players by value")
        if target_ids:
            if is_snake:
                st.caption("⭐ = Target player")
            else:
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

    # Player Notes management
    st.divider()
    with st.expander("Player Notes"):
        note_search = st.text_input(
            "Search player to add/edit note",
            placeholder="Player name...",
            key="note_search",
        )

        if note_search:
            note_matches = (
                session.query(Player)
                .filter(Player.name.ilike(f"%{note_search}%"))
                .limit(10)
                .all()
            )
            if note_matches:
                for np in note_matches:
                    col_name, col_note, col_save = st.columns([2, 3, 1])
                    with col_name:
                        drafted_marker = " (drafted)" if np.is_drafted else ""
                        st.text(f"{np.name}{drafted_marker}")
                    with col_note:
                        updated_note = st.text_input(
                            "Note",
                            value=np.note or "",
                            placeholder="Add a note...",
                            key=f"note_edit_{np.id}",
                            label_visibility="collapsed",
                        )
                    with col_save:
                        if st.button("Save", key=f"note_save_{np.id}"):
                            np.note = updated_note if updated_note else None
                            session.commit()
                            st.rerun()
            else:
                st.caption("No players found.")

        # Show all players with notes
        noted_players = (
            session.query(Player)
            .filter(Player.note.isnot(None), Player.note != "")
            .order_by(Player.name)
            .all()
        )
        if noted_players:
            st.markdown(f"**All Notes** ({len(noted_players)})")
            for np in noted_players:
                col_name, col_note, col_clear = st.columns([2, 3, 1])
                with col_name:
                    drafted_marker = " (drafted)" if np.is_drafted else ""
                    st.text(f"{np.name}{drafted_marker}")
                with col_note:
                    st.caption(np.note)
                with col_clear:
                    if st.button("Clear", key=f"note_clear_{np.id}"):
                        np.note = None
                        session.commit()
                        st.rerun()

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
                if is_snake:
                    st.text(f"{pick['team_name']}")
                else:
                    st.text(f"{pick['team_name']} - ${pick['price']}")

            with col4:
                if st.button("Undo", key=f"undo_{pick['pick_id']}"):
                    player = undo_pick(session, pick['pick_id'], settings)
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

            if is_snake:
                history_rows.append({
                    "Pick #": pick['pick_number'],
                    "Player": pick['player_name'],
                    "Team": pick['team_name'],
                    "Pos": player.positions if player else "",
                    "SGP": round(player.sgp, 1) if player and player.sgp else 0,
                })
            else:
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


def style_sgp(val):
    """Apply color gradient based on SGP value."""
    if pd.isna(val):
        return ''
    if val >= 2.0:
        return 'background-color: #2E7D32; color: white; font-weight: bold'
    elif val >= 1.0:
        return 'background-color: #66BB6A; color: #1B5E20; font-weight: bold'
    elif val >= 0.5:
        return 'background-color: #A5D6A7; color: #1B5E20'
    elif val >= -0.5:
        return ''  # Neutral
    elif val >= -1.0:
        return 'background-color: #FFCDD2; color: #B71C1C'
    elif val >= -2.0:
        return 'background-color: #EF9A9A; color: #B71C1C; font-weight: bold'
    else:
        return 'background-color: #E57373; color: white; font-weight: bold'


def create_category_bar_chart(analysis: dict) -> alt.Chart:
    """
    Create Altair horizontal bar chart with color-coded strength.

    Colors:
        - Green (#90EE90): Projected 1-4 (strong)
        - Yellow (#FFFFE0): Projected 5-8 (average)
        - Red (#FFB6C1): Projected 9-12 (weak)

    Args:
        analysis: Result from analyze_team_category_balance()

    Returns:
        Altair chart object
    """
    standings = analysis["standings"]
    sgp_totals = analysis["sgp_totals"]
    num_teams = analysis["num_teams"]
    hitting_cats = analysis["hitting_cats"]
    pitching_cats = analysis["pitching_cats"]

    # Build data for chart
    data = []
    for cat in hitting_cats + pitching_cats:
        position = standings.get(cat, num_teams // 2)
        sgp = sgp_totals.get(cat, 0)

        # Determine color based on position
        if position <= 4:
            color = "Strong"
        elif position <= 8:
            color = "Average"
        else:
            color = "Weak"

        # Determine category type
        cat_type = "Hitting" if cat in hitting_cats else "Pitching"

        data.append({
            "Category": cat.upper(),
            "Position": position,
            "SGP": round(sgp, 1),
            "Strength": color,
            "Type": cat_type,
            # For bar length, use inverse of position (so better = longer bar)
            "Bar": num_teams - position + 1,
        })

    df = pd.DataFrame(data)

    # Define color scale
    color_scale = alt.Scale(
        domain=["Strong", "Average", "Weak"],
        range=["#90EE90", "#FFFFE0", "#FFB6C1"]
    )

    # Create chart
    chart = alt.Chart(df).mark_bar().encode(
        y=alt.Y("Category:N", sort=None, title=None),
        x=alt.X("Bar:Q", scale=alt.Scale(domain=[0, num_teams]), title="Projected Standing"),
        color=alt.Color("Strength:N", scale=color_scale, legend=alt.Legend(title="Strength")),
        tooltip=[
            alt.Tooltip("Category:N", title="Category"),
            alt.Tooltip("Position:Q", title="Projected Rank"),
            alt.Tooltip("SGP:Q", title="Total SGP"),
            alt.Tooltip("Strength:N", title="Strength"),
        ]
    ).properties(
        height=250
    )

    # Add text labels
    text = alt.Chart(df).mark_text(
        align="left",
        baseline="middle",
        dx=5,
        fontSize=11,
    ).encode(
        y=alt.Y("Category:N", sort=None),
        x=alt.X("Bar:Q"),
        text=alt.Text("Position:Q", format=".0f"),
    )

    return chart + text


def render_category_balance_dashboard(analysis: dict, settings) -> None:
    """
    Render the complete Category Balance Dashboard.

    Args:
        analysis: Result from analyze_team_category_balance()
        settings: League settings
    """
    standings = analysis["standings"]
    sgp_totals = analysis["sgp_totals"]
    raw_stats = analysis["raw_stats"]
    recommendations = analysis["recommendations"]
    hitting_cats = analysis["hitting_cats"]
    pitching_cats = analysis["pitching_cats"]
    num_teams = analysis["num_teams"]

    # Create two columns for hitting and pitching
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Hitting Categories**")

        # Build hitting data
        hitting_data = []
        for cat in hitting_cats:
            pos = standings.get(cat, num_teams // 2)
            sgp = sgp_totals.get(cat, 0)
            raw = raw_stats.get(cat, 0)

            # Format raw stat
            if cat == "avg":
                raw_display = f"{raw:.3f}" if raw > 0 else ".000"
            else:
                raw_display = f"{int(raw)}"

            # Determine indicator
            if pos <= 4:
                indicator = ""
            elif pos <= 8:
                indicator = ""
            else:
                indicator = " !!"

            hitting_data.append({
                "Cat": cat.upper(),
                "Rank": f"{pos}th",
                "SGP": f"{sgp:+.1f}",
                "Projected": raw_display,
                "Status": indicator,
            })

        hitting_df = pd.DataFrame(hitting_data)
        st.dataframe(hitting_df, hide_index=True, use_container_width=True)

    with col2:
        st.markdown("**Pitching Categories**")

        # Build pitching data
        pitching_data = []
        for cat in pitching_cats:
            pos = standings.get(cat, num_teams // 2)
            sgp = sgp_totals.get(cat, 0)
            raw = raw_stats.get(cat, 0)

            # Format raw stat
            if cat in ["era", "whip"]:
                raw_display = f"{raw:.2f}" if raw > 0 else "0.00"
            else:
                raw_display = f"{int(raw)}"

            # Determine indicator
            if pos <= 4:
                indicator = ""
            elif pos <= 8:
                indicator = ""
            else:
                indicator = " !!"

            pitching_data.append({
                "Cat": cat.upper(),
                "Rank": f"{pos}th",
                "SGP": f"{sgp:+.1f}",
                "Projected": raw_display,
                "Status": indicator,
            })

        pitching_df = pd.DataFrame(pitching_data)
        st.dataframe(pitching_df, hide_index=True, use_container_width=True)

    # Visual chart
    st.markdown("**Projected Standings by Category**")
    chart = create_category_bar_chart(analysis)
    st.altair_chart(chart, use_container_width=True)

    # Recommendations
    if recommendations:
        st.markdown("**Recommendations**")
        for rec in recommendations:
            if rec["priority"] == "high":
                st.warning(f"! {rec['message']}")
            else:
                st.info(f"Consider: {rec['message']}")


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

        styled_df = df.style.map(style_surplus, subset=[c for c in surplus_cols if c in df.columns])

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

        # Category Balance Dashboard
        st.divider()
        with st.expander("Category Balance Dashboard", expanded=True):
            if len(picks) >= 1:
                settings = get_current_settings()
                analysis = analyze_team_category_balance(picks, settings)

                # Show early projection disclaimer for small rosters
                if len(picks) <= 2:
                    st.info("(Early projection - based on limited roster data)")

                render_category_balance_dashboard(analysis, settings)
            else:
                st.info("Draft players to see category balance analysis")

        # Team Needs Analysis
        st.divider()
        with st.expander("Team Needs Analysis", expanded=True):
            settings = get_current_settings()
            render_team_needs_analysis(session, user_team, settings)


def render_positional_roster_grid(positional_states: list) -> None:
    """
    Render the positional roster grid showing filled/needed positions.

    Color coding:
        - Green: Position fully filled
        - Yellow: Position partially filled
        - Red: Position empty
    """
    # Separate hitters and pitchers
    hitter_positions = ["C", "1B", "2B", "3B", "SS", "OF", "CI", "MI", "UTIL"]
    pitcher_positions = ["SP", "RP", "P"]

    hitter_states = [s for s in positional_states if s.position in hitter_positions]
    pitcher_states = [s for s in positional_states if s.position in pitcher_positions]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Hitter Positions**")
        if hitter_states:
            for state in hitter_states:
                if state.required == 0:
                    continue

                # Determine color based on fill status
                if state.remaining == 0:
                    color = "#90EE90"  # Green - filled
                    icon = ""
                elif state.filled > 0:
                    color = "#FFFFE0"  # Yellow - partial
                    icon = ""
                else:
                    color = "#FFB6C1"  # Red - empty
                    icon = ""

                # Build display
                players_str = ", ".join(state.players) if state.players else "Empty"
                st.markdown(
                    f'<div style="background-color: {color}; padding: 8px; margin: 4px 0; border-radius: 4px;">'
                    f'<strong>{state.position}</strong>: {state.filled}/{state.required} '
                    f'<span style="color: #666;">({players_str})</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No hitter positions configured")

    with col2:
        st.markdown("**Pitcher Positions**")
        if pitcher_states:
            for state in pitcher_states:
                if state.required == 0:
                    continue

                # Determine color based on fill status
                if state.remaining == 0:
                    color = "#90EE90"  # Green - filled
                elif state.filled > 0:
                    color = "#FFFFE0"  # Yellow - partial
                else:
                    color = "#FFB6C1"  # Red - empty

                # Build display
                players_str = ", ".join(state.players) if state.players else "Empty"
                st.markdown(
                    f'<div style="background-color: {color}; padding: 8px; margin: 4px 0; border-radius: 4px;">'
                    f'<strong>{state.position}</strong>: {state.filled}/{state.required} '
                    f'<span style="color: #666;">({players_str})</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No pitcher positions configured")


def render_recommendations_table(recommendations: list, session) -> None:
    """Render the smart recommendations table."""
    if not recommendations:
        st.info("No recommendations available. All positions may be filled.")
        return

    rows = []
    for rec in recommendations:
        player = rec.player
        rows.append({
            "Player": player.name,
            "Pos": player.positions or "",
            "Value": f"${player.dollar_value:.0f}" if player.dollar_value else "-",
            "Fills": ", ".join(rec.fills_positions),
            "Helps": ", ".join(rec.helps_categories) if rec.helps_categories else "-",
            "Score": f"{rec.composite_score:.2f}",
        })

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        width='stretch',
        hide_index=True,
    )

    st.caption("Score combines position urgency (35%), category fit (35%), and player value (30%)")


def render_comparative_standings(comparative_standings: dict, user_team_name: str, settings) -> None:
    """
    Render comparative standings heatmap across all teams.

    Color scale:
        - Green (1-4): Strong
        - Yellow (5-8): Average
        - Red (9-12): Weak
    """
    if not comparative_standings:
        st.info("No teams to compare yet.")
        return

    hitting_cats = [c.lower() for c in settings.hitting_categories]
    pitching_cats = [c.lower() for c in settings.pitching_categories]
    all_cats = hitting_cats + pitching_cats

    # Build dataframe
    rows = []
    for team_name, standings in comparative_standings.items():
        row = {"Team": team_name}
        for cat in all_cats:
            row[cat.upper()] = standings.get(cat, "-")
        rows.append(row)

    df = pd.DataFrame(rows)

    # Style function for standings
    def style_standing(val):
        if pd.isna(val) or val == "-":
            return ''
        try:
            pos = int(val)
            if pos <= 4:
                return 'background-color: #90EE90'  # Green
            elif pos <= 8:
                return 'background-color: #FFFFE0'  # Yellow
            else:
                return 'background-color: #FFB6C1'  # Red
        except (ValueError, TypeError):
            return ''

    # Highlight user's team row
    def highlight_user_team(row):
        if user_team_name in str(row.get("Team", "")):
            return ['font-weight: bold; border: 2px solid #1E88E5'] * len(row)
        return [''] * len(row)

    cat_cols = [c.upper() for c in all_cats]
    styled_df = df.style.map(style_standing, subset=[c for c in cat_cols if c in df.columns])
    styled_df = styled_df.apply(highlight_user_team, axis=1)

    st.dataframe(
        styled_df,
        width='stretch',
        hide_index=True,
    )

    st.caption("Rankings: 1 = best, higher = worse. Your team is highlighted.")


def render_team_needs_analysis(session, team, settings) -> None:
    """Render the complete Team Needs Analysis section."""
    # Perform analysis
    needs_analysis = analyze_team_needs(session, team, settings)

    # Positional Roster Grid
    st.markdown("### Positional Roster Status")
    render_positional_roster_grid(needs_analysis.positional_states)

    st.divider()

    # Smart Recommendations
    st.markdown("### Smart Recommendations")
    st.caption("Players that best address your positional needs and weak categories")
    render_recommendations_table(needs_analysis.recommendations, session)

    st.divider()

    # Comparative Standings
    st.markdown("### League Standings Comparison")
    st.caption("Projected standings by category across all teams")
    render_comparative_standings(
        needs_analysis.comparative_standings,
        team.name,
        settings,
    )


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
            styled_comparison = comparison_df.style.map(
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

                styled_df = df.style.map(style_surplus, subset=[c for c in surplus_cols if c in df.columns])
                st.dataframe(
                    styled_df,
                    width='stretch',
                    hide_index=True,
                )

                # Team totals
                total_value = df['Value'].sum()
                total_surplus = df['Surplus'].sum()
                st.caption(f"Total Value: ${total_value:.0f} | Total Surplus: ${total_surplus:+.0f}")


def show_settings_page(session):
    """Page for configuring league settings."""
    st.header("League Settings")

    # Get current settings from session state
    settings = get_current_settings()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Draft Format")

        # Draft type selector
        draft_type_options = ["auction", "snake"]
        current_draft_type = st.session_state.league_settings.get("draft_type", "auction")
        draft_type_index = draft_type_options.index(current_draft_type) if current_draft_type in draft_type_options else 0

        draft_type = st.radio(
            "Draft Type",
            options=draft_type_options,
            index=draft_type_index,
            format_func=lambda x: x.title(),
            key="settings_draft_type",
            horizontal=True,
        )
        st.session_state.league_settings["draft_type"] = draft_type

        st.divider()

        st.subheader("League Structure")
        num_teams = st.number_input(
            "Number of Teams",
            min_value=4,
            max_value=20,
            value=st.session_state.league_settings["num_teams"],
            key="settings_num_teams",
        )
        st.session_state.league_settings["num_teams"] = num_teams

        # Conditionally show auction or snake settings
        if draft_type == "auction":
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
            st.session_state.league_settings["budget_per_team"] = budget
            st.session_state.league_settings["min_bid"] = min_bid
        else:
            # Snake draft settings
            rounds = st.number_input(
                "Rounds per Team",
                min_value=10,
                max_value=30,
                value=st.session_state.league_settings.get("rounds_per_team", 23),
                key="settings_rounds",
                help="Total roster size - each team picks this many players",
            )
            st.session_state.league_settings["rounds_per_team"] = rounds

            st.info("In snake drafts, teams pick in serpentine order (1→12, 12→1, etc.) with no bidding.")

    with col2:
        st.subheader("Scoring Categories")
        st.markdown("**Hitting**")
        st.text("R, HR, RBI, SB, AVG")

        opt_hitting = st.session_state.league_settings.get("optional_hitting_cats", [])
        obp_on = st.checkbox("OBP", value="OBP" in opt_hitting, key="cat_obp")
        slg_on = st.checkbox("SLG", value="SLG" in opt_hitting, key="cat_slg")
        new_opt_hitting = []
        if obp_on:
            new_opt_hitting.append("OBP")
        if slg_on:
            new_opt_hitting.append("SLG")
        st.session_state.league_settings["optional_hitting_cats"] = new_opt_hitting

        st.markdown("**Pitching**")
        st.text("W, SV, K, ERA, WHIP")

        opt_pitching = st.session_state.league_settings.get("optional_pitching_cats", [])
        k9_on = st.checkbox("K/9", value="K9" in opt_pitching, key="cat_k9")
        hld_on = st.checkbox("HLD", value="HLD" in opt_pitching, key="cat_hld")
        new_opt_pitching = []
        if k9_on:
            new_opt_pitching.append("K9")
        if hld_on:
            new_opt_pitching.append("HLD")
        st.session_state.league_settings["optional_pitching_cats"] = new_opt_pitching

        all_hitting = ["R", "HR", "RBI", "SB", "AVG"] + new_opt_hitting
        all_pitching = ["W", "SV", "K", "ERA", "WHIP"] + new_opt_pitching
        st.caption(f"Active: {len(all_hitting)}x{len(all_pitching)}")

        st.divider()

        st.subheader("Value Calculation")
        use_pos_adj = st.checkbox(
            "Use Positional Adjustments",
            value=st.session_state.league_settings.get("use_positional_adjustments", True),
            key="settings_positional_adj",
            help="Adjust player values based on positional scarcity (FanGraphs-style replacement level methodology)",
        )
        st.session_state.league_settings["use_positional_adjustments"] = use_pos_adj

        if use_pos_adj:
            st.caption("Players at scarce positions (C, SS, 2B) will be valued higher relative to deep positions (OF, 1B)")

    st.divider()

    st.subheader("Roster Spots")

    # Hitter positions
    st.markdown("**Hitters**")
    hitter_cols = st.columns(4)

    for i, pos in enumerate(HITTER_ROSTER_POSITIONS):
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
            "use_positional_adjustments": DEFAULT_SETTINGS.use_positional_adjustments,
            "draft_type": DEFAULT_SETTINGS.draft_type,
            "rounds_per_team": DEFAULT_SETTINGS.rounds_per_team,
            "optional_hitting_cats": [],
            "optional_pitching_cats": [],
        }
        st.rerun()

    st.divider()

    # Summary - recalculate from current session state
    current_settings = get_current_settings()
    st.subheader("League Summary")
    st.write(f"**Draft Type:** {current_settings.draft_type.title()}")
    if current_settings.draft_type == "auction":
        total_budget = current_settings.num_teams * current_settings.budget_per_team
        st.write(f"**Total League Budget:** ${total_budget:,}")
    else:
        total_picks = current_settings.num_teams * current_settings.rounds_per_team
        st.write(f"**Total Picks:** {total_picks} ({current_settings.rounds_per_team} rounds × {current_settings.num_teams} teams)")
    st.write(f"**Hitters Drafted:** {current_settings.total_hitters_drafted}")
    st.write(f"**Pitchers Drafted:** {current_settings.total_pitchers_drafted}")

    # Positional demand breakdown (when positional adjustments enabled)
    if current_settings.use_positional_adjustments:
        st.divider()
        st.subheader("Positional Demand")
        st.caption("Number of players at each position that will be drafted league-wide (affects replacement level)")

        positional_demand = current_settings.get_positional_demand()

        # Split into hitter and pitcher positions
        hitter_demand = {pos: positional_demand.get(pos, 0) for pos in ["C", "1B", "2B", "3B", "SS", "OF"]}
        pitcher_demand = {pos: positional_demand.get(pos, 0) for pos in ["SP", "RP"]}

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Hitters**")
            for pos, count in hitter_demand.items():
                if count > 0:
                    st.write(f"{pos}: {count} players")

        with col2:
            st.markdown("**Pitchers**")
            for pos, count in pitcher_demand.items():
                if count > 0:
                    st.write(f"{pos}: {count} players")

        st.caption("Higher demand = lower replacement level = less positional value boost")

    # Data Management section
    st.divider()
    st.subheader("Data Management")

    total_players = session.query(Player).count()
    if total_players > 0:
        players_with_values = session.query(Player).filter(Player.dollar_value.isnot(None)).count()
        st.info(f"{total_players} players loaded ({players_with_values} with calculated values)")

        if st.button("Recalculate Values", type="primary"):
            try:
                count = calculate_all_player_values(session, get_current_settings())
                st.success(f"Calculated values for {count} players!")
                st.rerun()
            except Exception as e:
                st.error(f"Error calculating values: {e}")

        if st.button("Clear All Players", type="secondary"):
            clear_all_players(session)
            st.success("All players cleared!")
            st.rerun()
    else:
        st.warning("No players loaded. Place FGDC CSV files in the data/ folder and restart the app.")


if __name__ == "__main__":
    main()
