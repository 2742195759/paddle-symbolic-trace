from __future__ import annotations

import inspect
import operator
from functools import cached_property, reduce
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple, TypeVar

from ...utils import InnerError

if TYPE_CHECKING:
    T = TypeVar("T")
    Args = Tuple[T, ...]
    Kwargs = Dict[str, T]


def format_type(type_: type[Any] | tuple[type[Any], ...]) -> str:
    if not isinstance(type_, tuple):
        type_ = (type_,)
    return " | ".join([t.__name__ for t in type_])


def convert_annotation_to_type(type_str: str) -> tuple[type[Any], ...]:
    import builtins

    from . import variables

    type_str = type_str.strip()
    if type_str == "Any":
        type_str = "object"

    if "|" in type_str:
        return reduce(
            operator.add, map(convert_annotation_to_type, type_str.split("|"))
        )

    search_namespaces = [variables, builtins]
    for namespace in search_namespaces:
        if hasattr(namespace, type_str):
            return (getattr(namespace, type_str),)
    raise InnerError(f"Cannot find type {type_str} in {search_namespaces}")


class Pattern:
    type_strings: Args[str]
    kwtype_strings: Kwargs[str]

    def __init__(
        self,
        *types: str,
        **kwtypes: str,
    ):
        self.type_strings = types
        self.kwtype_strings = kwtypes

    @cached_property
    def types(self) -> Args[tuple[type[Any], ...]]:
        return tuple(
            convert_annotation_to_type(type_) for type_ in self.type_strings
        )

    @cached_property
    def kwtypes(self) -> Kwargs[tuple[type[Any], ...]]:
        return {
            name: convert_annotation_to_type(type_)
            for name, type_ in self.kwtype_strings.items()
        }

    def match_inputs(self, *args: Any, **kwargs: Any) -> bool:
        if len(args) != len(self.types):
            return False
        if any(name not in kwargs for name in self.kwtypes.keys()):
            return False
        return all(
            isinstance(arg, type_) for arg, type_ in zip(args, self.types)
        ) and all(
            isinstance(kwargs[name], type_)
            for name, type_ in self.kwtypes.items()
        )

    def __repr__(self) -> str:
        types_repr = ", ".join([format_type(type_) for type_ in self.types])
        kwtypes_repr = ", ".join(
            [
                f"{name}={format_type(type_)}"
                for name, type_ in self.kwtypes.items()
            ]
        )
        return f"Pattern({types_repr}, {kwtypes_repr})"


class Dispatcher:
    handlers: dict[
        Callable[..., Any], list[tuple[Pattern, Callable[..., Any]]]
    ] = {}

    @classmethod
    def register(
        cls,
        fn: Callable[..., Any],
        types: tuple[str, ...],
        kwtypes: dict[str, str],
        handler: Callable[..., Any],
    ):
        if fn not in cls.handlers:
            cls.handlers[fn] = []
        cls.handlers[fn].append((Pattern(*types, **kwtypes), handler))

    @classmethod
    def register_decorator(cls, fn: Callable[..., Any]):
        def decorator(handler: Callable[..., Any]):
            signature = inspect.signature(handler)
            types: list[str] = []
            for name, param in signature.parameters.items():
                if param.annotation == param.empty:
                    types.append("Any")
                elif (
                    param.kind == param.VAR_POSITIONAL
                    or param.kind == param.VAR_KEYWORD
                ):
                    raise InnerError("Not support varargs in decorator mode.")
                else:
                    types.append(str(param.annotation))
            cls.register(fn, tuple(types), {}, handler)
            return None

        return decorator

    @classmethod
    def dispatch(
        cls, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Callable[..., Any] | None:
        if fn not in cls.handlers:
            return None
        for pattern, handler in cls.handlers[fn]:
            if pattern.match_inputs(*args, **kwargs):
                return handler
        return None
