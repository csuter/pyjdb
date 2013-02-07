import jdwp2
import signal
import string
import subprocess
import time
import unittest

__JDWP_SPEC_FILE__="build-gen/jdwprpc/codegen/jdwp_spec.txt"
with open(__JDWP_SPEC_FILE__, "r") as f: __JDWP_SPEC_TEXT__ = f.read()

class TestJdwp2Package(unittest.TestCase):
  def setUp(self):
    # boot up the sample java program in target jvm
    test_target_script = "build-bin/sample/run.sh"
    self.test_target_subprocess = subprocess.Popen(test_target_script)
    time.sleep(1)
    self.jdwp = jdwp2.Jdwp(5005, __JDWP_SPEC_TEXT__)

  def tearDown(self):
    # disconnect debugger
    self.jdwp.disconnect()
    # kill target jvm
    self.test_target_subprocess.send_signal(signal.SIGKILL)

  def test_virtual_machine__version(self):
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
    print("all classes:\n%s" % all_classes_response)

if __name__ == '__main__':
  unittest.main()

