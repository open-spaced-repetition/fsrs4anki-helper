import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from anki.cards import Card, FSRSMemoryState
from anki.decks import DeckManager
from anki.stats import (
    CARD_TYPE_REV,
    QUEUE_TYPE_NEW,
    QUEUE_TYPE_PREVIEW,
    QUEUE_TYPE_SUSPENDED,
)
from anki.utils import ids2str
from aqt import mw
from aqt.qt import QInputDialog
from aqt.utils import tooltip

from ..i18n import t
from ..utils import (
    get_last_review_date_and_interval,
    update_card_due_ivl,
    write_custom_data,
)


@dataclass
class BusyCard:
    card: Card
    original_due: int
    last_review: int
    stability: float


def _ensure_memory_state(card: Card) -> Optional[FSRSMemoryState]:
    if card.memory_state:
        stability = card.memory_state.stability
        difficulty = card.memory_state.difficulty
        if stability is not None and difficulty is not None:
            return card.memory_state
    memory_state = mw.col.compute_memory_state(card.id)
    if (
        memory_state is None
        or memory_state.stability is None
        or memory_state.difficulty is None
    ):
        return None
    card.memory_state = FSRSMemoryState(
        stability=memory_state.stability, difficulty=memory_state.difficulty
    )
    if hasattr(memory_state, "decay") and hasattr(card, "decay"):
        card.decay = memory_state.decay
    return card.memory_state


def _prompt_busy_parameters():
    busy_days, ok = QInputDialog.getInt(
        mw,
        t("busy-reschedule-dialog-title"),
        t("busy-reschedule-dialog-busy-days"),
        value=3,
        min=1,
        max=60,
    )
    if not ok:
        return None
    spread_days, ok = QInputDialog.getInt(
        mw,
        t("busy-reschedule-dialog-title"),
        t("busy-reschedule-dialog-spread-days"),
        value=7,
        min=1,
        max=180,
    )
    if not ok:
        return None
    return busy_days, spread_days


def _fetch_window_cards(busy_start: int, window_end: int, did_query: str) -> List[Card]:
    cids = mw.col.db.list(
        f"""
        SELECT id
        FROM cards
        WHERE type = {CARD_TYPE_REV}
        AND queue NOT IN ({QUEUE_TYPE_SUSPENDED}, {QUEUE_TYPE_NEW}, {QUEUE_TYPE_PREVIEW})
        {did_query}
        AND CASE WHEN odid==0 THEN due ELSE odue END BETWEEN {busy_start} AND {window_end}
    """
    )
    return [mw.col.get_card(cid) for cid in cids]


def _build_busy_card(
    card: Card,
    busy_end: int,
) -> Optional[BusyCard]:
    memory_state = _ensure_memory_state(card)
    if memory_state is None:
        return None
    last_review, _ = get_last_review_date_and_interval(card)
    true_due = card.odue if card.odid else card.due

    return BusyCard(
        card=card,
        original_due=true_due,
        last_review=last_review,
        stability=memory_state.stability,
    )


def _allocate_busy_cards(
    cards: List[BusyCard],
    candidate_days: List[int],
    target_totals: Dict[int, int],
) -> Dict[int, List[BusyCard]]:
    assigned = defaultdict(list)
    current_totals = defaultdict(int)
    sorted_cards = sorted(
        cards,
        key=lambda c: (c.stability, c.last_review, c.original_due),
    )

    earliest_day = candidate_days[0] if candidate_days else 0
    for busy_card in sorted_cards:
        for day in candidate_days:
            if day < earliest_day:
                continue
            if current_totals[day] < target_totals[day]:
                current_totals[day] += 1
                assigned[day].append(busy_card)
                break
        else:
            fallback_day = candidate_days[-1]
            current_totals[fallback_day] += 1
            assigned[fallback_day].append(busy_card)
    return assigned


def _update_cards(assignments: Dict[int, List[BusyCard]], total: int) -> int:
    updated_cards = []
    processed = 0
    for due_day, cards in assignments.items():
        for busy_card in cards:
            interval = max(1, due_day - busy_card.last_review)
            update_card_due_ivl(busy_card.card, interval)
            write_custom_data(busy_card.card, "v", "reschedule")
            updated_cards.append(busy_card.card)
            processed += 1
            if processed == 1 or processed % 200 == 0:
                progress_count = processed
                mw.taskman.run_on_main(
                    lambda count=progress_count, total_cards=total: mw.progress.update(
                        label=t(
                            "busy-reschedule-update-progress",
                            count=count,
                            total=total_cards,
                        ),
                        value=count,
                        max=total_cards if total_cards > 0 else 1,
                    )
                )
    if updated_cards:
        mw.col.update_cards(updated_cards)
    mw.taskman.run_on_main(
        lambda total_cards=total: mw.progress.update(
            label=t(
                "busy-reschedule-update-progress",
                count=total_cards,
                total=total_cards,
            ),
            value=total_cards,
            max=total_cards if total_cards > 0 else 1,
        )
    )
    return len(updated_cards)


def _busy_reschedule_background(did, busy_days: int, spread_days: int):
    deck_manager = DeckManager(mw.col)
    today = mw.col.sched.today
    busy_start = today
    busy_end = today + busy_days - 1
    window_end = today + busy_days + spread_days - 1

    candidate_days = list(range(busy_end + 1, window_end + 1))
    if not candidate_days:
        return {"count": 0, "skipped": 0, "busy_days": busy_days}

    did_query = ""
    if did is not None:
        did_list = deck_manager.deck_and_child_ids(did)
        if not did_list:
            return {"count": 0, "skipped": 0, "busy_days": busy_days}
        did_query = (
            f"AND CASE WHEN odid==0 THEN did ELSE odid END IN {ids2str(did_list)}"
        )

    window_cards = _fetch_window_cards(busy_start, window_end, did_query)
    if not window_cards:
        return {"count": 0, "skipped": 0, "busy_days": busy_days}

    total_cards = len(window_cards)
    mw.taskman.run_on_main(
        lambda: mw.progress.start(
            label=t("busy-reschedule-label"), max=total_cards, immediate=True
        )
    )

    busy_card_entries: List[BusyCard] = []
    skipped_cards = 0
    base_counts = defaultdict(int)
    candidate_set = set(candidate_days)
    busy_period_cards = 0

    for index, card in enumerate(window_cards, start=1):
        if index == 1 or index % 200 == 0:
            progress_count = index
            mw.taskman.run_on_main(
                lambda count=progress_count: mw.progress.update(
                    label=t(
                        "busy-reschedule-analyze-progress",
                        count=count,
                        total=total_cards,
                    ),
                    value=count,
                    max=total_cards,
                )
            )
        busy_entry = _build_busy_card(
            card=card,
            busy_end=busy_end,
        )
        if busy_entry is None:
            skipped_cards += 1
            continue
        true_due = busy_entry.original_due
        if true_due <= busy_end:
            busy_period_cards += 1
        elif true_due in candidate_set:
            base_counts[true_due] += 1
        busy_card_entries.append(busy_entry)

    mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=t(
                "busy-reschedule-analyze-progress",
                count=total_cards,
                total=total_cards,
            ),
            value=total_cards,
            max=total_cards,
        )
    )

    if not busy_card_entries:
        return {
            "count": 0,
            "skipped": skipped_cards,
            "busy_days": busy_days,
            "spread_days": spread_days,
        }

    undo_entry = mw.col.add_custom_undo_entry(t("busy-reschedule-label"))
    assignment_total = len(busy_card_entries)
    mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=t(
                "busy-reschedule-update-progress",
                count=0,
                total=assignment_total,
            ),
            value=0,
            max=assignment_total if assignment_total > 0 else 1,
        )
    )

    extra_cards = busy_period_cards
    extra_quota, extra_remainder = divmod(extra_cards, len(candidate_days))
    target_totals = {}
    for idx, day in enumerate(candidate_days):
        additional = extra_quota + (1 if idx < extra_remainder else 0)
        target_totals[day] = base_counts[day] + additional

    assignments = _allocate_busy_cards(busy_card_entries, candidate_days, target_totals)
    updated_count = _update_cards(assignments, assignment_total)
    if updated_count > 0:
        mw.col.merge_undo_entries(undo_entry)
    return {
        "count": updated_count,
        "skipped": skipped_cards,
        "busy_days": busy_days,
        "spread_days": spread_days,
    }


def reschedule_busy_period(did):
    if not mw.col.get_config("fsrs"):
        tooltip(t("enable-fsrs-warning"))
        return None
    params = _prompt_busy_parameters()
    if params is None:
        return None
    busy_days, spread_days = params
    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        result = future.result()
        elapsed = time.time() - start_time
        if result["count"] == 0:
            if result.get("skipped", 0) > 0:
                tooltip(
                    t(
                        "busy-reschedule-no-eligible",
                        skipped=result.get("skipped", 0),
                    )
                )
                return
            else:
                tooltip(t("busy-reschedule-no-cards"))
                return
        message_key = (
            "busy-reschedule-done-skipped"
            if result.get("skipped", 0) > 0
            else "busy-reschedule-done"
        )
        tooltip(
            t(
                message_key,
                count=result["count"],
                seconds=f"{elapsed:.2f}",
                skipped=result.get("skipped", 0),
                busy_days=result.get("busy_days", busy_days),
                spread_days=result.get("spread_days", spread_days),
            )
        )
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: _busy_reschedule_background(did, busy_days, spread_days), on_done
    )
    return fut
