import json
import math
import random
from datetime import datetime, timedelta
from aqt import mw
from anki import scheduler
from .utils import *
from .configuration import Config


def has_again(revlog):
    for r in revlog:
        if r.button_chosen == 1:
            return True
    return False


def constrain_difficulty(difficulty: float) -> float:
    return min(10., max(1., difficulty))


class FSRS:
    w: list[float]
    enable_fuzz: bool
    enable_load_balance: bool
    free_days: list

    def __init__(self) -> None:
        self.w = [1., 1., 5., -0.5, -0.5, 0.2, 1.4, -0.12, 0.8, 2., -0.2, 0.2, 1.]
        self.enable_fuzz = False
        self.enable_load_balance = False
        self.free_days = []

    def init_stability(self, rating: int) -> float:
        return max(0.1, self.w[0] + self.w[1] * (rating - 1))

    def init_difficulty(self, rating: int) -> float:
        return constrain_difficulty(self.w[2] + self.w[3] * (rating - 3))

    def next_difficulty(self, d: float, rating: int) -> float:
        new_d = d + self.w[4] * (rating - 3)
        return constrain_difficulty(self.mean_reversion(self.w[2], new_d))

    def mean_reversion(self, init: float, current: float) -> float:
        return self.w[5] * init + (1 - self.w[5]) * current

    def next_recall_stability(self, d: float, s: float, r: float) -> float:
        return s * (1 + math.exp(self.w[6]) * (11 - d) * math.pow(s, self.w[7]) * (math.exp((1 - r) * self.w[8]) - 1))

    def next_forget_stability(self, d: float, s: float, r: float) -> float:
        return self.w[9] * math.pow(d, self.w[10]) * math.pow(s, self.w[11]) * math.exp((1 - r) * self.w[12])

    def set_fuzz_factor(self, cid: int, reps: int):
        random.seed(cid + reps)
        self.fuzz_factor = random.random()
        return round(self.fuzz_factor * 10000, 0)

    def apply_fuzz(self, ivl):
        if not self.enable_fuzz or ivl < 2.5:
            return ivl
        ivl = int(round(ivl))
        min_ivl = max(2, int(round(ivl * 0.95 - 1)))
        max_ivl = int(round(ivl * 1.05 + 1))
        if self.enable_load_balance:
            min_num_cards = 18446744073709551616
            best_ivl = ivl
            for check_ivl in reversed(range(min_ivl, max_ivl + 1)):
                due_date = datetime.now() + timedelta(days=self.card.due + check_ivl - self.card.ivl - mw.col.sched.today)
                num_cards = mw.col.db.scalar("select count() from cards where due = ? and queue = 2", self.card.due + check_ivl - self.card.ivl)
                if num_cards < min_num_cards and due_date.weekday() not in self.free_days:
                    best_ivl = check_ivl
                    min_num_cards = num_cards
            return best_ivl
        return int(self.fuzz_factor * (max_ivl - min_ivl + 1) + min_ivl)

    def next_interval(self, stability, retention, max_ivl):
        new_interval = self.apply_fuzz(stability * math.log(retention) / math.log(0.9))
        return min(max(int(round(new_interval)), 1), max_ivl)

    def set_card(self, card):
        self.card = card


def reschedule(did):
    config = Config()
    config.load()
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    global_deck_name = get_global_config_deck_name(version)
    rollover = mw.col.all_config()['rollover']

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    cnt = 0
    rescheduled_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    fsrs = FSRS()
    fsrs.enable_fuzz = get_fuzz_bool(custom_scheduler)
    fsrs.enable_load_balance = config.load_balance
    fsrs.free_days = config.free_days

    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            rescheduled_cards = rescheduled_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        (
            w,
            retention,
            max_ivl,
            easy_bonus,
            hard_factor,
        ) = deck_parameters[global_deck_name].values()
        for name, params in deck_parameters.items():
            if deck['name'].startswith(name):
                w, retention, max_ivl, easy_bonus, hard_factor = params.values()
                break
        fsrs.w = w
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\" -\"is:learn\" -\"is:suspended\""):
            if cid not in rescheduled_cards:
                rescheduled_cards.add(cid)
            else:
                continue
            last_date = None
            last_s = None
            last_rating = None
            s = None
            d = None
            rating = None
            revlogs = mw.col.card_stats_data(cid).revlog
            reps = len(revlogs)
            for i, revlog in enumerate(reversed(revlogs)):
                if i == 0 and (revlog.review_kind not in (0, 2)) and not has_again(revlogs):
                    break
                last_s = s
                rating = revlog.button_chosen
                if rating == 0:
                    if revlog.ease != 0:
                        # set due date
                        continue
                    else:
                        # forget card
                        last_date = None
                        last_s = None
                        s = None
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
                    ivl = datetime.fromtimestamp(revlog.time - rollover * 60 * 60).toordinal() - last_date.toordinal()
                    if ivl <= 0 and (revlog.review_kind == 0 or revlog.review_kind == 2):
                        continue
                    r = math.pow(0.9, ivl / s)
                    again_s = fsrs.next_forget_stability(fsrs.next_difficulty(d, 1), s, r)
                    hard_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 2), s, r)
                    good_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 3), s, r)
                    easy_s = fsrs.next_recall_stability(fsrs.next_difficulty(d, 4), s, r)
                    d = fsrs.next_difficulty(d, rating)
                    s = fsrs.next_recall_stability(d, s, r) if rating > 1 else fsrs.next_forget_stability(d, s, r)
                    last_date = datetime.fromtimestamp(revlog.time - rollover * 60 * 60)
                    last_rating = rating
            if rating is None or s is None:
                continue
            new_custom_data = {"s": round(s, 2), "d": round(d, 2), "v": "helper"}
            card = mw.col.get_card(cid)
            seed = fsrs.set_fuzz_factor(cid, reps)
            if card.custom_data != "":
                old_custom_data = json.loads(card.custom_data)
                if "seed" in old_custom_data:
                    new_custom_data["seed"] = old_custom_data["seed"]
            if "seed" not in new_custom_data:
                new_custom_data["seed"] = seed
            card.custom_data = json.dumps(new_custom_data)
            fsrs.set_card(card)
            if last_s is None:
                again_ivl = fsrs.next_interval(again_s, retention, max_ivl)
                hard_ivl = fsrs.next_interval(hard_s, retention, max_ivl)
                good_ivl = fsrs.next_interval(good_s, retention, max_ivl)
                easy_ivl = fsrs.next_interval(easy_s * easy_bonus, retention, max_ivl)
                easy_ivl = max(good_ivl + 1, easy_ivl)
            else:
                again_ivl = fsrs.next_interval(again_s, retention, max_ivl)
                hard_ivl = fsrs.next_interval(last_s * hard_factor, retention, max_ivl)
                good_ivl = fsrs.next_interval(good_s, retention, max_ivl)
                easy_ivl = fsrs.next_interval(easy_s * easy_bonus, retention, max_ivl)
                hard_ivl = min(hard_ivl, good_ivl)
                good_ivl = max(hard_ivl + 1, good_ivl)
                easy_ivl = max(good_ivl + 1, easy_ivl)
            if rating == 0:
                new_ivl = card.ivl
            else:
                new_ivl = [again_ivl, hard_ivl, good_ivl, easy_ivl][last_rating - 1]
            offset = new_ivl - card.ivl
            card.ivl = new_ivl
            if card.odid:  # Also update cards in filtered decks
                card.odue += offset
            else:
                card.due += offset
            card.flush()
            cnt += 1

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_(f"""{cnt} card rescheduled"""))
