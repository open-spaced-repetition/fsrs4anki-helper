from ..utils import *
from ..configuration import Config
from anki.cards import Card, FSRSMemoryState
from .disperse_siblings import disperse_siblings_backgroud
from anki.decks import DeckManager
from anki.utils import ids2str


class FSRS:
    max_ivl: int
    dr: float
    enable_load_balance: bool
    free_days: List[int]
    due_cnt_perday_from_first_day: Dict[int, int]
    learned_cnt_perday_from_today: Dict[int, int]
    card: Card
    elapsed_days: int

    def __init__(self) -> None:
        self.max_ivl = 36500
        self.dr = 0.9
        self.enable_load_balance = False
        self.free_days = []
        self.elapsed_days = 0

    def set_load_balance(self):
        self.enable_load_balance = True
        true_due = "CASE WHEN odid==0 THEN due ELSE odue END"
        self.due_cnt_perday_from_first_day = {
            day: cnt
            for day, cnt in mw.col.db.all(
                f"""SELECT {true_due}, count() 
                FROM cards 
                WHERE type = 2  
                AND queue != -1
                GROUP BY {true_due}"""
            )
        }
        for day in list(self.due_cnt_perday_from_first_day.keys()):
            if day < mw.col.sched.today:
                self.due_cnt_perday_from_first_day[mw.col.sched.today] = (
                    self.due_cnt_perday_from_first_day.get(mw.col.sched.today, 0)
                    + self.due_cnt_perday_from_first_day[day]
                )
                self.due_cnt_perday_from_first_day.pop(day)
        self.learned_cnt_perday_from_today = {
            day: cnt
            for day, cnt in mw.col.db.all(
                f"""SELECT (id/1000-{mw.col.sched.day_cutoff})/86400, count(distinct cid)
                FROM revlog
                WHERE ease > 0
                GROUP BY (id/1000-{mw.col.sched.day_cutoff})/86400"""
            )
        }

    def set_fuzz_factor(self, cid: int, reps: int):
        random.seed(cid + reps)
        self.fuzz_factor = random.random()
        return round(self.fuzz_factor * 10000, 0)

    def apply_fuzz(self, ivl):
        if ivl < 2.5:
            return ivl
        ivl = int(round(ivl))
        min_ivl, max_ivl = get_fuzz_range(ivl, self.elapsed_days)
        self.elapsed_days = 0
        if not self.enable_load_balance:
            return int(self.fuzz_factor * (max_ivl - min_ivl + 1) + min_ivl)
        else:
            min_num_cards = 18446744073709551616
            best_ivl = ivl
            step = (max_ivl - min_ivl) // 100 + 1
            due = self.card.due if self.card.odid == 0 else self.card.odue
            for check_ivl in reversed(range(min_ivl, max_ivl + step, step)):
                check_due = due + check_ivl - self.card.ivl
                day_offset = check_due - mw.col.sched.today
                due_date = datetime.now() + timedelta(days=day_offset)
                due_cards = self.due_cnt_perday_from_first_day.get(
                    max(check_due, mw.col.sched.today), 0
                )
                rated_cards = (
                    self.learned_cnt_perday_from_today.get(0, 0)
                    if day_offset <= 0
                    else 0
                )
                num_cards = due_cards + rated_cards
                if (
                    num_cards < min_num_cards
                    and due_date.weekday() not in self.free_days
                ):
                    best_ivl = check_ivl
                    min_num_cards = num_cards
            return best_ivl

    def next_interval(self, stability, retention, max_ivl):
        new_interval = self.apply_fuzz(9 * stability * (1 / retention - 1))
        return min(max(int(round(new_interval)), 1), max_ivl)

    def set_card(self, card: Card):
        self.card = card


def reschedule(
    did, recent=False, filter_flag=False, filtered_cids={}, filtered_nid_string=""
):
    if not mw.col.get_config("fsrs"):
        tooltip("Please enable FSRS first")
        return

    start_time = time.time()

    def on_done(future):
        mw.progress.finish()
        tooltip(f"{future.result()} in {time.time() - start_time:.2f} seconds")
        mw.col.reset()
        mw.reset()

    if filter_flag and len(filtered_cids) > 0:
        fut = mw.taskman.run_in_background(
            lambda: reschedule_background(did, recent, filter_flag, filtered_cids),
            on_done,
        )
        config = Config()
        config.load()
        if config.auto_disperse:
            text = fut.result()
            fut = mw.taskman.run_in_background(
                lambda: disperse_siblings_backgroud(
                    did, filter_flag, filtered_nid_string, text_from_reschedule=text
                ),
                on_done,
            )
    else:
        fut = mw.taskman.run_in_background(
            lambda: reschedule_background(did, recent, filter_flag, filtered_cids),
            on_done,
        )

    return fut


def reschedule_background(did, recent=False, filter_flag=False, filtered_cids={}):
    config = Config()
    config.load()

    undo_entry = mw.col.add_custom_undo_entry("Reschedule")
    mw.taskman.run_on_main(
        lambda: mw.progress.start(label="Rescheduling", immediate=False)
    )

    cnt = 0
    fsrs = FSRS()
    if config.load_balance:
        fsrs.set_load_balance()
        fsrs.free_days = config.free_days
    cancelled = False
    DM = DeckManager(mw.col)
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))
        did_query = f"AND did IN {did_list}"

    if recent:
        today_cutoff = mw.col.sched.day_cutoff
        day_before_cutoff = today_cutoff - (config.days_to_reschedule + 1) * 86400
        recent_query = (
            f"AND id IN (SELECT cid FROM revlog WHERE id >= {day_before_cutoff * 1000})"
        )

    if filter_flag:
        filter_query = f"AND id IN {ids2str(filtered_cids)}"

    cards = mw.col.db.all(
        f"""
        SELECT 
            id,
            CASE WHEN odid==0
            THEN did
            ELSE odid
            END
        FROM cards
        WHERE queue IN ({QUEUE_TYPE_REV}, {QUEUE_TYPE_REV}, {QUEUE_TYPE_DAY_LEARN_RELEARN})
        {did_query if did is not None else ""}
        {recent_query if recent else ""}
        {filter_query if filter_flag else ""}
    """
    )
    # x[0]: cid
    # x[1]: did
    # x[2]: desired retention
    # x[3]: max interval
    # x[4]: weights
    cards = map(
        lambda x: (
            x
            + [
                DM.config_dict_for_deck_id(x[1])["desiredRetention"],
                DM.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
            ]
        ),
        cards,
    )

    for cid, _, desired_retention, max_interval in cards:
        if cancelled:
            break
        fsrs.dr = desired_retention
        fsrs.max_ivl = max_interval
        card = reschedule_card(cid, fsrs, filter_flag)
        if card is None:
            continue
        mw.col.update_card(card)
        mw.col.merge_undo_entries(undo_entry)
        cnt += 1
        if cnt % 500 == 0:
            mw.taskman.run_on_main(
                lambda: mw.progress.update(value=cnt, label=f"{cnt} cards rescheduled")
            )
            if mw.progress.want_cancel():
                cancelled = True

    return f"{cnt} cards rescheduled"


def reschedule_card(cid, fsrs: FSRS, recompute=False):
    card = mw.col.get_card(cid)
    if recompute:
        memory_state = mw.col.compute_memory_state(cid)
        s = memory_state.stability
        d = memory_state.difficulty
        card.memory_state = FSRSMemoryState(stability=s, difficulty=d)
    else:
        memory_state = card.memory_state
        s = memory_state.stability
        d = memory_state.difficulty

    new_custom_data = {"v": "reschedule"}
    seed = fsrs.set_fuzz_factor(cid, card.reps)
    if card.custom_data != "":
        old_custom_data = json.loads(card.custom_data)
        if "seed" in old_custom_data:
            fsrs.fuzz_factor = old_custom_data["seed"] / 10000
            new_custom_data["seed"] = old_custom_data["seed"]
    if "seed" not in new_custom_data:
        new_custom_data["seed"] = seed
    card.custom_data = json.dumps(new_custom_data)

    try:
        revlog = filter_revlogs(mw.col.card_stats_data(cid).revlog)[0]
    except IndexError:
        return card

    if card.type == CARD_TYPE_REV and revlog.review_kind != REVLOG_RESCHED:
        fsrs.set_card(card)
        new_ivl = fsrs.next_interval(s, fsrs.dr, fsrs.max_ivl)
        due_before = max(card.odue if card.odid else card.due, mw.col.sched.today)
        card = update_card_due_ivl(card, revlog, new_ivl)
        due_after = max(card.odue if card.odid else card.due, mw.col.sched.today)
        if fsrs.enable_load_balance:
            fsrs.due_cnt_perday_from_first_day[due_before] -= 1
            fsrs.due_cnt_perday_from_first_day[due_after] = (
                fsrs.due_cnt_perday_from_first_day.get(due_after, 0) + 1
            )
    return card
