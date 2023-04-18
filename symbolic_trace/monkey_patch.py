from .utils import paddle_tensor_method, no_eval_frame
from .proxy_tensor import ProxyTensor


def build_magic_method(method_name):
    @no_eval_frame
    def __impl__(self, other):
        return self.call_method(method_name, self, other)
    return __impl__

def patch_proxy_tensor():
    for method_name in paddle_tensor_method:
        setattr(ProxyTensor, method_name, build_magic_method(method_name))
