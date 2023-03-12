"""
...fsrs4anki-helper/tests/ $ pytest shared_config_decks.py
"""
import pytest

import shared_config_decks


def test_empty_map_returns_empty_list():
    custom_scheduler = R"""const decks_with_shared_config = {};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == [], f"got {config!r}"
    assert decks == [], f"got {decks!r}"


def test_non_empty_map_returned_type_is_list():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":["deck_name"]};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert type(config) == list, f"got '{type(config)!r}"
    assert type(decks) == list, f"got '{type(decks)!r}"


def test_non_empty_map_returns_non_empty_list_of_string():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":["deck_name"]};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name"]], f"got {decks!r}"


def test_deck_name_with_no_quote_returns_empty_list():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":[deck_name]};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [], f"got {decks!r}"


def test_deck_name_with_single_quote():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":['deck_name']};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name"]], f"got {decks!r}"


def test_deck_name_with_double_quote():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":["deck_name"]};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name"]], f"got {decks!r}"


def test_ending_brace_in_trailing_line():
    custom_scheduler = R"""const decks_with_shared_config = {"cfg_name":["deck_name"]\n};"""
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name"]], f"got {decks!r}"


def test_multiple_decks():
    custom_scheduler = (
        R"""const decks_with_shared_config = {"cfg_name":["deck_name","deck_name"]};"""
    )
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name", "deck_name"]], f"got {decks!r}"


def test_new_line_between_decks():
    custom_scheduler = (
        R"""const decks_with_shared_config = {"cfg_name":["deck_name","""
        + "\n"
        + """"deck_name"]};"""
    )
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name"], f"got {config!r}"
    assert decks == [["deck_name", "deck_name"]], f"got {decks!r}"


def test_different_spacing_around_equal_sign():
    custom_scheduler0 = R"""const decks_with_shared_config ={"cfg_name":["deck_name"]};"""
    config0, decks0 = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler0)
    assert config0 == ["cfg_name"], f"got {config0!r}"
    assert decks0 == [["deck_name"]], f"got {decks0!r}"

    custom_scheduler1 = R"""const decks_with_shared_config={"cfg_name":["deck_name"]};"""
    config1, decks1 = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler1)
    assert config1 == ["cfg_name"], f"got {config1!r}"
    assert decks1 == [["deck_name"]], f"got {decks1!r}"

    custom_scheduler2 = R"""const decks_with_shared_config= {"cfg_name":["deck_name"]};"""
    config2, decks2 = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler2)
    assert config2 == ["cfg_name"], f"got {config2!r}"
    assert decks2 == [["deck_name"]], f"got {decks2!r}"


def test_multiple_config_in_map():
    custom_scheduler = (
        R"""const decks_with_shared_config ={"cfg_name":["deck_name"],"cfg_name":["deck_name"]};"""
    )
    config, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert config == ["cfg_name", "cfg_name"], f"got {config!r}"
    assert decks == [["deck_name"], ["deck_name"]], f"got {decks!r}"


def test_odd_spacing_separating_deck_names_is_stripped():
    custom_scheduler = (
        R"const decks_with_shared_config ={"
        R'"a":["b","c"],'
        R'"a":["d","e" ],'
        R'"a":["f", "g"],'
        R'"a":["h", "i" ],'
        R'"a":["j" ,"k"],'
        R'"a":["l" ,"m" ],'
        R'"a":["n" , "o"],'
        R'"a":["p" , "q" ],'
        R'"a":[ "r","s"],'
        R'"a":[ "t","u" ],'
        R'"a":[ "v", "w"],'
        R'"a":[ "x", "y" ],'
        R'"a":[ "z" ,"aa"],'
        R'"a":[ "ab" ,"ac" ],'
        R'"a":[ "ad" , "ae"],'
        R'"a":[ "af" , "ag" ],'
        R"};"
    )
    _, decks = shared_config_decks.get_shared_config_name_and_decks(custom_scheduler)
    assert decks == [
        ["b", "c"],
        ["d", "e"],
        ["f", "g"],
        ["h", "i"],
        ["j", "k"],
        ["l", "m"],
        ["n", "o"],
        ["p", "q"],
        ["r", "s"],
        ["t", "u"],
        ["v", "w"],
        ["x", "y"],
        ["z", "aa"],
        ["ab", "ac"],
        ["ad", "ae"],
        ["af", "ag"],
    ], f"got {decks!r}"
