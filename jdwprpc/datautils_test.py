""" Unit tests for datautils package"""

import datautils
import unittest


class TestDatautilsPackage(unittest.TestCase):

  def test_asdf(self):

    # S
    # I
    # b
    # B
    # L
    # V
    # T
    # X
    # A
    # ?
    # R
    fmt = "S"
    jdwp_bytes = bytearray([ 0x00, 0x00, 0x00, 0x01, 0x41 ])
    packed_data = ''.join([ chr(x) for x in jdwp_bytes ])

    self.assertEquals(
        datautils.unpack_jdwp_data(fmt, packed_data),
        ([u'A'], 5))

if __name__ == '__main__':
  unittest.main()
