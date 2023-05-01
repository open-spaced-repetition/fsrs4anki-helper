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

            self.process = Process(target=wrapper, args=[*args, self.locked])
            self.locked.value = True
            self.process.start()
            self.message = message
            tooltip(self.message) # Print the tooltip to the console even if nothing changed so that the user can see what its doing
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
        subprocess.run([sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", out_save])

    _worker.work(optimize)

    #tooltip(f"Parameters saved at \"{out_save}\"")

def install(_):
    global _worker

    confirmed = askUser(
"""This will install the optimizer onto your system.
This will occupy 0.5-1GB of space and can take some time.
Anki will appear frozen until it is complete.

There are other options if you just need to optimize a few decks
(consult https://github.com/open-spaced-repetition/fsrs4anki/releases)

Proceed?""",
title="Install local optimizer?")

    if confirmed:
        # I opted not to use subprocess's (and not freeze anki) purely because its impossible to notify the user when its completed
        # If someone can figure it out I implore you to implement it
        # _worker.work(_install,[],"installing/updating optimizer (Leave anki open. This may take some time)")

        _install()
        tooltip("Optimizer package installed successfully, Restart anki for it to take effect")

def _install():
    subprocess.run([sys.executable, "-m", "pip", "install", 
            'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.0#subdirectory=pip']
            ).check_returncode()