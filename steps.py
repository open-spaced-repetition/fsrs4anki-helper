from .utils import *


def log_loss(y_true, y_pred):
    epsilon = 1e-15
    y_pred = max(min(y_pred, 1 - epsilon), epsilon)
    return -(y_true * math.log(y_pred) + (1 - y_true) * math.log(1 - y_pred))


def total_loss(points, stability):
    return sum(log_loss(y, power_forgetting_curve(x, stability)) for x, y in points)


def fit_forgetting_curve(points, low=1, high=86400 * 30, tolerance=0.1):
    while high - low > tolerance:
        # Calculate two midpoints that divide range into three parts
        left_third = low + (high - low) / 3
        right_third = high - (high - low) / 3

        # Calculate loss at both points
        loss_left = total_loss(points, left_third)
        loss_right = total_loss(points, right_third)

        # Update search range based on which third contains minimum
        if loss_left < loss_right:
            high = right_third  # Minimum is in left part
        else:
            low = left_third  # Minimum is in right part

    return (high + low) / 2


def steps_stats(deck_lim, period_lim):
    sql = f"""
    WITH first_review AS (
    SELECT cid, MIN(id) AS first_id, ease AS first_rating
    FROM revlog
    WHERE ease BETWEEN 1 AND 4
    {"AND " + deck_lim if deck_lim else ""}
    GROUP BY cid
    {"HAVING " + period_lim if period_lim else ""}
    ),
    second_review AS (
    SELECT r.cid, r.id AS second_id, CASE WHEN r.ease=1 THEN 0 ELSE 1 END AS recall,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
    FROM revlog r
    JOIN first_review fr ON r.cid = fr.cid AND r.id > fr.first_id
    WHERE r.ease BETWEEN 1 AND 4
    ),
    review_stats AS (
    SELECT fr.first_rating,
            (sr.second_id - fr.first_id) / 1000.0 AS delta_t,
            sr.recall
    FROM first_review fr
    JOIN second_review sr ON fr.cid = sr.cid
    WHERE sr.review_order = 1
    )
    SELECT first_rating, delta_t, recall
    FROM review_stats
    WHERE first_rating BETWEEN 1 AND 3
    ORDER BY first_rating, delta_t
    """
    learning_revlogs = mw.col.db.all(sql)
    sql = f"""
    WITH first_review AS (
        SELECT cid, MIN(id) AS first_id, ease AS first_rating
        FROM revlog
        WHERE ease BETWEEN 1 AND 4
        {"AND " + deck_lim if deck_lim else ""}
        GROUP BY cid
        HAVING first_rating = 1
        {"AND " + period_lim if period_lim else ""}
    ),
    second_review AS (
        SELECT r.cid, r.id AS second_id, r.ease AS second_rating,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
        FROM revlog r
        JOIN first_review fr ON r.cid = fr.cid AND r.id > fr.first_id
        WHERE r.ease BETWEEN 1 AND 4
    ),
    third_review AS (
        SELECT r.cid, r.id AS third_id, CASE WHEN r.ease=1 THEN 0 ELSE 1 END AS recall,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
        FROM revlog r
        JOIN second_review sr ON r.cid = sr.cid AND r.id > sr.second_id
        WHERE r.ease BETWEEN 1 AND 4
    ),
    review_stats AS (
        SELECT fr.first_rating,
            sr.second_rating,
            (tr.third_id - sr.second_id) / 1000.0 AS delta_t,
            tr.recall
        FROM first_review fr
        JOIN second_review sr ON fr.cid = sr.cid
        JOIN third_review tr ON sr.cid = tr.cid
        WHERE sr.review_order = 1 AND tr.review_order = 1
    )
    SELECT delta_t, recall
    FROM review_stats
    WHERE second_rating = 3
    ORDER BY delta_t
    """
    again_then_good_revlogs = mw.col.db.all(sql)
    sql = f"""
    WITH first_review AS (
        SELECT cid, MIN(id) AS first_id, ease AS first_rating
        FROM revlog
        WHERE ease BETWEEN 1 AND 4
        {"AND " + deck_lim if deck_lim else ""}
        GROUP BY cid
        HAVING first_rating = 3
        {"AND " + period_lim if period_lim else ""}
    ),
    second_review AS (
        SELECT r.cid, r.id AS second_id, r.ease AS second_rating,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
        FROM revlog r
        JOIN first_review fr ON r.cid = fr.cid AND r.id > fr.first_id
        WHERE r.ease BETWEEN 1 AND 4
    ),
    third_review AS (
        SELECT r.cid, r.id AS third_id, CASE WHEN r.ease=1 THEN 0 ELSE 1 END AS recall,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
        FROM revlog r
        JOIN second_review sr ON r.cid = sr.cid AND r.id > sr.second_id
        WHERE r.ease BETWEEN 1 AND 4
    ),
    review_stats AS (
        SELECT fr.first_rating,
            sr.second_rating,
            (tr.third_id - sr.second_id) / 1000.0 AS delta_t,
            tr.recall
        FROM first_review fr
        JOIN second_review sr ON fr.cid = sr.cid
        JOIN third_review tr ON sr.cid = tr.cid
        WHERE sr.review_order = 1 AND tr.review_order = 1
    )
    SELECT delta_t, recall
    FROM review_stats
    WHERE second_rating = 1
    ORDER BY delta_t
    """
    good_then_again_revlogs = mw.col.db.all(sql)
    sql = f"""
    WITH first_fail AS (
        SELECT cid, id AS first_id
        FROM revlog
        WHERE type = {REVLOG_REV} AND ease = 1
        {"AND " + deck_lim if deck_lim else ""}
        {"AND " + period_lim if period_lim else ""}
    ),
    next_review AS (
        SELECT 
            f.cid,
            f.first_id,
            MIN(r.id) AS next_id,
            CASE WHEN r.ease = 1 THEN 0 ELSE 1 END AS recall
        FROM first_fail f
        JOIN revlog r ON f.cid = r.cid 
            AND r.id > f.first_id
        WHERE r.ease BETWEEN 1 AND 4
        GROUP BY f.cid, f.first_id
    ),
    review_stats AS (
        SELECT 
            nr.cid,
            (nr.next_id - nr.first_id) / 1000.0 AS delta_t,
            nr.recall
        FROM next_review nr
    )
    SELECT 
        delta_t,
        recall
    FROM review_stats
    ORDER BY delta_t;
    """
    relearning_revlogs = mw.col.db.all(sql)
    stats_dict = defaultdict(list)
    for first_rating, delta_t, recall in learning_revlogs:
        stats_dict[first_rating].append((delta_t, recall))

    if len(relearning_revlogs) > 0:
        for delta_t, recall in relearning_revlogs:
            stats_dict[0].append((delta_t, recall))

    if len(again_then_good_revlogs) > 0:
        for delta_t, recall in again_then_good_revlogs:
            stats_dict[4].append((delta_t, recall))

    if len(good_then_again_revlogs) > 0:
        for delta_t, recall in good_then_again_revlogs:
            stats_dict[5].append((delta_t, recall))

    display_dict = {}

    # Calculate median delta_t and mean recall for each first_rating
    results_dict = {}
    for rating in stats_dict:
        points = stats_dict[rating]
        n = len(points)
        delta_t_list = [x[0] for x in points]
        recall_list = [x[1] for x in points]
        q1_index = n // 4
        q2_index = n // 2
        q3_index = 3 * n // 4
        delay_q1 = (
            delta_t_list[q1_index]
            if n % 4
            else (delta_t_list[q1_index - 1] + delta_t_list[q1_index]) / 2
        )
        delay_q2 = (
            delta_t_list[q2_index]
            if n % 2
            else (delta_t_list[q2_index - 1] + delta_t_list[q2_index]) / 2
        )
        delay_q3 = (
            delta_t_list[q3_index]
            if n % 4
            else (delta_t_list[q3_index - 1] + delta_t_list[q3_index]) / 2
        )
        r1 = sum(recall_list[:q1_index]) / q1_index if q1_index > 0 else math.nan
        r2 = (
            sum(recall_list[q1_index:q2_index]) / (q2_index - q1_index)
            if q2_index > q1_index
            else math.nan
        )
        r3 = (
            sum(recall_list[q2_index:q3_index]) / (q3_index - q2_index)
            if q3_index > q2_index
            else math.nan
        )
        r4 = sum(recall_list[q3_index:]) / (n - q3_index) if q3_index < n else math.nan
        retention = sum(recall_list) / n
        results_dict[rating] = {
            "delay_q1": round(delay_q1),
            "delay_q2": round(delay_q2),
            "delay_q3": round(delay_q3),
            "r1": f"{r1:.2%}",
            "r2": f"{r2:.2%}",
            "r3": f"{r3:.2%}",
            "r4": f"{r4:.2%}",
            "retention": f"{retention:.2%}",
            "count": n,
        }

    display_dict["stats"] = results_dict
    rating2stability = {}
    for rating in stats_dict:
        if len(stats_dict[rating]) >= 250:
            Q1 = results_dict[rating]["delay_q1"]
            Q3 = results_dict[rating]["delay_q3"]
            IQR = Q3 - Q1
            LOWER = Q1 - 1.5 * IQR
            UPPER = Q3 + 1.5 * IQR
            points = list(filter(lambda x: LOWER <= x[0] <= UPPER, stats_dict[rating]))
        else:
            points = stats_dict[rating]
        rating2stability[rating] = round(fit_forgetting_curve(points))
    display_dict["stability"] = rating2stability
    return display_dict
