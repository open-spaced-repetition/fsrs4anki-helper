import re
import json
import math
from datetime import datetime
from collections import OrderedDict
from aqt import mw
from aqt.utils import getText, showWarning, tooltip


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None


def get_target_retention_with_response():
    inquire_text = "Postpone due cards whose retention is higher than your input retention (suggest 70~95).\n"
    info_text = "Only affect cards scheduled by FSRS4Anki Scheduler or rescheduled by FSRS4Anki Helper."
    (s, r) = getText(inquire_text + info_text)
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def postpone(did):
    # postpone card whose retention is higher than target_retention
    if 'cardStateCustomizer' not in mw.col.all_config():
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return
    custom_scheduler = mw.col.all_config()['cardStateCustomizer']
    if "FSRS4Anki" not in custom_scheduler:
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return
    version = list(map(int, re.findall(f'v(\d).(\d).(\d)', custom_scheduler)[0]))
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

    max_ivl_list = re.findall(r'maximumInterval ?= ?(.*);', custom_scheduler)
    deck_names = re.findall(r'deck_name(?: ?== ?|.startsWith\()+"(.*)"', custom_scheduler)
    deck_names.insert(0, "global")
    deck_parameters = {
        k: {
            "m": int(m)
        }
        for k, m in zip(deck_names, max_ivl_list)
    }
    deck_parameters = OrderedDict(
        {k: v for k, v in sorted(deck_parameters.items(), key=lambda item: item[0], reverse=True)})

    mw.checkpoint("Postponing")
    mw.progress.start()

    cnt = 0
    postponed_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        max_ivl = deck_parameters['global']['m']
        for key, value in deck_parameters.items():
            if deck['name'].startswith(key):
                max_ivl = value['m']
                break
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:due\" \"is:review\" -\"is:suspended\""):
            if cid not in postponed_cards:
                postponed_cards.add(cid)
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
            if r > target_retention:
                new_ivl = min(max(int(round(math.log(target_retention) / math.log(0.9) * s)), 1), max_ivl)
                offset = max(1, new_ivl - card.ivl)
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

    tooltip(_(f"""{cnt} card postponed"""))
