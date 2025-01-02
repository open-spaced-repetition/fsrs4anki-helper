from aqt import QAction, browser

from .disperse_siblings import disperse_siblings
from ..utils import *
from ..configuration import Config
from anki.cards import Card, FSRSMemoryState
from anki.decks import DeckManager
from anki.utils import ids2str
from aqt.gui_hooks import browser_menus_did_init


def check_review_distribution(actual_reviews: List[int], percentages: List[float]):
    if sum(percentages) == 0:
        return [1] * len(actual_reviews)
    total_actual = sum(actual_reviews)
    expected_distribution = [p * (total_actual / sum(percentages)) for p in percentages]
    return [max(e - a, 0) for a, e in zip(actual_reviews, expected_distribution)]


class FSRS:
    reschedule_threshold: float
    maximum_interval: int
    desired_retention: float
    easy_specific_due_dates: List[int]
    due_cnt_per_day_per_preset: Dict[int, Dict[int, int]]
    due_today_per_preset: Dict[int, int]
    reviewed_today_per_preset: Dict[int, int]
    card: Card
    elapsed_days: int
    apply_easy_days: bool
    current_date: date
    today: int
    did: int
    did_to_preset_id: Dict[int, int]
    preset_id_to_easy_days_percentages: Dict[int, List[float]]

    def __init__(self) -> None:
        self.reschedule_threshold = 0
        self.maximum_interval = 36500
        self.desired_retention = 0.9
        self.easy_specific_due_dates = []
        self.elapsed_days = 0
        self.apply_easy_days = False
        self.current_date = sched_current_date()
        self.today = mw.col.sched.today
        self.DM = DeckManager(mw.col)

    def set_load_balance(self, did_query=None):
        true_due = "CASE WHEN odid==0 THEN due ELSE odue END"
        original_did = "CASE WHEN odid==0 THEN did ELSE odid END"

        deck_stats = mw.col.db.all(
            f"""SELECT {original_did}, {true_due}, count() 
                FROM cards 
                WHERE type = 2  
                AND queue != -1
                {did_query if did_query is not None else ""}
                GROUP BY {original_did}, {true_due}"""
        )

        self.due_cnt_per_day_per_preset = defaultdict(lambda: defaultdict(int))
        self.did_to_preset_id = {}
        self.preset_id_to_easy_days_percentages = {}

        for did, due_date, count in deck_stats:
            preset_id = self.DM.config_dict_for_deck_id(did)["id"]
            self.due_cnt_per_day_per_preset[preset_id][due_date] += count
            self.did_to_preset_id[did] = preset_id
            self.preset_id_to_easy_days_percentages[preset_id] = (
                self.DM.config_dict_for_deck_id(did)["easyDaysPercentages"]
            )

        self.due_today_per_preset = defaultdict(
            int,
            {
                preset_id: sum(
                    due_cnt for due, due_cnt in config_dues.items() if due <= self.today
                )
                for preset_id, config_dues in self.due_cnt_per_day_per_preset.items()
            },
        )

        reviewed_stats = mw.col.db.all(
            f"""SELECT {original_did}, count(distinct revlog.cid)
                FROM revlog
                JOIN cards ON revlog.cid = cards.id
                WHERE revlog.ease > 0
                AND (revlog.type < 3 OR revlog.factor != 0)
                AND revlog.id/1000 >= {mw.col.sched.day_cutoff - 86400}
                GROUP BY {original_did}
            """
        )

        self.reviewed_today_per_preset = defaultdict(int)

        for did, count in reviewed_stats:
            preset_id = self.DM.config_dict_for_deck_id(did)["id"]
            self.reviewed_today_per_preset[preset_id] += count

    @property
    def preset_id(self):
        return self.did_to_preset_id[self.did]

    @property
    def due_cnt_per_day(self):
        return self.due_cnt_per_day_per_preset[self.preset_id]

    def update_due_cnt_per_day(self, due_before: int, due_after: int):
        self.due_cnt_per_day_per_preset[self.preset_id][due_before] -= 1
        self.due_cnt_per_day_per_preset[self.preset_id][due_after] += 1
        if due_before <= self.today and due_after > self.today:
            self.due_today -= 1
        if due_before > self.today and due_after <= self.today:
            self.due_today += 1

    @property
    def due_today(self):
        return self.due_today_per_preset[self.preset_id]

    @due_today.setter
    def due_today(self, value):
        self.due_today_per_preset[self.preset_id] = value

    @property
    def reviewed_today(self):
        return self.reviewed_today_per_preset[self.preset_id]

    @property
    def easy_days_review_ratio_list(self):
        easy_days_percentages = self.preset_id_to_easy_days_percentages[self.preset_id]
        return easy_days_percentages if easy_days_percentages else [1] * 7

    def set_fuzz_factor(self, cid: int, reps: int):
        random.seed(rotate_number_by_k(cid, 8) + reps)
        self.fuzz_factor = random.random()

    def load_balance(
        self,
        possible_intervals: List[int],
        review_cnts: List[int],
        last_review: int,
    ):
        if (
            len(set(self.easy_days_review_ratio_list)) == 1
            and len(self.easy_specific_due_dates) == 0
        ):
            return possible_intervals[review_cnts.index(min(review_cnts))]

        weights = [
            1 if r == 0 else (1 / (r**2)) * (1 / delta_t)
            for r, delta_t in zip(review_cnts, possible_intervals)
        ]

        possible_dates = [
            self.current_date + timedelta(days=(last_review + i - self.today))
            for i in possible_intervals
        ]
        weekdays = [date.weekday() for date in possible_dates]

        mask = check_review_distribution(
            review_cnts, [self.easy_days_review_ratio_list[wd] for wd in weekdays]
        )
        for idx, ivl in enumerate(possible_intervals):
            if last_review + ivl in self.easy_specific_due_dates:
                mask[idx] = False
        final_weights = [w * m for w, m in zip(weights, mask)]

        if sum(final_weights) > 0:
            return random.choices(possible_intervals, weights=final_weights)[0]
        else:
            return random.choices(possible_intervals, weights=weights)[0]

    def apply_fuzz(self, ivl):
        if ivl < 2.5:
            return ivl
        min_ivl, max_ivl = get_fuzz_range(ivl, self.elapsed_days, self.maximum_interval)
        self.elapsed_days = 0

        # Load balance
        due = self.card.odue if self.card.odid else self.card.due
        last_review = get_last_review_date(self.card)

        if self.apply_easy_days:
            if due > last_review + max_ivl + 2:
                current_ivl = due - last_review
                min_ivl, max_ivl = get_fuzz_range(
                    current_ivl, self.elapsed_days, current_ivl
                )

        if last_review + max_ivl < self.today:
            return min(ivl, max_ivl)

        min_ivl = max(min_ivl, self.today - last_review)

        possible_intervals = list(range(min_ivl, max_ivl + 1))
        review_cnts = []
        for i in possible_intervals:
            check_due = last_review + i
            if check_due > self.today:
                review_cnts.append(self.due_cnt_per_day[check_due])
            else:
                review_cnts.append(self.due_today + self.reviewed_today)

        best_ivl = self.load_balance(
            possible_intervals,
            review_cnts,
            last_review,
        )
        return best_ivl

    def fuzzed_next_interval(self, stability):
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
    fsrs.reschedule_threshold = config.reschedule_threshold
    did_query = None
    if did is not None:
        did_list = ids2str(fsrs.DM.deck_and_child_ids(did))
        did_query = f"AND did IN {did_list}"

    fsrs.set_load_balance(did_query=did_query)
    fsrs.easy_specific_due_dates = easy_specific_due_dates
    fsrs.apply_easy_days = apply_easy_days

    for easy_date_str in config.easy_dates:
        easy_date = datetime.strptime(easy_date_str, "%Y-%m-%d").date()
        specific_due = fsrs.today + (easy_date - fsrs.current_date).days
        if specific_due not in fsrs.easy_specific_due_dates:
            fsrs.easy_specific_due_dates.append(specific_due)

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
        AND id NOT IN (
                    SELECT cid
                    FROM revlog
                    GROUP BY cid
                    HAVING MAX(CASE WHEN type = 4 THEN id ELSE NULL END) = MAX(id)
                )
        ORDER BY ivl
    """
    )
    total_cnt = len(cid_did_nid)
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
                fsrs.DM.config_dict_for_deck_id(x[1])["desiredRetention"],
                fsrs.DM.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
            ]
        ),
        cid_did_nid,
    )
    cnt = 0
    cancelled = False
    rescheduled_cards = []
    filtered_nids = set()
    undo_entry = mw.col.add_custom_undo_entry("Reschedule")
    for cid, did, nid, desired_retention, maximum_interval in cards:
        if cancelled:
            break
        fsrs.desired_retention = desired_retention
        fsrs.maximum_interval = maximum_interval
        fsrs.did = did
        card = reschedule_card(cid, fsrs, filter_flag)
        if card is None:
            continue
        rescheduled_cards.append(card)
        filtered_nids.add(nid)
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

    mw.col.update_cards(rescheduled_cards)
    mw.col.merge_undo_entries(undo_entry)
    finish_text = f"{cnt} cards rescheduled"

    if config.auto_disperse_after_reschedule:
        filtered_nid_string = ids2str(filtered_nids)
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

    write_custom_data(card, "v", "reschedule")

    if card.type == CARD_TYPE_REV:
        fsrs.set_card(card)
        fsrs.set_fuzz_factor(cid, card.reps)
        new_ivl = fsrs.fuzzed_next_interval(s)

        if fsrs.reschedule_threshold > 0 and not fsrs.apply_easy_days:
            dr = fsrs.desired_retention
            odds = dr / (1 - dr)

            odds_lower = (1 - fsrs.reschedule_threshold) * odds
            dr_lower = odds_lower / (odds_lower + 1)
            adjusted_ivl_upper = next_interval(s, dr_lower)

            odds_upper = (1 + fsrs.reschedule_threshold) * odds
            dr_upper = odds_upper / (odds_upper + 1)
            adjusted_ivl_lower = next_interval(s, dr_upper)

            if card.ivl >= adjusted_ivl_lower and card.ivl <= adjusted_ivl_upper:
                return None

        due_before = card.odue if card.odid else card.due
        card = update_card_due_ivl(card, new_ivl)
        due_after = card.odue if card.odid else card.due
        fsrs.update_due_cnt_per_day(due_before, due_after)

    return card


def reschedule_browser_selected_cards(browser: browser.Browser):
    cids = browser.selected_cards()
    reschedule(did=None, recent=False, filter_flag=True, filtered_cids=cids)


@browser_menus_did_init.append
def on_browser_menus_did_init(browser: browser.Browser):
    action = QAction("FSRS: Update memory state and reschedule", browser)
    action.triggered.connect(lambda: reschedule_browser_selected_cards(browser))
    browser.form.menu_Cards.addSeparator()
    browser.form.menu_Cards.addAction(action)
