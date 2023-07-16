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
    
    if not askUser("""Undo all changes made by rescheduling. 
    It will set the interval and due of all cards to the original value set when ratings (not the previous rescheduling).
    Are you sure?"""):
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if geq_version(version, (3, 12, 0)) else []

    undo_entry = mw.col.add_custom_undo_entry("Reset")
    mw.progress.start()

    cnt = 0
    reseted_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            reseted_cards = reseted_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\"".replace('\\', '\\\\')))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\" -\"is:learn\" -\"is:suspended\"".replace('\\', '\\\\')):
            if cid not in reseted_cards:
                reseted_cards.add(cid)
            else:
                continue
            card = mw.col.get_card(cid)
            if card.custom_data == '':
                continue
            revlogs = filter_revlogs(mw.col.card_stats_data(cid).revlog)
            if len(revlogs) == 0:
                continue
            reset_ivl_and_due(cid, revlogs)
            card = mw.col.get_card(cid)
            card.custom_data = json.dumps({})
            mw.col.update_card(card)
            mw.col.merge_undo_entries(undo_entry)
            cnt += 1

    tooltip(f"""{cnt} cards reseted.""")
    mw.progress.finish()
    mw.col.reset()
    mw.reset()
