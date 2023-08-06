# New Supported Instructions:
# UNPACK_SEQUENCE (new)

from __future__ import annotations

import unittest

from test_case_base import TestCaseBase

import paddle


def foo(x: tuple[int, paddle.Tensor]):
    y, z = x
    return z + 1


def unpack_tensor(x: paddle.Tensor):
    a, b = x
    return (a, b)


class TestUnpack(TestCaseBase):
    def test_unpack_tuple(self):
        self.assert_results(foo, (1, paddle.to_tensor(2)))

    def test_unpack_tensor(self):
        self.assert_results(unpack_tensor, paddle.to_tensor([2, 3]))


if __name__ == "__main__":
    unittest.main()
