from ..utils import *


def clear_custom_data(did):
    if not askUser(
        """Clear custom data in all cards?
    The custom scheduling of FSRS4Anki stored memory state in custom data.
    It is unused when you enable the built-in FSRS.
    Are you sure?"""
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
    mw.col.merge_undo_entries(undo_entry)
    tooltip(f"""{cnt} cards cleared in {time.time() - start_time:.2f} seconds.""")
    mw.reset()
