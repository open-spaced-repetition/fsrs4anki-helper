#!/bin/bash

set -e

ADDON_NAME="fsrs4anki-helper"
OUT_ZIP="${ADDON_NAME}.ankiaddon"

rm -f "$OUT_ZIP"

zip -r "$OUT_ZIP" \
    __init__.py \
    utils.py \
    dsr_state.py \
    sync_hook.py \
    stats.py \
    configuration.py \
    i18n.py \
    steps.py \
    browser/__init__.py \
    browser/browser.py \
    browser/custom_columns.py \
    schedule/ \
    locale/ \
    python_i18n/ \
    manifest.json \
    README.md \
    License \
    config.json \
    config.md

echo "Package created: $OUT_ZIP"
