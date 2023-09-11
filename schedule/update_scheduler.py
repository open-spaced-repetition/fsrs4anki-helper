from aqt.utils import askUser
from aqt import mw

import urllib.request

def update_scheduler(_):
    custom_scheduler = mw.col.get_config("cardStateCustomizer", None)
    
    if not custom_scheduler:
        if askUser(
            "You dont appear to have the fsrs4anki scheduler set up\n"
            "Would you like to replace your custom scheduling code with the latest?"
        ):
            pass
        else:
            return