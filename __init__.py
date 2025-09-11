from pathlib import Path
from aqt.gui_hooks import deck_browser_will_show_options_menu, state_did_change
from aqt import mw
from aqt.qt import QAction, QDesktopServices, QUrl
from aqt.utils import openLink, askUser
from typing import Callable

from .utils import get_dr

from .dsr_state import init_dsr_status_hook
from .sync_hook import init_sync_hook
from .schedule.reschedule import reschedule
from .schedule.postpone import postpone
from .schedule.advance import advance
from .schedule.flatten import flatten
from .schedule.reset import clear_custom_data, clear_manual_rescheduling
from .schedule.disperse_siblings import disperse_siblings
from .schedule.easy_days import (
    easy_days,
    easy_day_for_sepcific_date,
)
from .schedule.remedy import remedy_hard_misuse, undo_remedy
from .schedule import init_review_hook
from .stats import init_stats
from .browser.browser import init_browser
from .configuration import Config, run_on_configuration_change
from .i18n import t

"""
Acknowledgement to Arthur Milchior, Carlos Duarte and oakkitten.
I learnt a lot from their add-ons.
https://github.com/Arthur-Milchior/Anki-postpone-reviews
https://github.com/cjdduarte/Free_Weekend_Load_Balancer
https://github.com/oakkitten/anki-delay-siblings
https://github.com/hgiesel/anki_straight_reward
"""

config = Config()
config.load()


# A tiny helper for menu items, since type checking is broken there
def checkable(title: str, on_click: Callable[[bool, QAction], None]) -> QAction:
    action = QAction(title, mw, checkable=True)

    def on_triggered(checked):
        on_click(checked, action)

    action.triggered.connect(on_triggered)
    return action


def build_action(fun, text, shortcut=None):
    """fun -- without argument
    text -- the text in the menu
    """
    action = QAction(text)
    action.triggered.connect(lambda b, did=None: fun(did))
    if shortcut:
        action.setShortcut(shortcut)
    return action


def add_action_to_gear(fun, text):
    """fun -- takes an argument, the did
    text -- what's written in the gear."""

    def aux(m, did):
        if not hasattr(m, "fsrs_helper_submenu"):
            m.fsrs_helper_submenu = m.addMenu(t("fsrs-helper"))
        a = m.fsrs_helper_submenu.addAction(text)
        a.triggered.connect(lambda b, did=did: fun(did))

    deck_browser_will_show_options_menu.append(aux)


def set_auto_reschedule_after_sync(checked, _):
    config.auto_reschedule_after_sync = checked


menu_auto_reschedule_after_sync = checkable(
    title=t("sync-auto-reschedule"),
    on_click=set_auto_reschedule_after_sync,
)


def set_auto_disperse_after_sync(checked, _):
    config.auto_disperse_after_sync = checked


menu_auto_disperse_after_sync = checkable(
    title=t("auto-disperse-after-sync"),
    on_click=set_auto_disperse_after_sync,
)


def set_auto_disperse_when_review(checked, _):
    config.auto_disperse_when_review = checked


menu_auto_disperse = checkable(
    title=t("auto-disperse-when-review"), on_click=set_auto_disperse_when_review
)


def set_auto_disperse_after_reschedule(checked, _):
    config.auto_disperse_after_reschedule = checked


menu_auto_disperse_after_reschedule = checkable(
    title=t("disperse-after-reschedule"),
    on_click=set_auto_disperse_after_reschedule,
)


def set_display_memory_state(checked, _):
    config.display_memory_state = checked


menu_display_memory_state = checkable(
    title=t("display-memory-state"), on_click=set_display_memory_state
)


def set_show_steps_stats(checked, _):
    if not config.show_steps_stats and not askUser(t("steps-stats-warning")):
        return
    config.show_steps_stats = checked


menu_show_steps_stats = checkable(
    title=t("show-steps-stats"), on_click=set_show_steps_stats
)


def reschedule_recent(did):
    reschedule(did, recent=True)


menu_reschedule = build_action(reschedule, t("reschedule-all-cards"))
add_action_to_gear(reschedule, t("reschedule-all-cards"))

menu_reschedule_recent = build_action(
    reschedule_recent,
    t("reschedule-recent-cards", count=config.days_to_reschedule),
)
add_action_to_gear(
    reschedule_recent,
    t("reschedule-recent-cards", count=config.days_to_reschedule),
)

menu_postpone = build_action(postpone, t("postpone-all-decks"))
add_action_to_gear(postpone, t("postpone-cards"))

menu_advance = build_action(advance, t("advance-all-decks"))
add_action_to_gear(advance, t("advance-cards"))

menu_flatten = build_action(flatten, t("flatten-all-decks"))
add_action_to_gear(flatten, t("flatten-cards"))

menu_reset = build_action(clear_custom_data, t("clear-custom-data-title"))

menu_clear_manual_rescheduling = build_action(
    clear_manual_rescheduling, t("delete-redundant-revlog")
)

menu_disperse_siblings = build_action(disperse_siblings, t("disperse-all-siblings"))

menu_remedy_hard_misuse = build_action(remedy_hard_misuse, t("remedy"))

menu_undo_remedy = build_action(undo_remedy, t("undo"))


def contact_author(did=None):
    openLink("https://github.com/open-spaced-repetition/fsrs4anki-helper")


menu_contact = build_action(contact_author, t("contact-author"))


def rate_on_ankiweb(did=None):
    openLink("https://ankiweb.net/shared/review/759844606")
    config.has_rated = True


menu_rate = build_action(rate_on_ankiweb, t("rate-addon"))


def visualize_schedule(did=None):
    url = "https://open-spaced-repetition.github.io/anki_fsrs_visualizer"
    deck = mw.col.decks.current()
    if "conf" in deck:
        config = mw.col.decks.get_config(deck["conf"])
        retention = get_dr(mw.col.decks, deck["id"])
        param_options = ["fsrsParams6", "fsrsParams5", "fsrsWeights"]
        fsrs_params = next(
            (
                config[param]
                for param in param_options
                if param in config and len(config[param]) > 0
            ),
            [],
        )
        fsrs_params_string = ",".join(f"{x:.4f}" for x in fsrs_params)
        url += f"/?w={fsrs_params_string}&m={retention}"

    openLink(url)


menu_visualize = build_action(visualize_schedule, t("visualize-schedule"))


def export_dataset(did=None):
    addon = mw.addonManager.addonFromModule(__name__)
    user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
    user_files.mkdir(parents=True, exist_ok=True)
    mw.col.export_dataset_for_research(f"{user_files}/{mw.pm.name}.revlog")
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(user_files.absolute())))


menu_export_dataset = build_action(export_dataset, t("export-dataset"))


def pass_fail(did=None):
    openLink("https://ankiweb.net/shared/info/876946123")


menu_pass_fail = build_action(pass_fail, t("pass-fail"))


def ajt_card_management(did=None):
    openLink("https://ankiweb.net/shared/info/1021636467")


menu_ajt_card_management = build_action(ajt_card_management, t("ajt-card-management"))


def search_stats_extended(did=None):
    openLink("https://ankiweb.net/shared/info/1613056169")


menu_search_stats_extended = build_action(
    search_stats_extended, t("search-stats-extended")
)

menu_for_helper = mw.form.menuTools.addMenu(t("fsrs-helper"))
menu_for_helper.addAction(menu_auto_reschedule_after_sync)
menu_for_helper.addAction(menu_auto_disperse_after_sync)
menu_for_helper.addAction(menu_auto_disperse)
menu_for_helper.addAction(menu_display_memory_state)
menu_for_helper.addAction(menu_show_steps_stats)
menu_for_helper.addAction(menu_auto_disperse_after_reschedule)
menu_for_easy_days = menu_for_helper.addMenu(t("less-anki-easy-days"))
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_reschedule)
menu_for_helper.addAction(menu_reschedule_recent)
menu_for_helper.addAction(menu_postpone)
menu_for_helper.addAction(menu_advance)
menu_for_helper.addAction(menu_flatten)
menu_for_helper.addAction(menu_disperse_siblings)
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_reset)
menu_for_helper.addAction(menu_clear_manual_rescheduling)
menu_for_remedy = menu_for_helper.addMenu(t("remedy-hard-misuse"))
menu_for_remedy.addAction(menu_remedy_hard_misuse)
menu_for_remedy.addAction(menu_undo_remedy)
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_contact)
menu_for_helper.addAction(menu_visualize)
if not config.has_rated:
    menu_for_helper.addAction(menu_rate)
menu_for_helper.addAction(menu_export_dataset)
menu_for_helper.addSeparator()
menu_for_recommended_addons = menu_for_helper.addMenu(t("recommended-addons"))
menu_for_recommended_addons.addAction(menu_pass_fail)
menu_for_recommended_addons.addAction(menu_ajt_card_management)
menu_for_recommended_addons.addAction(menu_search_stats_extended)

menu_apply_easy_days = build_action(easy_days, t("apply-easy-days-now"))
menu_apply_easy_days_for_specific_date = build_action(
    lambda did: easy_day_for_sepcific_date(did, config),
    t("apply-easy-days-specific"),
)


menu_for_easy_days.addAction(menu_apply_easy_days_for_specific_date)
menu_for_easy_days.addAction(menu_apply_easy_days)


def adjust_menu():
    if mw.col is not None:
        menu_reschedule_recent.setText(
            t("reschedule-recent-cards", count=config.days_to_reschedule)
        )
        menu_auto_reschedule_after_sync.setChecked(config.auto_reschedule_after_sync)
        menu_auto_disperse_after_sync.setChecked(config.auto_disperse_after_sync)
        menu_auto_disperse.setChecked(config.auto_disperse_when_review)
        menu_display_memory_state.setChecked(config.display_memory_state)
        menu_show_steps_stats.setChecked(config.show_steps_stats)
        menu_auto_disperse_after_reschedule.setChecked(
            config.auto_disperse_after_reschedule
        )


@state_did_change.append
def state_did_change(_next_state, _previous_state):
    adjust_menu()


@run_on_configuration_change
def configuration_changed():
    config.load()
    adjust_menu()


init_sync_hook()
init_stats()
init_browser()
init_review_hook()
init_dsr_status_hook()
