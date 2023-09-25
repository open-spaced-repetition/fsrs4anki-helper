from ..utils import *
from anki.decks import DeckManager
from anki.utils import ids2str


def get_desired_advance_cnt_with_response(safe_cnt, did):
    inquire_text = "Enter the number of cards to be advanced.\n"
    notification_text = f"{'For this deck' if did else 'For this collection'}, it is relatively safe to advance up to {safe_cnt} cards.\n"
    warning_text = "You can advance more cards if you wish, but it is not recommended.\nKeep in mind that whenever you use Postpone or Advance, you depart from the optimal scheduling.\n"
    info_text = (
        "This feature only affects the cards that have been scheduled by FSRS4Anki."
    )
    (s, r) = getText(
        inquire_text + notification_text + warning_text + info_text, default="10"
    )
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def advance(did):
    if not mw.col.get_config("fsrs"):
        tooltip("Please enable FSRS first")
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
            THEN {mw.col.sched.today} - (due - ivl)
            ELSE {mw.col.sched.today} - (odue - ivl)
            END,
            json_extract(data, '$.dr')
        FROM cards
        WHERE json_extract(data, '$.s') IS NOT NULL
        AND json_extract(data, '$.dr') IS NOT NULL
        AND due > {mw.col.sched.today}
        AND queue = {QUEUE_TYPE_REV}
        {"AND did IN %s" % did_list if did is not None else ""}
    """
    )
    # x[0]: cid
    # x[1]: did
    # x[2]: interval
    # x[3]: stability
    # x[4]: elapsed days
    # x[5]: desired retention
    # x[6]: current retention
    cards = map(
        lambda x: (
            x
            + [
                power_forgetting_curve(x[4], x[3]),
            ]
        ),
        cards,
    )

    # sort by (1 - elapsed_day / scheduled_day)
    # = 1-ln(current retention)/ln(requested retention), -interval (ascending)
    cards = sorted(cards, key=lambda x: (1 - (1 / x[6] - 1) / (1 / x[5] - 1), -x[2]))
    safe_cnt = len(
        list(filter(lambda x: 1 - (1 / x[6] - 1) / (1 / x[5] - 1) < 0.13, cards))
    )

    (desired_advance_cnt, resp) = get_desired_advance_cnt_with_response(safe_cnt, did)
    if desired_advance_cnt is None:
        if resp:
            showWarning("Please enter the number of cards you want to advance.")
        return
    else:
        if desired_advance_cnt <= 0:
            showWarning("Please enter a positive integer.")
            return

    undo_entry = mw.col.add_custom_undo_entry("Advance")

    mw.progress.start()
    start_time = time.time()

    cnt = 0
    max_retention = 0
    for cid, did, _, stability, _, _, _ in cards:
        if cnt >= desired_advance_cnt:
            break

        card = mw.col.get_card(cid)

        try:
            revlog = filter_revlogs(mw.col.card_stats_data(cid).revlog)[0]
        except IndexError:
            continue

        last_review = get_last_review_date(revlog)
        new_ivl = mw.col.sched.today - last_review
        card = update_card_due_ivl(card, revlog, new_ivl)
        old_custom_data = json.loads(card.custom_data)
        old_custom_data["v"] = "advance"
        card.custom_data = json.dumps(old_custom_data)
        mw.col.update_card(card)
        mw.col.merge_undo_entries(undo_entry)
        cnt += 1

        new_retention = power_forgetting_curve(new_ivl, stability)
        max_retention = max(max_retention, new_retention)

    tooltip(
        f"""{cnt} cards advanced in {time.time() - start_time:.2f} seconds. max retention: {max_retention:.2%}"""
    )
    mw.progress.finish()
    mw.col.reset()
    mw.reset()
