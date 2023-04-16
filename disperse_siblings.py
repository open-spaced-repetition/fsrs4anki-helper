
from .utils import *
import json
import math
import itertools


did_to_deck_parameters = {}


def maximize_siblings_due_gap(due_ranges):
    all_combinations = itertools.product(*due_ranges.values())

    max_gap_sum = 0
    max_gap_min = 0
    best_combination = []

    for combination in all_combinations:
        sorted_due_dates = sorted(combination)

        gap_sum = sum(sorted_due_dates[i+1] - sorted_due_dates[i] for i in range(len(sorted_due_dates) - 1))
        gap_min = min(sorted_due_dates[i+1] - sorted_due_dates[i] for i in range(len(sorted_due_dates) - 1))

        if gap_min >= max_gap_min:
            max_gap_min = gap_min
            if gap_sum >= max_gap_sum:
                max_gap_sum = gap_sum
                best_combination = combination

    return {card_id: due_date for card_id, due_date in sorted(zip(due_ranges.keys(), best_combination))}


def get_siblings():
    siblings = mw.col.db.all("""SELECT id, nid, did, data
    FROM cards
    WHERE nid IN (
        SELECT nid
        FROM cards
        WHERE queue = 2
        AND data like '%"cd"%'
        GROUP BY nid
        HAVING count(*) > 1
    )
    AND data like '%"cd"%'
    AND queue = 2
    AND odid = 0
    """)
    siblings = map(lambda x: (x[0], x[1], x[2], json.loads(json.loads(x[3])['cd'])['s']), siblings)
    siblings_dict = {}
    for cid, nid, did, stability in siblings:
        if nid not in siblings_dict:
            siblings_dict[nid] = []
        siblings_dict[nid].append((cid, did, stability))
    return siblings_dict

def get_due_range(cid, parameters, stability):
    card = mw.col.get_card(cid)
    ivl = card.ivl
    due = card.due
    last_due = due - ivl
    revlogs = mw.col.card_stats_data(cid).revlog
    last_rating = revlogs[0].button_chosen
    if last_rating == 4:
        easy_bonus = parameters['e']
    else:
        easy_bonus = 1
    new_ivl = int(round(stability * math.log(parameters['r']) * easy_bonus / math.log(0.9)))
    if new_ivl <= 2.5:
        return range(due, due + 1), last_due
    min_ivl = max(2, int(round(new_ivl * 0.95 - 1)))
    max_ivl = int(round(new_ivl * 1.05 + 1))
    step = max(1, math.floor((max_ivl - min_ivl) / 4))
    due_range = range(last_due + min_ivl, last_due + max_ivl + 1, step)
    if due_range.stop < mw.col.sched.today:
        due_range = range(due, due + 1)
    return due_range, last_due


def disperse(siblings):
    due_ranges_last_due = {cid: get_due_range(cid, did_to_deck_parameters[did], stability) for cid, did, stability in siblings}
    due_ranges = {cid: due_range for cid, (due_range, last_due) in due_ranges_last_due.items()}
    last_due = {cid: last_due for cid, (due_range, last_due) in due_ranges_last_due.items()}
    latest_due = max(last_due.values())
    due_ranges[-1] = range(latest_due, latest_due + 1)
    best_due_dates = maximize_siblings_due_gap(due_ranges)
    best_due_dates.pop(-1)
    return best_due_dates


def disperse_siblings(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = get_skip_decks(custom_scheduler) if geq_version(version, (3, 12, 0)) else []
    global_deck_name = get_global_config_deck_name(version)


    def get_parameters(deckname, mapping):
        parts = deckname.split("::")
        for i in range(len(parts), 0, -1):
            prefix = "::".join(parts[:i])
            if prefix in mapping:
                return mapping[prefix]
        return mapping[global_deck_name]


    deck_list = mw.col.decks.all()

    global did_to_deck_parameters
    for d in deck_list:
        parameters = get_parameters(d["name"], deck_parameters)
        did_to_deck_parameters[d["id"]] = parameters

    mw.checkpoint("Siblings Dispersing")
    mw.progress.start()

    cnt = 0
    siblings = get_siblings()
    for nid, cards in siblings.items():
        best_due_dates = disperse(cards)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            offset = card.due - due
            card.due = due
            card.ivl = card.ivl - offset
            card.flush()
            cnt += 1

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_(f"""{cnt} cards in {len(siblings)} notes dispersed."""))