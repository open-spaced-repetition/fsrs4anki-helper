from aqt.utils import askUser, askUserDialog, showInfo, showCritical, showWarning
from aqt import mw, qVersion
from ..utils import get_version, geq_version

import urllib.request
import socket
import re
import os.path
import sys
import traceback

scheduler_qt_suffix = "_qt5" if qVersion().split(".")[0] == "5" else ""

scheduler4_url = f"https://raw.githubusercontent.com/open-spaced-repetition/fsrs4anki/main/fsrs4anki_scheduler{scheduler_qt_suffix}.js"
scheduler3_url = f"https://raw.githubusercontent.com/open-spaced-repetition/fsrs4anki/v3.26.2/fsrs4anki_scheduler{scheduler_qt_suffix}.js"


def get_internet_scheduler(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as req:
            return req.read().decode("UTF8")
    except socket.timeout:
        showWarning(
            "Timeout while downloading scheduler, please try again later.\n"
            + "If you are in China, please use proxy or VPN."
        )


def set_scheduler(new_scheduler: str):
    # Backup the old scheduler to a file in case something goes wrong.
    with open(os.path.expanduser("~/fsrs4anki_scheduler_revert.js"), "w") as f:
        f.write(mw.col.get_config("cardStateCustomizer"))

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
                    "Are you sure you want to continue?",
                    title="Warning",
                ):
                    return

            internet_scheduler = get_internet_scheduler(scheduler4_url)
            if internet_scheduler is None:
                return
            set_scheduler(internet_scheduler)
            showInfo(
                "Successfully added scheduler. Find it in the custom scheduling section of your deck config."
            )
            return
        else:
            return

    upgrade_from_v3 = False
    if local_scheduler_version[0] == 3:
        upgrade_to_dialog = askUserDialog(
            "The v4 FSRS scheduler has been released and the v3 FSRS scheduler is no longer getting updates. So it is recommended that you upgrade to the v4 FSRS scheduler.\n"
            "\n"
            "NOTE: The weights of the v3 scheduler are incompatible with those of the v4 scheduler.\n"
            "If you upgrade to v4, you must re-optimize your weights using the optimizer and then replace the weights in the scheduler config.\n"
            "Your deck param configs will each be replaced with the default until you do this."
            "\n"
            "More info on optimizing: https://github.com/open-spaced-repetition/fsrs4anki/blob/main/README.md#step-2-personalizing-fsrs",
            ["Upgrade to V4", "Upgrade to latest V3", "Cancel"]
        )
        upgrade_to_dialog.setDefault(1)

        upgrade_to_response = upgrade_to_dialog.run()

        if upgrade_to_response == "Cancel":
            return
        if upgrade_to_response == "Upgrade to V4":
            scheduler_url = scheduler4_url
            upgrade_from_v3 = True
        else:
            scheduler_url = scheduler3_url

    else:
        scheduler_url = scheduler4_url

    internet_scheduler = get_internet_scheduler(scheduler_url)
    if internet_scheduler is None:
        return
    internet_scheduler_version = get_version(internet_scheduler)

    # Weight length checks

    def weight_count(scheduler: str):
        weight_regex = r'"w".*\[(.*)]'
        weight_match = re.search(weight_regex, scheduler)

        if weight_match is None:
            showWarning(
                "Could not find any weights in the scheduler config.\n"
                "If you wish to reinstall the scheduler from scratch, clear the entire custom scheduler section."
            )
            return 0

        return weight_match.group(1).strip(",").count(",")

    if not upgrade_from_v3 and weight_count(local_scheduler) != weight_count(internet_scheduler):
        showWarning(
            "The amount of weights in the latest scheduler default config and the amount of weights in the local scheduler differ.\n"
            "This likely means your configuration is incompatible with that of the latest optimizer\n"
            "Upgrade at your own risk."
        )

    def version_tuple_to_str(version: tuple[int, int, int]):
        return ".".join(str(a) for a in version)

    comparison = (
        f"Latest scheduler version = {version_tuple_to_str(internet_scheduler_version)}\n"
        f"Installed scheduler version = {version_tuple_to_str(local_scheduler_version)}"
    )

    if geq_version(local_scheduler_version, internet_scheduler_version):
        showInfo(comparison + "\n" "You are already up to date")
    else:
        if not askUser(
            comparison + "\n"
            f"Update the scheduler with the latest version? (Your config will {'NOT!!! ' if upgrade_from_v3 else ''}be preserved)"
        ):
            return

        start_regex = r"^.*\/\/\s*FSRS4Anki"
        config_regex = r"\/\/\s*Configuration\s+Start.+\/\/\s*Configuration\s+End"

        old_start = re.search(start_regex, local_scheduler, re.DOTALL)
        old_config = re.search(config_regex, local_scheduler, re.DOTALL)

        if old_config is None:
            showCritical(
                "Error extracting config from local scheduler\n."
                "Please ensure your config is surrounded by '// Configuration Start' and '// Configuration End'\n"
                "\n"
                "No changes have been made."
            )
            return

        old_config = old_config.group()

        # Upgrade config replacement
        if upgrade_from_v3:
            # Try block as this step isn't essential
            try:
                pref_regex = r"{.+?\"deckName\"\s*:\s*\"(.+?)\".+?}"

                new_default = re.search(
                    pref_regex, internet_scheduler, re.DOTALL)
                assert new_default is not None
                new_default = new_default.group()

                old_prefs: list[re.Match[str]] = re.findall(
                    pref_regex, old_config, re.DOTALL)
                assert old_prefs is not None
                new_prefs = ",\n  ".join(re.sub(
                    r"(\"deckName\"\s*:.+?\").+?,", f"\g<1>{pref},\"", new_default) for pref in old_prefs)
                new_prefs = f"\g<1>[\n  {new_prefs}\n]"

                old_config = re.sub(r"(const\s+deckParams\s*=\s*).+]",
                                    new_prefs, old_config, flags=re.DOTALL)
            except Exception:
                print(traceback.print_exc(), file=sys.stderr)
                showWarning(
                    f"There was an error setting your deck configs to defaults. Make sure you do this manually!")

        if old_start is not None:
            new_scheduler = re.sub(
                start_regex, old_start.group(), internet_scheduler, flags=re.DOTALL
            )
        new_scheduler = re.sub(
            config_regex, old_config, new_scheduler, flags=re.DOTALL
        )
        set_scheduler(new_scheduler)

        showInfo(
            "Scheduler updated successfully."
            if not upgrade_from_v3 else
            "Scheduler updated from v3 to v4 successfully.\n"
            "\n"
            "the weights have been replaced by the default weights for v4.\n"
            "Remember to re-optimize your weights using the optimizer and then replace the weights in the scheduler config."
        )
