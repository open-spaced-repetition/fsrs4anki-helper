from .utils import *
from .configuration import Config
from anki.decks import DeckManager
from anki.utils import ids2str
from collections import defaultdict
from datetime import datetime, timedelta
import copy

DM = None
did_to_deck_parameters = {}
free_days = []
enable_load_balance = False

def get_siblings(did=None, filter_flag=False, filtered_nid_string=""):
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
        {"AND nid IN (" + filtered_nid_string + ")" if filter_flag else ""}
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

def get_due_range(cid, parameters, stability):
    revlogs = filter_revlogs(mw.col.card_stats_data(cid).revlog)
    last_due = get_last_review_date(revlogs[0])
    last_rating = revlogs[0].button_chosen
    if last_rating == 4:
        easy_bonus = parameters['e']
    else:
        easy_bonus = 1
    new_ivl = int(round(stability * easy_bonus * math.log(parameters['r']) / math.log(0.9)))
    due = last_due + new_ivl
    if new_ivl <= 2.5:
        return (due, due), last_due
    last_elapsed_days = int((revlogs[0].time - revlogs[1].time) / 86400) if len(revlogs) >= 2 else 0
    min_ivl, max_ivl = get_fuzz_range(new_ivl, last_elapsed_days)
    due_range = (last_due + min_ivl, last_due + max_ivl)
    if due_range[1] < mw.col.sched.today:
        due_range = (due, due)
    return due_range, last_due

def disperse(siblings):
    due_ranges_last_due = {cid: get_due_range(cid, did_to_deck_parameters[did], stability) for cid, did, stability in siblings}
    due_ranges = {cid: due_range for cid, (due_range, last_due) in due_ranges_last_due.items()}
    last_due = {cid: last_due for cid, (due_range, last_due) in due_ranges_last_due.items()}
    latest_due = max(last_due.values())
    due_ranges[-1] = (latest_due, latest_due)
    best_due_dates = maximize_siblings_due_gap(due_ranges)
    best_due_dates.pop(-1)
    return best_due_dates

def disperse_siblings(did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""):
    mw.taskman.run_in_background(lambda: disperse_siblings_backgroud(did, filter_flag, filtered_nid_string, text_from_reschedule))

def disperse_siblings_backgroud(did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""):
    global DM
    DM = DeckManager(mw.col)
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        mw.taskman.run_on_main(lambda: showWarning("Require FSRS4Anki version >= 3.0.0"))
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = get_skip_decks(custom_scheduler) if geq_version(version, (3, 12, 0)) else []
    global_deck_name = get_global_config_deck_name(version)

    global did_to_deck_parameters
    did_to_deck_parameters = get_did_parameters(mw.col.decks.all(), deck_parameters, global_deck_name)

    card_cnt = 0
    note_cnt = 0
    siblings = get_siblings(did, filter_flag, filtered_nid_string)

    mw.checkpoint("Siblings Dispersing")
    mw.taskman.run_on_main(lambda: mw.progress.start(label="Siblings Dispersing", max=len(siblings), immediate=False))

    config = Config()
    config.load()
    global enable_load_balance, free_days
    enable_load_balance = config.load_balance
    free_days = config.free_days

    for nid, cards in siblings.items():
        best_due_dates = disperse(cards)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            last_revlog = mw.col.card_stats_data(cid).revlog[0]
            last_due = get_last_review_date(last_revlog)
            card = update_card_due_ivl(card, last_revlog, due - last_due)
            card.flush()
            card_cnt += 1
        note_cnt += 1

        if note_cnt % 500 == 0:
            mw.taskman.run_on_main(lambda: mw.progress.update(value=note_cnt, label=f"{note_cnt}/{len(siblings)} notes dispersed"))
            if mw.progress.want_cancel(): break
            
    finished_text = f"{text_from_reschedule +', ' if text_from_reschedule != '' else ''}{card_cnt} cards in {note_cnt} notes dispersed."

    def on_finish():
        mw.progress.finish()
        mw.col.reset()
        mw.reset()
        tooltip(finished_text)

    mw.taskman.run_on_main(on_finish)
    return finished_text

# https://stackoverflow.com/questions/68180974/given-n-points-where-each-point-has-its-own-range-adjust-all-points-to-maximize
def maximize_siblings_due_gap(cid_to_due_ranges: Dict[int, tuple]):
    max_attempts = 10
    allocation = allocate_ranges(list(cid_to_due_ranges.values()), max_attempts)
    due_dates_to_due_ranges = dict(sorted(allocation.items(), key=lambda item: item[1]))
    cid_to_due_ranges = dict(sorted(cid_to_due_ranges.items(), key=lambda item: item[1]))
    return {card_id: due_date for card_id, due_date in sorted(zip(cid_to_due_ranges.keys(), due_dates_to_due_ranges.keys()))}

def get_dues_bordering_min_gap(due_to_ranges, min_gap):
    dues_bordering_min_gap = set()
    if min_gap == 0:
        for due, ranges in due_to_ranges.items():
            if len(ranges) > 1:
                dues_bordering_min_gap.add(due)
    else:
        sorted_dues = sorted(due_to_ranges.keys())
        prior_due = sorted_dues[0]
        for cur_due in sorted_dues[1:]:
            cur_gap = cur_due - prior_due
            if cur_gap == min_gap:
                dues_bordering_min_gap.add(cur_due)
                dues_bordering_min_gap.add(prior_due)
            prior_due = cur_due
    return list(dues_bordering_min_gap)

def get_min_gap(due_to_ranges, input_ranges):
    if len(due_to_ranges) < len(input_ranges):
        return 0
    
    sorted_dues = sorted(due_to_ranges.keys())
    prior_due = sorted_dues[0]
    min_gap = None
    for cur_due in sorted_dues[1:]:
        if min_gap is None or cur_due - prior_due < min_gap:
            min_gap = cur_due - prior_due
        prior_due = cur_due
        if min_gap == 1:
            return min_gap
    return min_gap

def attempt_to_achieve_min_gap(due_to_ranges, target_min_gap):
    new_due_to_ranges = defaultdict(list)

    leftmost_due = min(due_to_ranges.keys())
    leftmost_range = due_to_ranges[leftmost_due][0]
    new_due_to_ranges[leftmost_range[0]].append(leftmost_range)

    sorted_dues = sorted(due_to_ranges.keys())
    prior_due = leftmost_due
    for cur_due in sorted_dues[1:]:
        cur_range = due_to_ranges[cur_due][0]
        target_due = prior_due + target_min_gap
        if target_due <= cur_range[0]:
            new_due_to_ranges[cur_range[0]].append(cur_range)
            prior_due = cur_range[0]
        elif target_due <= cur_range[1]:
            new_due_to_ranges[target_due].append(cur_range)
            prior_due = target_due
        else:
            return False
    return new_due_to_ranges

def allocate_ranges(input_ranges, max_attempts):
    due_to_ranges = defaultdict(list)
    for due_range in input_ranges:
        due = due_sampler(due_range[0], due_range[1])
        due_to_ranges[due].append(due_range)
    
    best_min_gap = -1
    best_allocation = None
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        min_gap = get_min_gap(due_to_ranges, input_ranges)
        if min_gap > 0:
            found_improvement = True
            while found_improvement:
                found_improvement = False
                trial_min_gap = max(min_gap, best_min_gap) + 1
                improved_results = attempt_to_achieve_min_gap(due_to_ranges, trial_min_gap)
                if improved_results:
                    found_improvement = True
                    min_gap = trial_min_gap
                    print(f"found improvement!: {min_gap}")
                    due_to_ranges = improved_results
        if min_gap > best_min_gap:
            best_min_gap = min_gap
            best_allocation = copy.deepcopy(due_to_ranges)
            print(f"found new gap after {attempts} tries: {best_min_gap}")
            attempts = 0
        dues_to_adjust = get_dues_bordering_min_gap(due_to_ranges, min_gap)
        ranges_to_reallocate = []
        for due in dues_to_adjust:
            ranges_to_reallocate += due_to_ranges.pop(due, [])
        for due_range in ranges_to_reallocate:
            new_due = due_sampler(due_range[0], due_range[1])
            due_to_ranges[new_due].append(due_range)
    return best_allocation

def due_sampler(min_due, max_due):
    if enable_load_balance and len(free_days) > 0:
        due_list = list(range(min_due, max_due + 1))
        for due in range(min_due, max_due + 1):
            day_offset = due - mw.col.sched.today
            due_date = datetime.now() + timedelta(days=day_offset)
            if due_date.weekday() in free_days and len(due_list) > 1:
                due_list.remove(due)
        return random.choice(due_list)
    else:
        return random.randint(min_due, max_due)