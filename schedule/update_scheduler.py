from aqt.utils import askUser, showInfo
from aqt import mw
from ..utils import get_version, geq_version

import urllib.request

SCHEDULER_URL = "https://raw.githubusercontent.com/open-spaced-repetition/fsrs4anki/main/fsrs4anki_scheduler.js"

def get_internet_scheduler():
    with urllib.request.urlopen(SCHEDULER_URL) as req:
        return req.read().decode("UTF8")

def update_scheduler(_):
    custom_scheduler = mw.col.get_config("cardStateCustomizer", None)
    try:
        version = get_version(custom_scheduler)
    except IndexError:
        if askUser(
            "You dont appear to have the fsrs4anki scheduler set up\n"
            "Would you like to replace your custom scheduling code with the latest?"
        ):
            mw.col.set_config("cardStateCustomizer", get_internet_scheduler(), undoable=True)
            showInfo("Successfully added scheduler, check it in the custom scheduling section of your deck config")
            return
        else:
            return