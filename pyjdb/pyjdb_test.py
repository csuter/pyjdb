"""Test package for pyjdb, the python java debugger library"""
import logging 
import os
import pyjdb
import signal
import socket
import subprocess
import tempfile
import time
import unittest


TEST_TMP_DIRNAME = tempfile.mkdtemp()


class PyjdbTestBase(unittest.TestCase):
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
              public static int start_n = 0;

              public static int compute(int n) {
                int sum = 0;
                for (int i = 0; i < n; i++) {
                  sum += i * i;
                }
                return sum;
              }

              public static void main(String[] args) throws Exception {
                int n = start_n;
                while (true) {
                  System.out.println(compute(n));
                  n++;
                  n %= 50;
                  Thread.sleep(1000);
                }
              }
            }
            """
            cls.debug_target_main_class = "PyjdbTest"
        test_source_filename = "%s.java" % cls.debug_target_main_class
        test_class_filename = "%s.class" % cls.debug_target_main_class
        test_source_filepath = os.path.join(TEST_TMP_DIRNAME, test_source_filename)
        test_class_filepath = os.path.join(TEST_TMP_DIRNAME, test_class_filename)
        with open(test_source_filepath, "w") as test_source_file:
            test_source_file.write(cls.debug_target_code)
        build_test_code = subprocess.check_output(
            "javac -g:source,lines,vars %s" % test_source_filepath, shell=True)

    def wait_for_server(self, host, port, max_tries=10, sleep=.1, timeout=10.0):
        start_time = time.time()
        num_tries = 0
        while num_tries < max_tries and (time.time() - start_time) < timeout:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            try:
                sock.connect((host, port))
                sock.close()
                return True
            except socket.error as e:
                pass
            num_tries += 1
            time.sleep(sleep)
        return False

    def __pick_port(self):
        port_picker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port_picker_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port_picker_socket.bind(("localhost", 0))
        port = port_picker_socket.getsockname()[1]
        port_picker_socket.close()
        return port

    def setUp(self):
        port = self.__pick_port()
        jvm_args = "-agentlib:jdwp=%s" % ",".join([
                "transport=dt_socket",
                "server=y",
                "suspend=y",
                "address=%d" % port])
        # boot up the sample java program in target jvm, redirect stdout and
        # stderr to devnull
        self.devnull = open(subprocess.os.devnull, "r")
        self.test_target_subprocess = subprocess.Popen(
            ["/usr/bin/java", "-cp", TEST_TMP_DIRNAME, jvm_args,
                    self.debug_target_main_class],
            stdout = self.devnull,
            stderr = self.devnull)
        try:
            self.wait_for_server("localhost", port)
        except socket.error as e:
            # something's wrong; let's try to kill the target jvm (tearDown
            # won't be called if we fail) and bail.
            self.test_target_subprocess.send_signal(signal.SIGKILL)
            raise e
        self.pyjdb = pyjdb.Pyjdb("localhost", port)
        self.pyjdb.initialize();

    def tearDown(self):
        # disconnect debugger
        self.pyjdb.disconnect()
        # kill target jvm
        self.test_target_subprocess.send_signal(signal.SIGKILL)
        self.test_target_subprocess.wait()
        self.devnull.close()

    def test_set_breakpoint_at_line(self):
        self.pyjdb.set_breakpoint_at_line("PyjdbTest.java", 49)
        self.pyjdb.run_to_breakpoint()

    #def test_set_method_breakpoint(self):
    #    self.pyjdb.set_method_breakpoint("PyjdbTest", "compute")
    #    self.pyjdb.resume_vm()

if __name__ == "__main__":
    unittest.main()
