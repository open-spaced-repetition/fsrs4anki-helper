from .utils import *
from anki.decks import DeckManager
from anki.utils import ids2str
import copy
from collections import defaultdict

DM = None
did_to_deck_parameters = {}

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

def get_due_range(cid, parameters, stability):
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
        return (due, due), last_due
    elapsed_days = int((revlogs[0].time - revlogs[1].time) / 86400) if len(revlogs) >= 2 else 0
    min_ivl, max_ivl = get_fuzz_range(new_ivl, elapsed_days)
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

def disperse_siblings(did, filter=False, filtered_nid_string="", text_from_reschedule=""):
    mw.taskman.run_in_background(lambda: disperse_siblings_backgroud(did, filter, filtered_nid_string, text_from_reschedule))

def disperse_siblings_backgroud(did, filter=False, filtered_nid_string="", text_from_reschedule=""):
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

    global did_to_deck_parameters
    did_to_deck_parameters = get_did_parameters(mw.col.decks.all(), deck_parameters, global_deck_name)

    card_cnt = 0
    note_cnt = 0
    siblings = get_siblings(did, filter, filtered_nid_string)

    mw.checkpoint("Siblings Dispersing")
    mw.taskman.run_on_main(lambda: mw.progress.start(label="Siblings Dispersing", max=len(siblings), immediate=True))

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
    allocation = allocate_points(list(cid_to_due_ranges.values()), max_attempts)
    due_dates_to_due_ranges = dict(sorted(allocation.items(), key=lambda item: item[1]))
    cid_to_due_ranges = dict(sorted(cid_to_due_ranges.items(), key=lambda item: item[1]))
    return {card_id: due_date for card_id, due_date in sorted(zip(cid_to_due_ranges.keys(), due_dates_to_due_ranges.keys()))}

def get_points_with_optimal_min_gap(n, range_):
    points = []
    for num in range(1, n + 1):
        points.append([max(0, round(num * range_/n) - random.randint(0, 5*range_/n)), round(num * range_/n) + random.randint(0, 5*range_/n)])
    random.shuffle(points)
    return points

def get_vals_bordering_min_gap(val_to_points, min_gap):
    vals_bordering_min_gap = set()
    if min_gap == 0:
        for val, points in val_to_points.items():
            if len(points) > 1:
                vals_bordering_min_gap.add(val)
    else:
        sorted_vals = sorted(val_to_points.keys())
        prior_val = sorted_vals[0]
        for cur_val in sorted_vals[1:]:
            cur_gap = cur_val - prior_val
            if cur_gap == min_gap:
                vals_bordering_min_gap.add(cur_val)
                vals_bordering_min_gap.add(prior_val)
            prior_val = cur_val
    return list(vals_bordering_min_gap)

def get_min_gap(val_to_points, input_points):
    if len(val_to_points) < len(input_points):
        return 0
    
    sorted_vals = sorted(val_to_points.keys())
    prior_val = sorted_vals[0]
    min_gap = None
    for cur_val in sorted_vals[1:]:
        if min_gap is None or cur_val - prior_val < min_gap:
            min_gap = cur_val - prior_val
        prior_val = cur_val
        if min_gap == 1:
            return min_gap
    return min_gap

def attempt_to_achieve_min_gap(val_to_points, target_min_gap):
    new_val_to_points = defaultdict(list)

    leftmost_val = min(val_to_points.keys())
    leftmost_point = val_to_points[leftmost_val][0]
    new_val_to_points[leftmost_point[0]].append(leftmost_point)

    sorted_vals = sorted(val_to_points.keys())
    prior_val = leftmost_val
    for cur_val in sorted_vals[1:]:
        cur_point = val_to_points[cur_val][0]
        target_val = prior_val + target_min_gap
        if target_val <= cur_point[0]:
            new_val_to_points[cur_point[0]].append(cur_point)
            prior_val = cur_point[0]
        elif target_val <= cur_point[1]:
            new_val_to_points[target_val].append(cur_point)
            prior_val = target_val
        else:
            return False
    return new_val_to_points

def allocate_points(input_points, max_attempts):
    val_to_points = defaultdict(list)
    for point in input_points:
        val = random.randint(point[0], point[1])
        val_to_points[val].append(point)
    
    best_min_gap = -1
    best_allocation = None
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        min_gap = get_min_gap(val_to_points, input_points)
        if min_gap > 0:
            found_improvement = True
            while found_improvement:
                found_improvement = False
                trial_min_gap = max(min_gap, best_min_gap) + 1
                improved_results = attempt_to_achieve_min_gap(val_to_points, trial_min_gap)
                if improved_results:
                    found_improvement = True
                    min_gap = trial_min_gap
                    print(f"found improvement!: {min_gap}")
                    val_to_points = improved_results
        if min_gap > best_min_gap:
            best_min_gap = min_gap
            best_allocation = copy.deepcopy(val_to_points)
            print(f"found new gap after {attempts} tries: {best_min_gap}")
            attempts = 0
        vals_to_adjust = get_vals_bordering_min_gap(val_to_points, min_gap)
        points_to_reallocate = []
        for val in vals_to_adjust:
            points_to_reallocate += val_to_points.pop(val, [])
        for point in points_to_reallocate:
            new_val = random.randint(point[0], point[1])
            val_to_points[new_val].append(point)
    return best_allocation
