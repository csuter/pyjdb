import os
import pyjdb
import signal
import string
import subprocess
import time
import unittest

class TestPyjdbPackage(unittest.TestCase):
    def setUp(self):
        # boot up the sample java program in target jvm
        self.devnull = open(subprocess.os.devnull, "r")
        self.test_target_subprocess = subprocess.Popen([
            "/usr/bin/java", "-cp", "java_sample/fib.jar",
            "-Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005",
            "com.alltheburritos.vimjdb.test.TestProgram"],
            stdout=self.devnull, stderr=self.devnull)
        self.test_class = "com.alltheburritos.vimjdb.test.TestProgram"
        self.test_sig = u"Lcom/alltheburritos/vimjdb/test/TestProgram;"
        self.jdwp = pyjdb.Jdwp("localhost", 5005)
        self.jdwp.initialize();

    def tearDown(self):
        # disconnect debugger
        self.jdwp.disconnect()
        # kill target jvm
        self.test_target_subprocess.send_signal(signal.SIGKILL)
        self.test_target_subprocess.wait()
        self.devnull.close()

    def test_virtual_machine_version(self):
        system_java_version = subprocess.check_output(
            "java -version 2>&1", shell=True)
        # the java -version output looks like
        #   java version "1.7.0_09"
        #   OpenJDK Runtime Environment .....
        #   OpenJDK 64-Bit Server VM (build 23.2-b09, mixed mode)
        # below, the inner split splits on any whitespace - the version is the 3rd
        # token (the 2th, from 0). It"s double-quoted so we split on double-quotes
        # and take the middle one.
        system_version_number = string.split(
            string.split(system_java_version)[2], "\"")[1]
        version_response = self.jdwp.VirtualMachine.Version()
        jdwp_jvm_version_number = version_response["vmVersion"]
        # if they"re equal, then we"re in business!
        self.assertEquals(system_version_number, jdwp_jvm_version_number)

    def test_virtual_machine_classes_by_signature(self):
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        # {'classes': [{'status': 7, 'typeID': 2, 'refTypeTag': 1}]}
        self.assertTrue("classes" in resp)
        self.assertTrue(len(resp["classes"]) > 0)
        self.assertTrue("status" in resp["classes"][0])
        self.assertTrue("typeID" in resp["classes"][0])
        self.assertTrue("refTypeTag" in resp["classes"][0])
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"asdf1234"})
        self.assertTrue("classes" in resp)
        self.assertEquals(0, len(resp["classes"]))

    def test_virtual_machine_all_classes(self):
        all_classes_response = self.jdwp.VirtualMachine.AllClasses()
        self.assertTrue(all_classes_response["classes"] != None)
        string_class = [ x for x in all_classes_response["classes"] if
            x["signature"] == u"Ljava/lang/String;" ]
        self.assertEquals(len(string_class), 1)

    def test_virtual_machine_all_threads(self):
        resp = self.jdwp.VirtualMachine.AllThreads()
        self.assertTrue("threads" in resp)
        self.assertTrue(len(resp["threads"]) > 0)
        self.assertTrue("thread" in resp["threads"][0])
        self.assertTrue(isinstance(resp["threads"][0]["thread"], int))

    def test_virtual_machine_top_level_thread_groups(self):
        resp = self.jdwp.VirtualMachine.TopLevelThreadGroups()
        self.assertTrue("groups" in resp)
        self.assertTrue(len(resp["groups"]) > 0)
        self.assertTrue("group" in resp["groups"][0])
        self.assertTrue(isinstance(resp["groups"][0]["group"], int))

    def test_virtual_machine_dispose(self):
        # TODO(cgs): test that this actually disposes?
        resp = self.jdwp.VirtualMachine.Dispose()
        self.assertIsNotNone(resp)

    def test_virtual_machine_suspend(self):
        # TODO(cgs): test that this actually suspends?
        resp = self.jdwp.VirtualMachine.Suspend()
        self.assertIsNotNone(resp)

    def test_virtual_machine_id_sizes(self):
        resp = self.jdwp.VirtualMachine.IDSizes()
        self.assertTrue("fieldIDSize" in resp)
        self.assertTrue("methodIDSize" in resp)
        self.assertTrue("objectIDSize" in resp)
        self.assertTrue("referenceTypeIDSize" in resp)
        self.assertTrue("frameIDSize" in resp)

    def test_virtual_machine_suspend(self):
        resp = self.jdwp.VirtualMachine.Suspend()
        self.assertIsNotNone(resp)

    def test_virtual_machine_resume(self):
        # suspend first, so it's not a noop
        self.jdwp.VirtualMachine.Suspend()
        # now resume
        resp = self.jdwp.VirtualMachine.Resume()
        self.assertIsNotNone(resp)

    def test_virtual_machine_exit(self):
        resp = self.jdwp.VirtualMachine.Exit({
            "exitCode": 1})
        self.assertIsNotNone(resp)

    def test_virtual_machine_create_string(self):
        resp = self.jdwp.VirtualMachine.CreateString({
            "utf": "This is a test string!"})
        self.assertTrue("stringObject" in resp)

    def test_virtual_machine_capabilities(self):
        resp = self.jdwp.VirtualMachine.Capabilities()
        self.assertTrue("canWatchFieldModification" in resp)
        self.assertTrue("canWatchFieldAccess" in resp)
        self.assertTrue("canGetBytecodes" in resp)
        self.assertTrue("canGetSyntheticAttribute" in resp)
        self.assertTrue("canGetOwnedMonitorInfo" in resp)
        self.assertTrue("canGetCurrentContendedMonitor" in resp)
        self.assertTrue("canGetMonitorInfo" in resp)

    def test_virtual_machine_class_paths(self):
        resp = self.jdwp.VirtualMachine.ClassPaths()
        self.assertTrue("classpaths" in resp)
        self.assertTrue("bootclasspaths" in resp)
        self.assertTrue(len(resp["classpaths"]) > 0)
        self.assertTrue(len(resp["bootclasspaths"]) > 0)
        self.assertTrue("path" in resp["classpaths"][0])
        self.assertTrue("path" in resp["bootclasspaths"][0])

    def test_virtual_machine_dispose_objects(self):
        # create a string object
        resp = self.jdwp.VirtualMachine.CreateString({
            "utf": "This is a test string!"})
        string_object_id = resp["stringObject"]
        # this doesn't appear to do anything, but also doesn't throw an error.
        resp = self.jdwp.VirtualMachine.DisposeObjects({
            "requests": [{
                "object": string_object_id,
                "refCnt": 0}]})

    def test_virtual_machine_hold_events(self):
        # TODO(cgs): make this a real test
        resp = self.jdwp.VirtualMachine.HoldEvents()
        self.assertIsNotNone(resp)

    def test_virtual_machine_release_events(self):
        # TODO(cgs): make this a real test
        resp = self.jdwp.VirtualMachine.ReleaseEvents()
        self.assertIsNotNone(resp)

    def test_virtual_machine_capabilities_new(self):
        resp = self.jdwp.VirtualMachine.CapabilitiesNew()
        self.assertTrue("canWatchFieldModification" in resp)
        self.assertTrue("canWatchFieldAccess" in resp)
        self.assertTrue("canGetBytecodes" in resp)
        self.assertTrue("canGetSyntheticAttribute" in resp)
        self.assertTrue("canGetOwnedMonitorInfo" in resp)
        self.assertTrue("canGetCurrentContendedMonitor" in resp)
        self.assertTrue("canGetMonitorInfo" in resp)
        self.assertTrue("canRedefineClasses" in resp)
        self.assertTrue("canAddMethod" in resp)
        self.assertTrue("canUnrestrictedlyRedefineClasses" in resp)
        self.assertTrue("canPopFrames" in resp)
        self.assertTrue("canUseInstanceFilters" in resp)
        self.assertTrue("canGetSourceDebugExtension" in resp)
        self.assertTrue("canRequestVMDeathEvent" in resp)
        self.assertTrue("canSetDefaultStratum" in resp)
        self.assertTrue("canGetInstanceInfo" in resp)
        self.assertTrue("canRequestMonitorEvents" in resp)
        self.assertTrue("canGetMonitorFrameInfo" in resp)
        self.assertTrue("canUseSourceNameFilters" in resp)
        self.assertTrue("canGetConstantPool" in resp)
        self.assertTrue("canForceEarlyReturn" in resp)
        self.assertTrue("reserved22" in resp)
        self.assertTrue("reserved23" in resp)
        self.assertTrue("reserved24" in resp)
        self.assertTrue("reserved25" in resp)
        self.assertTrue("reserved26" in resp)
        self.assertTrue("reserved27" in resp)
        self.assertTrue("reserved28" in resp)
        self.assertTrue("reserved29" in resp)
        self.assertTrue("reserved30" in resp)
        self.assertTrue("reserved31" in resp)
        self.assertTrue("reserved32" in resp)

    def test_virtual_machine_redefine_classes(self):
        # TODO(cgs): test this (we aim eventually to be able to compile
        # arbitrary code within a hypothetical scope of the program; this would
        # be a  good place to test, say, injection of such a class. for now...
        pass

    def test_virtual_machine_set_default_stratum(self):
        # TODO(cgs): issue filed for this; learn about strata (clj?) and figure
        # out how they would fit in here. main question: do they infiltrate
        # everything when present? probably. probably want to design things so
        # we can wrap with arbitrary strata (eventually...).
        pass

    def test_virtual_machine_all_classes_with_generic(self):
        resp = self.jdwp.VirtualMachine.AllClassesWithGeneric()
        print(resp)
        pass

    def test_virtual_machine_instance_counts(self):
        pass

    def test_reference_type_signature(self):
        pass

    def test_reference_type_class_loader(self):
        pass

    def test_reference_type_modifiers(self):
        pass

    def test_reference_type_fields(self):
        pass

    def test_reference_type_methods(self):
        pass

    def test_reference_type_get_values(self):
        pass

    def test_reference_type_source_file(self):
        pass

    def test_reference_type_nested_types(self):
        pass

    def test_reference_type_status(self):
        pass

    def test_reference_type_interfaces(self):
        pass

    def test_reference_type_class_object(self):
        pass

    def test_reference_type_source_debug_extension(self):
        pass

    def test_reference_type_signature_with_generic(self):
        pass

    def test_reference_type_fields_with_generic(self):
        pass

    def test_reference_type_methods_with_generic(self):
        pass

    def test_reference_type_instances(self):
        pass

    def test_reference_type_class_file_version(self):
        pass

    def test_reference_type_constant_pool(self):
        pass

    def test_class_type_superclass(self):
        pass

    def test_class_type_set_values(self):
        pass

    def test_class_type_invoke_method(self):
        pass

    def test_class_type_new_instance(self):
        pass

    def test_array_type_new_instance(self):
        pass

    def test_method_line_table(self):
        pass

    def test_method_variable_table(self):
        pass

    def test_method_bytecodes(self):
        pass

    def test_method_is_obsolete(self):
        pass

    def test_method_variable_table_with_generic(self):
        pass

    def test_object_reference_reference_type(self):
        pass

    def test_object_reference_get_values(self):
        pass

    def test_object_reference_set_values(self):
        pass

    def test_object_reference_monitor_info(self):
        pass

    def test_object_reference_invoke_method(self):
        pass

    def test_object_reference_disable_collection(self):
        pass

    def test_object_reference_enable_collection(self):
        pass

    def test_object_reference_is_collected(self):
        pass

    def test_object_reference_referring_objects(self):
        pass

    def test_string_reference_value(self):
        pass

    def test_thread_reference_name(self):
        pass

    def test_thread_reference_suspend(self):
        pass

    def test_thread_reference_resume(self):
        pass

    def test_thread_reference_status(self):
        pass

    def test_thread_reference_thread_group(self):
        pass

    def test_thread_reference_frames(self):
        pass

    def test_thread_reference_frame_count(self):
        pass

    def test_thread_reference_owned_monitors(self):
        pass

    def test_thread_reference_current_contended_monitor(self):
        pass

    def test_thread_reference_stop(self):
        pass

    def test_thread_reference_interrupt(self):
        pass

    def test_thread_reference_suspend_count(self):
        pass

    def test_thread_reference_owned_monitors_stack_depth_info(self):
        pass

    def test_thread_reference_force_early_return(self):
        pass

    def test_thread_group_reference_name(self):
        pass

    def test_thread_group_reference_parent(self):
        pass

    def test_thread_group_reference_children(self):
        pass

    def test_array_reference_length(self):
        pass

    def test_array_reference_get_values(self):
        pass

    def test_array_reference_set_values(self):
        pass

    def test_class_loader_reference_visible_classes(self):
        pass

    def test_event_request_set(self):
        pass

    def test_event_request_clear(self):
        pass

    def test_event_request_clear_all_breakpoints(self):
        pass

    def test_stack_frame_get_values(self):
        pass

    def test_stack_frame_set_values(self):
        pass

    def test_stack_frame_this_object(self):
        pass

    def test_stack_frame_pop_frames	(self):
        pass

    def test_class_object_reference_reflected_type(self):
        pass

    def test_event_composite(self):
        pass

if __name__ == "__main__":
  unittest.main()
