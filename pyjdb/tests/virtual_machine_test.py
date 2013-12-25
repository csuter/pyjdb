# pylint: disable=R0904,C0111
"""Functional tests for JDWP VirtualMachine CommandSet"""
import harness
import subprocess
import string


class VirtualMachineTest(harness.TestBase):
    """Test all RPCs in VirtualMachine CommandSet"""
    def test_version(self):
        """Ensure the jdwp version matches command line java version

        The java -version output looks like
          java version "1.7.0_09"
          OpenJDK Runtime Environment .....
          OpenJDK 64-Bit Server VM (build 23.2-b09, mixed mode)"""
        system_java_version = subprocess.check_output(
            "java -version 2>&1", shell=True)
        system_version_number = string.split(
            string.split(system_java_version)[2], "\"")[1]
        version_response = self.jdwp.VirtualMachine.Version()
        jdwp_jvm_version_number = version_response["vmVersion"]
        self.assertEquals(system_version_number, jdwp_jvm_version_number)

    def test_classes_by_signature(self):
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        self.assertIn("classes", resp)
        self.assertGreater(len(resp["classes"]), 0)
        self.assertIn("status", resp["classes"][0])
        self.assertIn("typeID", resp["classes"][0])
        self.assertIn("refTypeTag", resp["classes"][0])
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"asdf1234"})
        self.assertIn("classes", resp)
        self.assertEquals(0, len(resp["classes"]))

    def test_all_classes(self):
        all_classes_response = self.jdwp.VirtualMachine.AllClasses()
        self.assertIn("classes", all_classes_response)
        string_class = [x for x in all_classes_response["classes"] if
            x["signature"] == u"Ljava/lang/String;"]
        self.assertEquals(len(string_class), 1)

    def test_all_threads(self):
        resp = self.jdwp.VirtualMachine.AllThreads()
        self.assertIn("threads", resp)
        self.assertGreater(len(resp["threads"]), 0)
        self.assertIn("thread", resp["threads"][0])
        self.assertIsInstance(resp["threads"][0]["thread"], int)

    def test_top_level_thread_groups(self):
        resp = self.jdwp.VirtualMachine.TopLevelThreadGroups()
        self.assertIn("groups", resp)
        self.assertGreater(len(resp["groups"]), 0)
        self.assertIn("group", resp["groups"][0])
        self.assertIsInstance(resp["groups"][0]["group"], int)

    def test_dispose(self):
        # TODO(cgs): test that this actually disposes?
        resp = self.jdwp.VirtualMachine.Dispose()
        self.assertIsNotNone(resp)

    def test_suspend(self):
        # TODO(cgs): test that this actually suspends?
        resp = self.jdwp.VirtualMachine.Suspend()
        self.assertIsNotNone(resp)

    def test_id_sizes(self):
        resp = self.jdwp.VirtualMachine.IDSizes()
        self.assertIn("fieldIDSize", resp)
        self.assertIn("methodIDSize", resp)
        self.assertIn("objectIDSize", resp)
        self.assertIn("referenceTypeIDSize", resp)
        self.assertIn("frameIDSize", resp)

    def test_resume(self):
        # suspend first, so it's not a noop
        self.jdwp.VirtualMachine.Suspend()
        # now resume
        resp = self.jdwp.VirtualMachine.Resume()
        self.assertIsNotNone(resp)

    def test_exit(self):
        resp = self.jdwp.VirtualMachine.Exit({
            "exitCode": 1})
        self.assertIsNotNone(resp)

    def test_create_string(self):
        resp = self.jdwp.VirtualMachine.CreateString({
            "utf": "This is a test string!"})
        self.assertIn("stringObject", resp)

    def test_capabilities(self):
        resp = self.jdwp.VirtualMachine.Capabilities()
        self.assertIn("canWatchFieldModification", resp)
        self.assertIn("canWatchFieldAccess", resp)
        self.assertIn("canGetBytecodes", resp)
        self.assertIn("canGetSyntheticAttribute", resp)
        self.assertIn("canGetOwnedMonitorInfo", resp)
        self.assertIn("canGetCurrentContendedMonitor", resp)
        self.assertIn("canGetMonitorInfo", resp)

    def test_class_paths(self):
        resp = self.jdwp.VirtualMachine.ClassPaths()
        self.assertIn("classpaths", resp)
        self.assertIn("bootclasspaths", resp)
        self.assertGreater(len(resp["classpaths"]), 0)
        self.assertGreater(len(resp["bootclasspaths"]), 0)
        self.assertIn("path", resp["classpaths"][0])
        self.assertIn("path", resp["bootclasspaths"][0])

    def test_dispose_objects(self):
        # create a string object
        resp = self.jdwp.VirtualMachine.CreateString({
            "utf": "This is a test string!"})
        string_object_id = resp["stringObject"]
        # this doesn't appear to do anything, but also doesn't throw an error.
        resp = self.jdwp.VirtualMachine.DisposeObjects({
            "requests": [{
                "object": string_object_id,
                "refCnt": 0}]})

    def test_hold_events(self):
        # TODO(cgs): make this a real test
        resp = self.jdwp.VirtualMachine.HoldEvents()
        self.assertIsNotNone(resp)

    def test_release_events(self):
        # TODO(cgs): make this a real test
        resp = self.jdwp.VirtualMachine.ReleaseEvents()
        self.assertIsNotNone(resp)

    def test_capabilities_new(self):
        resp = self.jdwp.VirtualMachine.CapabilitiesNew()
        self.assertIn("canWatchFieldModification", resp)
        self.assertIn("canWatchFieldAccess", resp)
        self.assertIn("canGetBytecodes", resp)
        self.assertIn("canGetSyntheticAttribute", resp)
        self.assertIn("canGetOwnedMonitorInfo", resp)
        self.assertIn("canGetCurrentContendedMonitor", resp)
        self.assertIn("canGetMonitorInfo", resp)
        self.assertIn("canRedefineClasses", resp)
        self.assertIn("canAddMethod", resp)
        self.assertIn("canUnrestrictedlyRedefineClasses", resp)
        self.assertIn("canPopFrames", resp)
        self.assertIn("canUseInstanceFilters", resp)
        self.assertIn("canGetSourceDebugExtension", resp)
        self.assertIn("canRequestVMDeathEvent", resp)
        self.assertIn("canSetDefaultStratum", resp)
        self.assertIn("canGetInstanceInfo", resp)
        self.assertIn("canRequestMonitorEvents", resp)
        self.assertIn("canGetMonitorFrameInfo", resp)
        self.assertIn("canUseSourceNameFilters", resp)
        self.assertIn("canGetConstantPool", resp)
        self.assertIn("canForceEarlyReturn", resp)
        self.assertIn("reserved22", resp)
        self.assertIn("reserved23", resp)
        self.assertIn("reserved24", resp)
        self.assertIn("reserved25", resp)
        self.assertIn("reserved26", resp)
        self.assertIn("reserved27", resp)
        self.assertIn("reserved28", resp)
        self.assertIn("reserved29", resp)
        self.assertIn("reserved30", resp)
        self.assertIn("reserved31", resp)
        self.assertIn("reserved32", resp)

    def test_redefine_classes(self):
        # TODO(cgs): test this (we aim eventually to be able to compile
        # arbitrary code within a hypothetical scope of the program; this would
        # be a  good place to test, say, injection of such a class. for now...
        pass

    def test_set_default_stratum(self):
        # TODO(cgs): issue filed for this; learn about strata (clj?) and figure
        # out how they would fit in here. main question: do they infiltrate
        # everything when present? probably. probably want to design things so
        # we can wrap with arbitrary strata (eventually...).
        pass

    def test_all_classes_with_generic(self):
        resp = self.jdwp.VirtualMachine.AllClassesWithGeneric()
        self.assertIsNotNone(resp)

    def test_instance_counts(self):
        pass
