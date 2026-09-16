import time
from bisect import bisect_left, bisect_right
from heapq import heappop, heappush
from typing import Dict, Tuple

from anki.cards import Card
from anki.utils import ids2str
from aqt.utils import tooltip

from ..configuration import Config
from ..i18n import t
from ..utils import *


def get_siblings(did=None, filter_flag=False, filtered_nid_string=""):
    if did is not None:
        did_list = ids2str(mw.col.decks.deck_and_child_ids(did))
        did_query = f"AND did IN {did_list}"

    if filter_flag:
        nid_query = f"AND nid IN {filtered_nid_string}"

    siblings = mw.col.db.all(f"""
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
    """)
    nid_siblings_dict = {}
    deck_config_cache = {}
    for cid, nid, did, stability, due in siblings:
        if nid not in nid_siblings_dict:
            nid_siblings_dict[nid] = []

        if did not in deck_config_cache:
            deck_config_cache[did] = {
                "dr": get_dr(mw.col.decks, did),
                "max_ivl": mw.col.decks.config_dict_for_deck_id(did)["rev"]["maxIvl"],
            }

        config = deck_config_cache[did]
        nid_siblings_dict[nid].append(
            (
                cid,
                did,
                stability,
                due,
                config["dr"],
                config["max_ivl"],
            )
        )
    return nid_siblings_dict


def get_siblings_when_review(card: Card):
    siblings = mw.col.db.all(f"""
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
    """)
    siblings = map(
        lambda x: (
            x
            + [
                get_dr(mw.col.decks, x[1]),
                mw.col.decks.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
            ]
        ),
        siblings,
    )
    return list(siblings)


def get_due_range(cid, stability, due, desired_retention, maximum_interval):
    card = mw.col.get_card(cid)
    last_review, last_interval = get_last_review_date_and_interval(card)
    new_ivl = next_interval(stability, desired_retention, -get_decay(card))

    if new_ivl <= 2.5:
        return (due, due), last_review

    min_ivl, max_ivl = get_fuzz_range(new_ivl, last_interval, maximum_interval)

    # If the card is currently scheduled outside the fuzz range, don't reschedule the card to bring it within the fuzz range.
    # Rather, create a new fuzz range around the original due date. Users can use `reschedule` to bring the card in range.
    if (
        due > last_review + max_ivl + 2
    ):  # +2 is just a safeguard to exclude cards that go beyond the fuzz range due to rounding
        current_ivl = due - last_review
        # set maximum_interval = current_ivl to prevent a further increase in ivl
        min_ivl, max_ivl = get_fuzz_range(current_ivl, last_interval, current_ivl)

    if (
        due < last_review + min_ivl - 2
    ):  # +2 is just a safeguard to exclude cards that go beyond the fuzz range due to rounding
        current_ivl = due - last_review
        min_ivl, max_ivl = get_fuzz_range(current_ivl, last_interval, maximum_interval)
        # Prevent a further decrease in ivl because it is already lower than the optimal range
        min_ivl = max(current_ivl, min_ivl)

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
        tooltip(t("enable-fsrs-warning"))
        return None

    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        _, result = future.result()
        tooltip(
            t(
                "disperse-result",
                result=result,
                count=f"{time.time() - start_time:.2f}",
            )
        )
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: disperse_siblings_background(
            did, filter_flag, filtered_nid_string, text_from_reschedule
        ),
        on_done,
    )

    return fut


def disperse_siblings_background(
    did, filter_flag=False, filtered_nid_string="", text_from_reschedule=""
):
    nid_siblings = get_siblings(did, filter_flag, filtered_nid_string)
    sibilings_cnt = len(nid_siblings)

    mw.taskman.run_on_main(
        lambda: mw.progress.start(
            label=t("disperse-label"), max=sibilings_cnt, immediate=True
        )
    )

    card_cnt = 0
    note_cnt = 0
    dispersed_cards = []
    undo_entry = mw.col.add_custom_undo_entry(t("disperse-siblings"))
    for nid, siblings in nid_siblings.items():
        best_due_dates, _, _ = disperse(siblings)
        for cid, due in best_due_dates.items():
            card = mw.col.get_card(cid)
            last_review, _ = get_last_review_date_and_interval(card)
            card = update_card_due_ivl(card, due - last_review)
            write_custom_data(card, "v", "disperse")
            dispersed_cards.append(card)
            card_cnt += 1
        note_cnt += 1

        if note_cnt % 500 == 0:
            mw.taskman.run_on_main(
                lambda: mw.progress.update(
                    label=t(
                        "disperse-progress", count=note_cnt, total=len(nid_siblings)
                    ),
                    value=note_cnt,
                    max=sibilings_cnt,
                )
            )
            if mw.progress.want_cancel():
                break

    mw.col.update_cards(dispersed_cards)
    mw.col.merge_undo_entries(undo_entry)
    result_text = f"{text_from_reschedule + ', ' if text_from_reschedule != '' else ''}{card_cnt} {t('disperse-cards-in')} {note_cnt} {t('disperse-notes')}"
    return card_cnt, result_text


def disperse_siblings_when_review(reviewer, card: Card, ease):
    if not mw.col.get_config("fsrs"):
        tooltip(t("enable-fsrs-warning"))
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
    last_undo_step = mw.col.undo_status().last_step
    best_due_dates, due_ranges, min_gap = disperse(siblings)

    for cid, due in best_due_dates.items():
        card = mw.col.get_card(cid)
        old_due = card.odue if card.odid else card.due
        last_review, _ = get_last_review_date_and_interval(card)
        card = update_card_due_ivl(card, due - last_review)
        write_custom_data(card, "v", "disperse")
        dispersed_cards.append(card)
        card_cnt += 1
        message = t(
            "disperse-card-message",
            card_id=card.id,
            old_due=due_to_date_str(old_due),
            new_due=due_to_date_str(due),
        )
        messages.append(message)

    mw.col.update_cards(dispersed_cards)
    mw.col.merge_undo_entries(last_undo_step)

    if config.debug_notify:
        text = ""
        if min_gap == 0:
            for cid, due_range in due_ranges.items():
                text += (
                    t(
                        "disperse-card-range",
                        card_id=cid,
                        start_due=due_to_date_str(due_range[0]),
                        end_due=due_to_date_str(due_range[1]),
                    )
                    + "<br/>"
                )
            text = t("disperse-too-close") + "<br/>" + text
        tooltip(text + "<br/>".join(messages))


def maximize_siblings_due_gap(points_dict: Dict[int, Tuple[int, int]]):
    """Maximize the minimum gap without imposing an order on sibling cards."""
    # Stable identities make the result independent of database/insertion order.
    points_list = sorted(points_dict.items())
    max_min_gap, arrangement = find_max_min_gap_and_arrangement(
        [interval for _, interval in points_list]
    )

    # Preserve the existing preference for later dates, using the order actually
    # chosen by the solver. Deadline order may differ for nested windows.
    order = sorted(range(len(points_list)), key=arrangement.__getitem__)
    for position, i in enumerate(order):
        right_limit = points_list[i][1][1]
        if position + 1 < len(order):
            right_limit = min(
                right_limit, arrangement[order[position + 1]] - max_min_gap
            )
        arrangement[i] = right_limit

    return max_min_gap, {cid: arrangement[i] for i, (cid, _) in enumerate(points_list)}


def find_max_min_gap_and_arrangement(points):
    """Return the global maximum integer gap and dates in the input order.

    Inputs are inclusive integer windows. They are not mutated. For fewer than
    two points the gap is defined as zero.
    """
    arrangement = [left for left, _ in points]
    if len(points) < 2:
        return 0, arrangement

    min_gap = 1
    max_gap = (max(right for _, right in points) - min(arrangement)) // (
        len(points) - 1
    )
    best_gap = 0

    while min_gap <= max_gap:
        mid_gap = (min_gap + max_gap) // 2
        candidate = _place_siblings_with_gap(points, mid_gap)
        if candidate is not None:
            best_gap = mid_gap
            arrangement = candidate
            min_gap = mid_gap + 1
        else:
            max_gap = mid_gap - 1

    return best_gap, arrangement


def _place_siblings_with_gap(points, min_gap):
    """Find a feasible arrangement in any order, or return None.

    Treat a point in [L, R] as a job of length min_gap with release L and
    completion deadline R + min_gap. Earliest-deadline dispatch is sufficient
    after excluding forbidden start regions (Garey et al., 1981;
    https://doi.org/10.1137/0210018). See also the integer formulation in
    Artiouchine and Baptiste, section 3: https://doi.org/10.1007/s10601-006-9009-1.

    Incremental backward scheduling computes these regions in O(n^2 log n)
    time and O(n) space. A successful greedy pass skips that work entirely.
    """
    if not points or min_gap == 0:
        return [left for left, _ in points]

    release_order = sorted(
        range(len(points)), key=lambda i: (points[i][0], points[i][1], i)
    )

    def dispatch(forbidden_starts, forbidden_ends):
        ready = []
        pending = 0
        date = points[release_order[0]][0]
        arrangement = [0] * len(points)
        for _ in points:
            if not ready:
                date = max(date, points[release_order[pending]][0])
            region = bisect_right(forbidden_starts, date) - 1
            if region >= 0 and date <= forbidden_ends[region]:
                date = forbidden_ends[region] + 1
            while pending < len(points) and points[release_order[pending]][0] <= date:
                i = release_order[pending]
                left, right = points[i]
                heappush(ready, (right, left, i))
                pending += 1
            right, _, i = heappop(ready)
            if date > right:
                return None
            arrangement[i] = date
            date += min_gap
        return arrangement

    arrangement = dispatch([], [])
    if arrangement is not None:
        return arrangement

    # Inclusive forbidden integer regions, sorted and merged. No feasible
    # arrangement may put ANY point in these regions, regardless of its ID.
    forbidden_starts = []
    forbidden_ends = []
    deadlines = sorted({right for _, right in points})
    latest_starts = [right + min_gap for right in deadlines]
    first_active = len(deadlines)
    pending = len(points) - 1
    while pending >= 0:
        release = points[release_order[pending]][0]
        while pending >= 0 and points[release_order[pending]][0] == release:
            _, right = points[release_order[pending]]
            first_deadline = bisect_left(deadlines, right)
            first_active = min(first_active, first_deadline)
            # For each deadline, add this job to the set of jobs released at
            # or after 'release' that must finish by that deadline. Pack that
            # set backwards, skipping forbidden starts. Previously packed
            # jobs remain valid: new regions end before their release dates.
            for j in range(first_deadline, len(deadlines)):
                date = latest_starts[j] - min_gap
                region = bisect_right(forbidden_starts, date) - 1
                if region >= 0 and date <= forbidden_ends[region]:
                    date = forbidden_starts[region] - 1
                latest_starts[j] = date
            pending -= 1

        latest_start = min(latest_starts[first_active:])
        if latest_start < release:
            return None

        # A point starting here would prevent a constrained set from starting
        # by its latest feasible start. Integer endpoints are inclusive.
        lower = latest_start - min_gap + 1
        upper = release - 1
        if lower <= upper:
            # Releases decrease, so a new region can only touch the leftmost
            # existing region. Merge adjacent regions as well as overlaps.
            if forbidden_starts and upper >= forbidden_starts[0] - 1:
                forbidden_starts[0] = min(forbidden_starts[0], lower)
            else:
                forbidden_starts.insert(0, lower)
                forbidden_ends.insert(0, upper)

    return dispatch(forbidden_starts, forbidden_ends)
