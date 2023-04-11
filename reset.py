import json
from .utils import *


def reset(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    if deck_parameters is None:
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []

    mw.checkpoint("Resetting")
    mw.progress.start()

    cnt = 0
    reseted_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            reseted_cards = reseted_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\" {DONT_RESCHEDULE}"):
            if cid not in reseted_cards:
                reseted_cards.add(cid)
            else:
                continue
            card = mw.col.get_card(cid)
            if card.custom_data == '':
                continue
            revlogs = mw.col.card_stats_data(cid).revlog
            reset_ivl_and_due(cid, revlogs)
            card = mw.col.get_card(cid)
            card.custom_data = json.dumps({})
            card.flush()
            cnt += 1

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_(f"""{cnt} card reseted."""))
