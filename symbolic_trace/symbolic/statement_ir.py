"""
THIS FILE IS PRIVATE !!

use interface in symbolic_context.py first.
"""
import types

from ..utils import NameGenerator, is_proxy_tensor
from paddle.utils import is_sequence, map_structure
import paddle
from .bytecode_analysis import output_analysis

class Symbol: 
    """ 
    we need this class to distinguish the string and `math variable`
    """
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return str(self)
    
    def __eq__(self, other):
        return self.name == other.name
    
    def __hash__(self):
        return hash(self.name)

class Statement:
    def __init__(self, type, name, inputs, outputs):
        assert type in ['call', 'api', 'method']
        self.name = name
        self.inputs = inputs # list of Symbol | PythonObj
        self.outputs = outputs # list of Symbol | PythonObj
        self.type = type

    def __str__(self):
        def to_string(inps):
            if isinstance(inps, str) or not is_sequence(inps):
                return inps.__str__()
            inps = map(lambda x: x.__str__(), inps)
            return ", ".join(inps)
        name = self.name if isinstance(self.name, str) else 'paddle.' + self.name.__name__
        return "%s || %s = %s (%s) " % (self.type + ' '*(10 - len(self.type)), to_string(self.outputs), name, to_string(self.inputs))

    def __repr__(self):
        return self.__str__()

class StatementIR :
    """
    Don't create by yourself, just use the StatementIRCache.get()
    """
    def __init__(self, name):
        self.name = name
        self.inputs = [] # list of Symbol | PythonObj
        self.outputs = [] # list of Symbol | PythonObj
        self.statements = [] # list of Statement
        pass

    def add_input(self, input):
        self.inputs.append(input)

    def add_output(self, output):
        self.outputs.append(output)

    def add_statement(self, statement):
        assert isinstance(statement, Statement)
        self.statements.append(statement)

    def analysis_inputs(self): 
        used_symbols = set()
        generated_symbols = set()
        for stmt in self.statements:
            for inp in stmt.inputs:
                if isinstance(inp, Symbol):
                    used_symbols.add(inp)
            if isinstance(stmt.outputs, Symbol):
                generated_symbols.add(stmt.outputs)
        input_symbols = list(used_symbols - generated_symbols)
        self.inputs = input_symbols

    def analysis_outputs(self, runtime_context, frame: types.FrameType, additional_outputs=[]):
        reads = output_analysis(frame)
        reads_locals = [frame.f_locals[name] for name in reads]
        reads_symbols = []
        for local in reads_locals:
            proxy_tensor = local
            if isinstance(local, paddle.Tensor):
                proxy_tensor = runtime_context.from_tensor(local)
            # TODO(SigureMo): Handle other types
            reads_symbols.append(Symbol(proxy_tensor.name))

        # Add additional outputs
        output_symbols = list(set(reads_symbols) | set(additional_outputs))

        # Remove the outputs that are not in the statements
        stmt_outputs = [stmt.outputs for stmt in self.statements if isinstance(stmt.outputs, Symbol)]
        output_symbols = list(filter(lambda x: x in stmt_outputs, output_symbols))
        self.outputs = output_symbols

    def __str__(self):
        strs = []
        strs.append("StatmentIR: %s" % self.name)
        strs.append("  inputs: %s" % map_structure(lambda x: x.name, self.inputs))
        strs.append("  outputs: %s" % map_structure(lambda x: x.name, self.outputs))
        strs.append("  statements: ")
        for stmt in self.statements:
            strs.append("    %s" % stmt)
        return "\n".join(strs)

    def __repr__(self):
        return self.__str__()

class StatementIRFactory:
    def __init__(self):
        self.cache = {}
        self.name_generator = NameGenerator("SIR_")

    def __getitem__(self, key):
        return self.cache[key]

    def create(self):
        name = self.name_generator.next()
        sir = StatementIR(name)
        self.cache[name] = sir
        return sir

