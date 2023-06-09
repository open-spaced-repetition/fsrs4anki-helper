from .utils import *
from anki.decks import DeckManager
from anki.utils import ids2str


def get_desired_advance_cnt_with_response(safe_cnt):
    inquire_text = "Enter the number of cards to be advanced.\n"
    notification_text = f"It is relatively safe to advance up to {safe_cnt} cards\n"
    info_text = "This feature only affects the cards that have been scheduled by the FSRS4Anki.\n\n"
    warning_text = "Warning! Each time you use Advance or Postpone, you depart from optimal scheduling!\nUsing this feature often is not recommended."
    (s, r) = getText(inquire_text + notification_text + info_text + warning_text, default="10")
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def advance(did):
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
    if version[0] < 3:
        showWarning("Require FSRS4Anki version >= 3.0.0")
        return

    deck_parameters = get_deck_parameters(custom_scheduler)
    if deck_parameters is None:
        return
    
    skip_decks = get_skip_decks(custom_scheduler) if version[1] >= 12 else []
    global_deck_name = get_global_config_deck_name(version)
    did_to_deck_parameters = get_did_parameters(mw.col.decks.all(), deck_parameters, global_deck_name)

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
        AND due > {mw.col.sched.today}
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
    cards = filter(lambda x: x[3] is not None, cards)
    cards = map(lambda x: (x + [did_to_deck_parameters[x[1]]["r"], math.pow(0.9, x[4]/x[3])]), cards)
    # sort by (1 - elapsed_day / scheduled_day)
    # = 1-ln(current retention)/ln(requested retention), -interval (ascending)
    cards = sorted(cards, key=lambda x: (1-math.log(x[6])/math.log(x[5]), -x[2]))
    safe_cnt = len(list(filter(lambda x: 1-math.log(x[6])/math.log(x[5]) < 0.13, cards)))

    (desired_advance_cnt, resp) = get_desired_advance_cnt_with_response(safe_cnt)
    if desired_advance_cnt is None:
        if resp:
            showWarning("Please enter the number of cards you want to advance.")
        return
    else:
        if desired_advance_cnt <= 0:
            showWarning("Please enter a positive integer.")
            return

    mw.checkpoint("Advancing")
    mw.progress.start()

    cnt = 0
    max_retention = 0
    for cid, did, _, stability, _, _, _ in cards:
        if cnt >= desired_advance_cnt:
            break
        
        card = mw.col.get_card(cid)

        try:
            revlog = mw.col.card_stats_data(cid).revlog[0]
        except IndexError:
            continue

        last_due = get_last_review_date(revlog)
        new_ivl = mw.col.sched.today - last_due
        card = update_card_due_ivl(card, revlog, new_ivl)
        card.flush()
        cnt += 1

        new_retention = math.pow(0.9, new_ivl / stability)
        max_retention = max(max_retention, new_retention)

    mw.progress.finish()
    mw.col.reset()
    mw.reset()

    tooltip(f"""{cnt} cards advanced, max retention: {max_retention:.2%}""")
