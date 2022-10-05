from anki.lang import _
from aqt import mw

from .reschedule import reschedule


def addToMain(fun, text, shortcut=None):
    """fun -- without argument
    text -- the text in the menu
    """
    action = mw.form.menuTools.addAction(text)
    action.triggered.connect(fun)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))


addToMain(reschedule, _("Reschedule cards"))
