# pylint: disable=R0904
"""Test harness for jdwp functional tests"""
import atexit
from pyjdb import pyjdb
import os
import signal
import socket
import subprocess
import tempfile
import unittest


TEST_TMP_DIRNAME = tempfile.mkdtemp()

class TestBase(unittest.TestCase):
    """Base class for pyjdb package tests.

    Handles the work of compiling the test code once for each test class, and
    starting the java process for each test case. Namely, each test class
    derives from PyjdbTestBase. PyjdbTestBase has a default implementation of
    the TestCase @classmethod setUpClass() that creates a default sample test
    java class definition, writes it to a file, and calls javac on it. The
    setUp method then starts a jvm in debug mode running the test code once for
    each test method.

    Subclasses of PyjdbTestBase may override setUpClass and redefine
    'debug_target_code' (the java code to compile and debug) and
    'debug_target_main_class' (a class containing a public static void main
    method in the test java code) to fit the needs of a particular test case.
    """

    @classmethod
    def setUpClass(cls):
        if not hasattr(cls, "debug_target_code"):
            cls.debug_target_code = """
            public class PyjdbTest {
              public static void main(String[] args) throws Exception {
                while (true) {
                  Thread.sleep(1000);
                }
              }
            }
            """
            cls.debug_target_main_class = "PyjdbTest"
        test_source_filename = "%s.java" % cls.debug_target_main_class
        test_source_filepath = os.path.join(
            TEST_TMP_DIRNAME, test_source_filename)
        with open(test_source_filepath, "w") as test_source_file:
            test_source_file.write(cls.debug_target_code)
        subprocess.check_output(
            "javac -g:source,lines,vars %s" % test_source_filepath, shell=True)

    def __pick_port(self):
        port_picker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port_picker_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port_picker_socket.bind(("localhost", 0))
        port = port_picker_socket.getsockname()[1]
        port_picker_socket.close()
        return port

    def setUp(self):
        # boot up the sample java program in target jvm
        self.devnull = open(subprocess.os.devnull, "r")
        port = 5005
        #port = self.__pick_port()
        self.test_target_subprocess = subprocess.Popen([
            "/usr/bin/java", "-cp", TEST_TMP_DIRNAME,
            "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=%d" % port,
            self.debug_target_main_class],
            stdout=self.devnull, stderr=self.devnull)
        self.jdwp = pyjdb.Jdwp("localhost", port)
        try:
            self.jdwp.initialize()
        except pyjdb.Error as e:
            self.test_target_subprocess.send_signal(signal.SIGKILL)
            self.test_target_subprocess.wait()
            self.devnull.close()
            raise e

    def tearDown(self):
        self.jdwp.disconnect()
        self.test_target_subprocess.send_signal(signal.SIGKILL)
        self.test_target_subprocess.wait()
        self.devnull.close()

    def resume_and_await_class_load(self, class_name, suspend_policy=None):
        """Wait for specified java class to be loaded.

        This will call jdwp.EventRequest.Set to listen for CLASS_PREPARE
        events matching the given class_name. It then Resume()s the target JVM
        and waits for the event to arrive. The method will timeout according
        to the configuration of the jdwp instance."""
        if suspend_policy is None:
            suspend_policy = self.jdwp.SuspendPolicy.NONE
        signature = "L%s;" % class_name
        self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": suspend_policy,
                "modifiers": [{
                        "modKind": 5,
                        "classPattern": class_name}]})
        self.jdwp.VirtualMachine.Resume()
        # TODO(cgs): make a matcher maker
        def matcher(event_raw):
            """Match events with the right signature"""
            _, event_data = event_raw
            for event in event_data["events"]:
                if event["eventKind"] == self.jdwp.EventKind.CLASS_PREPARE:
                    if event["ClassPrepare"]["signature"] == signature:
                        return True
            return False
        _, test_class_prepare_event = self.jdwp.await_event(matcher)
        return test_class_prepare_event["events"][0]["ClassPrepare"]

    def set_breakpoint_in_method(self, class_name, method_name):
        """Set a method breakpoint. Assumes JVM has not been Resume()d yet"""
        self.resume_and_await_class_load(
                class_name, self.jdwp.SuspendPolicy.ALL)
        signature = "L%s;" % class_name
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": signature})
        class_id = resp["classes"][0]["typeID"]
        resp = self.jdwp.ReferenceType.Methods({"refType": class_id})
        methods_by_name = dict([(method["name"], method) for method in
                resp["declared"]])
        method = methods_by_name[method_name]
        resp = self.jdwp.Method.LineTable({
                "refType": class_id,
                "methodID": method["methodID"]})
        initial_index = resp["lines"][0]["lineCodeIndex"]
        resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.BREAKPOINT,
                "suspendPolicy": self.jdwp.SuspendPolicy.ALL,
                "modifiers": [{
                        "modKind": 7,
                        "typeTag": self.jdwp.TypeTag.CLASS,
                        "classID": class_id,
                        "methodID": method["methodID"],
                        "index": initial_index}]})
        def matcher(event_raw):
            """Match breakpoint event"""
            _, event = event_raw
            for event in event["events"]:
                if event["eventKind"] == self.jdwp.EventKind.BREAKPOINT:
                    return True
        self.jdwp.VirtualMachine.Resume()
        _, breakpoint_events = self.jdwp.await_event(matcher)
        return breakpoint_events["events"][0]["Breakpoint"]

    def set_breakpoint_in_main(self, main_class_name):
        """Set breakpoint in given class's main method

        See notes on set_breakpoint_in_method."""
        return self.set_breakpoint_in_method(main_class_name, "main")
