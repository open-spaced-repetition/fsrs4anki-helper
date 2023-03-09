import json
import math
from datetime import datetime
from aqt import mw
from .utils import *


def get_target_retention_with_response():
    inquire_text = "Advance undue cards whose retention is lower than your input retention (1, 99).\n"
    info_text = "Only affect cards scheduled by FSRS4Anki Scheduler or rescheduled by FSRS4Anki Helper.\n"
    ivl_text = "The new intervals are scheduled corresponding to your input retention.\n"
    (s, r) = getText(inquire_text + info_text + ivl_text)
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def advance(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    (target_retention, resp) = get_target_retention_with_response()
    if target_retention is None:
        if resp:
            showWarning("Please enter an integral number of retention percentage.")
        return
    else:
        if target_retention >= 100 or target_retention <= 0:
            showWarning("Please enter an integral number in range (1, 99).")
            return
        target_retention = target_retention / 100

    deck_parameters = get_deck_parameters(custom_scheduler)
    if deck_parameters is None:
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    global_deck_name = get_global_config_deck_name(version)

    mw.checkpoint("Advancing")
    mw.progress.start()

    cnt = 0
    advanced_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            advanced_cards = advanced_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        max_ivl = deck_parameters[global_deck_name]['m']
        for key, value in deck_parameters.items():
            if deck['name'].startswith(key):
                max_ivl = value['m']
                break
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" -\"is:due\" \"is:review\" {DONT_RESCHEDULE}"):
            if cid not in advanced_cards:
                advanced_cards.add(cid)
            else:
                continue
            card = mw.col.get_card(cid)
            if card.custom_data == '':
                continue
            custom_data = json.loads(card.custom_data)
            if 's' not in custom_data:
                continue
            s = custom_data['s']

            revlog = mw.col.card_stats_data(cid).revlog[0]

            ivl = datetime.today().toordinal() - datetime.fromtimestamp(revlog.time).toordinal()
            r = math.pow(0.9, ivl / s)
            if r < target_retention:
                new_ivl = min(max(int(round(math.log(target_retention) / math.log(0.9) * s)), 1), max_ivl)
                offset = new_ivl - card.ivl
                card.ivl = new_ivl
                if card.odid:  # Also update cards in filtered decks
                    card.odue += offset
                else:
                    card.due += offset
                card.flush()
                cnt += 1

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_(f"""{cnt} card advanced"""))
