from aqt.gui_hooks import deck_browser_will_show_options_menu, state_did_change
from aqt import mw
from aqt.qt import QAction
from aqt.utils import tooltip
from typing import Callable

from .dsr_state import init_dsr_status_hook
from .sync_hook import init_sync_hook
from .schedule.reschedule import reschedule
from .schedule.postpone import postpone
from .schedule.advance import advance
from .schedule.reset import clear_custom_data
from .schedule.disperse_siblings import disperse_siblings
from .schedule.easy_days import (
    easy_days,
    easy_day_for_sepcific_date,
    easy_days_review_ratio,
)
from .schedule import init_review_hook
from .stats import init_stats
from .browser.browser import init_browser
from .configuration import Config, run_on_configuration_change


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
        a = m.addAction(text)
        a.triggered.connect(lambda b, did=did: fun(did))

    deck_browser_will_show_options_menu.append(aux)


def set_auto_reschedule_after_sync(checked, _):
    config.auto_reschedule_after_sync = checked


menu_auto_reschedule_after_sync = checkable(
    title="Auto reschedule cards reviewed on other devices after sync",
    on_click=set_auto_reschedule_after_sync,
)


def set_auto_disperse_after_sync(checked, _):
    config.auto_disperse_after_sync = checked


menu_auto_disperse_after_sync = checkable(
    title="Auto disperse siblings reviewed on other devices after sync",
    on_click=set_auto_disperse_after_sync,
)


def set_auto_disperse_when_review(checked, _):
    config.auto_disperse_when_review = checked


menu_auto_disperse = checkable(
    title="Auto disperse siblings when review", on_click=set_auto_disperse_when_review
)


def set_auto_disperse_after_reschedule(checked, _):
    config.auto_disperse_after_reschedule = checked


menu_auto_disperse_after_reschedule = checkable(
    title="Disperse siblings after rescheduling (breaks Load Balance)",
    on_click=set_auto_disperse_after_reschedule,
)


def set_display_memory_state(checked, _):
    config.display_memory_state = checked


menu_display_memory_state = checkable(
    title="Display memory state after answer", on_click=set_display_memory_state
)


def set_load_balance(checked, _):
    config.load_balance = checked


menu_load_balance = checkable(
    title="Load Balance when rescheduling", on_click=set_load_balance
)


def reschedule_recent(did):
    reschedule(did, recent=True)


menu_reschedule = build_action(reschedule, "Reschedule all cards")
add_action_to_gear(reschedule, "Reschedule all cards")

menu_reschedule_recent = build_action(
    reschedule_recent,
    f"Reschedule cards reviewed in the last {config.days_to_reschedule} days",
)
add_action_to_gear(reschedule_recent, "Reschedule recently reviewed cards")

menu_postpone = build_action(postpone, "Postpone cards in all decks")
add_action_to_gear(postpone, "Postpone cards")

menu_advance = build_action(advance, "Advance cards in all decks")
add_action_to_gear(advance, "Advance cards")

menu_reset = build_action(clear_custom_data, "Clear custom data in all cards")

menu_disperse_siblings = build_action(disperse_siblings, "Disperse all siblings")


menu_for_helper = mw.form.menuTools.addMenu("FSRS4Anki Helper")
menu_for_helper.addAction(menu_auto_reschedule_after_sync)
menu_for_helper.addAction(menu_auto_disperse_after_sync)
menu_for_helper.addAction(menu_auto_disperse)
menu_for_helper.addAction(menu_display_memory_state)
menu_for_helper.addAction(menu_load_balance)
menu_for_helper.addAction(menu_auto_disperse_after_reschedule)
menu_for_easy_days = menu_for_helper.addMenu(
    "Less Anki on Easy Days (requires Load Balancing)"
)
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_reschedule)
menu_for_helper.addAction(menu_reschedule_recent)
menu_for_helper.addAction(menu_postpone)
menu_for_helper.addAction(menu_advance)
menu_for_helper.addAction(menu_reset)
menu_for_helper.addAction(menu_disperse_siblings)


menu_apply_easy_days = build_action(easy_days, "Apply easy days now")
menu_apply_easy_days_for_specific_date = build_action(
    easy_day_for_sepcific_date, "Apply easy days for specific dates"
)
menu_easy_days_review_ratio = build_action(
    lambda did: easy_days_review_ratio(did, config), "Set Easy Days Review Percentage"
)


def set_easy_days(day, checked, action):
    if len(config.easy_days) >= 6 and checked:
        tooltip("You can only select up to 6 days as easy days.")
        action.setChecked(False)
    else:
        config.easy_days = (day, checked)


menu_for_easy_0 = checkable(
    title="Easy Monday", on_click=lambda x, a: set_easy_days(0, x, a)
)
menu_for_easy_1 = checkable(
    title="Easy Tuesday", on_click=lambda x, a: set_easy_days(1, x, a)
)
menu_for_easy_2 = checkable(
    title="Easy Wednesday", on_click=lambda x, a: set_easy_days(2, x, a)
)
menu_for_easy_3 = checkable(
    title="Easy Thursday", on_click=lambda x, a: set_easy_days(3, x, a)
)
menu_for_easy_4 = checkable(
    title="Easy Friday", on_click=lambda x, a: set_easy_days(4, x, a)
)
menu_for_easy_5 = checkable(
    title="Easy Saturday", on_click=lambda x, a: set_easy_days(5, x, a)
)
menu_for_easy_6 = checkable(
    title="Easy Sunday", on_click=lambda x, a: set_easy_days(6, x, a)
)


def set_auto_easy_days(checked, _):
    config.auto_easy_days = checked


menu_for_auto_easy_days = checkable(
    title="Auto apply easy days on closing collection",
    on_click=set_auto_easy_days,
)

menu_for_easy_days.addAction(menu_apply_easy_days_for_specific_date)
menu_for_easy_days.addAction(menu_apply_easy_days)
menu_for_easy_days.addAction(menu_for_auto_easy_days)
menu_for_easy_days.addSeparator()
menu_for_easy_days.addAction(menu_for_easy_0)
menu_for_easy_days.addAction(menu_for_easy_1)
menu_for_easy_days.addAction(menu_for_easy_2)
menu_for_easy_days.addAction(menu_for_easy_3)
menu_for_easy_days.addAction(menu_for_easy_4)
menu_for_easy_days.addAction(menu_for_easy_5)
menu_for_easy_days.addAction(menu_for_easy_6)
menu_for_easy_days.addSeparator()
menu_for_easy_days.addAction(menu_easy_days_review_ratio)


def adjust_menu():
    if mw.col is not None:
        menu_reschedule_recent.setText(
            f"Reschedule cards reviewed in the last {config.days_to_reschedule} days"
        )
        menu_auto_reschedule_after_sync.setChecked(config.auto_reschedule_after_sync)
        menu_auto_disperse_after_sync.setChecked(config.auto_disperse_after_sync)
        menu_auto_disperse.setChecked(config.auto_disperse_when_review)
        menu_display_memory_state.setChecked(config.display_memory_state)
        menu_load_balance.setChecked(config.load_balance)
        menu_auto_disperse_after_reschedule.setChecked(
            config.auto_disperse_after_reschedule
        )
        menu_for_auto_easy_days.setChecked(config.auto_easy_days)
        menu_for_easy_0.setChecked(0 in config.easy_days)
        menu_for_easy_1.setChecked(1 in config.easy_days)
        menu_for_easy_2.setChecked(2 in config.easy_days)
        menu_for_easy_3.setChecked(3 in config.easy_days)
        menu_for_easy_4.setChecked(4 in config.easy_days)
        menu_for_easy_5.setChecked(5 in config.easy_days)
        menu_for_easy_6.setChecked(6 in config.easy_days)


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
