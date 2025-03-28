from ..utils import *
from ..i18n import t
from anki.utils import ids2str


def clear_custom_data(did):
    if not askUser(
        t("clear-custom-data-confirmation")
    ):
        return

    cards = mw.col.db.list(
        """
            SELECT id
            FROM cards
            WHERE data != '' 
            AND json_extract(data, '$.cd') IS NOT NULL
        """
    )

    cnt = 0
    reset_cards = []
    start_time = time.time()
    undo_entry = mw.col.add_custom_undo_entry("Clear custom data")
    for cid in cards:
        card = mw.col.get_card(cid)
        card.custom_data = ""
        reset_cards.append(card)
        cnt += 1

    mw.col.update_cards(reset_cards)
    #mw.col.merge_undo_entries(undo_entry) # Removed this line
    tooltip(t("clear-custom-data-result", count=cnt, seconds=f"{time.time() - start_time:.2f}"))
    mw.reset()


def clear_manual_rescheduling(did):
    if not askUser(
        t("clear-manual-rescheduling-confirmation")
    ):
        return

    if not ask_one_way_sync():
        return

    revlog_ids = mw.col.db.list(
        """
        SELECT cur.id
        FROM revlog as cur
        WHERE cur.type >= 4
        AND cur.factor <> 0
        AND (
        SELECT type
        FROM revlog
        WHERE id = (
                SELECT min(id)
                FROM revlog
                WHERE id > cur.id
                AND cid == cur.cid
            )
        ) >= 4
    """
    )
    cnt = len(revlog_ids)
    mw.col.db.execute(f"DELETE FROM revlog WHERE id IN {ids2str(revlog_ids)}")
    col_set_modified()
    tooltip(t("clear-manual-rescheduling-result", count=cnt)) # TODO Deduplicate this
    mw.reset()
