from typing import Sequence, Callable
from anki.cards import Card
from anki.consts import REVLOG_RESCHED
from aqt.utils import getText, showWarning, tooltip
from aqt.hooks_gen import deck_browser_will_show_options_menu
from aqt import mw
import json
import math


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None


def addActionToGear(fun, text):
    """fun -- takes an argument, the did
    text -- what's written in the gear."""
    def aux(m, did):
        a = m.addAction(text)
        a.triggered.connect(lambda b, did=did: fun(did))
    deck_browser_will_show_options_menu.append(aux)


def getRetentionWithResponse():
    (s, r) = getText("Set the request Retention (%). Recommended 80~90")
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def getMaximumIntervalWithResponse():
    (s, r) = getText("Set the maximum interval (days). Default 36500")
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def reschedule(cids):
    (retention, retentionResp) = getRetentionWithResponse()
    if retention is None:
        if retentionResp:
            showWarning("Please enter an integral number of retention")
        return

    if retention <= 0 or retention >= 100:
        if retentionResp:
            showWarning("Please enter an integral number between 0 and 100")
        return

    (maxInterval, maxIntervalResp) = getMaximumIntervalWithResponse()
    if maxInterval is None:
        maxInterval = 36500

    if maxInterval <= 0:
        if maxIntervalResp:
            showWarning("Please enter an integral number bigger than 0")
        return

    mw.checkpoint("Rescheduling")
    mw.progress.start()

    for cid in cids:
        card = mw.col.getCard(cid)
        if card.type != 2:
            continue
        if "s" not in card.custom_data:
            card.custom_data = "{\"s\":" + str(card.ivl) + "}"
        s = get_card_stability(card)
        newIvl = reschedule_interval(s, retention/100, maxInterval)
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


def reschedule_interval(stability, retention, maxInterval):
    return min(max(int(round(math.log(retention)/math.log(0.9)*stability)), 1), maxInterval)


def cidsInDid(did):
    deck = mw.col.decks.get(did)
    deckName = deck['name']
    return mw.col.findCards(f"\"deck:{deckName}\"")


def rescheduleFromDid(did):
    cids = cidsInDid(did)
    reschedule(cids)


def get_card_stability(card: Card):
    card.flush()
    return json.loads(card.custom_data)['s']


addActionToGear(rescheduleFromDid, "Reschedule cards")
