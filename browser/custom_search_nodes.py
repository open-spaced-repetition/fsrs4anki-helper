import math
from abc import ABC, abstractmethod
from typing import Optional, Sequence
from aqt.browser import Browser, ItemId
from anki.utils import ids2str
from ..utils import *


class CustomSearchNode(ABC):

    parameter_name: Optional[str] = None
    browser: Optional[Browser] = None

    @classmethod
    def from_parameter_type_opt_and_value(cls, browser, parameter_name, operator, value):
        custom_search_node_types = (
            DifficultySearchNode,
            StabilitySearchNode,
            RetrievabilitySearchNode,
        )
        for custom_search_node_type in custom_search_node_types:
            if custom_search_node_type.parameter_name == parameter_name:
                return custom_search_node_type(browser, operator, value)

        raise ValueError(f"Unknown custom search parameter: {parameter_name}")

    @abstractmethod
    def filter_ids(self, ids: Sequence[ItemId]) -> Sequence[ItemId]:
        pass

    def _retain_ids_where(self, ids: Sequence[ItemId], where: str) -> Sequence[ItemId]:
        query = f"""
        SELECT {"DISTINCT nid" if self.browser.table.is_notes_mode() else "id"}
        FROM cards
        WHERE {"nid" if self.browser.table.is_notes_mode() else "id"} IN {ids2str(ids)}
        AND data like '%"cd"%'
        AND type = 2
        AND {where}
        """
        return mw.col.db.list(query)
        

class DifficultySearchNode(CustomSearchNode):

    parameter_name = "d"

    def __init__(self, browser, operator: str, value: str):
        self.browser = browser
        self.operator = operator
        self.value = value

    def filter_ids(self, ids: Sequence[ItemId]) -> Sequence[ItemId]:
        try:
            difficulty = float(self.value)
            if difficulty < 1 or difficulty > 10:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid value for {self.parameter_name}: {self.value}. Must be a number between 1 and 10."
            )

        ids = self._retain_ids_where(ids, f"json_extract(json_extract(data, '$.cd'), '$.d') {self.operator} {difficulty}")

        return ids
        

class StabilitySearchNode(CustomSearchNode):

    parameter_name = "s"

    def __init__(self, browser, operator: str, value: str):
        self.browser = browser
        self.operator = operator
        self.value = value

    def filter_ids(self, ids: Sequence[ItemId]) -> Sequence[ItemId]:
        try:
            stability = float(self.value)
            if stability <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid value for {self.parameter_name}: {self.value}. Must be a postive number."
            )

        ids = self._retain_ids_where(ids, f"json_extract(json_extract(data, '$.cd'), '$.s') {self.operator} {stability}")

        return ids
        

class RetrievabilitySearchNode(CustomSearchNode):

    parameter_name = "r"

    def __init__(self, browser, operator: str, value: str):
        self.browser = browser
        self.operator = operator
        self.value = value

    def filter_ids(self, ids: Sequence[ItemId]) -> Sequence[ItemId]:
        custom_scheduler = check_fsrs4anki(mw.col.all_config())
        version = get_version(custom_scheduler)
        try:
            retrievability = float(self.value)
            if retrievability < 0 or retrievability > 1:
                raise ValueError
        except ValueError:
            raise ValueError(
                f"Invalid value for {self.parameter_name}: {self.value}. Must be a number between 0 and 1."
            )
        if version[0] == 3:
            threshold = math.log(retrievability) / math.log(0.9)
        elif version[0] == 4:
            threshold = 9 * (1 / retrievability - 1)
        ids = self._retain_ids_where(ids, f"""case when odid==0 
        then -({mw.col.sched.today} - (due-ivl)) / json_extract(json_extract(data, '$.cd'), '$.s')
        else -({mw.col.sched.today} - (odue-ivl)) / json_extract(json_extract(data, '$.cd'), '$.s')
        end {self.operator} -{threshold}""")

        return ids