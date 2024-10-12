from ..utils import *
from ..configuration import Config
from anki.utils import ids2str, html_to_text_line


def get_siblings(did=None, filter_flag=False, filtered_nid_string=""):
    if did is not None:
        did_list = ids2str(mw.col.decks.deck_and_child_ids(did))
        did_query = f"AND did IN {did_list}"

    if filter_flag:
        nid_query = f"AND nid IN {filtered_nid_string}"

    siblings = mw.col.db.all(
        f"""
    SELECT 
        id,
        nid,
        CASE WHEN odid==0
        THEN did
        ELSE odid
        END,
        json_extract(data, '$.s'),
        CASE WHEN odid==0 THEN due ELSE odue END
    FROM cards
    WHERE nid IN (
        SELECT nid
        FROM cards
        WHERE type = 2
        AND queue != -1
        AND data != ''
        AND json_extract(data, '$.s') IS NOT NULL
        {nid_query if filter_flag else ""}
        GROUP BY nid
        HAVING count(*) > 1
    )
    AND data != ''
    AND json_extract(data, '$.s') IS NOT NULL
    AND type = 2
    AND queue != -1
    {did_query if did is not None else ""}
    """
    )
    nid_siblings_dict = {}
    for cid, nid, did, stability, due in siblings:
        if nid not in nid_siblings_dict:
            nid_siblings_dict[nid] = []
        nid_siblings_dict[nid].append(
            (
                cid,
                did,
                stability,
                due,
                mw.col.decks.config_dict_for_deck_id(did)["desiredRetention"],
                mw.col.decks.config_dict_for_deck_id(did)["rev"]["maxIvl"],
            )
        )
    return nid_siblings_dict


def get_siblings_when_review(card: Card):
    siblings = mw.col.db.all(
        f"""
    SELECT 
        id,
        CASE WHEN odid==0
        THEN did
        ELSE odid
        END,
        json_extract(data, '$.s'),
        CASE WHEN odid==0 THEN due ELSE odue END
    FROM cards
    WHERE nid = {card.nid}
    AND data != ''
    AND json_extract(data, '$.s') IS NOT NULL
    AND type = 2
    AND queue != -1
    """
    )
    siblings = map(
        lambda x: x
        + [
            mw.col.decks.config_dict_for_deck_id(x[1])["desiredRetention"],
            mw.col.decks.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
        ],
        siblings,
    )
    return list(siblings)


def get_due_range(cid, stability, due, desired_retention, maximum_interval):
    card = mw.col.get_card(cid)
    last_review = get_last_review_date(card)
    new_ivl = next_interval(stability, desired_retention)

    if new_ivl <= 2.5:
        return (due, due), last_review

    revlogs = filter_revlogs(get_revlogs(cid))
    last_elapsed_days = (
        int((revlogs[0].time - revlogs[1].time) / 86400) if len(revlogs) >= 2 else 0
    )
    min_ivl, max_ivl = get_fuzz_range(new_ivl, last_elapsed_days, maximum_interval)
    if (
        due > last_review + max_ivl + 2
    ):  # +2 is just a safeguard to exclude cards that go beyond the fuzz range due to rounding
        # don't reschedule the card to bring it within the fuzz range. Rather, create another fuzz range around the original due date.
        current_ivl = due - last_review
        # set maximum_interval = current_ivl to prevent a further increase in ivl
        min_ivl, max_ivl = get_fuzz_range(current_ivl, last_elapsed_days, current_ivl)
    if due >= mw.col.sched.today:
        due_range = (
            max(last_review + min_ivl, mw.col.sched.today),
            max(last_review + max_ivl, mw.col.sched.today),
        )
    elif last_review + max_ivl > mw.col.sched.today:
        due_range = (mw.col.sched.today, last_review + max_ivl)
    else:
        due_range = (due, due)
    return due_range, last_review


def disperse(siblings):
    due_ranges_last_review = {
        cid: get_due_range(cid, stability, due, dr, max_ivl)
        for cid, _, stability, due, dr, max_ivl in siblings
    }
    due_ranges = {
        cid: due_range for cid, (due_range, _) in due_ranges_last_review.items()
    }
    last_review = {
        cid: last_review for cid, (_, last_review) in due_ranges_last_review.items()
    }
    latest_review = max(last_review.values())
    due_ranges[-1] = (latest_review, latest_review)
    min_gap, best_due_dates = maximize_siblings_due_gap(due_ranges)
    best_due_dates.pop(-1)
    return best_due_dates, due_ranges, min_gap


def disperse_siblings(
    did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""
):
    if not mw.col:
        return None
    if not mw.col.get_config("fsrs"):
        tooltip(FSRS_ENABLE_WARNING)
        return None

    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        tooltip(f"{future.result()} in {time.time() - start_time:.2f} seconds")
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: disperse_siblings_backgroud(
            did, filter_flag, filtered_nid_string, text_from_reschedule
        ),
        on_done,
    )

    return fut


def disperse_siblings_backgroud(
    did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""
):
    nid_siblings = get_siblings(did, filter_flag, filtered_nid_string)
    sibilings_cnt = len(nid_siblings)

    mw.taskman.run_on_main(
        lambda: mw.progress.start(
            label="Dispersing Siblings", max=sibilings_cnt, immediate=True
        )
    )

    card_cnt = 0
    note_cnt = 0
    dispersed_cards = []
    undo_entry = mw.col.add_custom_undo_entry("Disperse Siblings")
    for nid, siblings in nid_siblings.items():
        best_due_dates, _, _ = disperse(siblings)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            last_review = get_last_review_date(card)
            card = update_card_due_ivl(card, due - last_review)
            write_custom_data(card, "v", "disperse")
            dispersed_cards.append(card)
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

    mw.col.update_cards(dispersed_cards)
    mw.col.merge_undo_entries(undo_entry)
    return f"{text_from_reschedule +', ' if text_from_reschedule != '' else ''}{card_cnt} cards in {note_cnt} notes dispersed"


def disperse_siblings_when_review(reviewer, card: Card, ease):
    if not mw.col.get_config("fsrs"):
        tooltip(FSRS_ENABLE_WARNING)
        return

    config = Config()
    config.load()
    if not config.auto_disperse_when_review:
        return

    siblings = get_siblings_when_review(card)

    if len(siblings) <= 1:
        return

    messages = []

    card_cnt = 0
    dispersed_cards = []
    undo_entry = mw.col.undo_status().last_step
    best_due_dates, due_ranges, min_gap = disperse(siblings)

    for cid, due in best_due_dates.items():
        due = max(due, mw.col.sched.today + 1)
        card = mw.col.get_card(cid)
        old_due = card.odue if card.odid else card.due
        last_review = get_last_review_date(card)
        card = update_card_due_ivl(card, due - last_review)
        write_custom_data(card, "v", "disperse")
        dispersed_cards.append(card)
        card_cnt += 1
        message = f"Dispersed card {card.id} from {due_to_date_str(old_due)} to {due_to_date_str(due)}"
        messages.append(message)

    mw.col.update_cards(dispersed_cards)
    mw.col.merge_undo_entries(undo_entry)

    if config.debug_notify:
        text = ""
        if min_gap == 0:
            for cid, due_range in due_ranges.items():
                text += f"Card {cid} due range: {due_to_date_str(due_range[0])} - {due_to_date_str(due_range[1])}<br/>"
            text = "Due dates are too close to disperse:}<br/>" + text
        tooltip(text + "<br/>".join(messages))


# Modifying the algorithm to accept a dictionary as input and return a dictionary as output
def maximize_siblings_due_gap(points_dict: Dict[int, Tuple[int, int]]):
    """
    Function to find the arrangement that maximizes the gaps between adjacent points
    while maintaining the maximum minimum gap. Accepts and returns dictionaries.
    """
    # Convert the dictionary to a list of tuples and also keep track of the original keys
    points_list = [(k, v) for k, v in points_dict.items()]

    # Sort the list based on the right endpoints of the intervals
    points_list.sort(key=lambda x: x[1][1])

    # First, find the maximum minimum gap and the arrangement that achieves it
    intervals_only = [interval for _, interval in points_list]
    max_min_gap, initial_arrangement = find_max_min_gap_and_arrangement(intervals_only)

    # Initialize the optimized arrangement with the initial arrangement
    optimized_arrangement = initial_arrangement.copy()

    # Go through each point to try to maximize the gap with its adjacent points
    for i in range(len(points_list)):
        left_limit, right_limit = points_list[i][1]

        # Set initial boundaries based on the previous and next points in the arrangement
        if i > 0:
            left_limit = max(left_limit, optimized_arrangement[i - 1] + max_min_gap)
        if i < len(points_list) - 1:
            right_limit = min(right_limit, optimized_arrangement[i + 1] - max_min_gap)

        # Move the point as far to the right as possible within the adjusted limits
        optimized_arrangement[i] = right_limit

    # Convert the list back to a dictionary
    optimized_arrangement_dict = {
        points_list[i][0]: optimized_arrangement[i] for i in range(len(points_list))
    }

    return max_min_gap, optimized_arrangement_dict


def find_max_min_gap_and_arrangement(points):
    """
    Find the maximum minimum gap between adjacent points and also return the arrangement that achieves it.
    """
    # Sort the points based on their right endpoints
    points.sort(key=lambda x: x[1])

    # Initialize binary search parameters
    min_gap = 0  # Minimum possible gap
    max_gap = points[-1][1] - points[0][0]  # Maximum possible gap
    best_gap = 0  # To store the result

    arrangement = []  # To store the best arrangement of points

    def can_place_points_with_arrangement(points, min_gap):
        """
        A greedy algorithm to check if we can place all points with a minimum gap of `min_gap`.
        Also returns the arrangement if possible.
        """
        last_point_position = points[0][
            0
        ]  # Place the first point at its leftmost position
        temp_arrangement = [last_point_position]
        for i in range(1, len(points)):
            next_possible_point = last_point_position + min_gap
            # Find the rightmost position in the current point's range where it can be placed
            if next_possible_point > points[i][1]:
                return (
                    False,
                    [],
                )  # Can't place the point while maintaining the minimum gap
            last_point_position = max(next_possible_point, points[i][0])
            temp_arrangement.append(last_point_position)
        return True, temp_arrangement

    while min_gap <= max_gap:
        mid_gap = (min_gap + max_gap) // 2  # Compute the middle gap
        can_place, temp_arrangement = can_place_points_with_arrangement(points, mid_gap)
        if can_place:
            # If we can place all points with this gap, it means we can try to increase it
            best_gap = mid_gap
            arrangement = temp_arrangement  # Update the best arrangement
            min_gap = mid_gap + 1
        else:
            # If we can't place all points with this gap, it means we need to try a smaller gap
            max_gap = mid_gap - 1

    return best_gap, arrangement
