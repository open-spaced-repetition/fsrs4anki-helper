from anki.lang import _
from aqt.gui_hooks import deck_browser_will_show_options_menu
from aqt import mw
from aqt.qt import QAction
from typing import Callable

from .reschedule import reschedule
from .postpone import postpone
from .advance import advance
from .configuration import (
    Config,
    run_on_configuration_change
)

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


def set_load_balance(checked):
    config.load_balance = checked


menu_load_balance = checkable(
    title="Enable load balance during rescheduling",
    on_click=set_load_balance
)

menu_reschedule = build_action(reschedule, _("Reschedule all cards"), "CTRL+R")
add_action_to_gear(reschedule, "Reschedule cards in deck")

menu_postpone = build_action(postpone, _("Postpone all cards"))
add_action_to_gear(postpone, "Postpone cards in deck")

menu_advance = build_action(advance, _("Advance all cards"))
add_action_to_gear(advance, "Advance cards in deck")

menu_for_helper = mw.form.menuTools.addMenu("FSRS4Anki Helper")
menu_for_helper.addAction(menu_load_balance)
menu_for_helper.addSeparator()
menu_for_helper.addAction(menu_reschedule)
menu_for_helper.addAction(menu_postpone)
menu_for_helper.addAction(menu_advance)


def adjust_menu():
    if mw.col is not None:
        menu_load_balance.setChecked(config.load_balance)


@run_on_configuration_change
def configuration_changed():
    config.load()
    adjust_menu()
