from .utils import *

from anki.exporting import AnkiPackageExporter

import os
import subprocess
from multiprocessing import Process, Value
import ctypes
import sys
import json

class ExclusiveWorker:
    """Used to ensure that 2 tasks dont run at once"""
    process : None | Process = None
    locked = Value(ctypes.c_bool, False)
    message = ""

    def work(self, target, args=[], message="Something is processing"):
        """DO NOT use tooltips in the target function, for some reason it crashes my whole computer"""

        if not self.locked.value:
            def wrapper(*args, **kwargs):
                target(*args[:-1], **kwargs)
                
                working = args[-1]
                working.value = False

                print("In wrapper")

            self.process = Process(target=wrapper, args=[*args, self.locked])
            self.locked.value = True
            self.process.start()
            self.message = message
        tooltip(self.message) # Print the tooltip to the console even if nothing changed so that the user can see what its doing

_worker = ExclusiveWorker()
install_checked = False

def optimize(did: int):
    global _worker, install_checked

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

    def install():
        print("Hi")
        subprocess.run([sys.executable, "-m", "pip", "install", 
                'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.0#subdirectory=pip']
                )
        #tooltip("Installed")

    print(f"{_worker.locked=}")

    if not install_checked:
        print("In this place for some reason ", install_checked)
        _worker.work(install,[],"installing/updating optimizer")
        install_checked = True
        return

    out_save = os.path.expanduser("~/fsrs4ankioptimized")

    def noop():
        pass

    _worker.work(noop)
    # This should probably trigger a prompt warning the user its about to install the module

    #tooltip("Generating optimized parameters (This can take some time)")
    #subprocess.run([sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", out_save])

    #tooltip(f"Parameters saved at \"{out_save}\"")
