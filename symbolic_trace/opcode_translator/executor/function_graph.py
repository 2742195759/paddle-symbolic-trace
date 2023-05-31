# This file is specifically used to handle the problem
# of generating a Graph from a linear function call.

from __future__ import annotations

from collections import namedtuple
from copy import deepcopy
from typing import Any, Callable

from ...infer_meta import InferMetaCache, infer_meta, infer_meta_for_layer
from ...symbolic.statement_ir import Symbol
from ...symbolic.symbolic_context import SymbolicTraceContext
from ...utils import is_paddle_api, log, show_trackers
from .guard import Guard, StringifyExpression, make_guard
from .pycode_generator import PyCodeGen
from .tracker import DummyTracker
from .variables import (
    ContainerVariable,
    PaddleLayerVariable,
    TensorVariable,
    VariableBase,
    map_variables,
    topo_sort_vars,
)


def convert_to_meta(inputs):
    def func(x):
        if isinstance(x, TensorVariable):
            return x.meta
        return x.get_value()

    return map_variables(func, inputs)


def convert_to_symbol(inputs):
    def func(x):
        if isinstance(x, TensorVariable):
            return Symbol(x.var_name)
        return x.get_value()

    return map_variables(func, inputs)


class FunctionGraph:
    """
    A Graph representation corresponding to each FunctionFrame
    The input binding diagram containing the current call represents three parts of output settings,
    This Graph can be compiled as a f_locals dependency function which produce the same outputs.
    """

    Memo = namedtuple(
        "function_graph_memo",
        ['inner_out', 'input_variables', "stmt_ir", "global_guards"],
    )

    def __init__(self, frame):
        self.sir_ctx = SymbolicTraceContext()
        self.inner_out = set()
        self.input_variables = []
        self.pycode_gen = PyCodeGen(frame)
        self.py_frame = frame
        self.out_var_prefix = "___SIR_out_"
        self._global_guarded_variables: list[VariableBase] = []

    def need_add_input(self, var):
        if var.id in self.inner_out:
            return False
        for v in self.input_variables:
            if v.id == var.id:
                return False
        return True

    def save_memo(self):
        """
        Why don't use __deepcopy__:
            bacause memo is not a deepcopy, i.e inner_out is only a
            shallow copy, SIR is a deepcopy.
        """
        saved_stmt_ir = deepcopy(self.sir_ctx.TOS)
        return FunctionGraph.Memo(
            inner_out=set(self.inner_out),
            input_variables=list(self.input_variables),
            stmt_ir=saved_stmt_ir,
            global_guards=list(self._global_guarded_variables),
        )

    def restore_memo(self, memo):
        self.inner_out = memo.inner_out
        self.input_variables = memo.input_variables
        self.sir_ctx.replace_TOS(memo.stmt_ir)
        self._global_guarded_variables = memo.global_guards

    def collect_input_variables(self, inputs: list[VariableBase]):
        for inp in inputs:
            if isinstance(inp, ContainerVariable):
                self.collect_input_variables(inp.get_items())
            if isinstance(inp, VariableBase) and self.need_add_input(inp):
                self.input_variables.append(inp)

    @property
    def guard_fn(self) -> Guard:
        guards = [
            variable.make_stringify_guard()
            for variable in topo_sort_vars(
                self.input_variables + self._global_guarded_variables
            )
            if not isinstance(variable.tracker, DummyTracker)
        ]
        for guard in guards:
            assert isinstance(
                guard, StringifyExpression
            ), "guard must be StringifyExpression."

        return make_guard(guards)

    def start_compile(self, *ret_vars: VariableBase):
        ret_items = [
            ret_item
            for ret_var in ret_vars
            for ret_item in ret_var.flatten_items()
        ]
        tensor_items = self._find_tensor_outputs(ret_items)
        compiled_fn, statment_ir = self.sir_ctx.compile_fn(
            [Symbol(tensor_var.var_name) for tensor_var in tensor_items]
        )
        input_names = statment_ir.inputs
        compiled_fn_name = statment_ir.name
        # prepare function and inputs
        self.pycode_gen.gen_load_object(compiled_fn, compiled_fn_name)
        for name in input_names:
            found = False
            for variable in self.input_variables:
                if (
                    isinstance(variable, (TensorVariable, PaddleLayerVariable))
                    and variable.get_symbol().name == name
                ):
                    variable.tracker.gen_instructions(self.pycode_gen)
                    found = True
                    break
            assert found, f"can't find input {name} in SIR."
        # Pack all args into a tuple, because we don't support *args now.
        self.pycode_gen.gen_build_tuple(count=len(input_names))
        # call the compiled_fn
        self.pycode_gen.gen_call_function(argc=1)
        # Store outputs to f_locals
        self.pycode_gen.gen_unpack_sequence(count=len(tensor_items))
        for tensor_var in tensor_items:
            self.pycode_gen.gen_store_fast(tensor_var.out_var_name)
        # restore the outputs.
        for ret_var in ret_vars:
            ret_var.reconstruct(self.pycode_gen)

        # deal side effect
        # TODO(xiongkun): add side effect handle

        tracker_output_path = show_trackers()
        if tracker_output_path:
            from .tracker_viewer import view_tracker

            view_tracker(list(ret_vars), tracker_output_path, format="png")

    def call_paddle_api(
        self,
        func: Callable[..., Any],
        *args: VariableBase,
        **kwargs: VariableBase,
    ):
        assert is_paddle_api(func)
        # not fallback api, start symbolic trace.
        # TODO(xiokgun): multi-output support.
        # TODO(xiokgun): may have python buildin object inside metas.
        # TODO(xiokgun): 4 kinds of python arguments. support it !!
        log(3, f"call paddle.api : {func.__name__}", "\n")
        self.collect_input_variables(list(args))
        self.collect_input_variables(list(kwargs.values()))
        metas = convert_to_meta(args)
        kwmetas = convert_to_meta(kwargs)
        meta = InferMetaCache()(func, *metas, **kwmetas)
        inputs_symbols = (
            convert_to_symbol(args),
            convert_to_symbol(kwargs),
        )
        log(3, f"         inputs : {inputs_symbols}", "\n")
        variable = TensorVariable(
            meta,
            self,
            tracker=DummyTracker(list(args) + list(kwargs.values())),
        )
        self.sir_ctx.call_API(
            func,
            inputs=inputs_symbols,
            outputs=convert_to_symbol(variable),
        )  # symbolic only contain symbols.

        self._put_inner(variable)
        return variable

    def call_tensor_method(self, method_name: str, *args: VariableBase):
        self.collect_input_variables(list(args))
        metas = convert_to_meta(args)
        meta = infer_meta(method_name, *metas)
        variable = TensorVariable(meta, self, tracker=DummyTracker(list(args)))
        self.sir_ctx.call_METHOD(
            method_name,
            inputs=(convert_to_symbol(args), {}),
            outputs=convert_to_symbol(variable),
        )  # symbolic only contain symbols.
        self._put_inner(variable)
        return variable

    def call_layer(
        self,
        layer: PaddleLayerVariable,
        *args: VariableBase,
        **kwargs: VariableBase,
    ):
        self.collect_input_variables([layer, *args])
        self.collect_input_variables(list(kwargs.values()))
        metas = convert_to_meta(args)
        kwmetas = convert_to_meta(kwargs)
        meta = infer_meta_for_layer(layer.value, *metas, **kwmetas)
        inputs_symbols = (
            (layer.get_symbol(), *convert_to_symbol(args)),
            convert_to_symbol(kwargs),
        )
        variable = TensorVariable(
            meta,
            self,
            tracker=DummyTracker([layer, *args] + list(kwargs.values())),
        )
        self.sir_ctx.call_LAYER(
            layer.value.__class__.__name__,
            inputs=inputs_symbols,
            outputs=convert_to_symbol(variable),
        )
        self._put_inner(variable)
        return variable

    def _put_inner(self, var):
        self.inner_out.add(var.id)

    def add_global_guarded_variable(self, variable: VariableBase):
        self._global_guarded_variables.append(variable)

    def _find_tensor_outputs(
        self, outputs: list[VariableBase]
    ) -> list[TensorVariable]:
        output_tensors: list[TensorVariable] = []
        for output in outputs:
            if isinstance(output, TensorVariable) and isinstance(
                output.tracker, DummyTracker
            ):
                output_tensors.append(output)
        return output_tensors
