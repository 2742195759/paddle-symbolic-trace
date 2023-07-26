import unittest

from test_case_base import TestCaseBase

import paddle

global_x = 1
global_y = paddle.to_tensor(2)
global_z = None


def gloabl_func_int():
    global global_x
    global_x = global_x + 1
    return global_x


def gloabl_func_int_add():
    global global_x
    global_x = global_x + global_x
    return global_x + global_x


def gloabl_func_tensor():
    global global_y
    global_y = global_y + global_y
    return global_y


def gloabl_func_tensor_add():
    global global_y
    global_y = global_y + global_y
    return global_y + global_y


def global_func():
    global global_x
    global global_y
    global global_z

    global_z = global_x + global_y
    return global_z


def global_del_int():
    global global_x
    global global_y

    del global_x
    del global_y
    # return global_x


class TestExecutor(TestCaseBase):
    def test_global_func_int(self):
        self.assert_results_global(gloabl_func_int)
        self.assert_results_global(gloabl_func_int_add)

    def test_global_func_tensor(self):
        self.assert_results_global(gloabl_func_tensor)
        self.assert_results_global(gloabl_func_tensor_add)

    def test_global_func(self):
        self.assert_results_global(global_func)
        # There are currently no tests for errors
        # self.assert_results_error(global_del_int, KeyError)


if __name__ == "__main__":
    unittest.main()
