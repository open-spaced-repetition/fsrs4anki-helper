
from .utils import *
import json
import math
import itertools
from anki.decks import DeckManager
from anki.utils import ids2str


DM = None
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


def get_siblings(did=None, filter=False, filtered_nid_string=""):
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))
    siblings = mw.col.db.all(f"""SELECT id, nid, did, data
    FROM cards
    WHERE nid IN (
        SELECT nid
        FROM cards
        WHERE type = 2
        AND queue != -1
        AND data like '%"cd"%'
        {"AND nid IN (" + filtered_nid_string + ")" if filter else ""}
        GROUP BY nid
        HAVING count(*) > 1
    )
    AND data like '%"cd"%'
    AND type = 2
    AND queue != -1
    {"AND did IN %s" % did_list if did is not None else ""}
    """)
    siblings = map(lambda x: (x[0], x[1], x[2], json.loads(json.loads(x[3])['cd'])['s']), siblings)
    siblings_dict = {}
    for cid, nid, did, stability in siblings:
        if nid not in siblings_dict:
            siblings_dict[nid] = []
        siblings_dict[nid].append((cid, did, stability))
    return siblings_dict

def get_due_range(cid, parameters, stability, siblings_cnt):
    revlogs = mw.col.card_stats_data(cid).revlog
    last_due = get_last_review_date(revlogs[0])
    last_rating = revlogs[0].button_chosen
    if last_rating == 4:
        easy_bonus = parameters['e']
    else:
        easy_bonus = 1
    new_ivl = int(round(stability * math.log(parameters['r']) * easy_bonus / math.log(0.9)))
    due = last_due + new_ivl
    if new_ivl <= 2.5:
        return range(due, due + 1), last_due
    elapsed_days = int((revlogs[0].time - revlogs[1].time) / 86400) if len(revlogs) >= 2 else 0
    min_ivl, max_ivl = get_fuzz_range(new_ivl, elapsed_days)
    step = max(1, math.floor((max_ivl - min_ivl) / (4 if siblings_cnt <= 4 else 2)))
    due_range = range(last_due + min_ivl, last_due + max_ivl + 1, step)
    if due_range.stop < mw.col.sched.today:
        due_range = range(due, due + 1)
    return due_range, last_due


def disperse(siblings):
    siblings_cnt = len(siblings)
    due_ranges_last_due = {cid: get_due_range(cid, did_to_deck_parameters[did], stability, siblings_cnt) for cid, did, stability in siblings}
    due_ranges = {cid: due_range for cid, (due_range, last_due) in due_ranges_last_due.items()}
    last_due = {cid: last_due for cid, (due_range, last_due) in due_ranges_last_due.items()}
    latest_due = max(last_due.values())
    due_ranges[-1] = range(latest_due, latest_due + 1)
    best_due_dates = maximize_siblings_due_gap(due_ranges)
    best_due_dates.pop(-1)
    return best_due_dates


def disperse_siblings(did, filter=False, filtered_nid_string=""):
    global DM
    DM = DeckManager(mw.col)
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
    siblings = get_siblings(did, filter, filtered_nid_string)
    for nid, cards in siblings.items():
        best_due_dates = disperse(cards)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            last_revlog = mw.col.card_stats_data(cid).revlog[0]
            last_due = get_last_review_date(last_revlog)
            card = update_card_due_ivl(card, last_revlog, due - last_due)
            card.flush()
            cnt += 1

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_(f"""{cnt} cards in {len(siblings)} notes dispersed."""))