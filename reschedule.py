import re
import math
import json
from datetime import datetime
from aqt import mw
from aqt.utils import showWarning, tooltip


class FSRS():
    def __init__(self, w: list[float]) -> None:
        self.w = w

    def init_stability(self, rating: int) -> float:
        return max(0.1, self.w[0] + self.w[1] * (rating-1))

    def init_difficulty(self, rating: int) -> float:
        return self.constrain_difficulty(self.w[2] + self.w[3] * (rating-3))

    def next_difficulty(self, d: float, rating: int) -> float:
        new_d = d + self.w[4] * (rating - 3)
        return self.constrain_difficulty(self.mean_reversion(self.w[2], new_d))

    def mean_reversion(self, init: float, current: float) -> float:
        return self.w[5] * init + (1 - self.w[5]) * current

    def constrain_difficulty(self, difficulty: float) -> float:
        return min(10, max(1, difficulty))

    def next_recall_stability(self, d: float, s: float, r: float) -> float:
        return s * (1 + math.exp(self.w[6]) * (11 - d) * math.pow(s, self.w[7]) * (math.exp((1 - r) * self.w[8]) - 1))

    def next_forget_stability(self, d: float, s: float, r: float) -> float:
        return self.w[9] * math.pow(d, self.w[10]) * math.pow(s, self.w[11]) * math.exp((1 - r) * self.w[12])

def next_interval(stability, retention, max_ivl):
    return min(max(int(round(math.log(retention)/math.log(0.9) * stability)), 1), max_ivl)

def reschedule(did):
    custom_scheduler = mw.col.all_config()['cardStateCustomizer']
    if "FSRS4Anki" not in custom_scheduler:
        showWarning("Please use FSRS4Anki scheduler.")
        return
    version = list(map(int, re.findall(f'v(\d).(\d).(\d)', custom_scheduler)[0]))
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return
    weights = [list(map(float, w.strip('][').split(', '))) for w in re.findall(r'[var ]?w ?= ?(.*);', custom_scheduler)]
    deck_names = re.findall(r'deck_name(?: ?== ?|.startsWith\()+"(.*)"', custom_scheduler)
    deck_names.insert(0, "global")
    deck_w = {k: v for k, v in zip(deck_names, weights)}
    deck_retention = {k: float(v) for k, v in zip(deck_names, re.findall(r'requestRetention ?= ?(.*);', custom_scheduler))}
    deck_max_ivl = {k: int(v) for k, v in zip(deck_names, re.findall(r'maximumInterval ?= ?(.*);', custom_scheduler))}
    deck_easy_bonus = {k: float(v) for k, v in zip(deck_names, re.findall(r'easyBonus ?= ?(.*);', custom_scheduler))}
    deck_hard_ivl = {k: float(v) for k, v in zip(deck_names, re.findall(r'hardInterval ?= ?(.*);', custom_scheduler))}

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    cnt = 0
    decks = mw.col.decks.all() if did is None else [mw.col.decks.get(did)];
    for deck in decks:
        w = deck_w['global']
        retention = deck_retention['global']
        max_ivl = deck_max_ivl['global']
        easy_bonus = deck_easy_bonus['global']
        hard_ivl = deck_hard_ivl['global']
        if deck['name'] in deck_names:
            w = deck_w[deck['name']]
            retention = deck_retention[deck['name']]
            max_ivl = deck_max_ivl[deck['name']]
            easy_bonus = deck_easy_bonus[deck['name']]
            hard_ivl = deck_hard_ivl[deck['name']]
        else:
            for deck_name in deck_names:
                if deck['name'].startswith(deck_name):
                    w = deck_w[deck_name]
                    retention = deck_retention[deck_name]
                    max_ivl = deck_max_ivl[deck_name]
                    easy_bonus = deck_easy_bonus[deck_name]
                    hard_ivl = deck_hard_ivl[deck_name]
        scheduler = FSRS(w)
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""):
            last_date = None
            last_s = None
            s = None
            rating = None
            for revlog in reversed(mw.col.card_stats_data(cid).revlog):
                last_s = s
                rating = revlog.button_chosen
                if rating == 0:
                    continue
                if last_date is None:
                    again_s = scheduler.init_stability(1)
                    hard_s = scheduler.init_stability(2)
                    good_s = scheduler.init_stability(3)
                    easy_s = scheduler.init_stability(4)
                    d = scheduler.init_difficulty(rating)
                    s = scheduler.init_stability(rating)
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()
                else:
                    ivl = datetime.fromtimestamp(revlog.time).toordinal() - last_date
                    if ivl <= 0 or revlog.review_kind not in (0, 1, 3):
                        continue
                    r = math.pow(0.9, ivl / s)
                    again_s = scheduler.next_forget_stability(scheduler.next_difficulty(d, 1), s, r)
                    hard_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 2), s, r)
                    good_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 3), s, r)
                    easy_s = scheduler.next_recall_stability(scheduler.next_difficulty(d, 4), s, r)
                    d = scheduler.next_difficulty(d, rating)
                    s = scheduler.next_recall_stability(d, s, r) if rating > 1 else scheduler.next_forget_stability(d, s, r)
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()
            if rating is None:
                continue
            card = mw.col.get_card(cid)
            card.custom_data = json.dumps({"s": round(s, 4), "d": round(d, 4), "v": "3.4.0"})
            if last_s is None:
                again_ivl = next_interval(again_s, retention, max_ivl)
                hard_ivl = next_interval(hard_s, retention, max_ivl)
                good_ivl = next_interval(good_s, retention, max_ivl)
                easy_ivl = next_interval(easy_s*easy_bonus, retention, max_ivl)
                easy_ivl = max(good_ivl+1, easy_ivl)
            else:
                again_ivl = next_interval(again_s, retention, max_ivl)
                hard_ivl = next_interval(last_s*hard_ivl, retention, max_ivl)
                good_ivl = next_interval(good_s, retention, max_ivl)
                easy_ivl = next_interval(easy_s*easy_bonus, retention, max_ivl)
                hard_ivl = min(hard_ivl, good_ivl)
                good_ivl = max(hard_ivl+1, good_ivl)
                easy_ivl = max(good_ivl+1, easy_ivl)
            if rating == 0:
                newIvl = card.ivl
            else:
                newIvl = [again_ivl, hard_ivl, good_ivl, easy_ivl][rating-1]
            offset = newIvl - card.ivl
            card.ivl = newIvl
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
