from ..utils import *
from ..configuration import Config
from anki.cards import Card, FSRSMemoryState
from .disperse_siblings import disperse_siblings_backgroud
from anki.decks import DeckManager
from anki.utils import ids2str


DEFAULT_FSRS_WEIGHTS = [
    0.4,
    0.6,
    2.4,
    5.8,
    4.93,
    0.94,
    0.86,
    0.01,
    1.49,
    0.14,
    0.94,
    2.18,
    0.05,
    0.34,
    1.26,
    0.29,
    2.61,
]


def constrain_difficulty(difficulty: float) -> float:
    return min(10.0, max(1.0, difficulty))


class FSRS:
    w: List[float]
    max_ivl: int
    dr: float
    enable_load_balance: bool
    free_days: List[int]
    due_cnt_perday_from_first_day: Dict[int, int]
    learned_cnt_perday_from_today: Dict[int, int]
    card: Card
    elapsed_days: int

    def __init__(self) -> None:
        self.w = DEFAULT_FSRS_WEIGHTS
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

    def init_stability(self, rating: int) -> float:
        return max(0.1, self.w[rating - 1])

    def init_difficulty(self, rating: int) -> float:
        return constrain_difficulty(self.w[4] - self.w[5] * (rating - 3))

    def next_difficulty(self, d: float, rating: int) -> float:
        new_d = d - self.w[6] * (rating - 3)
        return constrain_difficulty(self.mean_reversion(self.w[4], new_d))

    def mean_reversion(self, init: float, current: float) -> float:
        return self.w[7] * init + (1 - self.w[7]) * current

    def next_recall_stability(self, d: float, s: float, r: float, rating: int) -> float:
        hard_penalty = self.w[15] if rating == 2 else 1
        easy_bonus = self.w[16] if rating == 4 else 1
        return min(
            max(
                0.1,
                s
                * (
                    1
                    + math.exp(self.w[8])
                    * (11 - d)
                    * math.pow(s, -self.w[9])
                    * (math.exp((1 - r) * self.w[10]) - 1)
                    * hard_penalty
                    * easy_bonus
                ),
            ),
            36500,
        )

    def next_forget_stability(self, d: float, s: float, r: float) -> float:
        return min(
            max(
                0.1,
                self.w[11]
                * math.pow(d, -self.w[12])
                * (math.pow(s + 1, self.w[13]) - 1)
                * math.exp((1 - r) * self.w[14]),
            ),
            s,
        )

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

    rollover = mw.col.all_config()["rollover"]
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
                DM.config_dict_for_deck_id(x[1])["fsrsWeights"]
                if len(DM.config_dict_for_deck_id(x[1])["fsrsWeights"]) > 0
                else DEFAULT_FSRS_WEIGHTS,
            ]
        ),
        cards,
    )

    for cid, _, desired_retention, max_interval, wegihts in cards:
        if cancelled:
            break
        fsrs.w = wegihts
        fsrs.dr = desired_retention
        fsrs.max_ivl = max_interval
        card = reschedule_card(cid, fsrs, rollover)
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


def reschedule_card(cid, fsrs: FSRS, rollover):
    last_date = None
    last_s = None
    last_rating = None
    last_kind = None
    s = None
    d = None
    rating = None
    revlogs = filter_revlogs(mw.col.card_stats_data(cid).revlog)
    reps = len(revlogs)
    for i, revlog in enumerate(reversed(revlogs)):
        if (
            i == 0
            and (revlog.review_kind not in (REVLOG_LRN, REVLOG_RELRN))
            and not (has_again(revlogs) or has_manual_reset(revlogs))
        ):
            break
        last_s = s
        rating = revlog.button_chosen

        if (
            last_kind is not None
            and last_kind in (REVLOG_REV, REVLOG_RELRN)
            and revlog.review_kind == REVLOG_LRN
        ):
            # forget card
            last_date = None
            last_s = None
            s = None
            d = None
        last_kind = revlog.review_kind

        if last_kind == REVLOG_RESCHED:
            if revlog.ease != 0:
                # set due date
                continue
            else:
                # forget card
                last_date = None
                last_s = None
                s = None
                d = None
                continue

        if last_date is None:
            again_s = fsrs.init_stability(1)
            hard_s = fsrs.init_stability(2)
            good_s = fsrs.init_stability(3)
            easy_s = fsrs.init_stability(4)
            d = fsrs.init_difficulty(rating)
            s = fsrs.init_stability(rating)
            last_date = datetime.fromtimestamp(revlog.time - rollover * 60 * 60)
            last_rating = rating
        else:
            elapsed_days = (
                datetime.fromtimestamp(revlog.time - rollover * 60 * 60).toordinal()
                - last_date.toordinal()
            )
            if elapsed_days <= 0:
                continue
            r = power_forgetting_curve(elapsed_days, s)
            fsrs.elapsed_days = elapsed_days
            again_s = fsrs.next_forget_stability(fsrs.next_difficulty(d, 1), s, r)
            hard_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 2), s, r, 2)
            good_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 3), s, r, 3)
            easy_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 4), s, r, 4)
            d = fsrs.next_difficulty(d, rating)
            s = (
                fsrs.next_recall_stability(d, s, r, rating)
                if rating > 1
                else fsrs.next_forget_stability(d, s, r)
            )
            last_date = datetime.fromtimestamp(revlog.time - rollover * 60 * 60)
            last_rating = rating

    if rating is None or s is None:
        return None

    new_custom_data = {"v": "reschedule"}
    card = mw.col.get_card(cid)
    card.memory_state = FSRSMemoryState(stability=s, difficulty=d)
    seed = fsrs.set_fuzz_factor(cid, reps)
    if card.custom_data != "":
        old_custom_data = json.loads(card.custom_data)
        if "seed" in old_custom_data:
            fsrs.fuzz_factor = old_custom_data["seed"] / 10000
            new_custom_data["seed"] = old_custom_data["seed"]
    if "seed" not in new_custom_data:
        new_custom_data["seed"] = seed
    card.custom_data = json.dumps(new_custom_data)
    if card.type == CARD_TYPE_REV and last_kind != REVLOG_RESCHED:
        fsrs.set_card(card)
        if last_s is None:
            again_ivl = fsrs.next_interval(again_s, fsrs.dr, fsrs.max_ivl)
            hard_ivl = fsrs.next_interval(hard_s, fsrs.dr, fsrs.max_ivl)
            good_ivl = fsrs.next_interval(good_s, fsrs.dr, fsrs.max_ivl)
            easy_ivl = fsrs.next_interval(easy_s, fsrs.dr, fsrs.max_ivl)
            easy_ivl = max(good_ivl + 1, easy_ivl)
        else:
            again_ivl = fsrs.next_interval(again_s, fsrs.dr, fsrs.max_ivl)
            hard_ivl = fsrs.next_interval(hard_s, fsrs.dr, fsrs.max_ivl)
            good_ivl = fsrs.next_interval(good_s, fsrs.dr, fsrs.max_ivl)
            easy_ivl = fsrs.next_interval(easy_s, fsrs.dr, fsrs.max_ivl)
            hard_ivl = min(hard_ivl, good_ivl)
            good_ivl = max(hard_ivl + 1, good_ivl)
            easy_ivl = max(good_ivl + 1, easy_ivl)
        new_ivl = [again_ivl, hard_ivl, good_ivl, easy_ivl][last_rating - 1]
        due_before = max(card.odue if card.odid else card.due, mw.col.sched.today)
        card = update_card_due_ivl(card, revlogs[0], new_ivl)
        due_after = max(card.odue if card.odid else card.due, mw.col.sched.today)
        if fsrs.enable_load_balance:
            fsrs.due_cnt_perday_from_first_day[due_before] -= 1
            fsrs.due_cnt_perday_from_first_day[due_after] = (
                fsrs.due_cnt_perday_from_first_day.get(due_after, 0) + 1
            )
    return card
