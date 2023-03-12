import re

# Type alias
Config = list[str]
Decks = list[list[str]]


def has_shared_config_decks_in(custom_scheduler: str) -> bool:
    return bool(re.search(r"decks_with_shared_config", custom_scheduler))


def _get_patterns() -> tuple[str, str, str]:
    """Returns the regexp patterns to find the const, config name and decks list."""
    pattern_to_find_const = r"""
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
    return pattern_to_find_const, pattern_to_find_config, pattern_to_find_decks


def get_shared_configs_and_decks(
    custom_scheduler: str,
) -> tuple[Config, Decks]:
    """Gets the config names and their decks from the custom_scheduler code."""
    const_pat, cfg_pat, decks_pat = _get_patterns()
    const_match = re.search(const_pat, custom_scheduler, re.VERBOSE)
    config = re.findall(cfg_pat, const_match.group(), re.VERBOSE)
    decks_match = re.findall(decks_pat, const_match.group(), re.VERBOSE)
    decks = []
    for decks_full_str in decks_match:
        _decks = decks_full_str.lstrip("[").rstrip("]").split(",")
        _decks = [deck.strip().lstrip(""""'""").rstrip(""""'""") for deck in _decks]
        _decks = [deck for deck in _decks if deck != ""]
        decks += (_decks,)
    return config, decks


def get_shared_config_decks(deck_parameters: dict, configs: Config, decks: Decks) -> list[dict]:
    configs_in_deck_params = [
        {deck: param} for deck, param in deck_parameters.items() if deck in configs
    ]
    shared_config_decks = []
    for config, shared_decks in zip(configs, decks):
        for config_name_and_params in configs_in_deck_params:
            deck_name = list(config_name_and_params.keys())[0]
            if deck_name != config:
                continue
            for deck in shared_decks:
                _deck = config_name_and_params.copy()
                # remove placeholder key 'config' from the _deck dict and add the key 'deck' to it
                _deck[deck] = _deck.pop(config)
                shared_config_decks += (_deck,)
    return shared_config_decks


def add_shared_decks(deck_parameters: dict, shared_decks: list[dict]) -> None:
    """Add to the deck parameters the shared decks."""
    for deck in shared_decks:
        deck_parameters.update(deck)


def remove_placeholder_decks(deck_parameters: dict, configs: list) -> None:
    """Remove from the deck parameters the config placeholders."""
    for cfg in configs:
        deck_parameters.pop(cfg)


def set_shared_decks(deck_parameters: dict, custom_scheduler: str) -> None:
    """Finds the shared configs in the custom scheduler and adds its decks to deck parameters.

    To avoid any issues it also removes the placeholders from the deck parameters.

    """
    config, decks = get_shared_configs_and_decks(custom_scheduler)
    shared_decks = get_shared_config_decks(deck_parameters, config, decks)
    add_shared_decks(deck_parameters, shared_decks)
    remove_placeholder_decks(deck_parameters, config)
