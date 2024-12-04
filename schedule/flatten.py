from ..configuration import Config
from ..utils import *
from anki.decks import DeckManager
from anki.utils import ids2str


def get_desired_flatten_limit_with_response(did):
    inquire_text = "Enter the maximum number of reviews you want in the future.\n"
    info_text = (
        "This feature only affects the cards that have been scheduled by FSRS.\n"
    )
    warning_text = "This feature doesn't respect maximum interval settings, and may reduce your true retention significantly.\n"
    (s, r) = getText(inquire_text + info_text + warning_text, default="100")
    if r:
        return (RepresentsInt(s), r)
    return (None, r)


def flatten(did):
    if not mw.col.get_config("fsrs"):
        tooltip(FSRS_ENABLE_WARNING)
        return

    (desired_flatten_limit, resp) = get_desired_flatten_limit_with_response(did)
    if desired_flatten_limit is None:
        if resp:
            showWarning("Please enter the number of cards you want to flatten.")
        return
    else:
        if desired_flatten_limit <= 0:
            showWarning("Please enter a positive integer.")
            return

    def on_done(future):
        result_text = future.result()
        mw.progress.finish()
        tooltip(result_text)
        mw.reset()

    fut = mw.taskman.run_in_background(
        lambda: flatten_background(did, desired_flatten_limit), on_done
    )
    return fut


def flatten_background(did, desired_flatten_limit):
    start_time = time.time()
    config = Config()
    config.load()

    DM = DeckManager(mw.col)
    if did is not None:
        did_list = ids2str(DM.deck_and_child_ids(did))

    today = mw.col.sched.today
    current_date = sched_current_date()
    true_due = "CASE WHEN odid==0 THEN due ELSE odue END"

    cards_exceed_future = mw.col.db.all(
        f"""
    SELECT rc.id, rc.true_due, rc.stability
    FROM (
        SELECT id,
            true_due,
            stability,
            ROW_NUMBER() OVER (
                PARTITION BY true_due
                ORDER BY stability
            ) AS rank
        FROM (
            SELECT id,
                {true_due} AS true_due,
                json_extract(data, '$.s') AS stability
            FROM cards
            WHERE true_due >= {today}
            AND data != ''
            AND json_extract(data, '$.s') IS NOT NULL
            AND queue = {QUEUE_TYPE_REV}
            {"AND did IN %s" % did_list if did is not None else ""}
        ) AS subquery
    ) AS rc
    JOIN (
        SELECT {true_due} AS true_due
        FROM cards
        WHERE true_due >= {today}
        AND queue = {QUEUE_TYPE_REV}
        AND data != ''
        AND json_extract(data, '$.s') IS NOT NULL
        {"AND did IN %s" % did_list if did is not None else ""}
        GROUP BY true_due
        HAVING COUNT(*) > {desired_flatten_limit}
    ) AS overdue ON rc.true_due = overdue.true_due
    WHERE rc.rank > {desired_flatten_limit}
    ORDER BY rc.true_due
        """
    )

    cards_backlog = mw.col.db.all(
        f"""
    SELECT id,
        {true_due} AS true_due,
        json_extract(data, '$.s') AS stability
    FROM cards
    WHERE true_due < { today }
    AND data != '' 
    AND json_extract(data, '$.s') IS NOT NULL
    AND queue = {QUEUE_TYPE_REV}
    {"AND did IN %s" % did_list if did is not None else ""}
    ORDER BY stability
    """
    )

    cards_to_flatten = cards_backlog + cards_exceed_future
    total_cnt = len(cards_to_flatten)

    due_cnt_per_day = defaultdict(
        int,
        {
            day: cnt
            for day, cnt in mw.col.db.all(
                f"""SELECT {true_due} AS true_due, count() 
                        FROM cards 
                        WHERE true_due >= { today }
                        AND queue = {QUEUE_TYPE_REV}
                        {"AND did IN %s" % did_list if did is not None else ""}
                        GROUP BY {true_due}"""
            )
        },
    )

    mw.taskman.run_on_main(
        lambda: mw.progress.start(label="Flattening", max=total_cnt, immediate=True)
    )
    cnt = 0
    cancelled = False
    new_target_rs = []
    prev_target_rs = []
    flattened_cards = []
    undo_entry = mw.col.add_custom_undo_entry("flatten")
    for new_due in range(today, today + 36500):
        if cancelled:
            break
        rest_cnt = len(cards_to_flatten) - cnt
        if rest_cnt <= 0:
            break
        # due_date = current_date + timedelta(days=new_due - today)
        due_cnt = due_cnt_per_day[new_due]
        quota = desired_flatten_limit - due_cnt
        if quota <= 0:
            continue
        start_index = cnt
        end_index = cnt + min(quota, rest_cnt)
        for cid, _, ivl in cards_to_flatten[start_index:end_index]:
            card = mw.col.get_card(cid)
            last_review = get_last_review_date(card)
            new_ivl = new_due - last_review
            card = update_card_due_ivl(card, new_ivl)
            write_custom_data(card, "v", "flatten")
            flattened_cards.append(card)
            stability = card.memory_state.stability
            prev_target_rs.append(power_forgetting_curve(ivl, stability))
            new_target_rs.append(power_forgetting_curve(new_ivl, stability))
            cnt += 1
            if cnt % 500 == 0:
                mw.taskman.run_on_main(
                    lambda: mw.progress.update(
                        label=f"{cnt}/{total_cnt} cards flattened",
                        value=cnt,
                        max=total_cnt,
                    )
                )
                if mw.progress.want_cancel():
                    cancelled = True

    mw.col.update_cards(flattened_cards)
    mw.col.merge_undo_entries(undo_entry)
    result_text = f"{cnt} cards flattened in {time.time() - start_time:.2f} seconds."
    if len(prev_target_rs) > 0 and len(new_target_rs) > 0:
        result_text += f"<br>Mean target retention of flattened cards: {sum(prev_target_rs) / len(prev_target_rs):.2%} -> {sum(new_target_rs) / len(new_target_rs):.2%}"
    return result_text
