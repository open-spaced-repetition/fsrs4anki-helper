from .utils import *


def log_loss(y_true, y_pred):
    epsilon = 1e-15
    y_pred = max(min(y_pred, 1 - epsilon), epsilon)
    return -(y_true * math.log(y_pred) + (1 - y_true) * math.log(1 - y_pred))


def total_loss(points, stability):
    return sum(log_loss(y, power_forgetting_curve(x, stability)) for x, y in points)


def binary_search(points, low=1, high=86400, tolerance=1e-6):
    while high - low > tolerance:
        mid = (low + high) / 2
        left = mid - tolerance
        right = mid + tolerance

        loss_left = total_loss(points, left)
        loss_right = total_loss(points, right)

        if loss_left < loss_right:
            high = mid
        else:
            low = mid

    return (low + high) / 2


def steps_stats(lim):
    results = mw.col.db.all(
        f"""
    WITH first_review AS (
    SELECT cid, MIN(id) AS first_id, ease AS first_rating
    FROM revlog
    WHERE ease BETWEEN 1 AND 4
    {"AND " + lim if lim else ""}
    GROUP BY cid
    ),
    second_review AS (
    SELECT r.cid, r.id AS second_id, CASE WHEN r.ease=1 THEN 0 ELSE 1 END AS recall,
            ROW_NUMBER() OVER (PARTITION BY r.cid ORDER BY r.id) AS review_order
    FROM revlog r
    JOIN first_review fr ON r.cid = fr.cid AND r.id > fr.first_id
    WHERE (r.id - fr.first_id) <= 43200000
    AND r.ease BETWEEN 1 AND 4
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
    WHERE first_rating != 4
    ORDER BY first_rating, delta_t
    """
    )
    stats_dict = {}
    for first_rating, delta_t, recall in results:
        if first_rating not in stats_dict:
            stats_dict[first_rating] = {"delta_t": [], "recall": []}
        stats_dict[first_rating]["delta_t"].append(delta_t)
        stats_dict[first_rating]["recall"].append(recall)

    display_dict = {}

    # Calculate median delta_t and mean recall for each first_rating
    results_dict = {}
    for rating in stats_dict:
        delta_t_list = sorted(stats_dict[rating]["delta_t"])
        n = len(delta_t_list)
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
        mean_recall = sum(stats_dict[rating]["recall"]) / len(
            stats_dict[rating]["recall"]
        )
        results_dict[rating] = {
            "delay_q1": round(delay_q1),
            "delay_q2": round(delay_q2),
            "delay_q3": round(delay_q3),
            "retention": f"{mean_recall:.2%}",
        }

    display_dict["stats"] = results_dict
    rating2stability = {}
    for rating in stats_dict:
        points = list(zip(stats_dict[rating]["delta_t"], stats_dict[rating]["recall"]))
        Q1 = results_dict[rating]["delay_q1"]
        Q3 = results_dict[rating]["delay_q3"]
        IQR = Q3 - Q1
        LOWER = Q1 - 1.5 * IQR
        UPPER = Q3 + 1.5 * IQR
        points = list(filter(lambda x: LOWER <= x[0] <= UPPER, points))
        rating2stability[rating] = round(binary_search(points))
    display_dict["stability"] = rating2stability
    return display_dict
