from .utils import *

from anki.exporting import AnkiPackageExporter
from anki.decks import DeckManager
from aqt.qt import QProcess, QThread, QObject, pyqtSignal
from aqt.utils import showInfo, showCritical

import os
import shutil
import sys
import json

# https://stackoverflow.com/a/67238486
# Disable this for anki to report a massive amount of errors
from tqdm import tqdm
from functools import partialmethod

tqdm.__init__ = partialmethod(tqdm.__init__, disable=True)

thread = QThread()

def optimize(did: int):
    global thread

    try:
        from fsrs4anki_optimizer import Optimizer
    except ImportError:
        showCritical(
"""
You need to have the optimizer installed in order to optimize your decks using this option.
Please run Tools>FSRS4Anki helper>Install local optimizer.
Alternatively, use a different method of optimizing (https://github.com/open-spaced-repetition/fsrs4anki/releases)
""")
        return

    exporter = AnkiPackageExporter(mw.col)
    manager = DeckManager(mw.col)
    deck = manager.get(did)
    assert deck
    name = deck["name"]

    dir_path = os.path.expanduser("~/.fsrs4ankiHelper")
    tmp_dir_path = f"{dir_path}/tmp"

    exporter.did = did
    exporter.includeMedia = False
    exporter.includeSched = True

    export_file_path = f"{tmp_dir_path}/{did}.apkg"
    
    if not os.path.isdir(dir_path):
        os.mkdir(dir_path)
    if not os.path.isdir(tmp_dir_path):
        os.mkdir(tmp_dir_path)


    preferences = mw.col.get_preferences()

    timezone = "Europe/London" # todo: Automate this
    revlog_start_date = "2000-01-01" # todo: implement this
    rollover = preferences.scheduling.rollover

    class Worker(QObject):
        finished = pyqtSignal(str)
        stage = pyqtSignal(str)

        def optimize(self):
            optimizer = Optimizer()

            self.stage.emit("Exporting deck")
            exporter.exportInto(export_file_path) # This is simply quicker than somehow making it so that anki doesn't zip the export
            optimizer.anki_extract(export_file_path)

            self.stage.emit("Training model")
            optimizer.create_time_series(timezone, revlog_start_date, rollover)
            optimizer.define_model()
            optimizer.train()

            self.stage.emit("Finding optimal retention")
            optimizer.predict_memory_states()
            optimizer.find_optimal_retention(False)

            result = \
f"""{{
    // Generated, Optimized anki deck settings
    // Need to add <div id=deck deck_name="{{{{Deck}}}}"></div> to your card's front template's first line.
    "deckName": "{name}",
    "w": {optimizer.w},
    "requestRetention": {optimizer.optimal_retention},
    "maximumInterval": 36500,
    "easyBonus": 1.3,
    "hardInterval": 1.2,
}},"""

            self.finished.emit(result)

    def on_complete(result: str):
        saved_results_path = f"{dir_path}/saved.json"

        try:
            with open(saved_results_path, "r+") as f:
                saved_results = json.load(f)
        except FileNotFoundError:
            saved_results = dict()

        saved_results[did] = result

        contents = '\n'.join(saved_results.values())
        output = \
f"""// Copy this into your optimizer code

const deckParams = [
{contents}]
"""

        showInfo(output)

        with open(saved_results_path, "w+") as f:
            json.dump(saved_results, f)

        shutil.rmtree(tmp_dir_path)

    # Cant just call the library functions directly without anki freezing
    worker = Worker()
    worker.finished.connect(on_complete)
    worker.stage.connect(tooltip)

    worker.moveToThread(thread)
    thread.started.connect(worker.optimize)
    thread.finished.connect(worker.deleteLater)
    thread.start()

downloader = QProcess()

def install(_):
    global downloader
    confirmed = askUser(
"""This will install the optimizer onto your system.
This will occupy 0.5-1GB of space and can take some time.
Please dont close anki until the popup arrives telling you its complete

There are other options if you just need to optimize a few decks
(consult https://github.com/open-spaced-repetition/fsrs4anki/releases)

Proceed?""",
title="Install local optimizer?")

    if confirmed: 
        downloader.start(
            sys.executable, ["-m", "pip", "install", 
                'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.1#subdirectory=package',
            ])
        tooltip("Installing optimizer")
        downloader.finished.connect(lambda: showInfo("Optimizer installed successfully, restart for it to take effect"),)
