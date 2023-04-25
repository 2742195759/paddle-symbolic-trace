import collections
import dis
import functools

import paddle

from ..utils import log, log_do, no_eval_frame
from .convert import Callbacks
from .instruction_translator import (
    InstructionTranslatorCache,
    convert_instruction,
    gen_code_options,
    locals_globals_injection,
    pycode_attributes,
)
from .opcode_generater import gen_new_opcode
from .skip_files import need_skip_path
from .skip_translate_names import SKIP_TRANSLATE_NAMES

CustomCode = collections.namedtuple("CustomCode", ["code"])


class ConvertGuard:
    def __init__(self, on_convert=None):
        self.on_convert = on_convert

    def __enter__(self):
        log(1, "[start_bytecode_transform] start transform\n")
        assert self.on_convert is None or callable(self.on_convert)
        self.old = Callbacks().set_on_convert(self.on_convert)

    def __exit__(self, exc_type, exc_value, traceback):
        log(1, "[start_bytecode_transform] end transform\n")
        Callbacks().set_on_convert(self.old)


def eval_frame_callback(frame):
    if not need_skip_path(frame.f_code.co_filename):
        log(
            2,
            "[eval_frame_callback] want translate: "
            + frame.f_code.co_name
            + "\n",
        )
        new_code = transform_opcode(frame)
        retval = CustomCode(new_code)
        return retval
    return None


def transform_opcode(frame):
    log(8, "[transform_opcode] old_opcode: " + frame.f_code.co_name + "\n")
    log_do(8, lambda: dis.dis(frame.f_code))

    code_options = gen_code_options(frame.f_code)
    locals_globals_injection(frame, code_options)
    new_code = InstructionTranslatorCache()(frame, code_options)

    log(7, "\n[transform_opcode] new_opcode:  " + frame.f_code.co_name + "\n")
    log_do(7, lambda: dis.dis(new_code))

    return new_code
