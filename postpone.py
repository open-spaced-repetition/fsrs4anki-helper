import math
from datetime import datetime
from .utils import *
from anki.decks import DeckManager
from anki.utils import ids2str


def get_desired_postpone_cnt_with_response():
    inquire_text = "Postpone {n} due cards.\n"
    info_text = "This feature only affects cards scheduled by FSRS4Anki Helper.\n"
    warning_text = "*Warning!* Each time you use Postpone or Advance, you depart from optimal scheduling!\nUsing this feature often is not recommended."
    (s, r) = getText(inquire_text + info_text + warning_text)
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def postpone(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    (desired_postpone_cnt, resp) = get_desired_postpone_cnt_with_response()
    if desired_postpone_cnt is None:
        if resp:
            showWarning("Please enter the number of cards you want to postpone.")
        return
    else:
        if desired_postpone_cnt <= 0:
            showWarning("Please enter a positive integer.")
            return

    deck_parameters = get_deck_parameters(custom_scheduler)
    if deck_parameters is None:
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    global_deck_name = get_global_config_deck_name(version)
    did_to_deck_parameters = get_did_parameters(mw.col.decks.all(), deck_parameters, global_deck_name)

    mw.checkpoint("Postponing")
    mw.progress.start()

    DM = DeckManager(mw.col)
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))

    cards = mw.col.db.all(f"""
        SELECT 
            id, 
            did,
            ivl,
            json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.s'),
            CASE WHEN odid==0
            THEN {mw.col.sched.today} - (due - ivl)
            ELSE {mw.col.sched.today} - (odue - ivl)
            END
        FROM cards
        WHERE data like '%"cd"%'
        AND due <= {mw.col.sched.today}
        AND queue = {QUEUE_TYPE_REV}
        {"AND did IN %s" % did_list if did is not None else ""}
    """)
    # x[0]: cid
    # x[1]: did
    # x[2]: interval
    # x[3]: stability
    # x[4]: elapsed days
    # x[5]: requested retention
    # x[6]: current retention
    cards = map(lambda x: (x + [did_to_deck_parameters[x[1]]["r"], math.pow(0.9, x[4]/x[3])]), cards)
    cards = filter(lambda x: x[3] is not None, cards)
    # sort by requested retention - current retention, -interval (ascending)
    cards = sorted(cards, key=lambda x: (x[5] - x[6], -x[2]))
    cnt = 0
    min_retention = 1
    for cid, did, ivl, stability, elapsed_days, _, _ in cards:
        if cnt >= desired_postpone_cnt:
            break
        
        card = mw.col.get_card(cid)
        max_ivl = did_to_deck_parameters[did]["m"]

        try:
            revlog = mw.col.card_stats_data(cid).revlog[0]
        except IndexError:
            continue

        random.seed(cid + ivl)
        delay = elapsed_days - ivl
        new_ivl = min(max(1, math.ceil(ivl * (1.05 + 0.05 * random.random())) + delay), max_ivl)
        card = update_card_due_ivl(card, revlog, new_ivl)
        card.flush()
        cnt += 1

        new_retention = math.pow(0.9, new_ivl / stability)
        min_retention = min(min_retention, new_retention)

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(f"""{cnt} cards postponed, min retention: {min_retention * 100:.2%}%""")
