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
i18n.add_translation("relearning", tr.statistics_counts_relearning_cards(), locale=locale)
i18n.add_translation("stability", tr.card_stats_fsrs_stability(), locale=locale)
i18n.add_translation("reviews", tr.statistics_reviews_title(), locale=locale)
i18n.add_translation("desired-retention", tr.deck_config_desired_retention(), locale=locale)
i18n.add_translation("again", tr.studying_again(), locale=locale)
i18n.add_translation("hard", tr.studying_hard(), locale=locale)
i18n.add_translation("good", tr.studying_good(), locale=locale)

# Uncomment this to mark translated text
# i18n.t = lambda *args, **kwargs: "Translated"