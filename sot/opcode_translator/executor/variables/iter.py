from __future__ import annotations

from typing import Any

from ..tracker import ConstTracker
from .base import VariableBase
from .basic import ConstantVariable


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
