import unittest

from test_case_base import TestCaseBase


def gen():
    for i in range(10):
        yield i


def case1():
    sum = 0
    for i in gen():
        sum += i
    return sum


class TestGen(TestCaseBase):
    def test_gen(self):
        self.assert_results(case1)


if __name__ == "__main__":
    unittest.main()
