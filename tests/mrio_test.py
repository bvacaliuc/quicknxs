#-*- coding: utf-8 -*-

import unittest


class Test(unittest.TestCase):
  def setUp(self):
    pass

  def test_nothing(self):
    pass


suite=unittest.TestLoader().loadTestsFromTestCase(Test)

