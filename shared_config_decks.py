import re

# Type alias
Config = list[str]
Decks = list[list[str]]


def has_const_decks_with_shared_config_in_code(custom_scheduler: str) -> bool:
    return bool(re.search(r"decks_with_shared_config", custom_scheduler))


def get_patterns_for_shared_config() -> tuple[str, str, str]:
    """Returns the regexp patterns to find the const, config name and decks list."""
    pattern_to_find_the_const = r"""
            const
            [ ]
            decks_with_shared_config    
            [ ]*                        
            =                           # equal sign with any amount of spacing around it
            [ ]*
            \{                          # opening of JS object
            [^}]*                       # anything inside the curly braces that is not a curly brace
            \}                          # ending of JS object
        """
    pattern_to_find_config = r"""
                "       # opening of the config name
                (      
                [^"]*   # anything besides an ending quote
                )       
                "       # ending of the config name
                :       # colon after the deck name
            """
    pattern_to_find_decks = r"""           
                \[      # opening of decks list
                [ ]*
                ["']    # opening quote
                [^]]*   # anything besides an ending bracket
                ["']    # ending quote
                [ ]*
                \]      # ending of decks list
            """
    return pattern_to_find_the_const, pattern_to_find_config, pattern_to_find_decks


def get_shared_config_name_and_decks(
    custom_scheduler: str,
) -> tuple[Config, Decks]:
    """Gets the config names and its decks from the custom_scheduler code."""
    (
        pattern_to_find_the_const,
        pattern_to_find_config,
        pattern_to_find_decks,
    ) = get_patterns_for_shared_config()
    match = re.search(pattern_to_find_the_const, custom_scheduler, re.VERBOSE)
    config = re.findall(pattern_to_find_config, match.group(), re.VERBOSE)
    decks_as_string = re.findall(pattern_to_find_decks, match.group(), re.VERBOSE)
    decks_as_list = []
    for decks in decks_as_string:
        deck = decks.lstrip("[").rstrip("]").split(",")
        deck = [dd.strip().lstrip(""""'""").rstrip(""""'""") for dd in deck]
        deck = [dd for dd in deck if dd != ""]
        decks_as_list += (deck,)
    return config, decks_as_list


def get_shared_config_decks(deck_parameters: dict, configs: Config, decks: Decks) -> list[dict]:
    filtered_deck_p = [{dd: pp} for dd, pp in deck_parameters.items() if dd in configs]
    created_decks = []
    for cfg_name, decks_list in zip(configs, decks):
        for deck_p in filtered_deck_p:
            deck_name = list(deck_p.keys())[0]
            if deck_name != cfg_name:
                continue
            for deck_list_item in decks_list:
                _temp_deck = deck_p.copy()
                _temp_deck[deck_list_item] = _temp_deck.pop(cfg_name)
                created_decks += (_temp_deck,)
    return created_decks


def add_shared_config_decks(deck_parameters: dict, shared_decks: list[dict]) -> None:
    for deck in shared_decks:
        deck_parameters.update(deck)


def remove_shared_config_decks(deck_parameters: dict, configs: list) -> None:
    for cfg in configs:
        deck_parameters.pop(cfg)


def set_shared_decks(deck_parameters, custom_scheduler) -> None:
    """Finds the shared configs in the custom scheduler and adds its decks to deck parameters.

    To avoid any issues it also removes the placeholders from the deck parameters.

    """
    config, decks = get_shared_config_name_and_decks(custom_scheduler)
    shared_decks = get_shared_config_decks(deck_parameters, config, decks)
    add_shared_config_decks(deck_parameters, shared_decks)
    remove_shared_config_decks(deck_parameters, config)
