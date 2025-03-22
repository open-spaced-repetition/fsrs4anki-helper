from .python_i18n import i18n
import os.path
from pathlib import Path
from aqt.utils import tooltip
from aqt import mw

locale = mw.pm.meta["defaultLang"]
addon_dir = Path(os.path.dirname(__file__))

i18n.load_path.append(addon_dir / "locale")
i18n.set('filename_format', '{locale}.{format}')
i18n.set('file_format', 'json')
i18n.set('locale', locale)
i18n.set('fallback', "en_US")