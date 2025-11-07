import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
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
from aqt.qt import QInputDialog, QMessageBox
from aqt.utils import tooltip

from ..i18n import t
from ..utils import (
    get_decay,
    get_last_review_date_and_interval,
    power_forgetting_curve,
    update_card_due_ivl,
    write_custom_data,
)


@dataclass
class BreakCard:
    card: Card
    original_due: int
    last_review: int
    stability: float
    original_interval: int


def _get_log_path() -> Optional[Path]:
    try:
        profile_folder = mw.pm.profileFolder()
    except Exception:
        return None
    return Path(profile_folder) / "fsrs_schedule_break.log"


def _append_log_entry(log_path: Optional[Path], break_card: BreakCard, new_due: int):
    if log_path is None:
        return

    original_interval = break_card.original_interval
    new_interval = max(1, new_due - break_card.last_review)
    decay = -get_decay(break_card.card)
    retention_original = power_forgetting_curve(
        original_interval, break_card.stability, decay
    )
    retention_new = power_forgetting_curve(new_interval, break_card.stability, decay)

    header = (
        "card_id,stability,last_review,original_due,new_due,"
        "original_interval,new_interval,retention_original,retention_new\n"
    )
    line = (
        f"{break_card.card.id},{break_card.stability:.6f},{break_card.last_review},"
        f"{break_card.original_due},{new_due},{original_interval},{new_interval},"
        f"{retention_original:.6f},{retention_new:.6f}\n"
    )

    try:
        if not log_path.exists():
            log_path.write_text(header, encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(line)
    except OSError:
        pass


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


def _prompt_break_parameters():
    break_days, ok = QInputDialog.getInt(
        mw,
        t("schedule-break-dialog-title"),
        t("schedule-break-dialog-break-days"),
        value=3,
        min=1,
        max=60,
    )
    if not ok:
        return None
    spread_days, ok = QInputDialog.getInt(
        mw,
        t("schedule-break-dialog-title"),
        t("schedule-break-dialog-spread-days"),
        value=7,
        min=1,
        max=180,
    )
    if not ok:
        return None

    # Confirm with user about the impact
    reply = QMessageBox.question(
        mw,
        t("schedule-break-confirm-title"),
        t("schedule-break-confirm-message"),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return None

    return break_days, spread_days


def _fetch_window_cards(window_end: int, did_query: str) -> List[Card]:
    cids = mw.col.db.list(
        f"""
        SELECT id
        FROM cards
        WHERE type = {CARD_TYPE_REV}
        AND queue NOT IN ({QUEUE_TYPE_SUSPENDED}, {QUEUE_TYPE_NEW}, {QUEUE_TYPE_PREVIEW})
        {did_query}
        AND CASE WHEN odid==0 THEN due ELSE odue END <= {window_end}
    """
    )
    return [mw.col.get_card(cid) for cid in cids]


def _build_break_card(
    card: Card,
    break_end: int,
) -> Optional[BreakCard]:
    memory_state = _ensure_memory_state(card)
    if memory_state is None:
        return None
    last_review, _ = get_last_review_date_and_interval(card)
    true_due = card.odue if card.odid else card.due
    original_interval = max(1, true_due - last_review)

    return BreakCard(
        card=card,
        original_due=true_due,
        last_review=last_review,
        stability=memory_state.stability,
        original_interval=original_interval,
    )


def _allocate_break_cards(
    cards: List[BreakCard],
    candidate_days: List[int],
    target_totals: Dict[int, int],
    log_path: Optional[Path],
) -> Dict[int, List[BreakCard]]:
    assigned = defaultdict(list)
    sorted_cards = sorted(
        cards,
        key=lambda c: (c.original_interval, c.original_due),
    )

    if not candidate_days:
        return assigned

    remaining = {day: target_totals.get(day, 0) for day in candidate_days}

    for break_card in sorted_cards:
        earliest_day = max(candidate_days[0], break_card.original_due)
        feasible_days = [
            day
            for day in candidate_days
            if day >= earliest_day and remaining.get(day, 0) > 0
        ]

        if not feasible_days:
            feasible_days = [day for day in candidate_days if remaining.get(day, 0) > 0]

        if not feasible_days:
            continue

        def day_cost(day: int) -> tuple[float, int]:
            cost = abs(day - break_card.original_due) / break_card.original_interval
            return (cost, day)

        best_day = min(feasible_days, key=day_cost)
        remaining[best_day] -= 1
        assigned[best_day].append(break_card)
        _append_log_entry(log_path, break_card, best_day)
    return assigned


def _update_cards(assignments: Dict[int, List[BreakCard]], total: int) -> int:
    updated_cards = []
    processed = 0
    for due_day, cards in assignments.items():
        for break_card in cards:
            interval = max(1, due_day - break_card.last_review)
            update_card_due_ivl(break_card.card, interval)
            write_custom_data(break_card.card, "v", "reschedule")
            updated_cards.append(break_card.card)
            processed += 1
            if processed == 1 or processed % 200 == 0:
                progress_count = processed
                mw.taskman.run_on_main(
                    lambda count=progress_count, total_cards=total: mw.progress.update(
                        label=t(
                            "schedule-break-update-progress",
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
                "schedule-break-update-progress",
                count=total_cards,
                total=total_cards,
            ),
            value=total_cards,
            max=total_cards if total_cards > 0 else 1,
        )
    )
    return len(updated_cards)


def _schedule_break_background(did, break_days: int, spread_days: int):
    deck_manager = DeckManager(mw.col)
    today = mw.col.sched.today
    break_end = today + break_days - 1
    window_end = today + break_days + spread_days - 1

    candidate_days = list(range(break_end + 1, window_end + 1))
    if not candidate_days:
        return {"count": 0, "skipped": 0, "break_days": break_days}

    did_query = ""
    if did is not None:
        did_list = deck_manager.deck_and_child_ids(did)
        if not did_list:
            return {"count": 0, "skipped": 0, "break_days": break_days}
        did_query = (
            f"AND CASE WHEN odid==0 THEN did ELSE odid END IN {ids2str(did_list)}"
        )

    log_path = _get_log_path()
    if log_path and log_path.exists():
        try:
            log_path.unlink()
        except OSError:
            log_path = None

    window_cards = _fetch_window_cards(window_end, did_query)
    if not window_cards:
        return {"count": 0, "skipped": 0, "break_days": break_days}

    total_cards = len(window_cards)
    mw.taskman.run_on_main(
        lambda: mw.progress.start(
            label=t("schedule-break-label"), max=total_cards, immediate=True
        )
    )

    break_card_entries: List[BreakCard] = []
    skipped_cards = 0
    base_counts = defaultdict(int)
    candidate_set = set(candidate_days)
    break_period_cards = 0

    for index, card in enumerate(window_cards, start=1):
        if index == 1 or index % 200 == 0:
            progress_count = index
            mw.taskman.run_on_main(
                lambda count=progress_count: mw.progress.update(
                    label=t(
                        "schedule-break-analyze-progress",
                        count=count,
                        total=total_cards,
                    ),
                    value=count,
                    max=total_cards,
                )
            )
        break_entry = _build_break_card(
            card=card,
            break_end=break_end,
        )
        if break_entry is None:
            skipped_cards += 1
            continue
        true_due = break_entry.original_due
        if true_due <= break_end:
            break_period_cards += 1
        elif true_due in candidate_set:
            base_counts[true_due] += 1
        break_card_entries.append(break_entry)

    mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=t(
                "schedule-break-analyze-progress",
                count=total_cards,
                total=total_cards,
            ),
            value=total_cards,
            max=total_cards,
        )
    )

    if not break_card_entries:
        return {
            "count": 0,
            "skipped": skipped_cards,
            "break_days": break_days,
            "spread_days": spread_days,
        }

    undo_entry = mw.col.add_custom_undo_entry(t("schedule-break-label"))
    assignment_total = len(break_card_entries)
    mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=t(
                "schedule-break-update-progress",
                count=0,
                total=assignment_total,
            ),
            value=0,
            max=assignment_total if assignment_total > 0 else 1,
        )
    )

    extra_cards = break_period_cards
    extra_quota, extra_remainder = divmod(extra_cards, len(candidate_days))
    target_totals = {}
    for idx, day in enumerate(candidate_days):
        additional = extra_quota + (1 if idx < extra_remainder else 0)
        target_totals[day] = base_counts[day] + additional

    assignments = _allocate_break_cards(
        break_card_entries, candidate_days, target_totals, log_path
    )
    updated_count = _update_cards(assignments, assignment_total)
    if updated_count > 0:
        mw.col.merge_undo_entries(undo_entry)
    return {
        "count": updated_count,
        "skipped": skipped_cards,
        "break_days": break_days,
        "spread_days": spread_days,
    }


def schedule_break(did):
    if not mw.col.get_config("fsrs"):
        tooltip(t("enable-fsrs-warning"))
        return None
    params = _prompt_break_parameters()
    if params is None:
        return None
    break_days, spread_days = params
    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        result = future.result()
        elapsed = time.time() - start_time
        if result["count"] == 0:
            if result.get("skipped", 0) > 0:
                tooltip(
                    t(
                        "schedule-break-no-eligible",
                        skipped=result.get("skipped", 0),
                    )
                )
                return
            else:
                tooltip(t("schedule-break-no-cards"))
                return
        message_key = (
            "schedule-break-done-skipped"
            if result.get("skipped", 0) > 0
            else "schedule-break-done"
        )
        tooltip(
            t(
                message_key,
                count=result["count"],
                seconds=f"{elapsed:.2f}",
                skipped=result.get("skipped", 0),
                break_days=result.get("break_days", break_days),
                spread_days=result.get("spread_days", spread_days),
            )
        )
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: _schedule_break_background(did, break_days, spread_days), on_done
    )
    return fut
