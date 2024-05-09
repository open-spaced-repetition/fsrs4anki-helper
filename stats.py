from anki.stats import CollectionStats
from .configuration import Config
from .utils import *


def _line_now(i, a, b, bold=True):
    colon = ":"
    style = "style='padding: 5px'"
    if bold:
        i.append(
            ("<tr><td align=left %s>%s%s</td><td align=left><b>%s</b></td></tr>")
            % (style, a, colon, b)
        )
    else:
        i.append(
            ("<tr><td align=left %s>%s%s</td><td align=left>%s</td></tr>")
            % (style, a, colon, b)
        )


def _lineTbl_now(i):
    return "<table>" + "".join(i) + "</table>"


def retention_stability_load(lim) -> tuple:
    elapse_stability_ivl_list = mw.col.db.all(
        f"""
    SELECT 
        CASE WHEN odid==0
            THEN {mw.col.sched.today} - (due - ivl)
            ELSE {mw.col.sched.today} - (odue - ivl)
        END
        ,json_extract(data, '$.s')
        ,ivl 
        ,(SELECT COUNT(*) FROM cards c2 WHERE c1.nid = c2.nid)
        ,nid
    FROM cards c1
    WHERE queue != 0 AND queue != -1
    AND data != ''
    AND json_extract(data, '$.s') IS NOT NULL
    """
        + lim
    )
    # x[0]: elapsed days
    # x[1]: stability
    # x[2]: interval
    # x[3]: same nid count
    # x[4]: nid
    elapse_stability_ivl_list = filter(
        lambda x: x[1] is not None, elapse_stability_ivl_list
    )
    retention_stability_load_list = list(
        map(
            lambda x: (
                power_forgetting_curve(max(x[0], 0), x[1]),
                x[1],
                1 / max(1, x[2]),
                x[3],
                x[4],
            ),
            elapse_stability_ivl_list,
        )
    )
    card_cnt = len(retention_stability_load_list)
    note_cnt = len(set(x[4] for x in retention_stability_load_list))
    if card_cnt == 0:
        return 0, 0, 0, 0, 0, 0, 0, 0
    recall_sum = sum(item[0] for item in retention_stability_load_list)
    stability_sum = sum(item[1] for item in retention_stability_load_list)
    load_sum = sum(item[2] for item in retention_stability_load_list)
    estimated_total_knowledge_notes = sum(
        item[0] / item[3] for item in retention_stability_load_list
    )

    time_sum = mw.col.db.scalar(
        f"""
    SELECT SUM(time)/1000
    FROM revlog
    WHERE cid IN (
        SELECT id
        FROM cards
        WHERE queue != 0 AND queue != -1
        AND data != ''
        AND json_extract(data, '$.s') IS NOT NULL
        {lim}
    )
    """
    )
    print(time_sum)
    return (
        recall_sum / card_cnt,
        stability_sum / card_cnt,
        load_sum,
        card_cnt,
        round(recall_sum),
        estimated_total_knowledge_notes,
        note_cnt,
        time_sum,
    )


def todayStats_new(self):
    if not mw.col.get_config("fsrs"):
        tooltip(FSRS_ENABLE_WARNING)
        return todayStats_old(self)
    return (
        todayStats_old(self)
        + get_true_retention(self)
        + get_fsrs_stats(self)
        + get_retention_graph(self)
    )


def get_fsrs_stats(self: CollectionStats):
    lim = self._limit()
    if lim:
        lim = " AND did IN %s" % lim

    (
        retention,
        stability,
        load,
        card_cnt,
        estimated_total_knowledge,
        estimated_total_knowledge_notes,
        note_cnt,
        time_sum,
    ) = retention_stability_load(lim)
    i = []
    _line_now(i, "Average predicted retention", f"{retention * 100: .2f}%")
    _line_now(i, "Average stability", f"{round(stability)} days")
    _line_now(i, "Daily Load", f"{round(load)} reviews/day")
    i.append(
        "<tr><td align=left style='padding: 5px'><b>Retention by Cards:</b></td></tr>"
    )
    _line_now(i, "Total Count", f"{card_cnt} cards")
    _line_now(
        i,
        "Estimated total knowledge",
        f"{estimated_total_knowledge} cards ({retention * 100:.2f}%)",
    )
    _line_now(i, "Total Time", f"{time_sum/3600:.1f} hours")
    if time_sum > 0:
        _line_now(
            i,
            "Knowledge acquisition rate",
            f"{estimated_total_knowledge / (time_sum/3600):.1f} cards/hour",
        )
    i.append(
        "<tr><td align=left style='padding: 5px'><b>Retention by Notes:</b></td></tr>"
    )
    _line_now(i, "Total Count", f"{note_cnt} notes")
    _line_now(
        i,
        "Estimated total knowledge",
        f"{round(estimated_total_knowledge_notes)} notes ({(estimated_total_knowledge_notes / max(note_cnt, 1)) * 100:.2f}%)",
    )
    title = CollectionStats._title(
        self,
        "FSRS Stats",
        "Only calculated for cards with FSRS memory states",
    )
    stats_data = _lineTbl_now(i)
    interpretation = (
        "<p>Note: Unless you have a huge backlog, the average predicted retention will be higher than your desired retention. For details, read the interpretation section.</p>"
        + "<details><summary>Interpretation</summary><ul>"
        + "<li><b>Average predicted retention</b>: the average probability of recalling a card today. Desired retention is the retention when the card is due. Average retention is the current retention of all cards, including those that are not yet due. These two values are different because most cards are not usually due. <b>The average predicted retention is calculated using FSRS formulas and depends on your parameters.</b> True retention is a measured value, not an algorithmic prediction. So, it doesn't change after changing the FSRS parameters.</li>"
        + "<li><b>Stability</b>: the time required for the retention to fall from 100% to 90%.</li>"
        + "<li><b>Load</b>: an estimate of the average number of cards to be reviewed daily (assuming review at the scheduled time without advancing or postponing). Load = 1/I<sub>1</sub> + 1/I<sub>2</sub> + 1/I<sub>3</sub> +...+ 1/I<sub>n</sub>, where I<sub>n</sub> is the current interval of the n-th card.</li>"
        + "<li><b>Count</b>: the number of cards with FSRS memory states, excluding cards in the (re)learning stage.</li> "
        + "<li><b>Estimated total knowledge</b>: the number of cards the user is expected to know today, calculated as the product of average predicted retention and count.</li>"
        + "<li><b>Total time</b>: the amount of time spent doing reviews in Anki. This does not include time spent on making and editing cards, as well as time spent on reviewing suspended and deleted cards.</li>"
        + "<li><b>Knowledge acquisition rate</b>: the number of cards memorized per hour of actively doing reviews in Anki, calculated as the ratio of total knowledge and total time. Larger values indicate efficient learning. This metric can be used to compare different learners. If your collection is very young, this number may initially be very low or very high.</li>"
        + "</ul></details>"
    )
    return self._section(
        title
        + stats_data
        + "<table style='text-align: left'><tr><td style='padding: 5px'>"
        + interpretation
        + "</td></tr></table>"
    )


def get_retention_graph(self: CollectionStats):
    config = Config()
    config.load()
    start, days, chunk = self.get_start_end_chunk()
    lims = []
    if days is not None:
        lims.append(
            "id > %d" % ((self.col.sched.day_cutoff - (days * chunk * 86400)) * 1000)
        )
    lim = "cid in (select id from cards where did in %s)" % self._limit()
    if lim:
        lims.append(lim)
    if lims:
        lim = "AND " + " AND ".join(lims)

    query = f"""SELECT
    CAST((id/1000.0 - {mw.col.sched.day_cutoff}) / 86400.0 as int)/{chunk} AS day,
    COUNT(CASE WHEN lastIvl < {config.mature_ivl} AND lastIvl > {config.mature_ivl} * -86400 THEN id ELSE NULL END) AS review_cnt_young,
    COUNT(CASE WHEN lastIvl >= {config.mature_ivl} OR lastIvl <= {config.mature_ivl} * -86400 THEN id ELSE NULL END) AS review_cnt_mature,
    (COUNT(CASE WHEN ease > 1 AND lastIvl < {config.mature_ivl} AND lastIvl > {config.mature_ivl} * -86400 THEN id ELSE NULL END) + 0.0001) / (COUNT(CASE WHEN lastIvl < {config.mature_ivl} AND lastIvl > {config.mature_ivl} * -86400 THEN id ELSE NULL END) + 0.0001),
    (COUNT(CASE WHEN ease > 1 AND (lastIvl >= {config.mature_ivl} OR lastIvl <= {config.mature_ivl} * -86400) THEN id ELSE NULL END) + 0.0001) / (COUNT(CASE WHEN lastIvl >= {config.mature_ivl} OR lastIvl <= {config.mature_ivl} * -86400 THEN id ELSE NULL END) + 0.0001)
    FROM revlog
    WHERE ease >= 1 AND (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1)
    {lim}
    GROUP BY day
    """

    offset_retention_review_cnt = mw.col.db.all(query)

    data, _ = self._splitRepData(
        offset_retention_review_cnt,
        (
            (1, "#7c7", "Review Count (young)"),
            (2, "#070", "Review Count (mature)"),
            (3, "#ffd268", "Retention Rate (young)"),
            (4, "#e49a60", "Retention Rate (mature)"),
        ),
    )

    if not data:
        return ""

    tmp = -2
    new_data = []
    for item in filter(lambda x: x["label"] is not None, data):
        if item["label"].startswith("Retention"):
            item["lines"] = {"show": True}
            item["bars"] = {"show": False}
            item["yaxis"] = 2
            item["stack"] = tmp
            tmp -= 1
        else:
            item["lines"] = {"show": False}
            item["bars"] = {"show": True}
            item["yaxis"] = 1
            item["stack"] = -1
        new_data.append(item)
    del tmp
    data = new_data

    recall_min = min(min(item[3], item[4]) for item in offset_retention_review_cnt)
    recall_min = math.floor(recall_min * 10) / 10
    recall_max = max(max(item[3], item[4]) for item in offset_retention_review_cnt)
    recall_max = math.ceil(recall_max * 10) / 10

    step = round((recall_max - recall_min) / 5, 2)
    ticks = [
        [recall_min + step * i, str(round(recall_min + step * i, 2))]
        for i in range(0, 6)
    ]

    conf = dict(
        xaxis=dict(tickDecimals=0, max=0.5),
        yaxes=[
            dict(position="left", min=0),
            dict(
                position="right",
                min=recall_min,
                max=recall_max,
                ticks=ticks,
            ),
        ],
    )
    if days is not None:
        conf["xaxis"]["min"] = -days + 0.5

    def plot(id: str, data, ylabel: str, ylabel2: str) -> str:
        return self._graph(
            id, data=data, conf=conf, xunit=chunk, ylabel=ylabel, ylabel2=ylabel2
        )

    txt1 = self._title("Retention Graph", "Retention rate and review count over time")
    txt1 += plot("retention", data, ylabel="Review Count", ylabel2="Retention Rate")
    return self._section(txt1)


def init_stats():
    config = Config()
    config.load()
    if config.fsrs_stats:
        global todayStats_old
        todayStats_old = CollectionStats.todayStats
        CollectionStats.todayStats = todayStats_new


# code modified from https://ankiweb.net/shared/info/1779060522
def get_true_retention(self):
    lim = "cid in (select id from cards where did in %s)" % self._limit()
    if lim:
        lim = " AND " + lim
    pastDay = stats_list(lim, (mw.col.sched.day_cutoff - 86400) * 1000)

    pastYesterday = stats_list(lim, (mw.col.sched.day_cutoff - 86400 * 2) * 1000)
    pastYesterday[0] -= pastDay[0]
    pastYesterday[1] -= pastDay[1]
    pastYesterday[2] = retentionAsString(
        pastYesterday[0], pastYesterday[0] + pastYesterday[1]
    )
    pastYesterday[3] -= pastDay[3]
    pastYesterday[4] -= pastDay[4]
    pastYesterday[5] = retentionAsString(
        pastYesterday[3], pastYesterday[3] + pastYesterday[4]
    )
    pastYesterday[6] = pastYesterday[0] + pastYesterday[3]
    pastYesterday[7] = pastYesterday[1] + pastYesterday[4]
    pastYesterday[8] = retentionAsString(
        pastYesterday[6], pastYesterday[6] + pastYesterday[7]
    )
    pastYesterday[9] -= pastDay[9]
    pastYesterday[10] -= pastDay[10]

    pastWeek = stats_list(lim, (mw.col.sched.day_cutoff - 86400 * 7) * 1000)

    if self.type == 0:
        period = 31
        pname = "Month"
    elif self.type == 1:
        period = 365
        pname = "Year"
    elif self.type == 2:
        period = 10000
        pname = "Deck life"
    pastPeriod = stats_list(lim, (mw.col.sched.day_cutoff - 86400 * period) * 1000)
    true_retention_part = CollectionStats._title(
        self,
        "True Retention",
        "<p>The True Retention is the pass rate calculated only on cards with intervals greater than or equal to one day. It is a better indicator of the learning quality than the Again rate.</p>",
    )
    config = Config()
    config.load()
    true_retention_part += """
        <style>
            td.trl { border: 1px solid; text-align: left; padding: 5px  }
            td.trr { border: 1px solid; text-align: right; padding: 5px  }
            td.trc { border: 1px solid; text-align: center; padding: 5px }
            span.young { color: #77cc77 }
            span.mature { color: #00aa00 }
            span.total { color: #55aa55 }
            span.relearn { color: #c35617 }
        </style>"""
    true_retention_part += f"""
        <table style="border-collapse: collapse;" cellspacing="0" cellpadding="2">
            <tr>
                <td class="trl" rowspan=3><b>Past</b></td>
                <td class="trc" colspan=9><b>Reviews on Cards</b></td>
                <td class="trc" colspan=2 valign=middle><b>Cards</b></td>
            </tr>
            <tr>
                <td class="trc" colspan=3><span class="young"><b>Young (ivl < {config.mature_ivl} d)</b></span></td>
                <td class="trc" colspan=3><span class="mature"><b>Mature (ivl ≥ {config.mature_ivl} d)</b></span></td>
                <td class="trc" colspan=3><span class="total"><b>Total</b></span></td>
                <td class="trc" rowspan=2><span class="young"><b>Learned</b></span></td>
                <td class="trc" rowspan=2><span class="relearn"><b>Relearned</b></span></td>
            </tr>
            <tr>
                <td class="trc"><span class="young">Pass</span></td>
                <td class="trc"><span class="young">Fail</span></td>
                <td class="trc"><span class="young">Retention</span></td>
                <td class="trc"><span class="mature">Pass</span></td>
                <td class="trc"><span class="mature">Fail</span></td>
                <td class="trc"><span class="mature">Retention</span></td>
                <td class="trc"><span class="total">Pass</span></td>
                <td class="trc"><span class="total">Fail</span></td>
                <td class="trc"><span class="total">Retention</span></td>
            </tr>"""
    true_retention_part += stats_row("Day", pastDay)
    true_retention_part += stats_row("Yesterday", pastYesterday)
    true_retention_part += stats_row("Week", pastWeek)
    true_retention_part += stats_row(pname, pastPeriod)
    true_retention_part += "</table>"
    true_retention_part += f"<p>By default, mature cards are defined as the cards with an interval of 21 days or longer. This cutoff can be adjusted in the add-on config.</p>"
    return self._section(true_retention_part)


def retentionAsString(n, d):
    return "%0.1f%%" % ((n * 100) / d) if d else "N/A"


def stats_list(lim, span):
    config = Config()
    config.load()
    yflunked, ypassed, mflunked, mpassed, learned, relearned = mw.col.db.first(
        """
    select
    sum(case when lastIvl < %(i)d and ease = 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* flunked young */
    sum(case when lastIvl < %(i)d and ease > 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* passed young */
    sum(case when lastIvl >= %(i)d and ease = 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* flunked mature */
    sum(case when lastIvl >= %(i)d and ease > 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* passed mature */
    count(DISTINCT case when type = 0 and (ivl >= 1 OR ivl <= -86400) and cid NOT in ( SELECT id FROM cards WHERE type = 0) then cid else NULL end), /* learned */
    sum(case when type = 2 and (ivl >= 1 OR ivl <= -86400) and (lastIvl > -86400 and lastIvl <= 0) then 1 else 0 end) + sum(case when type = 0 and (lastIvl <= -86400 OR lastIvl >= 1) and ease = 1 then 1 else 0 end)/* relearned */
    from revlog where id > ? """
        % dict(i=config.mature_ivl)
        + lim,
        span,
    )
    yflunked, mflunked = yflunked or 0, mflunked or 0
    ypassed, mpassed = ypassed or 0, mpassed or 0
    learned, relearned = learned or 0, relearned or 0

    return [
        ypassed,
        yflunked,
        retentionAsString(ypassed, float(ypassed + yflunked)),
        mpassed,
        mflunked,
        retentionAsString(mpassed, float(mpassed + mflunked)),
        ypassed + mpassed,
        yflunked + mflunked,
        retentionAsString(
            ypassed + mpassed, float(ypassed + mpassed + yflunked + mflunked)
        ),
        learned,
        relearned,
    ]


def stats_row(name, values):
    return (
        """
        <tr>
            <td class="trl">"""
        + name
        + """</td>
            <td class="trr"><span class="young">"""
        + str(values[0])
        + """</span></td>
            <td class="trr"><span class="young">"""
        + str(values[1])
        + """</span></td>
            <td class="trr"><span class="young">"""
        + values[2]
        + """</span></td>
            <td class="trr"><span class="mature">"""
        + str(values[3])
        + """</span></td>
            <td class="trr"><span class="mature">"""
        + str(values[4])
        + """</span></td>
            <td class="trr"><span class="mature">"""
        + values[5]
        + """</span></td>
            <td class="trr"><span class="total">"""
        + str(values[6])
        + """</span></td>
            <td class="trr"><span class="total">"""
        + str(values[7])
        + """</span></td>
            <td class="trr"><span class="total">"""
        + values[8]
        + """</span></td>
            <td class="trr"><span class="young">"""
        + str(values[9])
        + """</span></td>
            <td class="trr"><span class="relearn">"""
        + str(values[10])
        + """</span></td>
        </tr>"""
    )
