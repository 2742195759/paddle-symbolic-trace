import dis
import types

from ...utils import (
    InnerError,
    Singleton,
    UnsupportError,
    is_strict_mode,
    log,
    log_do,
)
from ..instruction_utils import get_instructions
from .function_graph import FunctionGraph
from .source import LocalSource
from .variables import (
    ConstantVariable,
    ListVariable,
    TupleVariable,
    VariableTrackerFactory,
)

SKIP = -1


@Singleton
class InstructionTranslatorCache:
    def __init__(self):
        self.cache = {}

    def __call__(self, frame):
        code = frame.f_code
        if code in self.cache:
            if self.cache[code] == SKIP:
                return frame.f_code
            elif (
                cached_code := self.lookup(frame, self.cache[code])
            ) is not None:
                log(3, "[Cache]: Cache hit\n")
                return cached_code
        return self.translate(frame)

    def lookup(self, frame, cache_list):
        for guard_fn, code in cache_list:
            if guard_fn(frame):
                return code
        return None

    def translate(self, frame):
        log(3, "[Cache]: Cache miss\n")
        code = frame.f_code
        result = start_translate(frame)
        if result is None:
            log(3, f"[Cache]: Skip frame {frame.f_code.co_name}\n")
            self.cache[code] = SKIP
            return code

        new_code, guard_fn = result
        if code not in self.cache:
            self.cache[code] = []
        self.cache[code].append((guard_fn, new_code))
        return new_code


def start_translate(frame):
    simulator = OpcodeExecutor(frame)
    try:
        new_code, guard_fn = simulator.run()
        log_do(3, lambda: dis.dis(new_code))
        return new_code, guard_fn
    except InnerError as e:
        raise
    except UnsupportError as e:
        if is_strict_mode():
            raise
        log(2, f"Unsupport Frame is {frame.f_code.co_name}")
        return None
    except Exception as e:
        raise


class OpcodeExecutor:
    def __init__(self, frame: types.FrameType):
        self._frame = frame
        self._stack = []
        self._code = frame.f_code
        # fake env for run, new env should be gened by PyCodeGen
        self._co_consts = self._code.co_consts
        self._locals = {}
        self._globals = {}
        self._lasti = 0  # idx of instruction list
        self.graph = FunctionGraph(self._frame)
        self.new_code = None

        self._instructions = get_instructions(self._code)
        self._prepare_locals_and_globals()

    def _prepare_locals_and_globals(self):
        for name, value in self._frame.f_locals.items():
            self._locals[name] = VariableTrackerFactory.from_value(
                value, self.graph
            )

        for name, value in self._frame.f_globals.items():
            self._globals[name] = VariableTrackerFactory.from_value(
                value, self.graph
            )

    def run(self):
        log(3, f"start execute opcode: {self._code}\n")
        self._lasti = 0
        while True:
            if self._lasti >= len(self._instructions):
                raise InnerError("lasti out of range, InnerError.")
            cur_instr = self._instructions[self._lasti]
            self._lasti += 1
            is_stop = self.step(cur_instr)
            if is_stop:
                break
        if self.new_code is None:
            raise InnerError("OpExecutor return a emtpy new_code.")
        return self.new_code, self.guard_fn

    def step(self, instr):
        if not hasattr(self, instr.opname):
            raise UnsupportError(f"opcode: {instr.opname} is not supported.")
        log(3, f"[TraceExecution]: {instr.opname}, stack is {self._stack}\n")
        getattr(self, instr.opname)(instr)  # run single step.
        if instr.opname == "RETURN_VALUE":
            return True
        return False

    def pop(self):
        return self._stack.pop()

    def push(self, val):
        self._stack.append(val)

    def LOAD_ATTR(self, instr):
        TODO  # noqa: F821

    def LOAD_FAST(self, instr):
        varname = instr.argval
        var = self._locals[varname]
        var.try_set_source(LocalSource(instr.arg, varname))
        self.push(var)

    def LOAD_METHOD(self, instr):
        TODO  # noqa: F821

    def STORE_FAST(self, instr):
        """
        TODO: side effect may happen
        """
        var = self.pop()
        self._locals[instr.argval] = var

    def LOAD_GLOBAL(self, instr):
        TODO  # noqa: F821

    def LOAD_CONST(self, instr):
        var = ConstantVariable(instr.argval)
        self.push(var)

    def BINARY_MULTIPLY(self, instr):
        b = self.pop()
        a = self.pop()
        self.push(a * b)

    def BINARY_ADD(self, instr):
        b = self.pop()
        a = self.pop()
        self.push(a + b)

    def BINARY_SUBSCR(self, instr):
        b = self.pop()
        a = self.pop()
        self.push(a[b])

    def INPLACE_ADD(self, instr):
        b = self.pop()
        a = self.pop()
        a += b
        self.push(a)

    def CALL_METHOD(self, instr):
        TODO  # noqa: F821

    def RETURN_VALUE(self, instr):
        assert len(self._stack) == 1, "Stack must have one element."
        ret_val = self.pop()
        self.new_code, self.guard_fn = self.graph.start_compile(ret_val)

    def BUILD_LIST(self, instr):
        list_size = instr.arg
        if list_size <= len(self._stack):
            val_list = self._stack[-list_size:]
            self._stack[-list_size:] = []
            self.push(ListVariable(val_list))
        else:
            raise InnerError(
                f"OpExecutor want BUILD_LIST with size {list_size}, but current stack do not have enough elems."
            )

    def BUILD_TUPLE(self, instr):
        tuple_size = instr.arg
        if tuple_size <= len(self._stack):
            val_tuple = self._stack[-tuple_size:]
            self._stack[-tuple_size:] = []
            self.push(TupleVariable(val_tuple))
        else:
            raise InnerError(
                f"OpExecutor want BUILD_TUPLE with size {tuple_size}, but current stack do not have enough elems."
            )
