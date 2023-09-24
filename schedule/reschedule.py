from ..utils import *
from ..configuration import Config
from anki.cards import Card
from .disperse_siblings import disperse_siblings_backgroud


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
    enable_fuzz: bool
    enable_load_balance: bool
    free_days: List[int]
    due_cnt_perday_from_first_day: Dict[int, int]
    learned_cnt_perday_from_today: Dict[int, int]
    card: Card
    elapsed_days: int

    def __init__(self) -> None:
        self.w = DEFAULT_FSRS_WEIGHTS
        self.enable_fuzz = False
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
        if not self.enable_fuzz or ivl < 2.5:
            return ivl
        ivl = int(round(ivl))
        min_ivl, max_ivl = get_fuzz_range(ivl, self.elapsed_days)
        self.elapsed_days = 0
        if self.enable_load_balance:
            min_num_cards = 18446744073709551616
            best_ivl = ivl
            step = (max_ivl - min_ivl) // 1000 + 1
            due = self.card.due if self.card.odid == 0 else self.card.odue
            for check_ivl in reversed(range(min_ivl, max_ivl + 1, step)):
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
        return int(self.fuzz_factor * (max_ivl - min_ivl + 1) + min_ivl)

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
    rescheduled_cards = set()
    deck_id_names = sorted(
        mw.col.decks.all_names_and_ids(), key=lambda item: item.name, reverse=True
    )
    fsrs = FSRS()
    fsrs.enable_fuzz = True
    if fsrs.enable_fuzz and config.load_balance:
        fsrs.set_load_balance()
    fsrs.free_days = config.free_days
    cancelled = False
    for deck_id_name in deck_id_names:
        deck_id, deck_name = deck_id_name.id, deck_id_name.name
        if cancelled:
            break
        if did is not None:
            if not deck_name.startswith(mw.col.decks.get(did)["name"]):
                continue
        cur_deck_param = get_current_deck_parameter(deck_id)
        if cur_deck_param is None:
            break
        fsrs.w = cur_deck_param["w"]
        query = f'"deck:{deck_name}" ("is:review" OR "is:learn") -"is:suspended"'
        if recent:
            query += f' "rated:{config.days_to_reschedule}"'
        for cid in mw.col.find_cards(query.replace("\\", "\\\\")):
            if cancelled:
                break
            if cid not in rescheduled_cards:
                rescheduled_cards.add(cid)
            else:
                continue
            if filter_flag and cid not in filtered_cids:
                continue
            card = reschedule_card(cid, fsrs, rollover, cur_deck_param)
            if card is None:
                continue
            mw.col.update_card(card)
            mw.col.merge_undo_entries(undo_entry)
            cnt += 1
            if cnt % 500 == 0:
                mw.taskman.run_on_main(
                    lambda: mw.progress.update(
                        value=cnt, label=f"{cnt} cards rescheduled"
                    )
                )
                if mw.progress.want_cancel():
                    cancelled = True

    return f"{cnt} cards rescheduled"


def get_current_deck_parameter(did):
    deck_config = mw.col.decks.config_dict_for_deck_id(did)
    return {
        "w": deck_config.get("fsrsWeights", [])
        if len(deck_config.get("fsrsWeights", [])) > 0
        else DEFAULT_FSRS_WEIGHTS,
        "m": deck_config.get("rev", dict()).get("maxIvl", 36500),
    }


def reschedule_card(cid, fsrs: FSRS, rollover, params):
    w, max_ivl = params.values()
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
    if not card.memory_state:
        print(card.id)
    card.memory_state.stability = s
    card.memory_state.difficulty = d
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
            again_ivl = fsrs.next_interval(again_s, card.desired_retention, max_ivl)
            hard_ivl = fsrs.next_interval(hard_s, card.desired_retention, max_ivl)
            good_ivl = fsrs.next_interval(good_s, card.desired_retention, max_ivl)
            easy_ivl = fsrs.next_interval(easy_s, card.desired_retention, max_ivl)
            easy_ivl = max(good_ivl + 1, easy_ivl)
        else:
            again_ivl = fsrs.next_interval(again_s, card.desired_retention, max_ivl)
            hard_ivl = fsrs.next_interval(hard_s, card.desired_retention, max_ivl)
            good_ivl = fsrs.next_interval(good_s, card.desired_retention, max_ivl)
            easy_ivl = fsrs.next_interval(easy_s, card.desired_retention, max_ivl)
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
