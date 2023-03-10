from aqt.gui_hooks import sync_did_finish
from .reschedule import reschedule
from .configuration import Config


def auto_reschedule():
    config = Config()
    config.load()
    if config.auto_reschedule_after_sync:
        reschedule(None, True)


def init_sync_hook():
    sync_did_finish.append(auto_reschedule)
