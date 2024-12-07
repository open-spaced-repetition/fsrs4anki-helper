from anki.stats import CollectionStats
from .configuration import Config
from .utils import *
from .steps import steps_stats


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


def retention_stability(lim) -> tuple:
    elapse_stability_list = mw.col.db.all(
        f"""
    SELECT 
        CASE WHEN odid==0
            THEN {mw.col.sched.today} - (due - ivl)
            ELSE {mw.col.sched.today} - (odue - ivl)
        END
        ,json_extract(data, '$.s')
    FROM cards c1
    WHERE queue != 0 AND queue != -1
    AND data != ''
    AND json_extract(data, '$.s') IS NOT NULL
    """
        + lim
    )
    # x[0]: elapsed days
    # x[1]: stability
    retention_list = list(
        map(
            lambda x: power_forgetting_curve(max(x[0], 0), x[1]),
            elapse_stability_list,
        )
    )
    card_cnt = len(retention_list)
    if card_cnt == 0:
        return 0, 0, 0
    recall_sum = sum(retention_list)

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
    return (
        card_cnt,
        round(recall_sum),
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
        + get_steps_stats(self)
    )


def get_steps_stats(self: CollectionStats):
    config = Config()
    config.load()
    if not config.show_steps_stats:
        return ""
    start, days, chunk = self.get_start_end_chunk()
    if days is not None:
        period_lim = "first_id > %d" % (
            (self.col.sched.day_cutoff - (days * chunk * 86400)) * 1000
        )
    else:
        period_lim = ""
    deck_lim = self._revlogLimit()
    results = steps_stats(deck_lim, period_lim)

    title = CollectionStats._title(
        self,
        "Steps Stats",
        "Statistics for different first ratings during (re)learning steps",
    )

    html = """
        <style>
            td.trl { border: 1px solid; text-align: left; padding: 5px  }
            td.trr { border: 1px solid; text-align: right; padding: 5px  }
            td.trc { border: 1px solid; text-align: center; padding: 5px }
            span.again { color: #f00 }
            span.hard { color: #ff8c00 }
            span.good { color: #008000 }
            span.again-then-good { color: #fdd835 }
            span.good-then-again { color: #007bff }
        </style>
        <table style="border-collapse: collapse;" cellspacing="0" cellpadding="2">
            <tr>
                <td class="trl" rowspan=2><b>State</b></td>
                <td class="trl" rowspan=2><b>First Ratings</b></td>
                <td class="trc" colspan=7><b>Delay And Retention Distribution</b></td>
                <td class="trc" colspan=3><b>Summary</b></td>
            </tr>
            <tr>
                <td class="trc"><b><span>R&#772;</span><sub>1</sub></b></td>
                <td class="trc"><b>T<sub>25%</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>2</sub></b></td>
                <td class="trc"><b>T<sub>50%</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>3</sub></b></td>
                <td class="trc"><b>T<sub>75%</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>4</sub></b></td>
                <td class="trc"><b><span>R&#772;</span></b></td>
                <td class="trc"><b>Stability</b></td>
                <td class="trc"><b>Reviews</b></td>
            </tr>"""

    ratings = {
        1: "again",
        2: "hard",
        3: "good",
        4: "again-then-good",
        5: "good-then-again",
        0: "lapse",
    }

    # Count how many non-lapse ratings we have for rowspan
    learning_count = sum(1 for r in ratings.items() if r[0] != 0)

    first_learning = True
    not_enough_data = True
    for rating, style in ratings.items():
        stats = results["stats"].get(rating, {})
        if not stats:
            results["stability"][rating] = 86400
            state_cell = ""
            if rating == 0:
                state_cell = '<td class="trl"><b>Relearning</b></td>'
            elif first_learning:
                state_cell = (
                    f'<td class="trl" rowspan="{learning_count}"><b>Learning</b></td>'
                )
                first_learning = False

            html += f"""
            <tr>
                {state_cell}
                <td class="trl"><span class="{style}"><b>{style.replace('-', ' ').title()}</b></span></td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
                <td class="trr">N/A</td>
            </tr>"""
            continue

        not_enough_data = False
        state_cell = ""
        if rating == 0:
            state_cell = '<td class="trl"><b>Relearning</b></td>'
        elif first_learning:
            state_cell = (
                f'<td class="trl" rowspan="{learning_count}"><b>Learning</b></td>'
            )
            first_learning = False

        html += f"""
            <tr>
                {state_cell}
                <td class="trl"><span class="{style}"><b>{style.replace('-', ' ').title()}</b></span></td>
                <td class="trr">{stats['r1']}</td>
                <td class="trr">{format_time(stats['delay_q1'])}</td>
                <td class="trr">{stats['r2']}</td>
                <td class="trr">{format_time(stats['delay_q2'])}</td>
                <td class="trr">{stats['r3']}</td>
                <td class="trr">{format_time(stats['delay_q3'])}</td>
                <td class="trr">{stats['r4']}</td>
                <td class="trr">{stats['retention']}</td>
                <td class="trr">{format_time(results['stability'][rating])}</td>
                <td class="trr">{stats['count']}</td>
            </tr>
            """

        if stats["retention"] == 1 or stats["retention"] == 0 or stats["count"] < 100:
            results["stability"][rating] = 86400

    html += (
        f"""
    <tr>
        <td colspan="12" class="trl">
            <strong>Desired retention:</strong>
            <input type="number" id="desired-retention" value="0.9" step="0.01" min="0.7" max="0.98" />
        </td>
    </tr>
    <tr>
        <td colspan="12" class="trl">
            <strong>Recommended learning steps</strong>: 
            <span id="learning-steps"></span>
        </td>
    </tr>
    <tr>
        <td colspan="12" class="trl">
            <strong>Recommended relearning steps</strong>: 
            <span id="relearning-steps"></span>
        </td>
    </tr>

    <script>
        const learningStepRow = document.querySelector('#learning-steps');
        const relearningStepRow = document.querySelector('#relearning-steps');
        const cutoff = 86400 / 2;
        const stability = {results['stability']};

        function formatTime (seconds) {{
            const h = Math.round(seconds / 3600);
            const m = Math.round(seconds / 60);
            return h > 5 ? `${{Math.round(h)}}h`
                : m > 5 ? `${{Math.round(m)}}m`
                : `${{Math.round(seconds)}}s`;
        }};


        const DECAY = -0.5;
        const FACTOR = Math.pow(0.9, (1 / DECAY)) - 1;

        function calculateFactor(dr) {{
            return 1 / FACTOR * (Math.pow(dr, (1 / DECAY)) - 1);
        }}

        function calculateStep(stability, factor) {{
            const step = stability * factor;
            return (step >= cutoff || Number.isNaN(step)) ? "" : formatTime(Math.max(step, 1));
        }};

        function calculateSteps() {{
            const factor = calculateFactor(parseFloat(document.querySelector("#desired-retention").value));

            const learningStep1 = calculateStep(stability[1], factor);
            const learningStep2 = calculateStep(Math.min(stability[2] * 2 - stability[1], stability[3], stability[4]), factor);

            learningStepRow.innerText = (!learningStep1 && !learningStep2) 
                ? "You don't need learning steps" 
                : `${{learningStep1}} ${{learningStep2}}`;

            const relearningStep = calculateStep(stability[0], factor);
            relearningStepRow.innerText = !relearningStep 
                ? "You don't need relearning steps" 
                : relearningStep;
        }};

        calculateSteps();

        document.querySelector('#desired-retention').addEventListener('input', calculateSteps);
    </script>
    """
        if not not_enough_data
        else ""
    )

    html += "</table>"
    html += (
        "<table style='text-align: left'><tr><td style='padding: 5px'>"
        + "<summary>Interpretation</summary><ul>"
        "<li>This table shows <b>the average time you wait before rating each card the next time</b> (Time Delay) based on your <b>first rating of the day for each card in the deck</b> (Again or Hard or Good or Lapse).</li>"
        + "<li>It also shows <b>how well you remember a card after each subsequent rating (after its first rating) on average.</b></li>"
        + "<li>The subsequent ratings after the first ratings of all cards in the deck are gathered and sorted by ascending order of the Time Delay (not shown on the table) and are then grouped into 4 groups (Time Delay 1<2<3<4).</li>"
        + "<li>The 4 groups are further split and assigned to whatever the first rating of the cards was (Again or Hard or Good or Lapse). Therefore, each First Rating has 4 groups of subsequent ratings (Groups 1,2,3,4).</li>"
        + "<li>Average Retention rates (R̅₁, R̅₂, R̅₃, R̅₄) for each group of subsequent ratings and the Average Overall Retention (R̅) for the first ratings are shown. Based on this, the average stability for cards after the first rating of the day (Again or Hard or Good or Lapse) is calculated.</li>"
        + "<li>T<sub>X%</sub> means that X% of the cards in this deck with a first rating (Again or Hard or Good or Lapse) are delayed by this amount of time or less till the next rating.</li>"
        + "<li>Recommended (re)learning steps are calculated from stability and desired retention. The 1st learning step is based S(Again). The 2nd learning step is based on the minimum of {S(Hard)* 2 - S(Again), S(Good), S(Again Then Good)}. The relearning step is base on S(Lapse).</li>"
        + "</ul>"
        "</td></tr></table>"
    )
    return self._section(title + html)


def get_fsrs_stats(self: CollectionStats):
    lim = self._limit()
    if lim:
        lim = " AND did IN %s" % lim

    (
        card_cnt,
        estimated_total_knowledge,
        time_sum,
    ) = retention_stability(lim)
    i = []
    _line_now(i, "Studied cards", f"{card_cnt} cards")
    _line_now(i, "Total review time", f"{time_sum/3600:.1f} hours")
    if time_sum > 0:
        _line_now(
            i,
            "Knowledge acquisition rate",
            f"{estimated_total_knowledge / (time_sum/3600):.1f} cards/hour",
        )
    title = CollectionStats._title(
        self,
        "FSRS Stats",
    )
    stats_data = _lineTbl_now(i)
    interpretation = (
        "<details><summary>Interpretation</summary><ul>"
        + "<li><b>Studied cards</b>: the number of cards with FSRS memory states, excluding suspended cards.</li> "
        + "<li><b>Total review time</b>: the amount of time spent doing reviews in Anki. This does not include the time spent on reviewing suspended and deleted cards.</li>"
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
    lim = self._revlogLimit()
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
    WHERE ease >= 1 
    AND (type != 3 or factor != 0) 
    AND (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1)
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
def get_true_retention(self: CollectionStats):
    if self._revlogLimit():
        lim = " AND " + self._revlogLimit()
    else:
        lim = ""
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
        period = 36500
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
    from revlog where id > ? and ease >= 1 and (type != 3 or factor != 0)"""
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
