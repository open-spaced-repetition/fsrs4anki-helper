from .utils import *

from anki.exporting import AnkiPackageExporter

import os
import subprocess
import sys
import json

def optimize(did: int):
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

    out_save = os.path.expanduser("~/fsrs4ankioptimized")

    # This should probably trigger a prompt warning the user its about to install the module
    subprocess.run([sys.executable, "-m", "pip", "install", 
                    'fsrs4anki_optimizer @ git+https://github.com/open-spaced-repetition/fsrs4anki@v3.18.0#subdirectory=pip'])


    tooltip("Generating optimized parameters (This can take some time)")
    subprocess.run([sys.executable, "-m", "fsrs4anki_optimizer", filepath, "-y", "-o", out_save])

    tooltip(f"Parameters saved at \"{out_save}\"")
