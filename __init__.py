from anki.lang import _
from aqt.gui_hooks import deck_browser_will_show_options_menu, state_did_change
from aqt import mw
from aqt.qt import QAction
from typing import Callable

from .sync_hook import init_sync_hook
from .reschedule import reschedule
from .postpone import postpone
from .advance import advance
from .reset import reset
from .disperse_siblings import disperse_siblings
from .stats import init_stats
from .configuration import (
    Config,
    run_on_configuration_change
)


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
def checkable(title: str, on_click: Callable[[bool], None]) -> QAction:
    action = QAction(title, mw, checkable=True)  # noqa
    action.triggered.connect(on_click)  # noqa
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


def set_auto_reschedule(checked):
    config.auto_reschedule_after_sync = checked


menu_auto_reschedule = checkable(
    title="Auto reschedule recent reviews after sync",
    on_click=set_auto_reschedule
)


def set_load_balance(checked):
    config.load_balance = checked


menu_load_balance = checkable(
    title="Load Balance when rescheduling (requires Fuzz)",
    on_click=set_load_balance
)


def reschedule_recent(did):
    reschedule(did, recent=True)


menu_reschedule = build_action(reschedule, _(
    "Reschedule all cards"), "CTRL+SHIFT+R")
add_action_to_gear(reschedule, "Reschedule cards in deck")

menu_reschedule_recent = build_action(
    reschedule_recent, _(f"Reschedule cards reviewed in the last {config.days_to_reschedule} days"), "CTRL+R")

menu_postpone = build_action(postpone, _("Postpone cards in all decks"))
add_action_to_gear(postpone, "Postpone cards in deck")

menu_advance = build_action(advance, _("Advance cards in all decks"))
add_action_to_gear(advance, "Advance cards in deck")

menu_reset = build_action(reset, _("Undo reschedulings in all cards"))

menu_disperse_siblings = build_action(disperse_siblings, _("Disperse Siblings in all decks"))

menu_for_helper = mw.form.menuTools.addMenu("FSRS4Anki Helper")
menu_for_helper.addAction(menu_auto_reschedule)
menu_for_helper.addAction(menu_load_balance)
menu_for_free_days = menu_for_helper.addMenu("No Anki on Free Days (requires Load Balancing)")
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_reschedule)
menu_for_helper.addAction(menu_reschedule_recent)
menu_for_helper.addAction(menu_postpone)
menu_for_helper.addAction(menu_advance)
menu_for_helper.addAction(menu_reset)
menu_for_helper.addAction(menu_disperse_siblings)


def set_free_days(day, checked):
    config.free_days = (day, checked)


menu_for_free_0 = checkable(
    title="Free Mon", on_click=lambda x: set_free_days(0, x))
menu_for_free_1 = checkable(
    title="Free Tue", on_click=lambda x: set_free_days(1, x))
menu_for_free_2 = checkable(
    title="Free Wed", on_click=lambda x: set_free_days(2, x))
menu_for_free_3 = checkable(
    title="Free Thu", on_click=lambda x: set_free_days(3, x))
menu_for_free_4 = checkable(
    title="Free Fri", on_click=lambda x: set_free_days(4, x))
menu_for_free_5 = checkable(
    title="Free Sat", on_click=lambda x: set_free_days(5, x))
menu_for_free_6 = checkable(
    title="Free Sun", on_click=lambda x: set_free_days(6, x))
menu_for_free_days.addAction(menu_for_free_0)
menu_for_free_days.addAction(menu_for_free_1)
menu_for_free_days.addAction(menu_for_free_2)
menu_for_free_days.addAction(menu_for_free_3)
menu_for_free_days.addAction(menu_for_free_4)
menu_for_free_days.addAction(menu_for_free_5)
menu_for_free_days.addAction(menu_for_free_6)


def adjust_menu():
    if mw.col is not None:
        menu_reschedule_recent.setText(f"Reschedule cards reviewed in the last {config.days_to_reschedule} days")
        menu_auto_reschedule.setChecked(config.auto_reschedule_after_sync)
        menu_load_balance.setChecked(config.load_balance)
        menu_for_free_0.setChecked(0 in config.free_days)
        menu_for_free_1.setChecked(1 in config.free_days)
        menu_for_free_2.setChecked(2 in config.free_days)
        menu_for_free_3.setChecked(3 in config.free_days)
        menu_for_free_4.setChecked(4 in config.free_days)
        menu_for_free_5.setChecked(5 in config.free_days)
        menu_for_free_6.setChecked(6 in config.free_days)


@state_did_change.append
def state_did_change(_next_state, _previous_state):
    adjust_menu()


@run_on_configuration_change
def configuration_changed():
    config.load()
    adjust_menu()


init_sync_hook()
init_stats()