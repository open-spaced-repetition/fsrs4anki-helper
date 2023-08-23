import re
from aqt.utils import tooltip, getText, showWarning, askUser, showText
from collections import OrderedDict
from typing import List, Dict, Tuple
from anki.stats_pb2 import CardStatsResponse
from anki.cards import Card
from anki.stats import (
    REVLOG_LRN, 
    REVLOG_REV, 
    REVLOG_RELRN,
    REVLOG_CRAM,
    REVLOG_RESCHED,
    CARD_TYPE_REV,
    QUEUE_TYPE_REV
)
from aqt import mw
import json
import math
import random
from datetime import datetime, timedelta


DECOUPLE_PARAMS_CODE_INITIAL_VERSION = (3, 14, 0)
GLOBAL_DECK_CONFIG_NAME = "global config for FSRS4Anki"
VERSION_NUMBER_LEN = 3

def check_fsrs4anki(all_config):
    if "cardStateCustomizer" not in all_config:
        mw.taskman.run_on_main(lambda: showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen."))
        return
    custom_scheduler = all_config['cardStateCustomizer']
    if "// FSRS4Anki" not in custom_scheduler:
        mw.taskman.run_on_main(lambda: showWarning(
            "Please paste the code of FSRS4Anki into custom scheduling at the bottom of the deck options screen."))
        return
    return custom_scheduler


def get_version(custom_scheduler):
    str_matches = re.findall(r'// FSRS4Anki v(\d+).(\d+).(\d+) Scheduler', custom_scheduler)
    version = tuple(map(int, str_matches[0]))
    if len(version) != VERSION_NUMBER_LEN:
        mw.taskman.run_on_main(lambda: showWarning(
            "Please check whether the version of FSRS4Anki scheduler matches X.Y.Z."))
        return
    return version


def get_fuzz_bool(custom_scheduler):
    enable_fuzz = re.findall(
        r"const enable_fuzz *= *(true|false) *;", custom_scheduler
    )[0]
    if enable_fuzz:
        return True if enable_fuzz == "true" else False
    mw.taskman.run_on_main(lambda: showWarning("Unable to get the value of enable_fuzz."))
    return


def uses_new_params_config(version):
    initial_version = DECOUPLE_PARAMS_CODE_INITIAL_VERSION
    return geq_version(version, initial_version)


def geq_version(version_1, version_2):
    assert len(version_1) == VERSION_NUMBER_LEN
    assert len(version_2) == VERSION_NUMBER_LEN
    for ii in range(VERSION_NUMBER_LEN):
        if version_1[ii] != version_2[ii]:
            return True if version_1[ii] > version_2[ii] else False
    return True


def get_global_config_deck_name(version):
    if uses_new_params_config(version):
        return GLOBAL_DECK_CONFIG_NAME
    return 'global'


def _get_regex_patterns(version):
    if version[0] == 3:
        if uses_new_params_config(version):
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
    elif version[0] == 4:
        decks = r'"deckName".*"(.*)"'
        weights = r'"w".*\[(.*)]'
        retentions = r'"requestRetention"[:\s]+([\d.]+)'
        max_intervals = r'"maximumInterval"[:\s]+(\d+)'
        return decks, weights, retentions, max_intervals


def _get_weights(version, str_matches):
    if uses_new_params_config(version):
        return [list(map(float, w.split(", "))) for w in str_matches]
    else:
        return [list(map(float, w.strip('][').split(', '))) for w in str_matches]


def _get_deck_names(version, str_matches):
    if uses_new_params_config(version):
        return str_matches
    else:
        str_matches.insert(0, get_global_config_deck_name(version))
        return str_matches


def _remove_comment_line(custom_scheduler):
    not_comment_line = '\n'.join([re.sub('^ *//..*$', '', _) for _ in custom_scheduler.split('\n')])
    return not_comment_line


def get_deck_parameters(custom_scheduler):
    version = get_version(custom_scheduler)
    custom_scheduler = _remove_comment_line(custom_scheduler)
    if version[0] == 3:
        d_pat, w_pat, r_pat, m_pat, e_pat, h_pat = _get_regex_patterns(version)
        d_str_matches = re.findall(d_pat, custom_scheduler)
        decks = _get_deck_names(version, d_str_matches)
        w_str_matches = re.findall(w_pat, custom_scheduler)
        weights = _get_weights(version, w_str_matches)
        retentions = re.findall(r_pat, custom_scheduler)
        max_intervals = re.findall(m_pat, custom_scheduler)
        easy_bonuses = re.findall(e_pat, custom_scheduler)
        hard_intervals = re.findall(h_pat, custom_scheduler)
        if not all([len(x) == len(decks) for x in [
            decks, weights, retentions, max_intervals, easy_bonuses, hard_intervals
        ]]):
            mw.taskman.run_on_main(lambda: showWarning(
                "The number of deckName, w, requestRetention, maximumInterval, easyBonus, or hardInterval unmatch.\n" +
                "Please confirm each item of deckParams have deckName, w, requestRetention, maximumInterval, easyBonus, and hardInterval."
            ))
            return
        deck_parameters = {
            d: {
                "w": w,
                "r": float(r),
                "m": int(m),
                "e": float(e),
                "h": float(h),
            } for d, w, r, m, e, h in zip(
                decks, weights, retentions, max_intervals, easy_bonuses, hard_intervals
            )
        }
    elif version[0] == 4:
        d_pat, w_pat, r_pat, m_pat = _get_regex_patterns(version)
        d_str_matches = re.findall(d_pat, custom_scheduler)
        decks = _get_deck_names(version, d_str_matches)
        w_str_matches = re.findall(w_pat, custom_scheduler)
        weights = _get_weights(version, w_str_matches)
        retentions = re.findall(r_pat, custom_scheduler)
        max_intervals = re.findall(m_pat, custom_scheduler)
        if not all([len(x) == len(decks) for x in [
            decks, weights, retentions, max_intervals
        ]]):
            mw.taskman.run_on_main(lambda: showWarning(
                "The number of deckName, w, requestRetention or maximumInterval unmatch.\n" +
                "Please confirm each item of deckParams have deckName, w, requestRetention and maximumInterval."
            ))
            return
        deck_parameters = {
            d: {
                "w": w,
                "r": float(r),
                "m": int(m),
            } for d, w, r, m in zip(
                decks, weights, retentions, max_intervals
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


def get_did_parameters(deck_list, deck_parameters, global_deck_name):
    did_to_deck_parameters = {}

    def get_parameters(deckname, mapping):
        parts = deckname.split("::")
        for i in range(len(parts), 0, -1):
            prefix = "::".join(parts[:i])
            if prefix in mapping:
                return mapping[prefix]
        return mapping[global_deck_name]
    
    for d in deck_list:
        parameters = get_parameters(d["name"], deck_parameters)
        did_to_deck_parameters[d["id"]] = parameters
    return did_to_deck_parameters


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


def reset_ivl_and_due(cid: int, revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    card = mw.col.get_card(cid)
    card.ivl = int(revlogs[0].interval / 86400)
    due = math.ceil((revlogs[0].time + revlogs[0].interval - mw.col.sched.day_cutoff) / 86400) + mw.col.sched.today
    if card.odid:
        card.odue = max(due, 1)
    else:
        card.due = due
    mw.col.update_card(card)


def filter_revlogs(revlogs: List[CardStatsResponse.StatsRevlogEntry]) -> List[CardStatsResponse.StatsRevlogEntry]:
    return list(filter(lambda x: x.review_kind != REVLOG_CRAM or x.ease != 0, revlogs))


def get_last_review_date(last_revlog: CardStatsResponse.StatsRevlogEntry):
    return math.ceil((last_revlog.time - mw.col.sched.day_cutoff) / 86400) + mw.col.sched.today


def update_card_due_ivl(card: Card, last_revlog: CardStatsResponse.StatsRevlogEntry, new_ivl: int):
    card.ivl = new_ivl
    last_review_date = get_last_review_date(last_revlog)
    if card.odid:
        card.odue = max(last_review_date + new_ivl, 1)
    else:
        card.due = last_review_date + new_ivl
    return card


def has_again(revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    for r in revlogs:
        if r.button_chosen == 1:
            return True
    return False


def has_manual_reset(revlogs: List[CardStatsResponse.StatsRevlogEntry]):
    last_kind = None
    for r in revlogs:
        if r.button_chosen == 0:
            return True
        if last_kind is not None and last_kind in (REVLOG_REV, REVLOG_RELRN) and r.review_kind == REVLOG_LRN:
            return True
        last_kind = r.review_kind
    return False


def get_fuzz_range(interval, elapsed_days):
    min_ivl = max(2, int(round(interval * 0.95 - 1)))
    max_ivl = int(round(interval * 1.05 + 1))
    if interval > elapsed_days:
        min_ivl = max(min_ivl, elapsed_days + 1)
    return min_ivl, max_ivl


def due_to_date(due: int) -> str:
    offset = due - mw.col.sched.today
    today_date = datetime.today()
    return (today_date + timedelta(days=offset)).strftime("%Y-%m-%d")


def exponential_forgetting_curve(elapsed_days, stability):
    return 0.9 ** (elapsed_days / stability)


def power_forgetting_curve(elapsed_days, stability):
    return (1 + elapsed_days / (9 * stability)) ** -1


if __name__ == '__main__':
    """Small test for 'uses_new_code'. Will check numbers of versions below, at
    and above the version number defined in the global configuration.
    Base 3 is used because all we need to check are the numbers one unit above 
    or below the version.
    """
    initial_version = DECOUPLE_PARAMS_CODE_INITIAL_VERSION
    print('does each version use the new code?:')
    for i in range(27):  # 222 in base 3
        modifier = (i // 9 - 1, i % 9 // 3 - 1, i % 3-1)  # produces numbers in base 3
        modified = tuple(sum(tup) for tup in zip(initial_version, modifier))
        print(modified, end=' is ')
        if i >= 13:  # 111 in base 3
            print(' True', end='. ')
        else:
            print(False, end='. ')
        print(uses_new_params_config(modified), end=' ')
        print('<-- Func returns ')