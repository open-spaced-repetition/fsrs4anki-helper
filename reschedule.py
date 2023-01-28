import re
import math
import json
from datetime import datetime
from collections import OrderedDict
from aqt import mw
from aqt.utils import showWarning, tooltip


def constrain_difficulty(difficulty: float) -> float:
    return min(10., max(1., difficulty))


class FSRS:
    def __init__(self, w: list[float]) -> None:
        self.w = w

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


def next_interval(stability, retention, max_ivl):
    return min(max(int(round(math.log(retention) / math.log(0.9) * stability)), 1), max_ivl)


def reschedule(did):
    if 'cardStateCustomizer' not in mw.col.all_config():
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return
    custom_scheduler = mw.col.all_config()['cardStateCustomizer']
    if "FSRS4Anki" not in custom_scheduler:
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return
    version = list(map(int, re.findall(f'v(\d).(\d).(\d)', custom_scheduler)[0]))
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return
    weight_list = [list(map(float, w.strip('][').split(', '))) for w in
                   re.findall(r'[var ]?w ?= ?(.*);', custom_scheduler)]
    retention_list = re.findall(r'requestRetention ?= ?(.*);', custom_scheduler)
    max_ivl_list = re.findall(r'maximumInterval ?= ?(.*);', custom_scheduler)
    easy_bonus_list = re.findall(r'easyBonus ?= ?(.*);', custom_scheduler)
    hard_ivl_list = re.findall(r'hardInterval ?= ?(.*);', custom_scheduler)
    deck_names = re.findall(r'deck_name(?: ?== ?|.startsWith\()+"(.*)"', custom_scheduler)
    deck_names.insert(0, "global")
    deck_parameters = {
        k: {
            "w": w,
            "r": float(r),
            "m": int(m),
            "e": float(e),
            "h": float(h)
        }
        for k, w, r, m, e, h in
        zip(deck_names, weight_list, retention_list, max_ivl_list, easy_bonus_list, hard_ivl_list)
    }
    deck_parameters = OrderedDict(
        {k: v for k, v in sorted(deck_parameters.items(), key=lambda item: item[0], reverse=True)})

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    cnt = 0
    rescheduled_cards = set()
    decks = sorted(mw.col.decks.all(), key=lambda item: item['name'], reverse=True)
    for deck in decks:
        if did is not None:
            deck_name = mw.col.decks.get(did)['name']
            if not deck['name'].startswith(deck_name):
                continue
        w = deck_parameters['global']['w']
        retention = deck_parameters['global']['r']
        max_ivl = deck_parameters['global']['m']
        easy_bonus = deck_parameters['global']['e']
        hard_ivl = deck_parameters['global']['h']
        for key, value in deck_parameters.items():
            if deck['name'].startswith(key):
                w = value['w']
                retention = value['r']
                max_ivl = value['m']
                easy_bonus = value['e']
                hard_ivl = value['h']
                break
        scheduler = FSRS(w)
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""):
            if cid not in rescheduled_cards:
                rescheduled_cards.add(cid)
            else:
                continue
            last_date = None
            last_s = None
            s = None
            d = None
            rating = None
            for revlog in reversed(mw.col.card_stats_data(cid).revlog):
                if revlog.review_kind == 2:
                    continue
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
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()
                else:
                    ivl = datetime.fromtimestamp(revlog.time).toordinal() - last_date
                    if ivl <= 0:
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
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()
            if rating is None or s is None:
                continue
            card = mw.col.get_card(cid)
            card.custom_data = json.dumps({"s": round(s, 4), "d": round(d, 4), "v": "3.4.0"})
            if last_s is None:
                again_ivl = next_interval(rescheduled_cards, retention, max_ivl)
                hard_ivl = next_interval(hard_s, retention, max_ivl)
                good_ivl = next_interval(good_s, retention, max_ivl)
                easy_ivl = next_interval(easy_s * easy_bonus, retention, max_ivl)
                easy_ivl = max(good_ivl + 1, easy_ivl)
            else:
                again_ivl = next_interval(again_s, retention, max_ivl)
                hard_ivl = next_interval(last_s * hard_ivl, retention, max_ivl)
                good_ivl = next_interval(good_s, retention, max_ivl)
                easy_ivl = next_interval(easy_s * easy_bonus, retention, max_ivl)
                hard_ivl = min(hard_ivl, good_ivl)
                good_ivl = max(hard_ivl + 1, good_ivl)
                easy_ivl = max(good_ivl + 1, easy_ivl)
            if rating == 0:
                new_ivl = card.ivl
            else:
                new_ivl = [again_ivl, hard_ivl, good_ivl, easy_ivl][rating - 1]
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
