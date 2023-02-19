import re
from aqt.utils import getText, showWarning, tooltip
from collections import OrderedDict


NEW_CODE_INITIAL_VERSION = (3, 14, 3)  # todo define the version number
GLOBAL_DECK_CONFIG_NAME = "global config for FSRS4Anki"


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


def uses_new_code(version):
    qty_version_labels = 3
    initial_version = NEW_CODE_INITIAL_VERSION
    assert len(initial_version) == qty_version_labels
    for ii in range(qty_version_labels):
        if version[ii] != initial_version[ii]:
            return True if version[ii] > initial_version[ii] else False
    return True


if __name__ == '__main__':
    """Small test for 'uses_new_code'. Will check numbers of versions below, at
    and above the version number defined in the global configuration.
    Base 3 is used because all we need to check are the numbers one unit above 
    or below the version.
    """
    initial_version = NEW_CODE_INITIAL_VERSION
    print('does each version use the new code?:')
    for i in range(27):  # 222 in base 3
        modifier = (i // 9 - 1, i % 9 // 3 - 1, i % 3-1)  # produces numbers in base 3
        modified = tuple(sum(tup) for tup in zip(initial_version, modifier))
        print(modified, end=' is ')
        if i >= 13:  # 111 in base 3
            print(' True', end='. ')
        else:
            print(False, end='. ')
        print(uses_new_code(modified), end=' ')
        print('<-- Func returns ')


def get_global_config_deck_name(version):
    if uses_new_code(version):
        return GLOBAL_DECK_CONFIG_NAME
    return 'global'


def _get_regex_patterns(version):
    if uses_new_code(version):
        decks = r'"deckName".*"(.*)"'
        weights = r'"w".*\[(.*)]'
        retentions = r'"requestRetention"[:\s]+([\d.]+)'
        max_intervals = r'"maximumInterval"[:\s]+(\d+)'
        easy_bonuses = r'"easyBonus"[:\s]+([\d.]+)'
        hard_intervals = r'"hardInterval"[:\s]+([\d.]+)'
    else:
        decks = r'deck_name(?: ?== ?|.startsWith\()+"(.*)"'
        weights = r'[var ]?w ?= ?([0-9\-., \[\]]*)'
        retentions = r'requestRetention ?= ?([0-9.]*)'
        max_intervals = r'maximumInterval ?= ?([0-9.]*)'
        easy_bonuses = r'easyBonus ?= ?([0-9.]*)'
        hard_intervals = r'hardInterval ?= ?([0-9.]*)'
    return decks, weights, retentions, max_intervals, easy_bonuses, hard_intervals


def _get_weights(version, str_matches):
    if uses_new_code(version):
        return [list(map(float, w.split(", "))) for w in str_matches]
    else:
        return [list(map(float, w.strip('][').split(', '))) for w in str_matches]


def _get_deck_names(version, str_matches):
    if uses_new_code(version):
        return str_matches
    else:
        str_matches.insert(0, get_global_config_deck_name(version))
        return str_matches


def get_deck_parameters(custom_scheduler):
    version = get_version(custom_scheduler)
    d_pat, w_pat, r_pat, m_pat, e_pat, h_pat, i_pat = _get_regex_patterns(version)
    d_str_matches = re.findall(d_pat, custom_scheduler)
    decks = _get_deck_names(version, d_str_matches)
    w_str_matches = re.findall(w_pat, custom_scheduler)
    weights = _get_weights(version, w_str_matches)
    retentions = re.findall(r_pat, custom_scheduler)
    max_intervals = re.findall(m_pat, custom_scheduler)
    easy_bonuses = re.findall(e_pat, custom_scheduler)
    hard_intervals = re.findall(h_pat, custom_scheduler)
    assert all([len(x) == len(decks)for x in [
        decks, weights, retentions, max_intervals, easy_bonuses, hard_intervals
    ]])  # wanted to use zip(..., strict=True) instead of this
    deck_parameters = {
        d: {
            "w": w,
            "r": float(r),
            "m": int(m),
            "e": float(e),
            "h": float(h),
        } for d, w, r, m, e, h, i in zip(
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
