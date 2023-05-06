from .utils import *
from .configuration import Config

from anki.exporting import AnkiPackageExporter
from anki.decks import DeckManager
from aqt.qt import QProcess, QThreadPool, QRunnable, QObject, pyqtSignal
from aqt.utils import showInfo, showCritical, askUserDialog

import os
import time
import sys

config = Config()

RETENTION_IS_OPTIMIZED = "retention_is_optimized"
REQUEST_RETENTION = "requested_retention"
MAX_INTERVAL = "maximum_interval"
EASY_BONUS = "easy_bonus"
HARD_INTERVAL = "hard_interval"
def displayResult(result: dict[str]):
    return \
f"""    {{
        // Generated, Optimized anki deck settings
        "deckName": "{result["name"]}",
        "w": {result["w"]},
        "requestRetention": {result[REQUEST_RETENTION]}, {"//Un-optimized, Replace this with desired number." if not result[RETENTION_IS_OPTIMIZED] else ""}
        "maximumInterval": {result[MAX_INTERVAL]},
        "easyBonus": {result[EASY_BONUS]},
        "hardInterval": {result[HARD_INTERVAL]},
    }},"""

def optimize(did: int):

    try:
        # Progress bar -> tooltip
                
        from tqdm import tqdm, notebook, cli
        #from functools import partialmethod

        # orig = tqdm.update
        def update(self, n=1):
            #orig(self,n)
            self.n += n # Cant use positional or it doesn't work for some reason
            if self.n % 100 == 0:
                tooltip(f"{self.n}/{self.total} {100 * self.n/self.total}%",period=10)

        noop = lambda *args, **kwargs: noop
        orig_init = tqdm.__init__

        def new_init(self, *args, **kwargs):
            kwargs["file"] = sys.stdout
            orig_init(self, *args, **kwargs)

        tqdm.__init__ = new_init

        tqdm.update = update
        tqdm.close = noop
        tqdm.status_printer = noop
        

        notebook.status_printer = noop
        cli.status_printer = noop

        from fsrs4anki_optimizer import Optimizer
        #tqdm.__init__ = partialmethod(tqdm.__init__, disable=True)
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

    # https://stackoverflow.com/questions/1111056/get-time-zone-information-of-the-system-in-python/10854983#10854983
    offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
    offset = offset / 60 / 60 * -1

    timezone = f"Etc/GMT{'+' if offset >= 0 else ''}{int(offset)}" # Maybe make this overridable?
    print(timezone)
    revlog_start_date = "2000-01-01" # todo: implement this
    rollover = preferences.scheduling.rollover

    diag = askUserDialog("Find optimal retention? (This takes an extra long time)", ["Yes", "No", "Cancel"])
    diag.setDefault(1)
    resp = diag.run()

    if resp == "Cancel": # If they hit cancel
        tooltip("Optimization cancelled")
        return
    else:
        get_optimal_retention = resp == "Yes" # If they didn't hit cancel convert answer to bool

    class OptimizeWorker(QRunnable):
        class Events(QObject):
            finished = pyqtSignal(dict)
            stage = pyqtSignal(str)
        
        events = Events()

        def run(self):
            optimizer = Optimizer()
            
            self.events.stage.emit("Exporting deck")
            exporter.exportInto(export_file_path) # This is simply quicker than somehow making it so that anki doesn't zip the export
            optimizer.anki_extract(export_file_path)

            self.events.stage.emit("Training model")
            optimizer.create_time_series(timezone, revlog_start_date, rollover)
            optimizer.define_model()
            optimizer.train()

            DEFAULT_RETENTION = 0.8

            if get_optimal_retention:
                self.events.stage.emit("Finding optimal retention")
                optimizer.predict_memory_states()
                optimizer.find_optimal_retention(False)
            else:
                optimizer.optimal_retention = DEFAULT_RETENTION

            result = {
                # Calculated
                "name": name,
                "w": optimizer.w,
                REQUEST_RETENTION: optimizer.optimal_retention,
                RETENTION_IS_OPTIMIZED: get_optimal_retention,
                
                # Defaults
                MAX_INTERVAL: 36500, 
                EASY_BONUS: 1.3,
                HARD_INTERVAL: 1.2
                }

            self.events.finished.emit(result)

    def on_complete(result: dict[str]):
        
        config.load()

        saved_results = config.saved_optimized
        saved_results[did] = result
        config.saved_optimized = saved_results

        contents = '\n'.join(displayResult(a) for a in saved_results.values())
        output = \
f"""// Copy this into your optimizer code.
// You can edit this in the addon config.

const deckParams = [
{contents}
]
"""

        showInfo(output)

        # shutil.rmtree(tmp_dir_path)

    # Cant just call the library functions directly without anki freezing
    worker = OptimizeWorker()
    worker.events.finished.connect(on_complete)
    worker.events.stage.connect(tooltip)

    QThreadPool.globalInstance().start(worker)

downloader = QProcess()
downloader.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)

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
        # Not everyone is going to have git installed but works for testing.
        downloader.start(
            sys.executable, ["-m", "pip", "install", 
                'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.1#subdirectory=package',
            ], )
        tooltip("Installing optimizer")
        def finished(exitCode,  exitStatus):
            if exitCode == 0:
                showInfo("Optimizer installed successfully, restart for it to take effect")
            else:
                showCritical(
f"""Optimizer wasn't installed. For more information, run anki in console mode. (on windows anki-console.bat)

Error code: '{exitCode}', Error status '{exitStatus}'
"""
)
        downloader.finished.connect(finished)
