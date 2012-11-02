"""Unit tests for jdwp package"""

import os
import jdwp_pb2
import signal
import string
import subprocess
import time
import unittest

from jdwp import *

class TestJdwpPackage(unittest.TestCase):
  def setUp(self):
    # boot up the sample java program in target jvm
    test_target_script = "build-bin/sample/run.sh 2>&1 >/dev/null"
    self.test_target_subprocess = subprocess.Popen(test_target_script, shell=True)
    time.sleep(1)

    # start up a jdwp connection
    self.jdwp = Jdwp(5005, self.event_callback)
  
  def event_callback(self, event):
    None

  def tearDown(self):
    # kill target jvm
    self.jdwp.disconnect()
    self.test_target_subprocess.send_signal(signal.SIGTERM)

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
    err, event_request_set_response = \
        self.jdwp.send_command_await_reply(15, 1, event_request_set_request)

    # CommandSet 1 - VirtualMachine
    #  Command 4 - AllClasses
    err, thread_ids = self.jdwp.send_command_await_reply(1, 4)
    # CommandSet 11 - ThreadReference
    #  Command 1 - Name
    #  Command 3 - Resume
    for thread_id in thread_ids:
      self.jdwp.send_command_no_wait(11, 3, thread_id)

    time.sleep(.1)

    self.assertTrue(
        "Lcom/alltheburritos/vimjdb/test/TestProgram;" in \
        [ event[1][1][4] for event in self.jdwp.events if event[1][0] == 8 ])

if __name__ == '__main__':
  unittest.main()