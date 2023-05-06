
from typing import Optional, Sequence
from aqt.browser import Browser, CellRow, Column, ItemId, SearchContext
from aqt.gui_hooks import (
    browser_did_fetch_columns,
    browser_did_fetch_row,
    browser_will_show,
    browser_did_search,
    browser_will_search,
)
from .custom_columns import (
    CustomColumn,
    DifficultyColumn,
    StabilityColumn,
    RetentionColumn,
)
from .custom_search_nodes import (
    CustomSearchNode,
)
from ..utils import *

browser: Optional[Browser] = None

custom_columns = [DifficultyColumn(), StabilityColumn(), RetentionColumn()]

# stores the custom search nodes for the current search
custom_search_nodes: List[CustomSearchNode] = []


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
    browser_did_search.append(_on_browser_did_search)


def _on_browser_will_search(ctx: SearchContext):
    _on_browser_will_search_handle_custom_column_ordering(ctx)
    _on_browser_will_search_handle_custom_search_parameters(ctx)


def _on_browser_will_search_handle_custom_column_ordering(ctx: SearchContext):
    if not isinstance(ctx.order, Column):
        return

    custom_column: CustomColumn = next(
        (c for c in custom_columns if c.builtin_column.key == ctx.order.key), None
    )
    if custom_column is None:
        return

    ctx.order = custom_column.order_by_str()


def _on_browser_will_search_handle_custom_search_parameters(ctx: SearchContext):
    if not ctx.search:
        return

    global custom_search_nodes
    custom_search_nodes = []

    for m in re.finditer(r"(d|s|r)(<=|>=|!=|=|<|>)(\d+\.{0,1}\d*)", ctx.search):
        if m.group(0) == "":
            continue
        parameter_name, parameter_operator, parameter_value = m.group(1), m.group(2), m.group(3)
        try:
            custom_search_nodes.append(
                CustomSearchNode.from_parameter_type_opt_and_value(
                    browser, parameter_name, parameter_operator, parameter_value
                )
            )
        except ValueError as e:
            showWarning(f"FSRS search error: {e}")
            return

        # remove the custom search parameter from the search string
        ctx.search = ctx.search.replace(m.group(0), "")

def _on_browser_did_search(ctx: SearchContext):
    _on_browser_did_search_handle_custom_search_parameters(ctx)


def _on_browser_did_search_handle_custom_search_parameters(ctx: SearchContext):
    global custom_search_nodes

    if not custom_search_nodes:
        return

    try:
        original_ids = ctx.ids
        for node in custom_search_nodes:
            ctx.ids = node.filter_ids(ctx.ids)
        ctx.ids = [id for id in original_ids if id in ctx.ids]
    except ValueError as e:
        showWarning(f"FSRS search error: {e}")
        return
    finally:
        custom_search_nodes = []