import re
import math
import json
from datetime import datetime
from aqt import mw
from aqt.utils import getText, showWarning, tooltip


class FSRS():
    def __init__(self, w: list[float]) -> None:
        self.w = w

    def init_stability(self, rating: int) -> float:
        return self.w[0] + self.w[1] * (rating-1)

    def init_difficulty(self, rating: int) -> float:
        return self.w[2] + self.w[3] * (rating-3)

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


def reschedule():
    custom_scheduler = mw.col.all_config()['cardStateCustomizer']
    if "FSRS4Anki" not in custom_scheduler:
        showWarning("Please use FSRS4Anki scheduler.")
        return
    version = list(
        map(int, re.findall(f'v(\d).(\d).(\d)', custom_scheduler)[0]))
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return
    ws = re.findall(r'[var ]?w ?= ?(.*);', custom_scheduler)
    weights = [list(map(float, w.strip('][').split(', '))) for w in ws]
    deck_names = re.findall(
        r'deck_name(?: ?== ?|.startsWith\()+"(.*)"', custom_scheduler)
    deck_names.insert(0, "global")
    deck_w = {k: v for k, v in zip(deck_names, weights)}
    retentions = re.findall(r'requestRetention ?= ?(.*);', custom_scheduler)
    deck_r = {k: float(v) for k, v in zip(deck_names, retentions)}
    max_ivls = re.findall(r'maximumInterval ?= ?(.*);', custom_scheduler)
    deck_i = {k: int(v) for k, v in zip(deck_names, max_ivls)}

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    for deck in mw.col.decks.all():
        w = deck_w['global']
        retention = deck_r['global']
        max_ivl = deck_i['global']
        for deck_name in deck_names:
            if deck['name'].startswith(deck_name):
                w = deck_w[deck_name]
                retention = deck_r[deck_name]
        scheduler = FSRS(w)
        for cid in mw.col.find_cards(f"\"deck:{deck['name']}\" \"is:review\""):
            last_date = 0
            revlogs = mw.col.card_stats_data(cid).revlog
            for id, revlog in enumerate(reversed(revlogs)):
                if id == 0:
                    rating = revlog.button_chosen
                    d = scheduler.init_difficulty(rating)
                    s = scheduler.init_stability(rating)
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()
                else:
                    ivl = datetime.fromtimestamp(
                        revlog.time).toordinal() - last_date
                    if ivl <= 0:
                        continue
                    r = math.pow(0.9, ivl / s)
                    rating = revlog.button_chosen
                    d = scheduler.next_difficulty(d, rating)
                    s = scheduler.next_recall_stability(
                        d, s, r) if rating > 1 else scheduler.next_forget_stability(d, s, r)
                    last_date = datetime.fromtimestamp(revlog.time).toordinal()

            card = mw.col.get_card(cid)
            card.custom_data = json.dumps(
                {"s": round(s, 4), "d": round(d, 4), "v": "3.0.0"})
            newIvl = min(
                max(int(round(math.log(retention)/math.log(0.9)*s)), 1), max_ivl)
            offset = newIvl - card.ivl
            card.ivl = newIvl
            if card.odid:  # Also update cards in filtered decks
                card.odue += offset
            else:
                card.due += offset
            card.flush()

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(_("""Rescheduled"""))
