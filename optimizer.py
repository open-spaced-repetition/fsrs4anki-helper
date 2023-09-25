import typing
from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget
from .utils import *
from .configuration import *

from anki.exporting import AnkiPackageExporter
from anki.decks import DeckManager
from aqt.qt import QProcess, QThreadPool, QRunnable, QObject, pyqtSignal, QDialog
from aqt.utils import showInfo, showCritical, askUserDialog
import aqt
import aqt.forms

import os
import time
import sys
import platform


class InstallerQDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.form = aqt.forms.synclog.Ui_Dialog()
        self.form.setupUi(self)
        self.form.plainTextEdit.setPlainText("Installing optimizer...")
        self.show()

    def _on_log_entry(self, entry) -> None:
        self.form.plainTextEdit.appendPlainText(entry)


config = Config()

class Progress(QObject):
    progress = pyqtSignal(int, int)
    critical = pyqtSignal(str)

    @staticmethod
    def tooltip(n, total):
        tooltip(f"{_stage}: {n}/{total} {100 * n/total}%")


update_period = 0.1 # how long the progress tooltips are refreshed in seconds
_progress = Progress()
_progress.progress.connect(Progress.tooltip)
_progress.critical.connect(showCritical)
_stage = "Error"

_optimizing = False

def optimize(did: int):
    global _optimizing

    if not _optimizing:
        _optimizing = True
        try:
            _optimize(did)
        except:
            _optimizing = False
    else:
        showWarning("A deck is already optimizing please wait.")

def _optimize(did: int):

    try: # This code is here so that when it fails the popup can show immediately rather than after the after the cancel prompt
        # Progress bar -> tooltip
                
        from tqdm import tqdm, cli
        from tqdm.notebook import tqdm_notebook

        # orig = tqdm.update
        last_print = time.time()
        def update(self, n=1):
            nonlocal last_print
            #orig(self,n)
            self.n += n
            if last_print + update_period < time.time():
                _progress.progress.emit(self.n, self.total)
                last_print = time.time()

        noop = lambda *args, **kwargs: noop
        
        orig_init = tqdm.__init__
        def new_init(self, *args, **kwargs):
            kwargs["file"] = sys.stdout
            orig_init(self, *args, **kwargs)
        tqdm.__init__ = new_init

        orig_notebook_init = tqdm_notebook.__init__
        def new_notebook_init(self, *args, **kwargs):
            kwargs["display"] = False
            orig_notebook_init(self, *args, **kwargs)
        tqdm_notebook.__init__ = new_notebook_init

        tqdm.update = update
        tqdm.close = noop

        from fsrs4anki_optimizer import Optimizer
    except ImportError as e:
        showCritical(
f"""
Error: {e}
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
    revlog_start_date = "2000-01-01" # TODO: implement this as a config option
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
            global _optimizing
            try:
                optimizer = Optimizer()
                
                self.events.stage.emit("Exporting deck")
                exporter.exportInto(export_file_path) # This is simply quicker than somehow making it so that anki doesn't zip the export
                optimizer.anki_extract(export_file_path)

                self.events.stage.emit("Training model")
                try:
                    optimizer.create_time_series(timezone, revlog_start_date, rollover)
                except ValueError as e:
                    _progress.critical.emit(
    """You got a value error, This usually happens when the deck has no or very few reviews.
    You have to do some reviews on the deck before you optimize it!""")
                    raise e
                
                optimizer.define_model()
                try:
                    optimizer.pretrain(verbose=False)
                except AttributeError: # The optimizer in version 3 has no pretrain function
                    pass
                optimizer.train(verbose=False)

                DEFAULT_RETENTION = 0.8

                if get_optimal_retention:
                    self.events.stage.emit("Finding optimal retention (Ignore right number)")
                    optimizer.predict_memory_states()
                    optimizer.find_optimal_retention()
                else:
                    optimizer.optimal_retention = DEFAULT_RETENTION

                result = {
                    # Calculated
                    "name": name,
                    "w": optimizer.w,
                    REQUEST_RETENTION: optimizer.optimal_retention,
                    RETENTION_IS_NOT_OPTIMIZED: not get_optimal_retention,
                    
                    # Defaults
                    MAX_INTERVAL: 36500, 
                    EASY_BONUS: 1.3,
                    HARD_INTERVAL: 1.2
                    }

                self.events.finished.emit(result)
            except Exception as e:
                _optimizing = False
                raise e


    def on_complete(result: dict[str]):
        global _optimizing

        _optimizing = False

        config.load()

        saved_results = config.saved_optimized
        saved_results[did] = result
        config.saved_optimized = saved_results

        showInfo(config.results_string())

        # shutil.rmtree(tmp_dir_path)

    # Uses workers to avoid blocking main thread
    worker = OptimizeWorker()
    worker.events.finished.connect(on_complete)

    def on_stage(stage):
        global _stage
        tooltip(stage)
        _stage = stage

    worker.events.stage.connect(on_stage)

    QThreadPool.globalInstance().start(worker)

downloader = QProcess()
# downloader.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    
def install(_):
    global downloader
    confirmed = askUser(
"""This will install the optimizer onto your system.

You will need to install python or at least pip for this to work.

This will occupy about 1GB of space and can take some time.
Please dont close anki until the popup arrives telling you its complete.

There are other options if you just need to optimize a few decks
(consult https://github.com/open-spaced-repetition/fsrs4anki/releases).

Proceed?""",
title="Install local optimizer?")

        
    diag = InstallerQDialog(mw)
    diag.show()

    def onReadyReadStandardOutput():
        diag._on_log_entry(downloader.readAllStandardOutput().data().decode("utf-8"))
        diag._on_log_entry(downloader.readAllStandardError().data().decode("utf-8"))
        # print(downloader.readAllStandardError().data().decode("utf-8"))

    downloader.readyReadStandardOutput.connect(onReadyReadStandardOutput)
    downloader.readyReadStandardError.connect(onReadyReadStandardOutput)

    cancelled = False

    def cancel(_):
        nonlocal cancelled
        cancelled = True
        downloader.close()
        showCritical("Installation canceled by user.")

    diag.closeEvent = cancel

    if confirmed: 
        # Not everyone is going to have git installed but works for testing.
        PACKAGE = 'fsrs4anki-optimizer'

        if platform.system() in ("Windows", "Darwin"): # For windows
            anki_path = sys.executable
            anki_lib_path = os.path.dirname(anki_path)
            anki_lib_path = os.path.join(anki_lib_path, "lib")

            print(anki_lib_path)

            # https://stackoverflow.com/a/2916320
            # --no-user apparently helps with microsoft store installed python https://stackoverflow.com/questions/63783587/pip-install-cannot-combine-user-and-target
            downloader.start("pip", ["install", f'--target={anki_lib_path}', PACKAGE, "--no-user"])
        elif platform.system() == "Linux": # For linux (mac untested)
            downloader.start(sys.executable, ["-m", "pip", "install", "--user", "--break-system-packages", PACKAGE])
        else:
            showCritical(f"Not supported for operating system: '{platform.system()}'")

        tooltip("Installing optimizer")

        def finished(exitCode,  exitStatus):
            if cancelled:
                return

            if exitCode == 0:
                showInfo("Optimizer installed successfully, restart for it to take effect")
            else:
                showCritical(
f"""Optimizer wasn't installed. For more information, run anki in console mode. (on windows anki-console.bat)

Error code: '{exitCode}', Error status '{exitStatus}'
"""
)
        downloader.finished.connect(finished)

        # timer = mw.progress.timer(100, lambda: onReadyReadStandardOutput(diag), True, False, parent=mw)

