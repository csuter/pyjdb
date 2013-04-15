""" Unit tests for pyjdb.internal.serialization package"""

import pyjdb.internal.serialization
import unittest

class TestDatautilsPackage(unittest.TestCase):

  def pack_and_unpack_test_helper(self, fmt, byte_array, python_obj):
    self.unpack_test_helper(fmt, byte_array, python_obj)
    self.pack_test_helper(fmt, python_obj, byte_array)

  def unpack_test_helper(self, fmt, byte_array, expected_output):
    self.assertEquals(
        pyjdb.internal.serialization.from_bytearray(
            fmt,
            ''.join([chr(x) for x in byte_array])),
        expected_output)

  def pack_test_helper(self, fmt, data, expected_list_of_bytes):
    self.assertEquals(
        pyjdb.internal.serialization.to_bytearray(
            fmt,
            data),
        bytearray(expected_list_of_bytes))

  def test_pack_and_unpack_string(self):
    # string
    fmt = "S"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x01, 0x41 ]
    unpacked = [u'A']
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_int32(self):
    # 32 bit integer
    fmt = "I"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x10 ]
    unpacked = [16]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_boolean(self):
    # boolean
    fmt = "bb"
    jdwp_bytes = [ 0x00, 0x01 ]
    unpacked = [False, True]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_byte(self):
    # byte
    fmt = "BB"
    jdwp_bytes = [ 0x08, 0x10 ]
    unpacked = [8, 16]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_int64(self):
    # 64 bit integer
    fmt = "LL"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
          0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01 ]
    unpacked = [16, 1152921504606846977]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  #def test_pack_and_unpack_tagged_value(self):
    # value (typetag + variable-size data)
    # TODO(implement value unpacking)
    ###self.pack_and_unpack_test_helper("V",
    ###    [ 0x01, 0x01 ],
    ###    (["asdf"], 2))

  def test_pack_and_unpack_tagged_object_id(self):
    # tagged objectId ( byte + long)
    fmt = "T"
    jdwp_bytes = [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01 ]
    unpacked = [(1, 1)]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_location(self):
    # location
    fmt = "X"
    jdwp_bytes = [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
    unpacked = [(1, 1, 2, 3)]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  #def test_pack_and_unpack_array_region(self):
    # array
    # TODO(implement array region unpacking)
    ###self.pack_and_unpack_test_helper("X",
    ###    [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
    ###      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
    ###      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ],
    ###    ([(1, 1, 2, 3)], 25))

  def test_pack_and_unpack_repeat(self):
    # repeat
    fmt = "*(BI)"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x02, # count
          0x01, 0x00, 0x00, 0x00, 0x07,
          0x05, 0x10, 0x00, 0x00, 0x00 ]
    unpacked = [[1, 7], [5, 268435456]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

  def test_pack_and_unpack_repeat_with_empty(self):
    fmt = "IL*(SB)"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x01,  # I
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,  # L
        0x00, 0x00, 0x00, 0x00 ]  # empty repeat
    unpacked = [1, 2]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
    
  def test_pack_and_unpack_select(self):
    # select
    fmt = "?B(1=IBB|2=L|3=X)"
    jdwp_bytes = [
          # select modifier = 1 (should be an IBB-type)
          0x01, 0x00, 0x00, 0x00, 0x20, 0x11, 0x12 ]
    unpacked = [1, [32, 17, 18]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

    fmt = "?B(1=IBB|2=L|3=X)"
    jdwp_bytes = [
          # select modifier = 2 (should be an L-type)
          0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07 ]
    unpacked = [2, [7]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

    fmt = "?B(1=IBB|2=L|3=X)"
    jdwp_bytes = [
          # select modifier = 3 (should be an X-type)
          0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
    unpacked = [3, [(1, 1, 2, 3)]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

    # select
    fmt = "*(?B(1=IBB|2=L|3=X))"
    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x03,  # count = 3
          # first select modifier = 1 (should be an IBB-type)
          0x01, 0x00, 0x00, 0x00, 0x20, 0x11, 0x12,
          # first select modifier = 2 (should be an L-type)
          0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07,
          # first select modifier = 3 (should be an X-type)
          0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
    unpacked = [[1, [32, 17, 18]], [2, [7]], [3, [(1, 1, 2, 3)]]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

    fmt = "BB*(?B(5=S))"
    jdwp_bytes = [ 0x08, 0x02,  # BB
        0x00, 0x00, 0x00, 0x01,
        0x05, 0x00, 0x00, 0x00, 0x03, 0x61, 0x62, 0x63 ]
    unpacked = [8, 2, [5, [u'abc']]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

    fmt = "BB*(?B(5=IBS))"
    jdwp_bytes = [ 0x08, 0x02,  # BB
        0x00, 0x00, 0x00, 0x01,
        0x05,  # ?B
        0x00, 0x00, 0x00, 0x07,  # I
        0x01,  # B
        0x00, 0x00, 0x00, 0x03, 0x61, 0x62, 0x63 ]  # S
    unpacked = [8, 2, [5, [7, 1, u'abc']]]
    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

if __name__ == '__main__':
  unittest.main()
