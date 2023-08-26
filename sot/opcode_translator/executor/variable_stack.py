from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar, overload

if TYPE_CHECKING:
    ValidateValueFunc = Callable[[Any], None]


StackDataT = TypeVar("StackDataT")


class VariableStack(Generic[StackDataT]):
    """
    A stack class for storing variables.

    Examples:
        >>> var1, var2, var3, var4 = range(1, 5)
        >>> stack = VariableStack()
        >>> stack.push(var1)
        >>> stack.push(var3)
        >>> stack.insert(1, var2)
        >>> stack
        [1, 2, 3]
        >>> stack.pop()
        3
        >>> stack.pop_n(2)
        [1, 2]
        >>> stack.push(var1)
        >>> stack.push(var2)
        >>> stack.push(var3)
        >>> stack
        [1, 2, 3]
        >>> stack.top
        3
        >>> stack.peek[1]
        3
        >>> stack.peek[:1]
        [3]
        >>> stack.peek[:2]
        [2, 3]
        >>> stack.peek[1] = var4
        >>> stack
        [1, 2, 4]

    """

    class VariablePeeker:
        @overload
        def __getitem__(self, index: int) -> StackDataT:
            ...

        @overload
        def __getitem__(self, index: slice) -> list[StackDataT]:
            ...

        @overload
        def __call__(self, index: int = 1) -> StackDataT:
            ...

        @overload
        def __call__(self, index: slice) -> list[StackDataT]:
            ...

        def __init__(
            self, data: list[StackDataT], validate_value: ValidateValueFunc
        ):
            self._data = data
            self.validate_value = validate_value

        def __getitem__(
            self, index: int | slice
        ) -> StackDataT | list[StackDataT]:
            if isinstance(index, int):
                assert index >= 0
                return self.stack._data[-index]
            if isinstance(index, slice):
                assert index.start is None
                assert index.step is None
                assert index.stop > 0
                return self.stack._data[-index.stop :]
            raise NotImplementedError(f"index type {type(index)} not supported")

        def __setitem__(self, index: int, value: Any):
            assert isinstance(
                index, int
            ), f"index type {type(index)} not supported"
            self.validate_value(value)
            self._data[-index] = value

        def __call__(
            self, index: int | slice = 1
        ) -> StackDataT | list[StackDataT]:
            return self[index]

    def __init__(
        self,
        data: list[StackDataT] | None = None,
        *,
        validator: ValidateValueFunc | None = None,
    ):
        if validator is None:
            validate_value = lambda _: None
        else:
            validate_value = validator
        self._data = data or []
        self._peeker = VariableStack.VariablePeeker(self._data, validate_value)

    def copy(self):
        return VariableStack(self._data.copy())

    def push(self, val: StackDataT):
        """
        Pushes a variable onto the stack.

        Args:
            val: The variable to be pushed.

        """
        self.validate_value(val)
        self._data.append(val)

    def insert(self, index: int, val: StackDataT):
        """
        Inserts a variable onto the stack.

        Args:
            index: The index at which the variable is to be inserted, the top of the stack is at index 0.
            val: The variable to be inserted.

        """
        assert index >= 0
        self.validate_value(val)
        self._data.insert(len(self) - index, val)

    def pop(self) -> StackDataT:
        """
        Pops the top value from the stack.

        Returns:
            The popped value.

        """
        return self._data.pop()

    def pop_n(self, n: int) -> list[StackDataT]:
        """
        Pops the top n values from the stack.

        Args:
            n: The number of values to pop.

        Returns:
            A list of the popped values.

        """
        assert (
            len(self) >= n >= 0
        ), f"n should be in [0, {len(self)}], but get {n}"
        if n == 0:
            return []
        retval = self._data[-n:]
        self._data[-n:] = []
        return retval

    @property
    def peek(self):
        return self._peeker

    @property
    def top(self):
        return self.peek[1]

    @top.setter
    def top(self, value):
        self.peek[1] = value

    def __len__(self):
        return len(self._data)

    def __repr__(self) -> str:
        return str(self._data)
