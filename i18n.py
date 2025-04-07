from .python_i18n import i18n
import os.path
from pathlib import Path
from aqt.utils import tooltip
from aqt import mw
from aqt.utils import tr

locale = mw.pm.meta["defaultLang"]
addon_dir = Path(os.path.dirname(__file__))

i18n.load_path.append(addon_dir / "locale")
i18n.set("filename_format", "{locale}.{format}")
i18n.set("file_format", "json")
i18n.set("locale", locale)
i18n.set("fallback", "en_US")

i18n.add_translation("learning", tr.statistics_counts_learning_cards(), locale=locale)
i18n.add_translation(
    "relearning", tr.statistics_counts_relearning_cards(), locale=locale
)
i18n.add_translation("stability", tr.card_stats_fsrs_stability(), locale=locale)
i18n.add_translation("reviews", tr.statistics_reviews_title(), locale=locale)
i18n.add_translation(
    "desired-retention", tr.deck_config_desired_retention(), locale=locale
)
i18n.add_translation("again", tr.studying_again(), locale=locale)
i18n.add_translation("hard", tr.studying_hard(), locale=locale)
i18n.add_translation("good", tr.studying_good(), locale=locale)
i18n.add_translation("day", tr.statistics_true_retention_month(), locale=locale)
i18n.add_translation("month", tr.statistics_true_retention_year(), locale=locale)
i18n.add_translation("deck-life", tr.statistics_range_all_history(), locale=locale)
i18n.add_translation(
    "true-retention", tr.statistics_true_retention_title(), locale=locale
)
i18n.add_translation("day", tr.statistics_true_retention_today(), locale=locale)
i18n.add_translation(
    "yesterday", tr.statistics_true_retention_yesterday(), locale=locale
)
i18n.add_translation("week", tr.statistics_true_retention_week(), locale=locale)
i18n.add_translation("pass", tr.statistics_true_retention_pass(), locale=locale)
i18n.add_translation("fail", tr.statistics_true_retention_fail(), locale=locale)
i18n.add_translation(
    "retention", tr.statistics_true_retention_retention(), locale=locale
)
i18n.add_translation("cards", tr.browsing_cards(), locale=locale)
i18n.add_translation("deck", tr.decks_deck(), locale=locale)
i18n.add_translation("collection", tr.browsing_whole_collection(), locale=locale)


def t(*args, **kwargs):
    # Uncomment this to mark translated text
    # return "Translated"
    return i18n.t(*args, **kwargs)
