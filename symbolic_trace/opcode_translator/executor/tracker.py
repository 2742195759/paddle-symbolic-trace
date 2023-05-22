from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from ...utils import InnerError
from .guard import StringifyExpression, union_free_vars

if TYPE_CHECKING:
    from .pycode_generator import PyCodeGen
    from .variables import VariableBase


def from_instruction(instr):
    pass


class Tracker:
    inputs: list[VariableBase]

    def __init__(self, inputs: list[VariableBase]):
        self.inputs = inputs

    def gen_instructions(self, codegen: PyCodeGen):
        raise NotImplementedError()

    def trace_value_from_frame(self) -> StringifyExpression:
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


class LocalTracker(Tracker):
    def __init__(self, name: str):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_fast(self.name)

    def trace_value_from_frame(self):
        return StringifyExpression(f"frame.f_locals['{self.name}']", {})


class GlobalTracker(Tracker):
    def __init__(self, name):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_global(self.name)

    def trace_value_from_frame(self):
        return StringifyExpression(f"frame.f_globals['{self.name}']", {})


class BuiltinTracker(Tracker):
    def __init__(self, name: str):
        super().__init__([])
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_global(self.name)

    def trace_value_from_frame(self):
        return StringifyExpression(
            f"builtins.__dict__[{self.name}]", {"builtins": builtins}
        )


class ConstTracker(Tracker):
    def __init__(self, value):
        super().__init__([])
        self.value = value

    def gen_instructions(self, codegen: PyCodeGen):
        codegen.gen_load_const(self.value)

    def trace_value_from_frame(self):
        return StringifyExpression(f"{self.value}", {})


class GetAttrTracker(Tracker):
    def __init__(self, obj: VariableBase, attr: str):
        super().__init__([obj])
        self.obj = obj
        self.attr = attr

    def gen_instructions(self, codegen: PyCodeGen):
        self.obj.tracker.gen_instructions(codegen)
        codegen.gen_load_attr(self.attr)

    def trace_value_from_frame(self):
        obj_tracer = self.obj.tracker.trace_value_from_frame()
        return StringifyExpression(
            f"getattr({obj_tracer.expr}, '{self.attr}')",
            union_free_vars(obj_tracer.free_vars),
        )


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
        container_tracer = self.container.tracker.trace_value_from_frame()
        return StringifyExpression(
            f"{container_tracer.expr}[{self.key}]",
            union_free_vars(container_tracer.free_vars),
        )
