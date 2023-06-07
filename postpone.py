import math
from datetime import datetime
from .utils import *


def get_desired_postpone_cnt_with_response():
    inquire_text = "Postpone {n} due cards.\n"
    info_text = "Only affect cards scheduled by FSRS4Anki Scheduler or rescheduled by FSRS4Anki Helper.\n"
    ivl_text = "The new interval is the current interval * 1.05. And it skips those cards whose retention < requested retention - 1%\n"
    (s, r) = getText(inquire_text + info_text + ivl_text)
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def postpone(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    (desired_postpone_cnt, resp) = get_desired_postpone_cnt_with_response()
    if desired_postpone_cnt is None:
        if resp:
            showWarning("Please enter the number of cards you want to postpone.")
        return
    else:
        if desired_postpone_cnt <= 0:
            showWarning("Please enter an postive integral number.")
            return

    deck_parameters = get_deck_parameters(custom_scheduler)
    if deck_parameters is None:
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    global_deck_name = get_global_config_deck_name(version)

    mw.checkpoint("Postponing")
    mw.progress.start()

    cnt = 0
    postponed_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'])
    min_retention = 1
    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            postponed_cards = postponed_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\"".replace('\\', '\\\\')))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        (
            _,
            _,
            max_ivl,
            _,
            _,
        ) = deck_parameters[global_deck_name].values()
        for name, params in deck_parameters.items():
            if deck['name'].startswith(name):
                _, _, max_ivl, _, _ = params.values()
                break
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:due\" \"is:review\" -\"is:learn\" -\"is:suspended\"".replace('\\', '\\\\'), order=f"cast({mw.col.sched.today}-c.due+0.001 as real) / c.ivl asc, c.ivl desc"):
            if cnt >= desired_postpone_cnt:
                break
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

            try:
                revlog = mw.col.card_stats_data(cid).revlog[0]
            except IndexError:
                continue

            elapsed_days = datetime.today().toordinal() - datetime.fromtimestamp(revlog.time).toordinal()
            new_ivl = min(max(1, round(elapsed_days * 1.05)), max_ivl)
            card = update_card_due_ivl(card, revlog, new_ivl)
            card.flush()
            cnt += 1

            new_retention = math.pow(0.9, new_ivl / s)
            min_retention = min(min_retention, new_retention)

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(f"""{cnt} cards postponed, min retention: {min_retention:.2%}""")
