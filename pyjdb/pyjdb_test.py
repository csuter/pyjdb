import pyjdb
import signal
import string
import subprocess
import time
import unittest

class TestJdwpPackage(unittest.TestCase):
  def setUp(self):
    # boot up the sample java program in target jvm
    self.test_target_subprocess = subprocess.Popen([
        "/usr/bin/java", "-cp", "fib.jar",
        "-Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005",
        "com.alltheburritos.vimjdb.test.TestProgram"])
    time.sleep(1)
    self.jdwp = pyjdb.Jdwp(5005)
    self.jdwp.Initialize();

  def tearDown(self):
    # disconnect debugger
    self.jdwp.disconnect()
    # kill target jvm
    self.test_target_subprocess.send_signal(signal.SIGKILL)
    time.sleep(1)

  def test_VirtualMachine_Version(self):
    system_java_version = subprocess.check_output(
        "java -version 2>&1", shell=True)
    # the java -version output looks like
    #   java version "1.7.0_09"
    #   OpenJDK Runtime Environment .....
    #   OpenJDK 64-Bit Server VM (build 23.2-b09, mixed mode)
    # below, the inner split splits on any whitespace - the version is the 3rd
    # token (the 2th, from 0). It's double-quoted so we split on double-quotes
    # and take the middle one.
    system_version_number = string.split(
        string.split(system_java_version)[2], "\"")[1]
    version_response = self.jdwp.VirtualMachine.Version()
    jdwp_jvm_version_number = version_response['vmVersion']
    # if they're equal, then we're in business!
    self.assertEquals(system_version_number, jdwp_jvm_version_number)

  def test_virtual_machine__all_classes(self):
    all_classes_response = self.jdwp.VirtualMachine.AllClasses()
    self.assertTrue(all_classes_response['classes'] != None)
    string_class = [ x for x in all_classes_response['classes'] if
        x['signature'] == u'Ljava/lang/String;' ]
    self.assertEquals(len(string_class), 1)

  #def test_event_request_set_and_resume(self):
  #  # in this test we will
  #  #   1. get a list of all loaded classes
  #  #   2. request notification of class load events
  #  #   3. resume our suspended program
  #  #   4. assert that com.alltheburritos.defbug.test.TestProgram gets loaded
  #  all_classes_response = self.jdwp.VirtualMachine.AllClasses()
  #  loaded_class_signatures =\
  #      [ entry['signature'] for entry in all_classes_response['classes'] ]
  #  self.jdwp.EventRequest.Set(
  #      self.jdwp.EventKind.CLASS_PREPARE,
  #      self.jdwp.SuspendPolicy.NONE)
  #  # send vm resume to start things off
  #  self.jdwp.VirtualMachine.Resume()
  #  time.sleep(.5)
  #  print("EVENTS: ", events)
  #  #self.assertTrue(
  #      #"Lcom/alltheburritos/vimjdb/test/TestProgram;" in \
  #      #[ event[1][1][4] for request_id, event in self.jdwp.events if event[1][0] == 8 ])

  #def test_set_breakpoint(self):
    #   # we have to first await the loading of our class, so we set an event.
    #   self.jdwp.EventRequest.Set(
    #       jdwp_pb2.EventKind_CLASS_PREPARE,
    #       jdwp_pb2.SuspendPolicy_ALL,
    #       [{"eventKind": 5, ["com.alltheburritos.vimjdb.test.TestProgram"]]]
    #   self.jdwp.send_command_await_reply(15, 1, event_request_set_request)
    #   # send vm resume to start things off
    #   self.jdwp.send_command_await_reply(1, 9)
    #   # wait for class prepare event
    #   request_id, class_prepare_event = \
    #       self.await_event_kind(jdwp_pb2.EventKind_CLASS_PREPARE, 2)
    #   class_id = class_prepare_event[1][1][3]
    #   # get class methods
    #   err, data = self.jdwp.send_command_await_reply(2, 5, [class_id])
    #   for method in data:
    #     if method[1] == u'main':
    #       # find main method id
    #       main_method_id = method[0]
    #   # set breakpoint
    #   breakpoint_request = [
    #       jdwp_pb2.EventKind_BREAKPOINT,
    #       jdwp_pb2.SuspendPolicy_ALL,
    #       [7, [(1, class_id, main_method_id, 0)]]]
    #   err, data = self.jdwp.send_command_await_reply(15, 1, breakpoint_request)
    #   breakpoint_request_id = data[0]
    #   # send vm resume
    #   self.jdwp.send_command_await_reply(1, 9)
    #   # wait for breakpoint event
    #   request_id, breakpoint_event = \
    #       self.await_event_kind(jdwp_pb2.EventKind_BREAKPOINT, 1)
    #   expected_breakpoint_event = \
    #       [jdwp_pb2.SuspendPolicy_ALL,
    #           [jdwp_pb2.EventKind_BREAKPOINT,
    #               [breakpoint_request_id,
    #                1,  # thread_id (get programmatically?)
    #                (1, class_id, main_method_id, 0)]]]
    #   # breakpoint should look as expected
    #   self.assertEquals(breakpoint_event, expected_breakpoint_event)

#class TestDatautilsPackage(unittest.TestCase):
#
#  def pack_and_unpack_test_helper(self, fmt, byte_array, python_obj):
#    self.unpack_test_helper(fmt, byte_array, python_obj)
#    self.pack_test_helper(fmt, python_obj, byte_array)
#
#  def unpack_test_helper(self, fmt, byte_array, expected_output):
#    self.assertEquals(
#        pyjdb.serialization.from_bytearray(
#            fmt,
#            ''.join([chr(x) for x in byte_array])),
#        expected_output)
#
#  def pack_test_helper(self, fmt, data, expected_list_of_bytes):
#    self.assertEquals(
#        pyjdb.serialization.to_bytearray(
#            fmt,
#            data),
#        bytearray(expected_list_of_bytes))
#
#  def test_pack_and_unpack_string(self):
#    # string
#    fmt = "S"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x01, 0x41 ]
#    unpacked = [u'A']
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_int32(self):
#    # 32 bit integer
#    fmt = "I"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x10 ]
#    unpacked = [16]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_boolean(self):
#    # boolean
#    fmt = "bb"
#    jdwp_bytes = [ 0x00, 0x01 ]
#    unpacked = [False, True]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_byte(self):
#    # byte
#    fmt = "BB"
#    jdwp_bytes = [ 0x08, 0x10 ]
#    unpacked = [8, 16]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_int64(self):
#    # 64 bit integer
#    fmt = "LL"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
#          0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01 ]
#    unpacked = [16, 1152921504606846977]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  #def test_pack_and_unpack_tagged_value(self):
#    # value (typetag + variable-size data)
#    # TODO(implement value unpacking)
#    ###self.pack_and_unpack_test_helper("V",
#    ###    [ 0x01, 0x01 ],
#    ###    (["asdf"], 2))
#
#  def test_pack_and_unpack_tagged_object_id(self):
#    # tagged objectId ( byte + long)
#    fmt = "T"
#    jdwp_bytes = [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01 ]
#    unpacked = [(1, 1)]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_location(self):
#    # location
#    fmt = "X"
#    jdwp_bytes = [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
#          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
#          0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
#    unpacked = [(1, 1, 2, 3)]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  #def test_pack_and_unpack_array_region(self):
#    # array
#    # TODO(implement array region unpacking)
#    ###self.pack_and_unpack_test_helper("X",
#    ###    [ 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
#    ###      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
#    ###      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ],
#    ###    ([(1, 1, 2, 3)], 25))
#
#  def test_pack_and_unpack_repeat(self):
#    # repeat
#    fmt = "*(BI)"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x02, # count
#          0x01, 0x00, 0x00, 0x00, 0x07,
#          0x05, 0x10, 0x00, 0x00, 0x00 ]
#    unpacked = [[1, 7], [5, 268435456]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#  def test_pack_and_unpack_repeat_with_empty(self):
#    fmt = "IL*(SB)"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x01,  # I
#        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,  # L
#        0x00, 0x00, 0x00, 0x00 ]  # empty repeat
#    unpacked = [1, 2]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#    
#  def test_pack_and_unpack_select(self):
#    # select
#    fmt = "?B(1=IBB|2=L|3=X)"
#    jdwp_bytes = [
#          # select modifier = 1 (should be an IBB-type)
#          0x01, 0x00, 0x00, 0x00, 0x20, 0x11, 0x12 ]
#    unpacked = [1, [32, 17, 18]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#    fmt = "?B(1=IBB|2=L|3=X)"
#    jdwp_bytes = [
#          # select modifier = 2 (should be an L-type)
#          0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07 ]
#    unpacked = [2, [7]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#    fmt = "?B(1=IBB|2=L|3=X)"
#    jdwp_bytes = [
#          # select modifier = 3 (should be an X-type)
#          0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
#                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
#                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
#    unpacked = [3, [(1, 1, 2, 3)]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#    # select
#    fmt = "*(?B(1=IBB|2=L|3=X))"
#    jdwp_bytes = [ 0x00, 0x00, 0x00, 0x03,  # count = 3
#          # first select modifier = 1 (should be an IBB-type)
#          0x01, 0x00, 0x00, 0x00, 0x20, 0x11, 0x12,
#          # first select modifier = 2 (should be an L-type)
#          0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07,
#          # first select modifier = 3 (should be an X-type)
#          0x03, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
#                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02,
#                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x03 ]
#    unpacked = [[1, [32, 17, 18]], [2, [7]], [3, [(1, 1, 2, 3)]]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#    fmt = "BB*(?B(5=S))"
#    jdwp_bytes = [ 0x08, 0x02,  # BB
#        0x00, 0x00, 0x00, 0x01,
#        0x05, 0x00, 0x00, 0x00, 0x03, 0x61, 0x62, 0x63 ]
#    unpacked = [8, 2, [5, [u'abc']]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)
#
#    fmt = "BB*(?B(5=IBS))"
#    jdwp_bytes = [ 0x08, 0x02,  # BB
#        0x00, 0x00, 0x00, 0x01,
#        0x05,  # ?B
#        0x00, 0x00, 0x00, 0x07,  # I
#        0x01,  # B
#        0x00, 0x00, 0x00, 0x03, 0x61, 0x62, 0x63 ]  # S
#    unpacked = [8, 2, [5, [7, 1, u'abc']]]
#    self.pack_and_unpack_test_helper(fmt, jdwp_bytes, unpacked)

if __name__ == '__main__':
  unittest.main()
