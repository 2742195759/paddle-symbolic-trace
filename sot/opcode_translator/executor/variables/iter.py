from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..tracker import ConstTracker, DummyTracker, Tracker
from .base import VariableBase
from .basic import ConstantVariable, TensorVariable
from .callable import PaddleLayerVariable
from .container import DictVariable, ListVariable, RangeVariable, TupleVariable

if TYPE_CHECKING:
    from ..function_graph import FunctionGraph


class IterVariable(VariableBase):
    """
    This Variable (include subclasses) should be generated only when simulate GET_ITER opcode
    """

    def __init__(self, obj, graph, tracker):
        super().__init__(tracker)
        assert isinstance(obj, VariableBase)
        self.hold = obj
        self.graph = graph

    def make_stringify_guard(self):
        return self.hold.make_stringify_guard()


class SequenceIterVariable(IterVariable):
    def __init__(self, obj, graph, tracker):
        super().__init__(obj, graph, tracker)
        self.idx = 0

    def next(self):
        if self.idx < len(self.hold):
            val = self.hold[self.idx]
            self.idx += 1
            return val
        else:
            raise StopIteration()

    @property
    def main_info(self) -> dict[str, Any]:
        return {
            "idx": self.idx,
        }


class EnumerateVariable(IterVariable):

    """
    EnumerateVariable is a subclass of IterVariable used to wrap an Iteraable type.

    Args:
        val_iterator (Iterable): The Iterable to be wrapped.
        graph (FunctionGraph): The FunctionGraph object that this variable is associated with.
        tracker (Tracker): The Tracker object that tracks the information of this variable.
    """

    def __init__(self, val_iterator, graph, tracker):
        super().__init__(val_iterator, graph, tracker)
        self.idx = 0

    def next(self):
        if self.idx < len(self.hold):
            val = self.hold[self.idx]
            # wrap
            idx_var = ConstantVariable(
                self.idx, self.graph, ConstTracker(self.idx)
            )
            self.idx += 1
            return TupleVariable(
                (idx_var, val), self.graph, DummyTracker([idx_var, val])
            )
        else:
            raise StopIteration()

    def get_items(self):
        size = len(self.hold)
        list_enum: list = []
        for idx in range(size):
            val = self.hold[idx]
            idx_var = ConstantVariable(idx, self.graph, ConstTracker(idx))
            tuple_var = TupleVariable(
                (idx_var, val), self.graph, DummyTracker([idx_var, val])
            )
            list_enum.append(tuple_var)
        return list_enum

    def get_wrapped_items(self):
        return self.get_items()

    @staticmethod
    def from_iterator(value, graph: FunctionGraph | None, tracker: Tracker):
        # breakpoint()
        if isinstance(
            value,
            (
                ListVariable,
                TupleVariable,
                RangeVariable,
                DictVariable,
                PaddleLayerVariable,
                TensorVariable,
            ),
        ):
            return EnumerateVariable(value, graph, tracker)
        # FIXME(zmh): to delete

        else:
            return UserDefinedIterVariable(value, graph, tracker)


class DictIterVariable(IterVariable):
    def __init__(self, obj, graph, tracker):
        super().__init__(obj, graph, tracker)
        self.key_list = [
            ConstantVariable(x, graph, ConstTracker(x)) for x in self.hold
        ]
        self.idx = 0

    def next(self):
        if self.idx < len(self.key_list):
            val = self.key_list[self.idx]
            return val
        else:
            raise StopIteration()


class TensorIterVariable(IterVariable):
    def __init__(self, obj, graph, tracker):
        super().__init__(obj, graph, tracker)


# what UserDefinedIterVariable holds doesn't matter, because use user defined iterator will trigger break graph
class UserDefinedIterVariable(IterVariable):
    def __init__(self, obj, graph, tracker):
        super().__init__(obj, graph, tracker)
