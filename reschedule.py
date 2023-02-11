import json
import math
import random
from datetime import datetime
from aqt import mw
from .utils import *


def constrain_difficulty(difficulty: float) -> float:
    return min(10., max(1., difficulty))


class FSRS:
    def __init__(self, w: list[float]) -> None:
        self.w = w
        self.enable_fuzz = False

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
        ivl = round(ivl, 0)
        min_ivl = max(2, round(ivl * 0.95 - 1, 0))
        max_ivl = round(ivl * 1.05 + 1)
        return int(self.fuzz_factor * (max_ivl - min_ivl + 1) + min_ivl)

    def next_interval(self, stability, retention, max_ivl):
        new_interval = self.apply_fuzz(stability * math.log(retention) / math.log(0.9))
        return min(max(int(round(new_interval)), 1), max_ivl)


def reschedule(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    rollover = mw.col.all_config()['rollover']
    enable_fuzz = get_fuzz_bool(custom_scheduler)

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    cnt = 0
    rescheduled_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if any([deck['name'].startswith(i) for i in skip_decks]):
            rescheduled_cards = rescheduled_cards.union(mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""))
            continue
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        w = deck_parameters['global']['w']
        retention = deck_parameters['global']['r']
        max_ivl = deck_parameters['global']['m']
        easy_bonus = deck_parameters['global']['e']
        hard_factor = deck_parameters['global']['h']
        for key, value in deck_parameters.items():
            if deck['name'].startswith(key):
                w = value['w']
                retention = value['r']
                max_ivl = value['m']
                easy_bonus = value['e']
                hard_factor = value['h']
                break
        scheduler = FSRS(w)
        if enable_fuzz:
            scheduler.enable_fuzz = True
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
                if i == 0 and revlog.review_kind != 0:
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
                    again_s = scheduler.init_stability(1)
                    hard_s = scheduler.init_stability(2)
                    good_s = scheduler.init_stability(3)
                    easy_s = scheduler.init_stability(4)
                    d = scheduler.init_difficulty(rating)
                    s = scheduler.init_stability(rating)
                    last_date = datetime.fromtimestamp(revlog.time - rollover * 60 * 60)
                    last_rating = rating
                else:
                    ivl = datetime.fromtimestamp(revlog.time - rollover * 60 * 60).toordinal() - last_date.toordinal()
                    if ivl <= 0 and (revlog.review_kind == 0 or revlog.review_kind == 2):
                        continue
                    r = math.pow(0.9, ivl / s)
                    again_s = scheduler.next_forget_stability(scheduler.next_difficulty(d, 1), s, r)
                    hard_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 2), s, r)
                    good_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 3), s, r)
                    easy_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 4), s, r)
                    d = scheduler.next_difficulty(d, rating)
                    s = scheduler.next_recall_stability(d, s, r) if rating > 1 else scheduler.next_forget_stability(d,
                                                                                                                    s,
                                                                                                                    r)
                    last_date = datetime.fromtimestamp(revlog.time - rollover * 60 * 60)
                    last_rating = rating
            if rating is None or s is None:
                continue
            new_custom_data = {"s": round(s, 2), "d": round(d, 2), "v": "helper"}
            card = mw.col.get_card(cid)
            seed = scheduler.set_fuzz_factor(cid, reps)
            if card.custom_data != "":
                old_custom_data = json.loads(card.custom_data)
                if "seed" in old_custom_data:
                    new_custom_data["seed"] = old_custom_data["seed"]
            if "seed" not in new_custom_data:
                new_custom_data["seed"] = seed
            card.custom_data = json.dumps(new_custom_data)
            if last_s is None:
                again_ivl = scheduler.next_interval(again_s, retention, max_ivl)
                hard_ivl = scheduler.next_interval(hard_s, retention, max_ivl)
                good_ivl = scheduler.next_interval(good_s, retention, max_ivl)
                easy_ivl = scheduler.next_interval(easy_s * easy_bonus, retention, max_ivl)
                easy_ivl = max(good_ivl + 1, easy_ivl)
            else:
                again_ivl = scheduler.next_interval(again_s, retention, max_ivl)
                hard_ivl = scheduler.next_interval(last_s * hard_factor, retention, max_ivl)
                good_ivl = scheduler.next_interval(good_s, retention, max_ivl)
                easy_ivl = scheduler.next_interval(easy_s * easy_bonus, retention, max_ivl)
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
