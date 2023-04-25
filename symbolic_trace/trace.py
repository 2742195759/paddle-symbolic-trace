import contextlib

import paddle

from .convert_functions import convert_function
from .opcode_translator import ConvertGuard, eval_frame_callback
from .proxy_tensor import ProxyTensor, ProxyTensorContext


def symbolic_trace(func):
    def symbolic_traced_func(*args, **kwargs):
        ProxyTensorContext().reset()
        with ConvertGuard(convert_function) as ctx:
            paddle.fluid.core.set_eval_frame(eval_frame_callback)
            try:
                returns = func(*args, **kwargs)
            except Exception as e:
                raise e
            finally:
                paddle.fluid.core.set_eval_frame(None)
        return returns

    return symbolic_traced_func
