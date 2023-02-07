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
    return list(map(int, re.findall(f'v(\d+).(\d+).(\d+)', custom_scheduler)[0]))


def get_deck_parameters(custom_scheduler):
    weight_list = [list(map(float, w.strip('][').split(', '))) for w in
                   re.findall(r'[var ]?w ?= ?([0-9\-., \[\]]*)', custom_scheduler)]
    retention_list = re.findall(r'requestRetention ?= ?([0-9.]*)', custom_scheduler)
    max_ivl_list = re.findall(r'maximumInterval ?= ?([0-9.]*)', custom_scheduler)
    easy_bonus_list = re.findall(r'easyBonus ?= ?([0-9.]*)', custom_scheduler)
    hard_ivl_list = re.findall(r'hardInterval ?= ?([0-9.]*)', custom_scheduler)
    deck_names = re.findall(r'deck_name(?: ?== ?|.startsWith\()+"(.*)"', custom_scheduler)
    deck_names.insert(0, "global")
    deck_parameters = {
        k: {
            "w": w,
            "r": float(r),
            "m": int(m),
            "e": float(e),
            "h": float(h)
        }
        for k, w, r, m, e, h in
        zip(deck_names, weight_list, retention_list, max_ivl_list, easy_bonus_list, hard_ivl_list)
    }
    deck_parameters = OrderedDict(
        {k: v for k, v in sorted(deck_parameters.items(), key=lambda item: item[0], reverse=True)})
    return deck_parameters


def get_skip_decks(custom_scheduler):
    return list(map(lambda x: x.strip(']["'), re.findall(r'[const ]?skip_decks ?= ?(.*);', custom_scheduler)[0].split(', ')))


def RepresentsInt(s):
    try:
        return int(s)
    except ValueError:
        return None
