import re
from aqt.utils import getText, showWarning, tooltip
from collections import OrderedDict


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
    str_matches = re.findall(r'// FSRS4Anki v(\d+).(\d+).(\d+) Scheduler', custom_scheduler)
    return list(map(int, str_matches[0]))


def get_fuzz_bool(custom_scheduler):
    enable_fuzz = re.findall(
        r"const enable_fuzz *= *(true|false) *;", custom_scheduler
    )[0]
    if enable_fuzz:
        return True if enable_fuzz == "true" else False
    showWarning("Unable to get the value of enable_fuzz.")
    return


def get_deck_parameters(custom_scheduler):
    decks = re.findall(r'"deckName".*"(.*)"', custom_scheduler)
    str_matches = re.findall(r'"w".*\[(.*)]', custom_scheduler)
    weights = [list(map(float, w.split(", "))) for w in str_matches]
    retentions = re.findall(r'"requestRetention"[:\s]+([\d.]+)', custom_scheduler)
    max_intervals = re.findall(r'"maximumInterval"[:\s]+(\d+)', custom_scheduler)
    easy_bonuses = re.findall(r'"easyBonus"[:\s]+([\d.]+)', custom_scheduler)
    hard_intervals = re.findall(r'"hardInterval"[:\s]+([\d.]+)', custom_scheduler)
    deck_parameters = {
        d: {
            "w": w,
            "r": float(r),
            "m": int(m),
            "e": float(e),
            "h": float(h)
        } for d, w, r, m, e, h in zip(
            decks, weights, retentions, max_intervals, easy_bonuses, hard_intervals
        )
    }
    deck_parameters = OrderedDict(
        {name: parameters for name, parameters in sorted(
            deck_parameters.items(),
            key=lambda item: item[0],
            reverse=True
        )}
    )
    return deck_parameters


def get_skip_decks(custom_scheduler):
    pattern = r'[const ]?skip_decks ?= ?(.*);'
    str_matches = re.findall(pattern, custom_scheduler)
    names = str_matches[0].split(', ')
    return list(map(lambda x: x.strip(']["'), names))


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None
