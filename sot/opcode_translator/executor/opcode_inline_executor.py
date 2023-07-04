from __future__ import annotations

import builtins
import contextlib
import inspect
import re
from typing import TYPE_CHECKING

from ...utils import BreakGraphError, log
from .guard import StringifyExpression, union_free_vars
from .opcode_executor import OpcodeExecutorBase, Stop
from .tracker import BuiltinTracker, ConstTracker, DummyTracker, Tracker
from .variables import (
    CellVariable,
    DictIterVariable,
    IterVariable,
    SequenceIterVariable,
)

if TYPE_CHECKING:
    from .pycode_generator import PyCodeGen
    from .variables import FunctionVariable


class FunctionGlobalTracker(Tracker):
    def __init__(self, fn: FunctionVariable, name: str):
        super().__init__([fn])
        self.fn = fn
        self.name = name

    def gen_instructions(self, codegen: PyCodeGen):
        self.fn.tracker.gen_instructions(codegen)
        codegen.gen_load_attr("__globals__")
        codegen.gen_load_const(self.name)
        codegen.gen_subscribe()

    def trace_value_from_frame(self):
        fn_tracer = self.fn.tracker.trace_value_from_frame()
        return StringifyExpression(
            f"{fn_tracer.expr}.__globals__['{self.name}']",
            union_free_vars(fn_tracer.free_vars),
        )

    def __repr__(self) -> str:
        return f"FunctionGlobalTracker(fn={self.fn}, name={self.name})"


class FunctionClosureTracker(Tracker):
    def __init__(self, fn: FunctionVariable, idx: int):
        super().__init__([fn])
        self.fn = fn
        self.idx = idx

    def gen_instructions(self, codegen: PyCodeGen):
        self.fn.tracker.gen_instructions(codegen)
        codegen.gen_load_attr("__closure__")
        codegen.gen_load_const(self.idx)
        codegen.gen_subscribe()
        codegen.gen_load_attr("cell_contents")

    def trace_value_from_frame(self):
        fn_tracer = self.fn.tracker.trace_value_from_frame()
        return StringifyExpression(
            f"{fn_tracer.expr}.__closure__[{self.idx}].cell_contents",
            union_free_vars(fn_tracer.free_vars),
        )

    def __repr__(self) -> str:
        return f"FunctionClosureTracker(fn={self.fn}, idx={self.idx})"


@contextlib.contextmanager
def signature_clear_guard(fn, name):
    if not hasattr(fn, name):
        yield
    else:
        saved_attr = getattr(fn, name)
        delattr(fn, name)
        yield
        setattr(fn, name, saved_attr)


class OpcodeInlineExecutor(OpcodeExecutorBase):
    def __init__(self, fn_variable, *args, **kwargs):
        self._fn_var = fn_variable
        self.return_value = None
        self._fn_value = fn_variable.value
        super().__init__(fn_variable.get_code(), fn_variable.graph)
        self._name = "Inline"
        self._prepare_locals(*args, **kwargs)
        self._prepare_closure()
        # TODO: consider generator.

    def _handle_comps(self):
        is_comp = any(
            x in self._fn_value.__name__
            for x in ['<listcomp>', '<dictcomp>', '<genexpr>']
        )
        if not is_comp:
            return
        pattern = r'implicit\d+'
        for name in list(self._locals.keys()):
            if re.match(pattern, name):
                self._locals[name.replace('implicit', '.')] = self._locals[name]

    def _prepare_locals(self, *args, **kwargs):
        from .variables import VariableBase, VariableFactory

        # temparay clear the fn.__signature__ to avoid signature check error
        with signature_clear_guard(
            self._fn_value, "__signature__"
        ), signature_clear_guard(self._fn_value, "__wrapped__"):
            sig = inspect.signature(self._fn_value)
            bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        for name, value in bound_args.arguments.items():
            assert name in sig.parameters
            # Convert varargs and kwargs to Variable
            if sig.parameters[name].kind == inspect.Parameter.VAR_POSITIONAL:
                tracker = DummyTracker(value)
            elif sig.parameters[name].kind == inspect.Parameter.VAR_KEYWORD:
                tracker = DummyTracker(list(value.values()))
            # Convert default args to Variable
            elif not isinstance(value, VariableBase):
                tracker = ConstTracker(value)
            else:
                tracker = value.tracker
            value = VariableFactory.from_value(value, self._graph, tracker)
            self._locals[name] = value

        self._handle_comps()

        log(
            5, f"[INLINE CALL] {self._code.co_name} with locals: ", self._locals
        )

    def _prepare_closure(self):
        from .variables import VariableFactory

        closure = self._fn_var.get_value().__closure__
        for name in self._code.co_cellvars + self._code.co_freevars:
            # create a cell for each variable.
            self._cells[name] = CellVariable()  # put in cells.
            if name in self._locals:
                self._cells[name].set_value(self._locals[name])

        if closure is None:
            return
        assert len(closure) == len(self._code.co_freevars)
        for idx, (name, cell) in enumerate(
            zip(self._code.co_freevars, closure)
        ):
            value = cell.cell_contents
            value = VariableFactory.from_value(
                value, self._graph, FunctionClosureTracker(self._fn_var, idx)
            )
            # wrapped by a CellVariable
            if not isinstance(value, CellVariable):
                value = CellVariable(value)
            self._cells[name] = value

    def _prepare_virtual_env(self):
        # prepare globals
        from .variables import VariableFactory

        globals_items = self._fn_value.__globals__.items()
        for name, value in globals_items:
            self._globals[name] = VariableFactory.from_value(
                value, self._graph, FunctionGlobalTracker(self._fn_var, name)
            )

        # prepare builtins
        for name, value in builtins.__dict__.items():
            self._builtins[name] = VariableFactory.from_value(
                value, self._graph, BuiltinTracker(name)
            )

        # prepare consts
        for value in self._code.co_consts:
            self._co_consts.append(
                VariableFactory.from_value(
                    value, self._graph, ConstTracker(value)
                )
            )

    def inline_call(self):
        self.run()
        return self.return_value

    def RETURN_VALUE(self, instr):
        assert (
            len(self._stack) == 1
        ), f"Stack must have one element, but get {len(self._stack)} elements."
        self.return_value = self.pop()
        return Stop()

    def _break_graph_in_jump(self, result, instr):
        raise BreakGraphError("_break_graph_in_jump.")

    def _create_resume_fn(self, index, stack_size=0):
        raise BreakGraphError("_create_resume_fn.")

    def FOR_ITER(self, instr):
        iterator = self.peek()
        assert isinstance(iterator, IterVariable)

        self._graph.add_global_guarded_variable(iterator)

        # simplely get next
        if isinstance(iterator, (SequenceIterVariable, DictIterVariable)):
            try:
                self.push(iterator.next())
            except StopIteration:
                self.pop()
                self._lasti = self.indexof(instr.jump_to)

        else:
            raise BreakGraphError("For loop fallback.")
