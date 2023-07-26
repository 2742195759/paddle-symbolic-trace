from __future__ import annotations

from typing import TYPE_CHECKING

import paddle
from paddle.amp.auto_cast import amp_state
from paddle.fluid.framework import _dygraph_tracer

from ..utils import (
    Cache,
    GraphLogger,
    Singleton,
    event_register,
    log,
    log_do,
    map_if,
)
from .interpreter import compile_sir

if TYPE_CHECKING:
    from .symbolic_context import SymbolicTraceContext


def clear_eager_tensor_name(output_tensors):
    for output_tensor in output_tensors:
        output_tensor.name = ""


class FallbackWrapper:
    """
    Used to store and call static graph methods generated by paddle.jit.to_static
    """

    def __init__(self, compiled_fn, SIR):
        self.compiled_fn = compiled_fn
        self.partial_program = None
        self.concrete_program = None
        self.SIR = SIR  # for debug

    def amp_cast_inputs(self, args, kwargs):
        """Prepare inputs for amp, cast float32 into float16 if needed."""
        current_amp_state = amp_state()
        if current_amp_state is None:
            return args, kwargs
        # skip if not gpu / xpu / custom place
        tracer = _dygraph_tracer()
        if not (
            tracer._expected_place.is_gpu_place()
            or tracer._expected_place.is_xpu_place()
            or tracer._expected_place.is_custom_place()
        ):
            return args, kwargs
        amp_dtype = current_amp_state["dtype"]
        log(3, f"[AMP] Cast float32 into {amp_dtype}")
        return map_if(
            (args, kwargs),
            pred=lambda x: isinstance(x, paddle.Tensor)
            and x.dtype == paddle.float32,
            true_fn=lambda x: x.cast(amp_dtype),
            false_fn=lambda x: x,
        )

    @event_register("FallbackWrapper")
    def __call__(self, *args, **kwargs):
        """TODO: we disable partial_program cache here because some bugs in ast to_static.
        >>> def func(x, y):
        >>>     return x + y

        if we call with f(tx, tx) and then f(tx, ty), we get wrong answer, because caches is hit but should not.
        we get a function: f x = 2 * x .

        we use `and False` to disable this cache.
        """

        # TODO(xiongkun): or True is on purpose, we should remove it later after
        # dy2static bug is fixed.
        log_do(
            2, lambda: print("[FallbackWrapper] start run SIR: \n", self.SIR)
        )
        args, kwargs = self.amp_cast_inputs(args, kwargs)
        log_do(
            4,
            lambda: print(
                self.compiled_fn.get_concrete_program(*args, **kwargs)[
                    1
                ].train_program
            ),
        )
        if self.partial_program is None or True:
            outputs = self.compiled_fn(*args, **kwargs)
            (
                self.concrete_program,
                self.partial_program,
            ) = self.compiled_fn.get_concrete_program(*args, **kwargs)
        else:
            # Speed up Resnet from 0.0068 --> 0.0057
            outputs = self.partial_program(*args, **kwargs)

        clear_eager_tensor_name(outputs)
        log_do(
            1,
            lambda: GraphLogger().add_subgraph(
                self.concrete_program.main_program
            ),
        )
        log_do(
            4,
            lambda: print("[CompileCache] run sir forward success."),
        )
        return outputs


@Singleton
class CompileSIRCache(Cache):
    """
    Cache the compiled function of SIR
    """

    def __init__(self):
        super().__init__(weak=False)

    def key_fn(
        self, context: SymbolicTraceContext, sir_name: str, build_strategy
    ):
        """
        generate a hash key for a SIR

        Args:
            context: The context to compile
            sir_name: The name of the sir to compile
            build_strategy: The build strategy to compile

        Returns:
            The hash key of the SIR
        """
        sir = context.get_sir(sir_name)
        # NOTE(dev): Is str(sir) a heavy opearation ?
        hash_key = hash(str(sir))
        return hash_key

    def value_fn(
        self, context: SymbolicTraceContext, sir_name: str, build_strategy
    ):
        """
        Generate static graph function

        Args:
            context: The context to compile
            sir_name: The name of the sir to compile
            build_strategy: The build strategy to compile

        Returns:
            The static graph function
        """
        return FallbackWrapper(
            paddle.jit.to_static(
                compile_sir(context, sir_name),
                build_strategy=build_strategy,
                enable_fallback=False,
            ),
            context.get_sir(sir_name),
        )
