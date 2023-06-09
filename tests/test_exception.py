import re
import unittest

import paddle
from symbolic_trace import symbolic_trace


def case1(x):
    return n  # noqa: F821


def case2(x):
    x = x + 1
    return x @ x


def case3(x):
    y = x.undefined_attr
    return y


def case4_inner(x):
    y = x * 2
    print(x)
    y = y + 1
    return y[100]


def case4(x):
    return case4_inner(x)


class TestAnalysisInputs(unittest.TestCase):
    def catch_error(self, func, inputs, error_line):
        try:
            symbolic_trace(func)(inputs)
        except Exception as e:
            match_results = re.compile(r'File ".*", line (\d+)').findall(str(e))
            assert len(match_results) >= 0
            assert match_results[0] == str(error_line)
            print(e)

    def test_all_case(self):
        self.catch_error(case1, paddle.rand([2, 1]), 9)
        # TODO: support runtime error
        # self.catch_error(case2, paddle.rand([2, 1]))
        self.catch_error(case3, paddle.rand([2, 1]), 18)
        self.catch_error(case4, paddle.rand([2, 1]), 26)


if __name__ == "__main__":
    unittest.main()
