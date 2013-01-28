"""Unit tests for jdwp package"""

import os
import jdwp_pb2
import signal
import string
import subprocess
import time
import unittest

import pprint

from jdwp import *

class TestJdwpPackage(unittest.TestCase):
  def setUp(self):
    # boot up the sample java program in target jvm
    test_target_script = "build-bin/sample/run.sh"
    self.test_target_subprocess = subprocess.Popen(test_target_script)
    time.sleep(1)

    # start up a jdwp connection
    self.jdwp = Jdwp(5005, self.event_callback)
  
  def event_callback(self, event):
    #print("EVENT: %s" % event)
    return

  def tearDown(self):
    # kill target jvm
    self.jdwp.disconnect()
    self.test_target_subprocess.send_signal(signal.SIGKILL)

  def await_event_kind(self, event_kind, timeout = 0):
    start = time.time()
    while True:
      if timeout > 0 and time.time() - start > timeout:
        raise Exception("Timed out")
      for event in self.jdwp.events:
        if event[1][0] == event_kind:
          return event
      time.sleep(.05)

  def test_creation(self):
    # make sure jdwp object was created
    self.assertTrue(self.jdwp != None)
    tries = 3
    num_true = 0
    vm_start_event_unpacked = [2, [90, [0, 1]]]
    while tries > 0:
      num_true += vm_start_event_unpacked in self.jdwp.events
      time.sleep(.1)
      tries -= 1
    # make sure jdwp vm_start event was sent
    self.assertGreater(num_true, 0)

  def test_version(self):
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

    # in the jdwp version output, the 4th element (3th, from 0) is the version
    # number string (ie 1.7.0_05)
    err, jdwp_jvm_version_info = self.jdwp.send_command_await_reply(1, 1, [])
    jdwp_jvm_version_number = jdwp_jvm_version_info[3]

    # if they're equal, then we're in business!
    self.assertEquals(system_version_number, jdwp_jvm_version_number)


  def test_event_request_set_and_resume(self):
    # in this test we will
    #   1. get a list of all loaded classes
    #   2. request notification of class load events
    #   3. resume our suspended program
    #   4. assert that com.alltheburritos.defbug.test.TestProgram gets loaded

    # CommandSet 1 - VirtualMachine
    #  Command 3 - AllClasses
    err, all_classes = self.jdwp.send_command_await_reply(1, 3)
    loaded_classnames = [ entry[2] for entry in all_classes ]

    # CommandSet 15 - EventRequest
    #  Command 1 - Set
    event_request_set_request = \
        [ jdwp_pb2.EventKind_CLASS_PREPARE, jdwp_pb2.SuspendPolicy_NONE, []]
    self.jdwp.send_command_no_wait(15, 1, event_request_set_request)

    # CommandSet 1 - VirtualMachine
    #  Command 4 - AllThreads
    err, thread_ids = self.jdwp.send_command_await_reply(1, 4)
    # CommandSet 11 - ThreadReference
    #  Command 3 - Resume
    for thread_id in thread_ids:
      self.jdwp.send_command_no_wait(11, 3, thread_id)

    time.sleep(.1)

    self.assertTrue(
        "Lcom/alltheburritos/vimjdb/test/TestProgram;" in \
        [ event[1][1][4] for event in self.jdwp.events if event[1][0] == 8 ])

  def test_set_breakpoint(self):
    event_request_set_request = [
        jdwp_pb2.EventKind_CLASS_PREPARE,
        jdwp_pb2.SuspendPolicy_ALL,
        [[5, "com.alltheburritos.vimjdb.test.TestProgram"]] ]

    err, data = self.jdwp.send_command_await_reply(
        15, 1, event_request_set_request)
    #print("err, data: ", err, data)

    err, data = self.jdwp.send_command_await_reply(1, 9)
    #print("err, data: ", err, data)

    class_prepare_event = \
        self.await_event_kind(jdwp_pb2.EventKind_CLASS_PREPARE)
    class_id = class_prepare_event[1][1][3]

    methods_request = [ class_id ]
    err, data = self.jdwp.send_command_await_reply(
        2, 5, methods_request)
    #print("err, data: ", err, data)

    for method in data:
      if method[1] == u'main':
        main_method_id = method[0]

    event_request_set_request = [
        jdwp_pb2.EventKind_BREAKPOINT,
        jdwp_pb2.SuspendPolicy_ALL,
        [[7, [1, class_id, main_method_id, 0]]]]
    err, data = self.jdwp.send_command_await_reply(
        15, 1, event_request_set_request)
    #print("err, data: ", err, data)
    breakpoint_request_id = data[0]

    err, data = self.jdwp.send_command_await_reply(1, 9)
    #print("err, data: ", err, data)

    breakpoint_event = \
        self.await_event_kind(jdwp_pb2.EventKind_BREAKPOINT, 1)
    self.assertEquals(
        breakpoint_event,
        [jdwp_pb2.SuspendPolicy_ALL, [jdwp_pb2.EventKind_BREAKPOINT,
            [breakpoint_request_id,
             1,  # thread_id
             (1,  # type_tag class
              class_id,
              main_method_id,
              0)]]]  # index 0 (start of method)
        )

    #print(breakpoint_event)


if __name__ == '__main__':
  unittest.main()
