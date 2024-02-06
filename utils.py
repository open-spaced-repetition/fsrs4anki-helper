import re
from aqt.utils import tooltip, getText, showWarning, askUser, showText
from collections import OrderedDict
from typing import List, Dict, Tuple
from anki.stats_pb2 import CardStatsResponse
from anki.cards import Card
from anki.stats import (
    REVLOG_LRN,
    REVLOG_REV,
    REVLOG_RELRN,
    REVLOG_CRAM,
    REVLOG_RESCHED,
    CARD_TYPE_REV,
    QUEUE_TYPE_LRN,
    QUEUE_TYPE_REV,
    QUEUE_TYPE_DAY_LEARN_RELEARN,
)
from aqt import mw
import json
import math
import random
import time
from datetime import datetime, timedelta
from anki.utils import int_version


FSRS_ENABLE_WARNING = (
    "Please either enable FSRS in your deck options, or disable the FSRS helper add-on."
)


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None


def reset_ivl_and_due(cid: int, revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    card = mw.col.get_card(cid)
    card.ivl = int(revlogs[0].interval / 86400)
    due = (
        math.ceil(
            (revlogs[0].time + revlogs[0].interval - mw.col.sched.day_cutoff) / 86400
        )
        + mw.col.sched.today
    )
    if card.odid:
        card.odue = max(due, 1)
    else:
        card.due = due
    mw.col.update_card(card)


def filter_revlogs(
    revlogs: List[CardStatsResponse.StatsRevlogEntry],
) -> List[CardStatsResponse.StatsRevlogEntry]:
    return list(
        filter(
            lambda x: x.button_chosen >= 1
            and (x.review_kind != REVLOG_CRAM or x.ease != 0),
            revlogs,
        )
    )


def get_last_review_date(card: Card):
    revlogs = mw.col.card_stats_data(card.id).revlog
    try:
        last_revlog = filter_revlogs(revlogs)[0]
        last_review_date = (
            math.ceil((last_revlog.time - mw.col.sched.day_cutoff) / 86400)
            + mw.col.sched.today
        )
    except IndexError:
        due = card.odue if card.odid else card.due
        last_review_date = due - card.ivl
    return last_review_date


def update_card_due_ivl(card: Card, new_ivl: int):
    card.ivl = new_ivl
    last_review_date = get_last_review_date(card)
    if card.odid:
        card.odue = max(last_review_date + new_ivl, 1)
    else:
        card.due = last_review_date + new_ivl
    return card


def has_again(revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    for r in revlogs:
        if r.button_chosen == 1:
            return True
    return False


def has_manual_reset(revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    last_kind = None
    for r in revlogs:
        if r.button_chosen == 0:
            return True
        if (
            last_kind is not None
            and last_kind in (REVLOG_REV, REVLOG_RELRN)
            and r.review_kind == REVLOG_LRN
        ):
            return True
        last_kind = r.review_kind
    return False


FUZZ_RANGES = [
    {
        "start": 2.5,
        "end": 7.0,
        "factor": 0.15,
    },
    {
        "start": 7.0,
        "end": 20.0,
        "factor": 0.1,
    },
    {
        "start": 20.0,
        "end": math.inf,
        "factor": 0.05,
    },
]


def get_fuzz_range(interval, elapsed_days, maximum_interval):
    delta = 1.0
    for range in FUZZ_RANGES:
        delta += range["factor"] * max(
            min(interval, range["end"]) - range["start"], 0.0
        )

    min_ivl = int(round(interval - delta))
    max_ivl = int(round(interval + delta))
    min_ivl = max(2, min_ivl)
    max_ivl = min(max_ivl, maximum_interval)
    if interval > elapsed_days:
        min_ivl = max(min_ivl, elapsed_days + 1)
    min_ivl = min(min_ivl, max_ivl)
    return min_ivl, max_ivl


def due_to_date(due: int) -> str:
    offset = due - mw.col.sched.today
    today_date = datetime.today()
    return (today_date + timedelta(days=offset)).strftime("%Y-%m-%d")


if int_version() < 231200:
    DECAY = -1
else:
    DECAY = -0.5  # FSRS-4.5
FACTOR = 0.9 ** (1 / DECAY) - 1


def power_forgetting_curve(t, s):
    return (1 + FACTOR * t / s) ** DECAY


def next_interval(s, r):
    ivl = s / FACTOR * (r ** (1 / DECAY) - 1)
    return max(1, int(round(ivl)))


def write_custom_data(card: Card, key, value):
    if card.custom_data != "":
        custom_data = json.loads(card.custom_data)
        custom_data[key] = value
    else:
        custom_data = {key: value}
    card.custom_data = json.dumps(custom_data)


def rotate_number_by_k(N, K):
    num = str(N)
    length = len(num)
    K = K % length
    rotated = num[K:] + num[:K]
    return int(rotated)


def p_obey_easy_days(num_of_easy_days, easy_days_review_ratio):
    return (7 - num_of_easy_days) / (
        easy_days_review_ratio * num_of_easy_days + 7 - num_of_easy_days
    )
