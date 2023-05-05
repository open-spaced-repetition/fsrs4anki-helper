from abc import abstractmethod
from typing import Optional, Sequence
import math
from aqt.browser import Browser, CellRow, Column, ItemId, SearchContext
from aqt.gui_hooks import (
    browser_did_fetch_columns,
    browser_did_fetch_row,
    browser_will_show,
    browser_did_search,
    browser_will_search,
)
from anki.cards import Card
from anki.collection import BrowserColumns
from .utils import *

browser: Optional[Browser] = None

def init_browser() -> None:
    browser_will_show.append(_store_browser_reference)

    _setup_custom_columns()
    _setup_search()

def _store_browser_reference(browser_: Browser) -> None:
    global browser

    browser = browser_


class CustomColumn:
    builtin_column: Column

    def on_browser_did_fetch_row(
        self,
        browser: Browser,
        item_id: ItemId,
        row: CellRow,
        active_columns: Sequence[str],
    ) -> None:
        if (
            index := active_columns.index(self.key)
            if self.key in active_columns
            else None
        ) is None:
            return

        card = browser.table._state.get_card(item_id)
        try:
            value = self._display_value(card)
            row.cells[index].text = value
        except Exception as error:
            row.cells[index].text = str(error)

    @property
    def key(self):
        return self.builtin_column.key

    @abstractmethod
    def _display_value(
        self,
        card: Card,
    ) -> str:
        raise NotImplementedError

    def order_by_str(self) -> Optional[str]:
        """Return the SQL string that will be appended after "ORDER BY" to the query that
        fetches the search results when sorting by this column."""
        return None
    

class StabilityColumn(CustomColumn):
    builtin_column = Column(
        key="stability",
        cards_mode_label="Stability",
        notes_mode_label="Stability",
        sorting=BrowserColumns.SORTING_DESCENDING,
        uses_cell_font=False,
        alignment=BrowserColumns.ALIGNMENT_CENTER,
    )

    def _display_value(self, card: Card) -> str:
        if card.custom_data == "":
            return "N/A"
        custom_data = json.loads(card.custom_data)
        if 's' not in custom_data:
            return "N/A"

        return f"{custom_data['s']} days"
    
    def order_by_str(self) -> str:
        return "json_extract(json_extract(data, '$.cd'), '$.s') DESC"


class DifficultyColumn(CustomColumn):
    builtin_column = Column(
        key="difficulty",
        cards_mode_label="Difficulty",
        notes_mode_label="Difficulty",
        sorting=BrowserColumns.SORTING_DESCENDING,
        uses_cell_font=False,
        alignment=BrowserColumns.ALIGNMENT_CENTER,
    )

    def _display_value(self, card: Card) -> str:
        if card.custom_data == "":
            return "N/A"
        custom_data = json.loads(card.custom_data)
        if 'd' not in custom_data:
            return "N/A"

        return custom_data['d']
    
    def order_by_str(self) -> str:
        return "json_extract(json_extract(data, '$.cd'), '$.d') DESC"


class RetentionColumn(CustomColumn):
    builtin_column = Column(
        key="retention",
        cards_mode_label="Retention",
        notes_mode_label="Retention",
        sorting=BrowserColumns.SORTING_DESCENDING,
        uses_cell_font=False,
        alignment=BrowserColumns.ALIGNMENT_CENTER,
    )

    def _display_value(self, card: Card) -> str:
        if card.type != 2:
            return "N/A"
        if card.custom_data == "":
            return "N/A"
        custom_data = json.loads(card.custom_data)
        if 's' not in custom_data:
            return "N/A"
        today = mw.col.sched.today
        if card.odid:
            last_due = card.odue - card.ivl
        else:
            last_due = card.due - card.ivl
        elapsed_days = today - last_due
        retention = math.pow(0.9, elapsed_days / custom_data['s'])
        return f"{retention * 100:.2f}%"
    
    def order_by_str(self) -> str:
        return f"""case when odid==0 
        then ({mw.col.sched.today} - (due-ivl)) / json_extract(json_extract(data, '$.cd'), '$.s')
        else ({mw.col.sched.today} - (odue-ivl)) / json_extract(json_extract(data, '$.cd'), '$.s')
        end ASC"""


custom_columns = [StabilityColumn(), DifficultyColumn(), RetentionColumn()]


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