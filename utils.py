import re
from aqt.utils import getText, showWarning, tooltip


def check_fsrs4anki(all_config):
    if "cardStateCustomizer" not in all_config:
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return None
    custom_scheduler = all_config['cardStateCustomizer']
    if "// FSRS4Anki" not in custom_scheduler:
        showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen.")
        return None
    return custom_scheduler


def get_version(custom_scheduler):
    return list(map(int, re.findall(f'v(\d+).(\d+).(\d+)', custom_scheduler)[0]))


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None
