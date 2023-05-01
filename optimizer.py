from .utils import *

from anki.exporting import AnkiPackageExporter
from aqt.qt import QProcess
from aqt.utils import showInfo

import os
import sys
import json

class ExclusiveWorker:
    """Used to ensure that 2 tasks dont run at once"""
    process = QProcess()
    working = False
    message = ""

    def work(self, args=[], on_complete=lambda:None, message="Something is processing"):
        if not self.working:
            
            def wrapper():
                on_complete()
                self.process.finished.disconnect()
                self.working = False

            self.process.start(args[0], args[1:])
            self.process.finished.connect(wrapper)
            self.working = True

        else:
            tooltip(f"Waiting for '{self.message}' to complete")

_worker = ExclusiveWorker()
install_checked = False

def optimize(did: int):
    global _worker

    try:
        from fsrs4anki_optimizer import Optimizer
    except ImportError:
        showWarning("You need to have the optimizer installed in order to optimize your decks using this option")
        return

    exporter = AnkiPackageExporter(mw.col)

    exporter.did = did
    exporter.includeMedia = False
    exporter.includeSched = True
    
    dirpath = os.path.expanduser("~/.fsrs4ankiHelperTemp")
    filepath = f"{dirpath}/{did}.apkg"
    
    if not os.path.isdir(dirpath):
        os.mkdir(dirpath)

    exporter.exportInto(filepath) 

    preferences = mw.col.get_preferences()

    timezone = "Europe/London" # todo: Automate this

    revlog_start_date = "2000-01-01" # todo: implement this

    # This is a workaround to the fact that module doesn't take these as arguments
    remembered_fallbacks = { 
        "timezone": timezone, 
        "next_day": preferences.scheduling.rollover,
        "revlog_start_date": revlog_start_date,
        "preview": "n"
    }
    config_save = os.path.expanduser("~/.fsrs4anki_optimizer")
    with open(config_save, "w+") as f:
        json.dump(remembered_fallbacks, f)

    # The actual optimizer bit

    out_save = os.path.expanduser("~/fsrs4ankioptimized")

    def optimize():
        _worker.work([sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", out_save])

    _worker.work(optimize)

    #tooltip(f"Parameters saved at \"{out_save}\"")

def install(_):
    global _worker

    confirmed = askUser(
"""This will install the optimizer onto your system.
This will occupy 0.5-1GB of space and can take some time.
Please dont close anki until the popup arrives telling you its complete

There are other options if you just need to optimize a few decks
(consult https://github.com/open-spaced-repetition/fsrs4anki/releases)

Proceed?""",
title="Install local optimizer?")

    if confirmed: 
        _worker.work(
            [sys.executable, "-m", "pip", "install", 
                'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.0#subdirectory=pip',
                ],
                lambda: showInfo("Optimizer installed successfully, restart for it to take effect"),
                "Installing optimizer"
            )
