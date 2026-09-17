import time
from bisect import bisect_left, bisect_right
from heapq import heappop, heappush

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


def maximize_siblings_due_gap(points_dict: dict[int, tuple[int, int]]):
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

    Algorithm B's task loads, relevant deadlines and pseudo-offsets give
    O(n log n) time and O(n) space, including forbidden-region construction.
    All arithmetic stays integral; fractional offsets become residues mod g.
    """
    if not points or min_gap == 0:
        return [left for left, _ in points]

    release_order = sorted(
        range(len(points)), key=lambda i: (points[i][0], points[i][1], i)
    )

    arrangement = _dispatch_sibling_points(points, min_gap, release_order, [], [])
    if arrangement is not None:
        return arrangement
    # With both endpoints ordered, an exchange argument fixes the optimal
    # point order. Greedy failure then proves infeasibility, avoiding the
    # data-structure setup for ordinary, non-nested windows.
    if all(
        points[first][1] <= points[second][1]
        for first, second in zip(release_order, release_order[1:])
    ):
        return None

    regions = _sibling_forbidden_regions(points, min_gap, release_order)
    if regions is None:
        return None
    return _dispatch_sibling_points(points, min_gap, release_order, *regions)


def _dispatch_sibling_points(points, min_gap, release_order, starts, ends):
    """Dispatch by earliest deadline, respecting inclusive forbidden regions."""
    ready = []
    pending = 0
    date = points[release_order[0]][0]
    arrangement = [0] * len(points)
    for _ in points:
        if not ready:
            date = max(date, points[release_order[pending]][0])
        region = bisect_right(starts, date) - 1
        if region >= 0 and date <= ends[region]:
            date = ends[region] + 1
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


def _sibling_forbidden_regions(points, min_gap, release_order):
    """Algorithm B, Part I: exact feasibility in O(n log n), without dispatch.

    A deadline's pseudo-critical time is D - g * load - pseudo_offset.
    Later deadlines that dominate an earlier one stay dominant (Lemma 5).
    Load updates can invalidate only predecessors of the first affected
    relevant deadline (Lemma 6), so each deadline is deleted at most once.
    """
    deadlines = []
    for right in sorted(right for _, right in points):
        deadline = right + min_gap
        if not deadlines or deadline != deadlines[-1]:
            deadlines.append(deadline)
    count = len(deadlines)
    loads = _GapFenwickTree(count)
    relevant = _GapFenwickTree(count, full=True)
    predecessor = list(range(-1, count - 1))
    offsets = _GapOffsets(deadlines, min_gap)

    def critical(index):
        return (
            deadlines[index]
            - min_gap * loads.prefix_sum(index + 1)
            - offsets.offset(index)
        )

    # Regions are built right-to-left. Append/merge here and reverse once at
    # the end; inserting each region at index zero would be quadratic.
    forbidden_starts = []
    forbidden_ends = []
    first_active = count
    next_offset = count - 1
    pending = len(points) - 1
    while pending >= 0:
        release = points[release_order[pending]][0]
        while pending >= 0 and points[release_order[pending]][0] == release:
            _, right = points[release_order[pending]]
            index = bisect_left(deadlines, right + min_gap)
            loads.add(index, 1)
            successor = relevant.select(relevant.prefix_sum(index) + 1)
            successor_time = critical(successor)
            while (
                predecessor[successor] >= 0
                and critical(predecessor[successor]) > successor_time
            ):
                removed = predecessor[successor]
                relevant.add(removed, -1)
                predecessor[successor] = predecessor[removed]
                if first_active == removed:
                    first_active = successor
            first_active = min(first_active, successor)
            pending -= 1

        latest_start = critical(first_active)
        if latest_start < release:
            return None

        lower = latest_start - min_gap + 1
        upper = release - 1
        if lower <= upper:
            # A deadline <= latest_start cannot encounter this region while
            # scheduling backwards. Each other deadline is activated once.
            while next_offset >= 0 and deadlines[next_offset] > latest_start:
                offsets.activate(next_offset, deadlines[next_offset])
                next_offset -= 1
            offsets.forbid(latest_start - min_gap, release)
            if forbidden_starts and upper >= forbidden_starts[-1] - 1:
                forbidden_starts[-1] = min(forbidden_starts[-1], lower)
            else:
                forbidden_starts.append(lower)
                forbidden_ends.append(upper)

    forbidden_starts.reverse()
    forbidden_ends.reverse()
    return forbidden_starts, forbidden_ends


class _GapFenwickTree:
    """Counts with O(log n) point updates, prefix sums and rank selection."""

    def __init__(self, size, full=False):
        self.size = size
        self.tree = [0] + ([i & -i for i in range(1, size + 1)] if full else [0] * size)
        self.top_bit = 1 << (size.bit_length() - 1) if size else 0

    def add(self, index, delta):
        index += 1
        while index <= self.size:
            self.tree[index] += delta
            index += index & -index

    def prefix_sum(self, end):
        """Sum over zero-based indices strictly below end."""
        total = 0
        while end:
            total += self.tree[end]
            end -= end & -end
        return total

    def select(self, rank):
        """Zero-based index of a one-based rank; size if rank exceeds total."""
        index = 0
        bit = self.top_bit
        while bit:
            candidate = index + bit
            if candidate <= self.size and self.tree[candidate] < rank:
                rank -= self.tree[candidate]
                index = candidate
            bit >>= 1
        return index


class _GapOffsets:
    """Pseudo-offset groups indexed by (deadline - offset) modulo gap.

    A forbidden open region (a, b) moves the affected residues onto a % gap.
    This target is the residue of the deadline attaining the critical time,
    so it already exists: all possible residues are initial deadline residues.
    A compressed Fenwick tree therefore replaces the paper's search tree.

    Each removal merges a group permanently; at most n groups are inserted.
    The weighted forest uses union by size, giving O(log n) offset queries
    without path compression and O(1) merges of known roots.
    """

    def __init__(self, deadlines, gap):
        self.gap = gap
        self.phases = []
        for phase in sorted(deadline % gap for deadline in deadlines):
            if not self.phases or phase != self.phases[-1]:
                self.phases.append(phase)
        self.present = _GapFenwickTree(len(self.phases))
        self.roots = [-1] * len(self.phases)
        self.parents = [-1] * len(deadlines)
        self.sizes = [1] * len(deadlines)
        # Roots store absolute offsets; other nodes store offset differences
        # relative to their parent. Their path sum is the deadline's offset.
        self.weights = [0] * len(deadlines)

    def offset(self, index):
        if self.parents[index] < 0:
            return 0
        value = self.weights[index]
        while self.parents[index] != index:
            index = self.parents[index]
            value += self.weights[index]
        return value

    def _union(self, first, second):
        if self.sizes[first] < self.sizes[second]:
            first, second = second, first
        self.parents[second] = first
        self.weights[second] -= self.weights[first]
        self.sizes[first] += self.sizes[second]
        return first

    def activate(self, index, deadline):
        self.parents[index] = index
        phase = bisect_left(self.phases, deadline % self.gap)
        if self.roots[phase] < 0:
            self.roots[phase] = index
            self.present.add(phase, 1)
        else:
            self.roots[phase] = self._union(self.roots[phase], index)

    def forbid(self, start, end):
        """Apply an open forbidden region of width at most gap."""
        left = start % self.gap
        right = end % self.gap
        target = bisect_left(self.phases, left)
        # Algorithm B activates the critical deadline before this operation.
        assert self.phases[target] == left and self.roots[target] >= 0
        if left < right:
            self._merge_phases(
                target, bisect_right(self.phases, left), bisect_left(self.phases, right)
            )
        else:
            # A wrapping arc includes residue zero; equal endpoints mean a
            # full period with just the target residue excluded.
            self._merge_phases(
                target, bisect_right(self.phases, left), len(self.phases)
            )
            self._merge_phases(target, 0, bisect_left(self.phases, right))

    def _merge_phases(self, target, start, end):
        rank = self.present.prefix_sum(start) + 1
        phase = self.present.select(rank)
        while phase < end:
            root = self.roots[phase]
            self.weights[root] += (self.phases[phase] - self.phases[target]) % self.gap
            self.roots[target] = self._union(self.roots[target], root)
            self.roots[phase] = -1
            self.present.add(phase, -1)
            phase = self.present.select(rank)
