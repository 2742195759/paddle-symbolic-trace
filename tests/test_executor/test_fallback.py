import unittest

from test_case_base import TestCaseBase

import paddle


def ifelse_func(x, y):
    if x > 0:
        y = y + 1
    else:
        y = y + 2
    return y


class TestIfElse(TestCaseBase):
    def test_simple(self):
        x = paddle.to_tensor([1.0])
        y = paddle.to_tensor([2.0])
        self.assert_results(ifelse_func, x, y)


def multi_output(x: paddle.Tensor):
    m = x + 1
    if x > 0:
        return m
    else:
        return 2 * m


class TestExecutor(TestCaseBase):
    def test_simple(self):
        x = paddle.to_tensor(2)
        self.assert_results(multi_output, x)
        x = paddle.to_tensor(-2)
        self.assert_results(multi_output, x)


def print_fallback(x, y, z):
    x = x + 1
    print(x)
    out = x + y + z
    return out


class TestPrint(TestCaseBase):
    def test_simple(self):
        x = paddle.to_tensor(2)
        y = paddle.to_tensor(3)
        z = paddle.to_tensor(4)
        self.assert_results(print_fallback, x, y, z)


if __name__ == "__main__":
    unittest.main()
