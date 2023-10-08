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
    return list(filter(lambda x: x.review_kind != REVLOG_CRAM or x.ease != 0, revlogs))


def get_last_review_date(last_revlog: CardStatsResponse.StatsRevlogEntry):
    return (
        math.ceil((last_revlog.time - mw.col.sched.day_cutoff) / 86400)
        + mw.col.sched.today
    )


def update_card_due_ivl(
    card: Card, last_revlog: CardStatsResponse.StatsRevlogEntry, new_ivl: int
):
    card.ivl = new_ivl
    last_review_date = get_last_review_date(last_revlog)
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


def get_fuzz_range(interval, elapsed_days):
    min_ivl = max(2, int(round(interval * 0.95 - 1)))
    max_ivl = int(round(interval * 1.05 + 1))
    if interval > elapsed_days:
        min_ivl = max(min_ivl, elapsed_days + 1)
    return min_ivl, max_ivl


def due_to_date(due: int) -> str:
    offset = due - mw.col.sched.today
    today_date = datetime.today()
    return (today_date + timedelta(days=offset)).strftime("%Y-%m-%d")


def power_forgetting_curve(elapsed_days, stability):
    return (1 + elapsed_days / (9 * stability)) ** -1


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
