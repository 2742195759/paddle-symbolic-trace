import paddle
from paddle.static import Program
from paddle.utils import flatten, is_sequence

from .utils import Cache, NameGenerator, Singleton, map_if, meta_str


@Singleton
class InferMetaCache(Cache):
    def key_fn(self, *args, **kwargs):
        return hash(
            (tuple(flatten(args)), tuple(kwargs.keys()), tuple(flatten(kwargs)))
        )

    def value_fn(self, *args, **kwargs):
        return infer_meta(*args, **kwargs)


class MetaInfo:
    def __init__(self, shape, dtype, stop_gradient):
        self.shape = shape
        self.dtype = dtype
        self.stop_gradient = stop_gradient

    @staticmethod
    def from_tensor(tensor):
        return MetaInfo(tensor.shape, tensor.dtype, tensor.stop_gradient)

    def is_dynamic_shape(self):
        """
        if -1 in shape, return True
        else: return False
        """
        return -1 in self.shape

    def to_input_spec(self):
        return paddle.static.InputSpec(
            self.shape, dtype=self.dtype, stop_gradient=self.stop_gradient
        )

    def __repr__(self):
        return meta_str(self.shape, self.dtype, self.stop_gradient)

    def __eq__(self, meta):
        return (
            self.shape == meta.shape
            and self.dtype == meta.dtype
            and self.stop_gradient == meta.stop_gradient
        )

    def __hash__(self):
        return hash((tuple(self.shape), self.dtype, self.stop_gradient))


@Singleton
class VariableCreator:
    def __init__(self):
        self.var_cache = {}
        self.main_program = Program()
        self.startup_program = Program()
        self.var_name_generator = NameGenerator("infer_meta_variable_")

    def gen_name(self, meta):
        name = f"{meta.dtype}_{meta.stop_gradient}"
        for l in meta.shape:
            name += f"_{l}"
        return name

    def create_var(self, meta):
        var = self.main_program.global_block().create_var(
            name=self.var_name_generator.next(),
            shape=meta.shape,
            dtype=meta.dtype,
            stop_gradient=meta.stop_gradient,
        )
        assert not isinstance(
            var, paddle.Tensor
        ), "Expect a Variable, but got a Tensor."
        return var

    def get_variable(self, meta):
        var_feature_name = self.gen_name(meta)

        if var_feature_name not in self.var_cache:
            # create_var will generate "generated_var_0", "generated_var_1", ...
            # have risk to conflict with last name.
            self.var_cache[var_feature_name] = self.create_var(meta)
        return self.var_cache[var_feature_name]

    def infer_meta(self, func, *args, **kwargs):
        with paddle.fluid.framework._dygraph_guard(None):
            args, kwargs = convert_to_variable(args), convert_to_variable(
                kwargs
            )

            with paddle.static.program_guard(
                self.main_program, self.startup_program
            ):
                if isinstance(func, str):
                    # TODO(Aurelius84): Is length of args always greater than 0?
                    # Do we need add condition check here?
                    out = getattr(args[0], func)(*args[1:], **kwargs)
                else:
                    out = func(*args, **kwargs)

        return variable_to_meta_info(out)


def convert_to_variable(args):
    return map_if(
        args,
        pred=lambda x: isinstance(x, MetaInfo),
        true_fn=lambda x: VariableCreator().get_variable(x),
        false_fn=lambda x: x,
    )


def convert_to_input_spec(args):
    return map_if(
        args,
        pred=lambda x: isinstance(x, MetaInfo),
        true_fn=lambda x: x.to_input_spec(),
        false_fn=lambda x: paddle.static.InputSpec.from_tensor(x),
    )


def variable_to_meta_info(args):
    return map_if(
        args,
        pred=lambda x: isinstance(x, paddle.static.Variable),
        true_fn=lambda x: MetaInfo(
            list(x.shape),
            x.dtype,
            x.stop_gradient,
        ),
        false_fn=lambda x: x,
    )


def infer_meta(func, *args, **kwargs):
    fn = SpecialInferMeta().get_infermeta_fn(func)
    if fn:
        return fn(*args, **kwargs)
    return VariableCreator().infer_meta(func, *args, **kwargs)


def infer_meta_for_layer(layer, *args, **kwargs):
    assert isinstance(
        layer, paddle.nn.Layer
    ), f"Expect a Layer, but got {layer}."
    layer = paddle.jit.to_static(layer, enable_fallback=False)

    args, kwargs = convert_to_input_spec(args), convert_to_input_spec(kwargs)
    concrete_program = layer.forward.get_concrete_program(*args, **kwargs)[0]
    out = concrete_program.outputs[0]
    out = MetaInfo(
        list(out.shape),
        out.dtype,
        out.stop_gradient,
    )
    layer.forward.rollback()
    return out


@Singleton
class SpecialInferMeta:
    def __init__(self):
        pass

    def get_infermeta_fn(self, fn):
        try:
            funcname = fn.__name__
            return getattr(self, f"infermeta_{funcname}")
        except:
            pass
        return None

    def infermeta_grad(
        self,
        outputs,
        inputs,
        grad_outputs=None,
        retain_graph=None,
        create_graph=False,
        only_inputs=True,
        allow_unused=False,
        no_grad_vars=None,
    ):
        if not is_sequence(inputs):
            inputs = [inputs]
        return inputs
