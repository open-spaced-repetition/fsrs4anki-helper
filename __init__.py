from anki.lang import _
from aqt.gui_hooks import deck_browser_will_show_options_menu
from aqt import mw

from .reschedule import reschedule


def addToMain(fun, text, shortcut=None):
    """fun -- without argument
    text -- the text in the menu
    """
    action = mw.form.menuTools.addAction(text)
    action.triggered.connect(lambda b, did=None: fun(did))
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))


def addActionToGear(fun, text):
    """fun -- takes an argument, the did
    text -- what's written in the gear."""

    def aux(m, did):
        a = m.addAction(text)
        a.triggered.connect(lambda b, did=did: fun(did))

    deck_browser_will_show_options_menu.append(aux)


addToMain(reschedule, _("Reschedule all cards"))
addActionToGear(reschedule, "Reschedule cards in deck")
