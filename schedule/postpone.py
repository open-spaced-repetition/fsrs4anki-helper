import random
import time
import math
from anki.decks import DeckManager
from anki.utils import ids2str
from anki.stats import QUEUE_TYPE_REV
from aqt.utils import tooltip, showWarning, getText
from ..i18n import t
from ..utils import *

def get_desired_postpone_cnt_with_response(safe_cnt, did):
    inquire_text = t("postpone-inquire-text")
    notification_text = t(
        "postpone-notification-text",
        deck=("For this deck" if did else "For this collection"),
        safe_cnt=safe_cnt,
    )
    warning_text = t("postpone-warning-text")
    info_text = t("postpone-info-text")
    (s, r) = getText(
        inquire_text + notification_text + warning_text + info_text,
        default=f"{min(safe_cnt, 10)}",
    )
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def postpone(did):
    if not mw.col.get_config("fsrs"):
        tooltip(t("enable-fsrs-warning"))
        return

    DM = DeckManager(mw.col)
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))

    cards = mw.col.db.all(
        f"""
        SELECT 
            id, 
            CASE WHEN odid==0
            THEN did
            ELSE odid
            END,
            ivl,
            json_extract(data, '$.s'),
            CASE WHEN odid==0
            THEN {mw.col.sched.today} - (due - ivl) + ivl * 0.075
            ELSE {mw.col.sched.today} - (odue - ivl) + ivl * 0.075
            END,
            json_extract(data, '$.dr'),
            COALESCE(json_extract(data, '$.decay'), 0.5)
        FROM cards
        WHERE data != ''
        AND json_extract(data, '$.s') IS NOT NULL
        AND json_extract(data, '$.dr') IS NOT NULL
        AND due <= {mw.col.sched.today}
        AND queue = {QUEUE_TYPE_REV}
        {"AND did IN %s" % did_list if did is not None else ""}
    """
    )
    # x[0]: cid
    # x[1]: did
    # x[2]: interval
    # x[3]: stability
    # x[4]: approx elapsed days after postpone
    # x[5]: desired retention
    # x[6]: decay
    # x[7]: approx retention after postpone
    # x[8]: max interval
    cards = map(
        lambda x: (
            x
            + [
                power_forgetting_curve(max(x[4], 0), x[3], -x[6]),
                DM.config_dict_for_deck_id(x[1])["rev"]["maxIvl"],
            ]
        ),
        cards,
    )
    # sort by (elapsed_days / scheduled_days - 1)
    # = ln(current retention)/ln(requested retention)-1, -stability (ascending)
    cards = sorted(
        cards,
        key=lambda x: (
            (x[7] ** (-1 / x[6]) - 1) / (x[5] ** (-1 / x[6]) - 1) - 1,
            -x[3],
        ),
    )
    safe_cnt = len(
        list(
            filter(
                lambda x: (x[7] ** (-1 / x[6]) - 1) / (x[5] ** (-1 / x[6]) - 1) - 1
                < 0.15,
                cards,
            )
        )
    )

    (desired_postpone_cnt, resp) = get_desired_postpone_cnt_with_response(safe_cnt, did)
    if desired_postpone_cnt is None:
        if resp:
            showWarning(t("postpone-enter-number"))
        return
    else:
        if desired_postpone_cnt <= 0:
            showWarning(t("postpone-positive-integer"))
            return

    cnt = 0
    reach_max_ivl_cnt = 0
    new_target_rs = []
    prev_target_rs = []
    postponed_cards = []
    start_time = time.time()
    undo_entry = mw.col.add_custom_undo_entry(t("postpone"))
    for cid, did, ivl, stability, elapsed_days, _, decay, _, max_ivl in cards:
        if cnt >= desired_postpone_cnt:
            break

        card = mw.col.get_card(cid)
        random.seed(cid + ivl)
        last_review = get_last_review_date(card)
        elapsed_days = mw.col.sched.today - last_review
        delay = max(elapsed_days - ivl, 0)
        new_ivl = min(
            max(1, math.ceil(ivl * (1.05 + 0.05 * random.random())) + delay), max_ivl
        )
        if new_ivl <= ivl and new_ivl == max_ivl:
            reach_max_ivl_cnt += 1
        card = update_card_due_ivl(card, new_ivl)
        write_custom_data(card, "v", "postpone")
        postponed_cards.append(card)
        prev_target_rs.append(power_forgetting_curve(ivl, stability, -decay))
        new_target_rs.append(power_forgetting_curve(new_ivl, stability, -decay))
        cnt += 1
    cnt -= reach_max_ivl_cnt
    mw.col.update_cards(postponed_cards)
    mw.col.merge_undo_entries(undo_entry)
    result_text = t(
        "postpone-result-text", count=cnt, seconds=f"{(time.time() - start_time):.2f}"
    )
    if reach_max_ivl_cnt > 0:
        result_text += t(
            "postpone-reach-max-ivl",
            reach_max_ivl_cnt=reach_max_ivl_cnt,
        )
    if len(prev_target_rs) > 0 and len(new_target_rs) > 0:
        result_text += t(
            "postpone-retention-change",
            prev_retention=f"{sum(prev_target_rs) / len(prev_target_rs):.2f}",
            new_retention=f"{sum(new_target_rs) / len(new_target_rs):.2f}",
        )
    tooltip(result_text)
    mw.reset()
