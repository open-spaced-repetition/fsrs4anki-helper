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
            index := (
                active_columns.index(self.key) if self.key in active_columns else None
            )
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


class TargetRetrievabilityColumn(CustomColumn):
    builtin_column = Column(
        key="target_retrievability",
        cards_mode_label="Target R",
        notes_mode_label="Target R",
        sorting_cards=BrowserColumns.SORTING_DESCENDING,
        uses_cell_font=False,
        alignment=BrowserColumns.ALIGNMENT_CENTER,
    )

    def _display_value(self, card: Card) -> str:
        if not mw.col.get_config("fsrs"):
            tooltip(FSRS_ENABLE_WARNING)
            return "N/A"
        if card.ivl < 1:
            return "N/A"
        if not card.memory_state:
            return "N/A"
        retrievability = power_forgetting_curve(card.ivl, card.memory_state.stability)
        return f"{retrievability * 100:.2f}%"

    def order_by_str(self) -> str:
        return """ivl / json_extract(CASE WHEN c.data != "" THEN c.data ELSE "{}" END, '$.s') ASC"""
