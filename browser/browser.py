from typing import Optional, Sequence
from aqt.browser import Browser, CellRow, Column, ItemId, SearchContext
from aqt.gui_hooks import (
    browser_did_fetch_columns,
    browser_did_fetch_row,
    browser_will_show,
    browser_will_search,
)
from .custom_columns import (
    CustomColumn,
    TargetRetrievabilityColumn,
)
from ..utils import *

browser: Optional[Browser] = None

custom_columns = [
    TargetRetrievabilityColumn(),
]


def init_browser() -> None:
    browser_will_show.append(_store_browser_reference)

    _setup_custom_columns()
    _setup_search()


def _store_browser_reference(browser_: Browser) -> None:
    global browser

    browser = browser_


# custom columns
def _setup_custom_columns():
    browser_did_fetch_columns.append(_on_browser_did_fetch_columns)
    browser_did_fetch_row.append(_on_browser_did_fetch_row)


def _on_browser_did_fetch_columns(columns: dict[str, Column]):
    for column in custom_columns:
        columns[column.key] = column.builtin_column


def _on_browser_did_fetch_row(
    item_id: ItemId,
    is_notes_mode: bool,
    row: CellRow,
    active_columns: Sequence[str],
) -> None:
    for column in custom_columns:
        column.on_browser_did_fetch_row(
            browser=browser,
            item_id=item_id,
            row=row,
            active_columns=active_columns,
        )


# cutom search nodes
def _setup_search():
    browser_will_search.append(_on_browser_will_search)


def _on_browser_will_search(ctx: SearchContext):
    _on_browser_will_search_handle_custom_column_ordering(ctx)


def _on_browser_will_search_handle_custom_column_ordering(ctx: SearchContext):
    if not isinstance(ctx.order, Column):
        return

    custom_column: CustomColumn = next(
        (c for c in custom_columns if c.builtin_column.key == ctx.order.key), None
    )
    if custom_column is None:
        return

    ctx.order = custom_column.order_by_str()
