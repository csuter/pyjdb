import pyjdb.internal.jdwp
import signal
import string
import subprocess
import time
import unittest

class JdwpTest(unittest.TestCase):
  def setUp(self):
    # boot up the sample java program in target jvm
    self.test_target_subprocess = subprocess.Popen([
        "java", "-cp", "fib.jar",
        "-Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005",
        "com.alltheburritos.vimjdb.test.TestProgram"])
    time.sleep(1)
    self.jdwp = pyjdb.internal.jdwp.Jdwp(5005)

  def tearDown(self):
    # disconnect debugger
    self.jdwp.Disconnect()
    # kill target jvm
    self.test_target_subprocess.send_signal(signal.SIGKILL)
    time.sleep(1)

  def test_Creation(self):
    print(self.jdwp._Jdwp__id_sizes)
    pass

  #def test_VirtualMachine_Version(self):
  #  system_java_version = subprocess.check_output(
  #      "java -version 2>&1", shell=True)
  #  # the java -version output looks like
  #  #   java version "1.7.0_09"
  #  #   OpenJDK Runtime Environment .....
  #  #   OpenJDK 64-Bit Server VM (build 23.2-b09, mixed mode)
  #  # below, the inner split splits on any whitespace - the version is the 3rd
  #  # token (the 2th, from 0). It's double-quoted so we split on double-quotes
  #  # and take the middle one.
  #  system_version_number = string.split(
  #      string.split(system_java_version)[2], "\"")[1]
  #  version_response = self.jdwp.VirtualMachine.Version()
  #  jdwp_jvm_version_number = version_response['vmVersion']
  #  # if they're equal, then we're in business!
  #  self.assertEquals(system_version_number, jdwp_jvm_version_number)

  #def test_virtual_machine__all_classes(self):
  #  all_classes_response = self.jdwp.VirtualMachine.AllClasses()
  #  self.assertTrue(all_classes_response['classes'] != None)
  #  string_class = [ x for x in all_classes_response['classes'] if
  #      x['signature'] == u'Ljava/lang/String;' ]
  #  self.assertEquals(len(string_class), 1)

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

if __name__ == '__main__':
  unittest.main()
