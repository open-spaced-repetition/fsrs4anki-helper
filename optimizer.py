from .utils import *

from anki.exporting import AnkiPackageExporter

import os
import sys

def optimize(did: int):
    export(did)

def export(did: int):
    exporter = AnkiPackageExporter(mw.col)

    exporter.did = did
    exporter.includeMedia = False
    exporter.includeSched = True
    
    path = os.path.expanduser("~/.fsrs4ankiHelperTemp")
    
    if not os.path.isdir(path):
        os.mkdir(path)

    exporter.exportInto(f"{path}/{did}.apkg")