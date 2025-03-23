from anki.stats import CollectionStats
from .configuration import Config
from .utils import *
from .steps import steps_stats
from .i18n import i18n


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
        i18n.t("step-stats"),
        i18n.t("step-stats-subtitle"),
    )

    html = (
        """
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
        """
        f"""
        <table style="border-collapse: collapse;" cellspacing="0" cellpadding="2">
            <tr>
                <td class="trl" rowspan=2><b>{i18n.t("state")}</b></td>
                <td class="trl" rowspan=2><b>{i18n.t("first-ratings")}</b></td>
                <td class="trc" colspan=7><b>{i18n.t("delay-and-retention-distribution")}</b></td>
                <td class="trc" colspan=3><b>{i18n.t("summary")}</b></td>
            </tr>
            <tr>
                <td class="trc"><b><span>R&#772;</span><sub>1</sub></b></td>
                <td class="trc"><b>T<sub>{i18n.t("x-%", count=25)}</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>2</sub></b></td>
                <td class="trc"><b>T<sub>{i18n.t("x-%", count=50)}</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>3</sub></b></td>
                <td class="trc"><b>T<sub>{i18n.t("x-%", count=75)}</sub></b></td>
                <td class="trc"><b><span>R&#772;</span><sub>4</sub></b></td>
                <td class="trc"><b><span>R&#772;</span></b></td>
                <td class="trc"><b>{i18n.t("stability")}</b></td>
                <td class="trc"><b>{i18n.t("reviews")}</b></td>
            </tr>"""
    )

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
        if not stats or stats["count"] < 4:
            results["stability"][rating] = 86400
            if "count" not in stats:
                results["stats"][rating] = {"count": 0}
            state_cell = ""
            if rating == 0:
                state_cell = f'<td class="trl"><b>{i18n.t("relearning")}</b></td>'
            elif first_learning:
                state_cell = f'<td class="trl" rowspan="{learning_count}"><b>{i18n.t("learning")}</b></td>'
                first_learning = False

            html += f"""
            <tr>
                {state_cell}
                <td class="trl"><span class="{style}"><b>{i18n.t(style)}</b></span></td>
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
            state_cell = f'<td class="trl"><b>{i18n.t("relearning")}</b></td>'
        elif first_learning:
            state_cell = f'<td class="trl" rowspan="{learning_count}"><b>{i18n.t("learning")}</b></td>'
            first_learning = False

        html += f"""
            <tr>
                {state_cell}
                <td class="trl"><span class="{style}"><b>{i18n.t(style)}</b></span></td>
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

        if stats["retention"] == 1 or stats["retention"] == 0:
            results["stability"][rating] = 86400

    html += (
        f"""
    <tr>
        <td colspan="12" class="trl">
            <strong>{i18n.t("desired-retention")}:</strong>
            <input type="number" id="desired-retention" value="0.9" step="0.01" min="0.7" max="0.98" />
        </td>
    </tr>
    <tr>
        <td colspan="12" class="trl">
            <strong>{i18n.t("recommended-learning-steps")}</strong>: 
            <span id="learning-steps"></span>
        </td>
    </tr>
    <tr>
        <td colspan="12" class="trl">
            <strong>{i18n.t("recommended-relearning-steps")}</strong>: 
            <span id="relearning-steps"></span>
        </td>
    </tr>

    <script>
        const learningStepRow = document.querySelector('#learning-steps');
        const relearningStepRow = document.querySelector('#relearning-steps');
        const cutoff = 86400 / 2;
        const stability = {results['stability']};
        const stats = {results['stats']};

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
            if ((step >= cutoff || Number.isNaN(step))) {{
                return '';
            }}
            return formatTime(Math.max(step, 1));
        }};

        function calculateSteps() {{
            const desiredRetention = parseFloat(document.querySelector("#desired-retention").value);
            const factor = calculateFactor(desiredRetention);

            const learningStep1Count = stats[1]['count'];
            const learningStep1 = calculateStep(stability[1], factor);
            const learningStep2Count = (stats[2]['count'] + stats[3]['count'] + stats[4]['count']) / 3;
            const learningStep2 = calculateStep(Math.min(stability[2] * 2 - stability[1], stability[3], stability[4]), factor);

            if (learningStep1Count < 100) {{
                learningStepRow.innerText = '{i18n.t("insufficient-learn-step-data")}';
            }} else if (learningStep2Count < 100) {{
                learningStepRow.innerText = `${{learningStep1}}`;
            }} else {{
                learningStepRow.innerText = (!learningStep1 && !learningStep2) 
                    ? '{i18n.t("keep-steps-blank")}' 
                    : `${{learningStep1}} ${{learningStep2}}`;
            }}

            const relearningStepCount = stats[0]['count'];
            const relearningStep = calculateStep(stability[0], factor, relearningStepCount);
            if (relearningStepCount < 100) {{
                relearningStepRow.innerText = '{i18n.t("insufficient-learn-step-data")}';
            }} else {{
                relearningStepRow.innerText = !relearningStep 
                    ? "You don't need relearning steps" 
                    : relearningStep;
            }}
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
        f"<summary>{i18n.t('interpretation')}</summary>"
        "<ul>" + i18n.t("step-stats-help") + "</ul>"
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
    _line_now(i, i18n.t("studied-cards"), f"{card_cnt} cards")
    _line_now(i, i18n.t('total-review-time'), f"{time_sum/3600:.1f} hours")
    if time_sum > 0:
        _line_now(
            i,
            i18n.t('knowledge-acquisition-rate'),
            i18n.t('x-cards-per-hour', count=round(estimated_total_knowledge / (time_sum/3600), 1)),
        )
    title = CollectionStats._title(
        self,
        i18n.t("fsrs-stats"),
    )
    stats_data = _lineTbl_now(i)
    interpretation = (
        f"<details><summary>{i18n.t('interpretation')}</summary><ul>" +
        i18n.t("fsrs-stats-help")
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
            (1, "#7c7", i18n.t("review-count-young")),
            (2, "#070", i18n.t("review-count-mature")),
            (3, "#ffd268", i18n.t("retention-rate-young")),
            (4, "#e49a60", i18n.t("retention-rate-mature")),
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

    txt1 = self._title(i18n.t('retention-graph'), i18n.t('retention-graph-help'))
    txt1 += plot("retention", data, ylabel=i18n.t('review-count'), ylabel2=i18n.t('retention-rate'))
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
        pname = i18n.t('month')
    elif self.type == 1:
        period = 365
        pname = i18n.t('year')
    elif self.type == 2:
        period = 36500
        pname = i18n.t('deck-life')
    pastPeriod = stats_list(lim, (mw.col.sched.day_cutoff - 86400 * period) * 1000)
    true_retention_part = CollectionStats._title(
        self,
        i18n.t('true-retention'),
        f"<p>{i18n.t('true-retention-help')}</p>",
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
                <td class="trl" rowspan=3><b>{i18n.t('past')}</b></td>
                <td class="trc" colspan=9><b>{i18n.t('reviews-on-cards')}</b></td>
                <td class="trc" colspan=2 valign=middle><b>{i18n.t('cards')}</b></td>
            </tr>
            <tr>
                <td class="trc" colspan=3><span class="young"><b>{i18n.t('young-annotated', mature_ivl=config.mature_ivl)}</b></span></td>
                <td class="trc" colspan=3><span class="mature"><b>{i18n.t('mature-annotated', mature_ivl=config.mature_ivl)}</b></span></td>
                <td class="trc" colspan=3><span class="total"><b>{i18n.t('total')}</b></span></td>
                <td class="trc" rowspan=2><span class="young"><b>{i18n.t('learned')}</b></span></td>
                <td class="trc" rowspan=2><span class="relearn"><b>{i18n.t('relearned')}</b></span></td>
            </tr>
            <tr>
                <td class="trc"><span class="young">{i18n.t('pass')}</span></td>
                <td class="trc"><span class="young">{i18n.t('fail')}</span></td>
                <td class="trc"><span class="young">{i18n.t('retention')}</span></td>
                <td class="trc"><span class="mature">{i18n.t('pass')}</span></td>
                <td class="trc"><span class="mature">{i18n.t('fail')}</span></td>
                <td class="trc"><span class="mature">{i18n.t('retention')}</span></td>
                <td class="trc"><span class="total">{i18n.t('pass')}</span></td>
                <td class="trc"><span class="total">{i18n.t('fail')}</span></td>
                <td class="trc"><span class="total">{i18n.t('retention')}</span></td>
            </tr>"""
    true_retention_part += stats_row(i18n.t('day'), pastDay)
    true_retention_part += stats_row(i18n.t('yesterday'), pastYesterday)
    true_retention_part += stats_row(i18n.t('week'), pastWeek)
    true_retention_part += stats_row(pname, pastPeriod)
    true_retention_part += "</table>"
    true_retention_part += f"<p>{i18n.t('true-retention-mature-help')}</p>"
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
