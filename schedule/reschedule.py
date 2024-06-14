from typing import Set
from aqt import QAction, browser

from .disperse_siblings import disperse_siblings
from ..utils import *
from ..configuration import Config
from anki.cards import Card, FSRSMemoryState
from anki.decks import DeckManager
from anki.utils import ids2str
from aqt.gui_hooks import browser_menus_did_init
from collections import defaultdict


class FSRS:
    maximum_interval: int
    desired_retention: float
    enable_load_balance: bool
    easy_days: List[int]
    easy_days_review_ratio: float
    p_obey_easy_days: float
    easy_specific_due_dates: List[int]
    p_obey_specific_due_dates: float
    due_cnt_perday_from_first_day: Dict[int, int]
    backlog: int
    learned_cnt_today: int
    card: Card
    elapsed_days: int
    allow_to_past: bool
    apply_easy_days: bool

    def __init__(self) -> None:
        self.maximum_interval = 36500
        self.desired_retention = 0.9
        self.enable_load_balance = False
        self.easy_days = []
        self.easy_days_review_ratio = 0
        self.p_obey_easy_days = 1
        self.easy_specific_due_dates = []
        self.p_obey_specific_due_dates = 1
        self.elapsed_days = 0
        self.allow_to_past = True
        self.apply_easy_days = False

    def set_load_balance(self, did_query=None):
        self.enable_load_balance = True
        true_due = "CASE WHEN odid==0 THEN due ELSE odue END"
        self.due_cnt_perday_from_first_day = defaultdict(
            int,
            {
                day: cnt
                for day, cnt in mw.col.db.all(
                    f"""SELECT {true_due}, count() 
                        FROM cards 
                        WHERE type = 2  
                        AND queue != -1
                        {did_query if did_query is not None else ""}
                        GROUP BY {true_due}"""
                )
            },
        )
        self.backlog = sum(
            due_cnt
            for due, due_cnt in self.due_cnt_perday_from_first_day.items()
            if due <= mw.col.sched.today
        )
        self.learned_cnt_today = mw.col.db.scalar(
            f"""SELECT count(distinct cid)
            FROM revlog
            WHERE ease > 0
            AND (type < 3 OR factor != 0)
            AND id >= {mw.col.sched.day_cutoff * 1000}"""
        )

    def set_fuzz_factor(self, cid: int, reps: int):
        random.seed(rotate_number_by_k(cid, 8) + reps)
        self.fuzz_factor = random.random()

    def apply_fuzz(self, ivl):
        if ivl < 2.5:
            return ivl
        min_ivl, max_ivl = get_fuzz_range(ivl, self.elapsed_days, self.maximum_interval)
        self.elapsed_days = 0
        if not self.enable_load_balance:
            if int_version() >= 231001:
                return ivl + mw.col.fuzz_delta(self.card.id, ivl)
            else:
                return int(self.fuzz_factor * (max_ivl - min_ivl + 1) + min_ivl)
        else:
            # Load balance
            due = self.card.odue if self.card.odid else self.card.due
            if due - self.card.ivl + max_ivl < mw.col.sched.today:
                # If the latest possible due date is in the past, don't load balance
                return ivl

            if self.apply_easy_days:
                last_review = get_last_review_date(self.card)
                if due > last_review + max_ivl + 2:
                    current_ivl = due - last_review
                    min_ivl, max_ivl = get_fuzz_range(
                        current_ivl, self.elapsed_days, current_ivl
                    )

            min_workload = math.inf
            best_ivl = (max_ivl + min_ivl) // 2 if self.allow_to_past else max_ivl
            step = (max_ivl - min_ivl) // 100 + 1

            if self.easy_days_review_ratio == 0:
                obey_easy_days = True
                obey_specific_due_dates = True
            else:
                obey_easy_days = random.random() < self.p_obey_easy_days
                obey_specific_due_dates = (
                    random.random() < self.p_obey_specific_due_dates
                )

            for check_ivl in reversed(range(min_ivl, max_ivl + step, step)):
                check_due = due - self.card.ivl + check_ivl
                if (
                    obey_specific_due_dates
                    and check_due in self.easy_specific_due_dates
                ):
                    continue

                day_offset = check_due - mw.col.sched.today
                if not self.allow_to_past and day_offset < 0:
                    break

                due_date = sched_current_date() + timedelta(days=day_offset)
                if obey_easy_days and due_date.weekday() in self.easy_days:
                    continue

                if check_due > mw.col.sched.today:
                    # If the due date is in the future, the workload is the number of cards due on that day
                    workload = self.due_cnt_perday_from_first_day[check_due]
                else:
                    # If the due date is in the past or today, the workload is the number of cards due today plus the number of cards learned today
                    workload = self.backlog + self.learned_cnt_today
                if workload < min_workload:
                    best_ivl = check_ivl
                    min_workload = workload
            return best_ivl

    def next_interval(self, stability):
        new_interval = next_interval(stability, self.desired_retention)
        return self.apply_fuzz(new_interval)

    def set_card(self, card: Card):
        self.card = card


def reschedule(
    did,
    recent=False,
    filter_flag=False,
    filtered_cids={},
    easy_specific_due_dates=[],
    apply_easy_days=False,
):
    if not mw.col.get_config("fsrs"):
        tooltip(FSRS_ENABLE_WARNING)
        return None

    start_time = time.time()

    def on_done(future):
        config = Config()
        config.load()
        if config.auto_disperse_after_reschedule:
            finish_text, filtered_nid_string = future.result()
            mw.progress.finish()
            mw.reset()
            disperse_siblings(did, True, filtered_nid_string, finish_text)
        else:
            finish_text = future.result()
            mw.progress.finish()
            tooltip(f"{finish_text} in {time.time() - start_time:.2f} seconds")
            mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: reschedule_background(
            did,
            recent,
            filter_flag,
            filtered_cids,
            easy_specific_due_dates,
            apply_easy_days,
        ),
        on_done,
    )

    return fut


def reschedule_background(
    did,
    recent=False,
    filter_flag=False,
    filtered_cids={},
    easy_specific_due_dates=[],
    apply_easy_days=False,
):
    config = Config()
    config.load()

    fsrs = FSRS()
    DM = DeckManager(mw.col)
    did_query = None
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))
        did_query = f"AND did IN {did_list}"

    if config.load_balance:
        fsrs.set_load_balance(did_query=did_query)
        fsrs.easy_days = config.easy_days
        fsrs.easy_days_review_ratio = config.easy_days_review_ratio
        fsrs.p_obey_easy_days = p_obey_easy_days(
            len(fsrs.easy_days), fsrs.easy_days_review_ratio
        )
        fsrs.easy_specific_due_dates = easy_specific_due_dates

        current_date = sched_current_date()
        today = mw.col.sched.today
        for easy_date_str in config.easy_dates:
            easy_date = datetime.strptime(easy_date_str, "%Y-%m-%d").date()
            specific_due = today + (easy_date - current_date).days
            if specific_due not in fsrs.easy_specific_due_dates:
                fsrs.easy_specific_due_dates.append(specific_due)

        fsrs.p_obey_specific_due_dates = obey_specific_due_dates(
            len(fsrs.easy_specific_due_dates), fsrs.easy_days_review_ratio
        )
        if len(easy_specific_due_dates) > 0:
            fsrs.allow_to_past = False
        fsrs.apply_easy_days = apply_easy_days

    if recent:
        today_cutoff = mw.col.sched.day_cutoff
        day_before_cutoff = today_cutoff - (config.days_to_reschedule + 1) * 86400
        recent_query = f"""AND id IN 
            (
                SELECT cid 
                FROM revlog 
                WHERE id >= {day_before_cutoff * 1000}
                AND ease > 0
                AND (type < 3 OR factor != 0)
            )
            """

    if filter_flag:
        filter_query = f"AND id IN {ids2str(filtered_cids)}"

    cid_did_nid = mw.col.db.all(
        f"""
        SELECT 
            id,
            CASE WHEN odid==0
            THEN did
            ELSE odid
            END,
            nid
        FROM cards
        WHERE queue IN ({QUEUE_TYPE_LRN}, {QUEUE_TYPE_REV}, {QUEUE_TYPE_DAY_LEARN_RELEARN})
        {did_query if did_query is not None else ""}
        {recent_query if recent else ""}
        {filter_query if filter_flag else ""}
        ORDER BY ivl
    """
    )
    total_cnt = len(cid_did_nid)
    undo_entry = mw.col.add_custom_undo_entry("Reschedule")
    mw.taskman.run_on_main(
        lambda: mw.progress.start(label="Rescheduling", max=total_cnt, immediate=True)
    )
    # x[0]: cid
    # x[1]: did
    # x[2]: nid
    # x[3]: desired retention
    # x[4]: max interval
    cards = map(
        lambda x: (
            x
            + [
                DM.config_dict_for_deck_id(x[1])["desiredRetention"],
                DM.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
            ]
        ),
        cid_did_nid,
    )
    cnt = 0
    cancelled = False
    for cid, _, _, desired_retention, maximum_interval in cards:
        if cancelled:
            break
        fsrs.desired_retention = desired_retention
        fsrs.maximum_interval = maximum_interval
        card = reschedule_card(cid, fsrs, filter_flag)
        if card is None:
            continue
        mw.col.update_card(card)
        mw.col.merge_undo_entries(undo_entry)
        cnt += 1
        if cnt % 500 == 0:
            mw.taskman.run_on_main(
                lambda: mw.progress.update(
                    label=f"{cnt}/{total_cnt} cards rescheduled",
                    value=cnt,
                    max=total_cnt,
                )
            )
            if mw.progress.want_cancel():
                cancelled = True

    finish_text = f"{cnt} cards rescheduled"

    if config.auto_disperse_after_reschedule:
        filtered_nid_string = ids2str(set(map(lambda x: x[2], cid_did_nid)))
        return (finish_text, filtered_nid_string)

    return finish_text


def reschedule_card(cid, fsrs: FSRS, recompute=False):
    card = mw.col.get_card(cid)
    if recompute:
        memory_state = mw.col.compute_memory_state(cid)
        s = memory_state.stability
        d = memory_state.difficulty
        if s is None or d is None:
            return None
        card.memory_state = FSRSMemoryState(stability=s, difficulty=d)
    elif card.memory_state:
        memory_state = card.memory_state
        s = memory_state.stability
        d = memory_state.difficulty
    else:
        return None

    new_custom_data = {"v": "reschedule"}
    card.custom_data = json.dumps(new_custom_data)

    if card.type == CARD_TYPE_REV:
        fsrs.set_card(card)
        fsrs.set_fuzz_factor(cid, card.reps)
        new_ivl = fsrs.next_interval(s)
        due_before = card.odue if card.odid else card.due
        card = update_card_due_ivl(card, new_ivl)
        due_after = card.odue if card.odid else card.due
        if fsrs.enable_load_balance:
            fsrs.due_cnt_perday_from_first_day[due_before] -= 1
            fsrs.due_cnt_perday_from_first_day[due_after] += 1
            if due_before <= mw.col.sched.today and due_after > mw.col.sched.today:
                fsrs.backlog -= 1
            if due_before > mw.col.sched.today and due_after <= mw.col.sched.today:
                fsrs.backlog += 1
    return card


def reschedule_browser_selected_cards(browser: browser.Browser):
    cids = browser.selected_cards()
    reschedule(None, False, True, cids)


@browser_menus_did_init.append
def on_browser_menus_did_init(browser: browser.Browser):
    action = QAction("FSRS: Update memory state and reschedule", browser)
    action.triggered.connect(lambda: reschedule_browser_selected_cards(browser))
    browser.form.menu_Cards.addSeparator()
    browser.form.menu_Cards.addAction(action)
