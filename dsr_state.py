from anki import hooks
from anki.template import TemplateRenderContext, TemplateRenderOutput

from .configuration import Config
from .utils import power_forgetting_curve, get_last_review_date, mw


# called each time a custom filter is encountered
def fsrs_field_filter(
    field_text: str,
    field_name: str,
    filter_name: str,
    context: TemplateRenderContext,
) -> str:
    if not filter_name.startswith("fsrs-"):
        # not our filter, return string unchanged
        return field_text

    # split the name into the 'fsrs' prefix, and the rest
    try:
        (label, rest) = filter_name.split("-", maxsplit=1)
    except ValueError:
        return invalid_name(filter_name)

    # call the appropriate function
    if rest == "D":
        return calc_d(context)
    elif rest == "S":
        return calc_s(context)
    elif rest == "R":
        return calc_r(context)
    else:
        return invalid_name(filter_name)


def invalid_name(filter_name: str) -> str:
    return f"invalid filter name: {filter_name}"


def calc_s(ctx: TemplateRenderContext) -> str:
    card = ctx.card()
    if card.memory_state is None:
        return ""
    stability = card.memory_state.stability
    return f"{stability:.2f} days"


def calc_d(ctx: TemplateRenderContext) -> str:
    card = ctx.card()
    if card.memory_state is None:
        return ""
    difficulty = (card.memory_state.difficulty - 1) / 9
    return f"{(difficulty * 100):.0f}%"


def calc_r(ctx: TemplateRenderContext) -> str:
    card = ctx.card()
    if card.memory_state is None:
        return ""
    stability = card.memory_state.stability
    last_review_date = get_last_review_date(card)
    elapsed_days = mw.col.sched.today - last_review_date
    retrievability = power_forgetting_curve(elapsed_days, stability)
    return f"{(retrievability * 100):.1f}%"


def on_card_did_render(
    output: TemplateRenderOutput, context: TemplateRenderContext
) -> None:
    config = Config()
    config.load()
    if config.display_memory_state:
        fsrs_enabled = mw.col.get_config("fsrs")
        fsrs_status = f"""<br><span id="FSRS_status" style="font-size:12px;opacity:0.5;font-family:monospace;text-align:left;line-height:1em;margin-top:10em;display:inline-block;">
        {"FSRS: enabled" if fsrs_enabled else "FSRS: disabled"}
        <br>D: {calc_d(context) if fsrs_enabled else "Unknown"}
        <br>S: {calc_s(context) if fsrs_enabled else "Unknown"}
        <br>R: {calc_r(context) if fsrs_enabled else "Unknown"}
        </span>"""
        output.answer_text += fsrs_status


def init_dsr_status_hook():
    hooks.card_did_render.append(on_card_did_render)
    hooks.field_filter.append(fsrs_field_filter)
