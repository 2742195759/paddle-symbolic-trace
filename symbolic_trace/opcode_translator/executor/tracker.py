from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from ...utils import InnerError, NameGenerator

if TYPE_CHECKING:
    from .pycode_generator import PyCodeGen
    from .variables import VariableBase


def from_instruction(instr):
    pass


class Tracker:
    inputs: list[VariableBase]
    name_generator = NameGenerator("tracker_")

    def __init__(self, inputs: list[VariableBase]):
        self.inputs = inputs
        self.id = Tracker.name_generator.next()

    def gen_instructions(self, codegen: PyCodeGen):
        raise NotImplementedError()

    def trace_value_from_frame(self):
        raise NotImplementedError()

    def is_traceable(self):
        for input in self.inputs:
            if not input.tracker.is_traceable():
                return False
        return True


class DummyTracker(Tracker):
    def __init__(self, inputs: list[VariableBase]):
        super().__init__(inputs)

    def gen_instructions(self, codegen: PyCodeGen):
        raise InnerError("DummyTracker has no instructions")

    def trace_value_from_frame(self):
        raise InnerError("DummyTracker can't trace value from frame")

    def __repr__(self) -> str:
        return f"DummyTracker(num_inputs={len(self.inputs)})"


class LocalTracker(Tracker):
    def __init__(self, name: str):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_fast(self.name)

    def trace_value_from_frame(self):
        return lambda frame: frame.f_locals[self.name]

    def __repr__(self) -> str:
        return f"LocalTracker(name={self.name})"


class GlobalTracker(Tracker):
    def __init__(self, name):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_global(self.name)

    def trace_value_from_frame(self):
        return lambda frame: frame.f_globals[self.name]

    def __repr__(self) -> str:
        return f"GlobalTracker(name={self.name})"


class BuiltinTracker(Tracker):
    def __init__(self, name: str):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_global(self.name)

    def trace_value_from_frame(self):
        return lambda frame: builtins.__dict__[self.name]

    def __repr__(self) -> str:
        return f"BuiltinTracker(name={self.name})"


class ConstTracker(Tracker):
    def __init__(self, value):
        super().__init__([])
        self.value = value

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_const(self.value)

    def trace_value_from_frame(self):
        return lambda frame: self.value

    def __repr__(self) -> str:
        return f"ConstTracker(value={self.value})"


class GetAttrTracker(Tracker):
    def __init__(self, obj: VariableBase, attr: str):
        super().__init__([obj])
        self.obj = obj
        self.attr = attr

    def gen_instructions(self, codegen: PyCodeGen):
        self.obj.tracker.gen_instructions(codegen)
        codegen.gen_load_attr(self.attr)

    def trace_value_from_frame(self):
        return lambda frame: getattr(
            self.obj.tracker.trace_value_from_frame()(frame), self.attr
        )

    def __repr__(self) -> str:
        return f"GetAttrTracker(attr={self.attr})"


class GetItemTracker(Tracker):
    def __init__(self, container_var: VariableBase, key: object):
        super().__init__([container_var])
        self.container = container_var
        self.key = key

    def gen_instructions(self, codegen: PyCodeGen):
        self.container.tracker.gen_instructions(codegen)
        codegen.gen_load_const(self.key)
        codegen.gen_subscribe()

    def trace_value_from_frame(self):
        def trace_value(frame):
            container = self.container.tracker.trace_value_from_frame()(frame)
            return container[self.key]

        return trace_value

    def __repr__(self) -> str:
        return f"GetItemTracker(key={self.key})"
