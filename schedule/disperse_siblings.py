from ..utils import *
from ..configuration import Config
from anki.utils import ids2str, html_to_text_line
from collections import defaultdict
from datetime import datetime, timedelta
import copy

did_to_deck_parameters = {}
enable_load_balance = None
free_days = None
version = None


def get_siblings(did=None, filter_flag=False, filtered_nid_string=""):
    if did is not None:
        did_list = ids2str(mw.col.decks.deck_and_child_ids(did))
    siblings = mw.col.db.all(
        f"""
    SELECT 
        id,
        nid,
        did,
        json_extract(data, '$.s'),
        CASE WHEN odid==0 THEN due ELSE odue END
    FROM cards
    WHERE nid IN (
        SELECT nid
        FROM cards
        WHERE type = 2
        AND queue != -1
        AND json_extract(data, '$.s') IS NOT NULL
        {"AND nid IN (" + filtered_nid_string + ")" if filter_flag else ""}
        GROUP BY nid
        HAVING count(*) > 1
    )
    AND json_extract(data, '$.s') IS NOT NULL
    AND type = 2
    AND queue != -1
    {"AND did IN %s" % did_list if did is not None else ""}
    """
    )
    siblings = filter(lambda x: x[3] is not None, siblings)
    nid_siblings_dict = {}
    for cid, nid, did, stability, due in siblings:
        if nid not in nid_siblings_dict:
            nid_siblings_dict[nid] = []
        nid_siblings_dict[nid].append((cid, did, stability, due))
    return nid_siblings_dict


def get_due_range(cid, parameters, stability, due):
    revlogs = filter_revlogs(mw.col.card_stats_data(cid).revlog)
    last_review = get_last_review_date(revlogs[0])
    if version[0] == 4:
        new_ivl = int(round(9 * stability * (1 / parameters["r"] - 1)))
    elif version[0] == 3:
        last_rating = revlogs[0].button_chosen
        if last_rating == 4:
            new_ivl = int(
                round(
                    stability
                    * parameters["e"]
                    * math.log(parameters["r"])
                    / math.log(0.9)
                )
            )
        else:
            new_ivl = int(round(stability * math.log(parameters["r"]) / math.log(0.9)))

    new_ivl = min(new_ivl, parameters["m"])

    if new_ivl <= 2.5:
        return (due, due, cid), last_review

    last_elapsed_days = (
        int((revlogs[0].time - revlogs[1].time) / 86400) if len(revlogs) >= 2 else 0
    )
    min_ivl, max_ivl = get_fuzz_range(new_ivl, last_elapsed_days)
    if due >= mw.col.sched.today:
        due_range = (
            max(last_review + min_ivl, mw.col.sched.today),
            max(last_review + max_ivl, mw.col.sched.today),
            cid,
        )
    elif last_review + max_ivl > mw.col.sched.today:
        due_range = (mw.col.sched.today, last_review + max_ivl, cid)
    else:
        due_range = (due, due, cid)
    return due_range, last_review


def disperse(siblings):
    due_ranges_last_review = {
        cid: get_due_range(cid, did_to_deck_parameters[did], stability, due)
        for cid, did, stability, due in siblings
    }
    due_ranges = {
        cid: due_range for cid, (due_range, _) in due_ranges_last_review.items()
    }
    last_review = {
        cid: last_review for cid, (_, last_review) in due_ranges_last_review.items()
    }
    latest_review = max(last_review.values())
    due_ranges[-1] = (latest_review, latest_review, -1)
    best_due_dates = maximize_siblings_due_gap(due_ranges)
    best_due_dates.pop(-1)
    return best_due_dates


def disperse_siblings(
    did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""
):
    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        tooltip(f"{future.result()} in {time.time() - start_time:.2f} seconds")
        mw.col.reset()
        mw.reset()

    mw.taskman.run_in_background(
        lambda: disperse_siblings_backgroud(
            did, filter_flag, filtered_nid_string, text_from_reschedule
        ),
        on_done,
    )


def disperse_siblings_backgroud(
    did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""
):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    global version
    version = get_version(custom_scheduler)
    if version[0] < 3:
        mw.taskman.run_on_main(
            lambda: showWarning("Require FSRS4Anki version >= 3.0.0")
        )
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = (
        get_skip_decks(custom_scheduler) if geq_version(version, (3, 12, 0)) else []
    )
    global_deck_name = get_global_config_deck_name(version)

    global did_to_deck_parameters
    did_to_deck_parameters = get_did_parameters(
        mw.col.decks.all(), deck_parameters, global_deck_name
    )

    config = Config()
    config.load()
    global enable_load_balance, free_days
    enable_load_balance = config.load_balance
    free_days = config.free_days

    card_cnt = 0
    note_cnt = 0
    nid_siblings = get_siblings(did, filter_flag, filtered_nid_string)
    sibilings_cnt = len(nid_siblings)

    undo_entry = mw.col.add_custom_undo_entry("Disperse Siblings")
    mw.taskman.run_on_main(
        lambda: mw.progress.start(
            label="Siblings Dispersing", max=sibilings_cnt, immediate=False
        )
    )

    for nid, siblings in nid_siblings.items():
        best_due_dates = disperse(siblings)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            last_revlog = mw.col.card_stats_data(cid).revlog[0]
            if last_revlog.review_kind == REVLOG_RESCHED:
                continue
            last_review = get_last_review_date(last_revlog)
            card = update_card_due_ivl(card, last_revlog, due - last_review)
            old_custom_data = json.loads(card.custom_data)
            old_custom_data["v"] = "disperse"
            card.custom_data = json.dumps(old_custom_data)
            mw.col.update_card(card)
            mw.col.merge_undo_entries(undo_entry)
            card_cnt += 1
        note_cnt += 1

        if note_cnt % 500 == 0:
            mw.taskman.run_on_main(
                lambda: mw.progress.update(
                    label=f"{note_cnt}/{len(nid_siblings)} notes dispersed",
                    value=note_cnt,
                    max=sibilings_cnt,
                )
            )
            if mw.progress.want_cancel():
                break

    return f"{text_from_reschedule +', ' if text_from_reschedule != '' else ''}{card_cnt} cards in {note_cnt} notes dispersed"


# https://stackoverflow.com/questions/68180974/given-n-points-where-each-point-has-its-own-range-adjust-all-points-to-maximize
def maximize_siblings_due_gap(cid_to_due_ranges: Dict[int, tuple]):
    max_attempts = 10
    allocation = allocate_ranges(list(cid_to_due_ranges.values()), max_attempts)
    return {
        item[2]: due_date
        for due_date, due_ranges in allocation.items()
        for item in due_ranges
    }


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
                improved_results = attempt_to_achieve_min_gap(
                    due_to_ranges, trial_min_gap
                )
                if improved_results:
                    found_improvement = True
                    min_gap = trial_min_gap
                    # print(f"found improvement!: {min_gap}")
                    due_to_ranges = improved_results
        if min_gap > best_min_gap:
            best_min_gap = min_gap
            best_allocation = copy.deepcopy(due_to_ranges)
            # print(f"found new gap after {attempts} tries: {best_min_gap}")
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


def get_siblings_when_review(card: Card):
    siblings = mw.col.db.all(
        f"""
    SELECT 
        id,
        did,
        json_extract(data, '$.s'),
        CASE WHEN odid==0 THEN due ELSE odue END
    FROM cards
    WHERE nid = {card.nid}
    AND json_extract(data, '$.s') IS NOT NULL
    AND type = 2
    AND queue != -1
    """
    )
    return list(filter(lambda x: x[2] is not None, siblings))


def disperse_siblings_when_review(reviewer, card: Card, ease):
    config = Config()
    config.load()
    if not config.auto_disperse:
        return

    global enable_load_balance, free_days
    enable_load_balance = config.load_balance
    free_days = config.free_days

    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return

    global version
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = (
        get_skip_decks(custom_scheduler) if geq_version(version, (3, 12, 0)) else []
    )
    deck_name = mw.col.decks.name(card.current_deck_id())
    if any([deck_name.startswith(deck) for deck in skip_decks if deck != ""]):
        return

    global_deck_name = get_global_config_deck_name(version)
    global did_to_deck_parameters
    did_to_deck_parameters = get_did_parameters(
        mw.col.decks.all(), deck_parameters, global_deck_name
    )

    siblings = get_siblings_when_review(card)

    if len(siblings) <= 1:
        return

    messages = []

    card_cnt = 0
    undo_entry = mw.col.add_custom_undo_entry("Disperse")
    best_due_dates = disperse(siblings)
    for cid, due in best_due_dates.items():
        card = mw.col.get_card(cid)
        old_due = card.odue if card.odid else card.due
        last_revlog = mw.col.card_stats_data(cid).revlog[0]
        last_review = get_last_review_date(last_revlog)
        card = update_card_due_ivl(card, last_revlog, due - last_review)
        old_custom_data = json.loads(card.custom_data)
        old_custom_data["v"] = "disperse"
        card.custom_data = json.dumps(old_custom_data)
        mw.col.update_card(card)
        mw.col.merge_undo_entries(undo_entry)
        card_cnt += 1
        message = f"Dispersed card {card.id} from {due_to_date(old_due)} to {due_to_date(due)}"
        messages.append(message)

    if config.debug_notify:
        tooltip("<br/>".join(messages))
