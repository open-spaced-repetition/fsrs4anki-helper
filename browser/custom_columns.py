import math
from abc import abstractmethod
from typing import Optional, Sequence
from anki.cards import Card
from anki.collection import BrowserColumns
from aqt.browser import Browser, CellRow, Column, ItemId
from ..utils import *

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