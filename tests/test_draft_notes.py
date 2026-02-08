"""Tests for draft notes functionality."""

from src.database import Player


class TestAddNote:
    def test_add_note_to_player(self, session, sample_hitter):
        sample_hitter.note = "Injury concern - back issues"
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.note == "Injury concern - back issues"

    def test_add_note_to_pitcher(self, session, sample_pitcher):
        sample_pitcher.note = "Sleeper pick"
        session.commit()

        player = session.get(Player, sample_pitcher.id)
        assert player.note == "Sleeper pick"

    def test_note_defaults_to_none(self, session, sample_hitter):
        assert sample_hitter.note is None


class TestUpdateNote:
    def test_update_existing_note(self, session, sample_hitter):
        sample_hitter.note = "Sleeper"
        session.commit()

        sample_hitter.note = "Avoid - overpriced"
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.note == "Avoid - overpriced"

    def test_clear_note_with_none(self, session, sample_hitter):
        sample_hitter.note = "Some note"
        session.commit()

        sample_hitter.note = None
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.note is None

    def test_clear_note_with_empty_string(self, session, sample_hitter):
        sample_hitter.note = "Some note"
        session.commit()

        sample_hitter.note = ""
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.note == ""


class TestNotesWithDraft:
    def test_note_persists_after_draft(self, session, sample_hitter, sample_team):
        from src.database import DraftPick

        sample_hitter.note = "Great value"
        session.commit()

        # Simulate drafting the player
        pick = DraftPick(team_id=sample_team.id, price=30, pick_number=1)
        session.add(pick)
        session.flush()
        sample_hitter.is_drafted = True
        sample_hitter.draft_pick_id = pick.id
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.is_drafted is True
        assert player.note == "Great value"

    def test_note_independent_of_draft_status(self, session, sample_hitter):
        sample_hitter.note = "Watch closely"
        assert sample_hitter.is_drafted is False
        session.commit()

        player = session.get(Player, sample_hitter.id)
        assert player.note == "Watch closely"
        assert player.is_drafted is False


class TestQueryPlayersWithNotes:
    def test_filter_players_with_notes(self, session, sample_hitter, sample_pitcher):
        sample_hitter.note = "Sleeper"
        session.commit()

        noted = (
            session.query(Player)
            .filter(Player.note.isnot(None), Player.note != "")
            .all()
        )
        assert len(noted) == 1
        assert noted[0].id == sample_hitter.id

    def test_no_players_with_notes(self, session, sample_hitter, sample_pitcher):
        noted = (
            session.query(Player)
            .filter(Player.note.isnot(None), Player.note != "")
            .all()
        )
        assert len(noted) == 0

    def test_multiple_players_with_notes(self, session, sample_hitter, sample_pitcher):
        sample_hitter.note = "Injury risk"
        sample_pitcher.note = "Bust candidate"
        session.commit()

        noted = (
            session.query(Player)
            .filter(Player.note.isnot(None), Player.note != "")
            .all()
        )
        assert len(noted) == 2
