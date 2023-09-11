from aqt.utils import askUser, showInfo, showCritical, showWarning
from aqt import mw
from ..utils import get_version, geq_version

import urllib.request
import re
import os.path

SCHEDULER_URL = "https://raw.githubusercontent.com/open-spaced-repetition/fsrs4anki/main/fsrs4anki_scheduler.js"

def get_internet_scheduler():
    with urllib.request.urlopen(SCHEDULER_URL) as req:
        return req.read().decode("UTF8")

def set_scheduler(new_scheduler: str):
    # Backup the old scheduler to a file in case something goes wrong.
    with open(os.path.expanduser("~/fsrs4anki_scheduler_revert.js"), "w") as f: 
        f.write(new_scheduler)

    mw.col.set_config("cardStateCustomizer", new_scheduler, undoable=True)

def update_scheduler(_):
    local_scheduler = mw.col.get_config("cardStateCustomizer", None)
    try:
        local_scheduler_version = get_version(local_scheduler)
    except IndexError:
        if askUser(
            "You dont appear to have the fsrs4anki scheduler set up\n"
            "Would you like to set up your custom scheduling code to enable fsrs?"
        ):
            if local_scheduler:
                if not askUser(
                    "You appear to have some none Fsrs scheduling code already, This will overwrite that.\n"
                    "Are you sure you want to continue?"
                    , title="Warning"
                ):
                    return

            set_scheduler(get_internet_scheduler())
            showInfo("Successfully added scheduler. Find it in the custom scheduling section of your deck config.")
            return
        else:
            return
        
    internet_scheduler = get_internet_scheduler()
    internet_scheduler_version = get_version(internet_scheduler)

    # Weight length checks

    def weight_count(scheduler: str):
        weight_regex = r'"w".*\[(.*)]'
        weight_match = re.search(weight_regex, scheduler)

        if weight_match is None:
            showWarning(
                "Could not find any weights in the scheduler config.\n"
                "If you wish to reinstall the scheduler from scratch clear the entire custom scheduler section."
            )
            return 0

        return weight_match.group(1).strip(',').count(',')

    if weight_count(local_scheduler) != weight_count(internet_scheduler):
        showWarning(
            "The amount of weights in the latest scheduler default config and the amount of weights in the local scheduler differ.\n"
            "This likely means your configuration is incompatible with that of the latest optimizer\n"
            "Upgrade at your own risk."
        )

    def version_tuple_to_str(version : tuple[int, int, int]):
        return ".".join(str(a) for a in version)

    comparison =  (
            f"Latest scheduler version = {version_tuple_to_str(internet_scheduler_version)}\n"
            f"Local scheduler version = {version_tuple_to_str(local_scheduler_version)}"
    )

    if geq_version(local_scheduler_version, internet_scheduler_version):
        showInfo(
            comparison + "\n"
            "You are already up to date"
        )
    else:
        if not askUser(
            comparison + "\n"
            "Update the scheduler with the latest version? (Your config will be preserved)"
        ):
            return
        
        config_regex = r"\/\/\s*Configuration\s+Start.+\/\/\s*Configuration\s+End"

        old_config = re.search(config_regex, local_scheduler, re.DOTALL)

        if old_config is None:
            showCritical(
                "Error extracting config from local scheduler\n."
                "Please ensure your config is surrounded by '// Configuration Start' and '// Configuration End'\n"
                "\n"
                "No changes have been made."
            )
            return 

        new_scheduler = re.sub(config_regex, old_config.group(), internet_scheduler, flags=re.DOTALL)
        set_scheduler(new_scheduler)

        showInfo("Scheduler updated successfully.")