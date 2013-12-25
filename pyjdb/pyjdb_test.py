import logging 
import os
import pyjdb
import signal
import string
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
              public static void main(String[] args) throws Exception {
                while (true) {
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

    def setUp(self):
        # boot up the sample java program in target jvm
        self.devnull = open(subprocess.os.devnull, "r")
        self.test_target_subprocess = subprocess.Popen([
            "/usr/bin/java", "-cp", TEST_TMP_DIRNAME,
            "-Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005",
            self.debug_target_main_class],
            stdout = self.devnull, stderr = self.devnull)
        self.jdwp = pyjdb.Jdwp("localhost", 5005)
        self.jdwp.initialize();

    def tearDown(self):
        # disconnect debugger
        self.jdwp.disconnect()
        # kill target jvm
        self.test_target_subprocess.send_signal(signal.SIGKILL)
        self.test_target_subprocess.wait()
        self.devnull.close()

    def resume_and_await_class_load(self, class_name, suspend_policy = None):
        if not suspend_policy:
            suspend_policy = self.jdwp.SuspendPolicy.NONE
        signature = "L%s;" % class_name
        event_req_set_resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": suspend_policy,
                "modifiers": [{
                        "modKind": 5,
                        "classPattern": class_name}]})
        self.jdwp.VirtualMachine.Resume()
        def matcher(event_raw):
            req_id, event_data = event_raw
            for event in event_data["events"]:
                if event["eventKind"] == self.jdwp.EventKind.CLASS_PREPARE:
                    if event["ClassPrepare"]["signature"] == signature:
                        return True
            return False
        _, test_class_prepare_event = self.jdwp.await_event(matcher)
        class_prepare_event = test_class_prepare_event["events"][0]["ClassPrepare"]

    def set_breakpoint_in_main(self, main_class_name):
        self.resume_and_await_class_load(main_class_name, self.jdwp.SuspendPolicy.ALL)
        signature = "L%s;" % main_class_name
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": "L%s;" % main_class_name})
        main_class_id = resp["classes"][0]["typeID"]
        resp = self.jdwp.ReferenceType.Methods({"refType": main_class_id})
        methods_by_name = dict([(method["name"], method) for method in
                resp["declared"]])
        main_method = methods_by_name["main"]
        resp = self.jdwp.Method.LineTable({
                "refType": main_class_id,
                "methodID": main_method["methodID"]})
        initial_index = resp["lines"][0]["lineCodeIndex"]
        resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.BREAKPOINT,
                "suspendPolicy": self.jdwp.SuspendPolicy.ALL,
                "modifiers": [{
                        "modKind": 7,
                        "typeTag": self.jdwp.TypeTag.CLASS,
                        "classID": main_class_id,
                        "methodID": main_method["methodID"],
                        "index": initial_index}]})
        def matcher(event_raw):
            _, event = event_raw
            for event in event["events"]:
                if event["eventKind"] == self.jdwp.EventKind.BREAKPOINT:
                    return True
        self.jdwp.VirtualMachine.Resume()
        _, breakpoint_events = self.jdwp.await_event(matcher)
        return breakpoint_events

    def test_resume_and_await_class_load(self):
        self.resume_and_await_class_load("PyjdbTest")

    def test_set_breakpoint_in_main(self):
        breakpoint_events = self.set_breakpoint_in_main("PyjdbTest")
        self.assertIn("events", breakpoint_events)
        self.assertIn("suspendPolicy", breakpoint_events)
        self.assertEquals(len(breakpoint_events["events"]), 1)
        self.assertIn("Breakpoint", breakpoint_events["events"][0])
        breakpoint_event = breakpoint_events["events"][0]["Breakpoint"]
        self.assertIn("classID", breakpoint_event)
        self.assertIn("index", breakpoint_event)
        self.assertIn("methodID", breakpoint_event)
        self.assertIn("thread", breakpoint_event)
        self.assertIn("requestID", breakpoint_event)
        self.assertIn("typeTag", breakpoint_event)


class VirtualMachineTest(PyjdbTestBase):
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
        self.assertIn("classes", resp)
        self.assertGreater(len(resp["classes"]), 0)
        self.assertIn("status", resp["classes"][0])
        self.assertIn("typeID", resp["classes"][0])
        self.assertIn("refTypeTag", resp["classes"][0])
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"asdf1234"})
        self.assertIn("classes", resp)
        self.assertEquals(0, len(resp["classes"]))

    def test_virtual_machine_all_classes(self):
        all_classes_response = self.jdwp.VirtualMachine.AllClasses()
        self.assertIn("classes", all_classes_response)
        string_class = [ x for x in all_classes_response["classes"] if
            x["signature"] == u"Ljava/lang/String;" ]
        self.assertEquals(len(string_class), 1)

    def test_virtual_machine_all_threads(self):
        resp = self.jdwp.VirtualMachine.AllThreads()
        self.assertIn("threads", resp)
        self.assertGreater(len(resp["threads"]), 0)
        self.assertIn("thread", resp["threads"][0])
        self.assertIsInstance(resp["threads"][0]["thread"], int)

    def test_virtual_machine_top_level_thread_groups(self):
        resp = self.jdwp.VirtualMachine.TopLevelThreadGroups()
        self.assertIn("groups", resp)
        self.assertGreater(len(resp["groups"]), 0)
        self.assertIn("group", resp["groups"][0])
        self.assertIsInstance(resp["groups"][0]["group"], int)

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
        self.assertIn("fieldIDSize", resp)
        self.assertIn("methodIDSize", resp)
        self.assertIn("objectIDSize", resp)
        self.assertIn("referenceTypeIDSize", resp)
        self.assertIn("frameIDSize", resp)

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
        self.assertIn("stringObject", resp)

    def test_virtual_machine_capabilities(self):
        resp = self.jdwp.VirtualMachine.Capabilities()
        self.assertIn("canWatchFieldModification", resp)
        self.assertIn("canWatchFieldAccess", resp)
        self.assertIn("canGetBytecodes", resp)
        self.assertIn("canGetSyntheticAttribute", resp)
        self.assertIn("canGetOwnedMonitorInfo", resp)
        self.assertIn("canGetCurrentContendedMonitor", resp)
        self.assertIn("canGetMonitorInfo", resp)

    def test_virtual_machine_class_paths(self):
        resp = self.jdwp.VirtualMachine.ClassPaths()
        self.assertIn("classpaths", resp)
        self.assertIn("bootclasspaths", resp)
        self.assertGreater(len(resp["classpaths"]), 0)
        self.assertGreater(len(resp["bootclasspaths"]), 0)
        self.assertIn("path", resp["classpaths"][0])
        self.assertIn("path", resp["bootclasspaths"][0])

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
        self.assertIsNotNone(resp)
        pass

    def test_virtual_machine_instance_counts(self):
        pass


class ReferenceTypeTest(PyjdbTestBase):
    def setUp(self):
        super(ReferenceTypeTest, self).setUp()
        self.string_class_signature = u"Ljava/lang/String;"
        self.string_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": self.string_class_signature})["classes"][0]["typeID"]
        self.integer_class_signature = u"Ljava/lang/Integer;"
        self.integer_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": self.integer_class_signature})["classes"][0]["typeID"]
        self.thread_class_signature = u"Ljava/lang/Thread;"
        self.thread_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": self.thread_class_signature})["classes"][0]["typeID"]
        self.array_list_class_signature = u"Ljava/util/ArrayList;"
        self.array_list_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": self.array_list_class_signature})["classes"][0]["typeID"]

    def test_reference_type_signature(self):
        resp = self.jdwp.ReferenceType.Signature({
            "refType": self.string_class_id})
        self.assertEquals(self.string_class_signature, resp["signature"])

    def test_reference_type_class_loader(self):
        resp = self.jdwp.ReferenceType.ClassLoader({
            "refType": self.string_class_id})
        self.assertIn("classLoader", resp)

    def test_reference_type_modifiers(self):
        resp = self.jdwp.ReferenceType.Modifiers({
            "refType": self.string_class_id})
        self.assertIn("modBits", resp)

    def test_reference_type_fields(self):
        resp = self.jdwp.ReferenceType.Fields({"refType": self.string_class_id})
        self.assertIn("declared", resp)
        self.assertGreater(len(resp["declared"]), 0)
        field_entry = resp["declared"][0]
        self.assertIn("modBits", field_entry)
        self.assertIn("fieldID", field_entry)
        self.assertIn("name", field_entry)
        self.assertIn("signature", field_entry)

    def test_reference_type_methods(self):
        resp = self.jdwp.ReferenceType.Methods({
            "refType": self.string_class_id})
        self.assertIn("declared", resp)
        self.assertGreater(len(resp["declared"]), 0)
        method_entry = resp["declared"][0]
        self.assertIn("modBits", method_entry)
        self.assertIn("methodID", method_entry)
        self.assertIn("name", method_entry)
        self.assertIn("signature", method_entry)

    def test_reference_type_get_values(self):
        # TODO(cgs): add more value types; verify edge cases of signed/unsigned
        # integer types, etc.
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.integer_class_id})
        fields_by_name = dict([(field["name"], field) for field in
                fields_resp["declared"]])
        field_ids = [fields_by_name["MIN_VALUE"], fields_by_name["MAX_VALUE"]]
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": self.integer_class_id,
            "fields": field_ids})
        values = [entry["value"] for entry in get_values_resp["values"]]
        self.assertIn(-2147483648, values)
        self.assertIn(2147483647, values)

    def test_reference_type_source_file(self):
        source_file_resp = self.jdwp.ReferenceType.SourceFile({
                "refType": self.integer_class_id})
        self.assertEquals("Integer.java", source_file_resp["sourceFile"])

    def test_reference_type_nested_types(self):
        nested_types_resp = self.jdwp.ReferenceType.NestedTypes({
                "refType": self.thread_class_id})
        self.assertIn("classes", nested_types_resp)
        self.assertGreater(len(nested_types_resp["classes"]), 0)
        cls = nested_types_resp["classes"][0]
        self.assertIn("typeID", cls)
        self.assertIn("refTypeTag", cls)

    def test_reference_type_status(self):
        status_resp = self.jdwp.ReferenceType.Status({
                "refType": self.thread_class_id})
        self.assertIn("status", status_resp)
        self.assertIsInstance(status_resp["status"], int)

    def test_reference_type_interfaces(self):
        interfaces_resp = self.jdwp.ReferenceType.Interfaces({
            "refType": self.thread_class_id})
        signatures = []
        for interface in interfaces_resp["interfaces"]:
            ref_type_signature = self.jdwp.ReferenceType.Signature({
                "refType": interface["interfaceType"]})
            signatures.append(ref_type_signature["signature"])
        self.assertIn(u"Ljava/lang/Runnable;", signatures)

    def test_reference_type_class_object(self):
        class_object_resp = self.jdwp.ReferenceType.ClassObject({
                "refType": self.thread_class_id})
        self.assertIn("classObject", class_object_resp)
        self.assertIsInstance(class_object_resp["classObject"], int)

    def test_reference_type_source_debug_extension(self):
        # not clear whether this is implemented or useful. jsr045
        pass

    def test_reference_type_signature_with_generic(self):
        signature_with_generic_resp = self.jdwp.ReferenceType.SignatureWithGeneric({
                "refType": self.array_list_class_id})
        self.assertIn("genericSignature", signature_with_generic_resp)
        self.assertIn("signature", signature_with_generic_resp)

    def test_reference_type_fields_with_generic(self):
        fields_with_generic_resp = self.jdwp.ReferenceType.FieldsWithGeneric({
                "refType": self.array_list_class_id})
        self.assertIn("declared", fields_with_generic_resp)
        self.assertGreater(len(fields_with_generic_resp["declared"]), 0)
        field = fields_with_generic_resp["declared"][0]
        self.assertIn("genericSignature", field)
        self.assertIn("fieldID", field)
        self.assertIn("name", field)
        self.assertIn("modBits", field)
        self.assertIn("signature", field)

    def test_reference_type_methods_with_generic(self):
        methods_with_generic_resp = self.jdwp.ReferenceType.MethodsWithGeneric({
                "refType": self.array_list_class_id})
        self.assertIn("declared", methods_with_generic_resp)
        self.assertGreater(len(methods_with_generic_resp["declared"]), 0)
        method = methods_with_generic_resp["declared"][0]
        self.assertIn("genericSignature", method)
        self.assertIn("methodID", method)
        self.assertIn("name", method)
        self.assertIn("modBits", method)
        self.assertIn("signature", method)

    def test_reference_type_instances(self):
        instances_resp = self.jdwp.ReferenceType.Instances({
                "refType": self.thread_class_id,
                "maxInstances": 0})
        self.assertIn("instances", instances_resp)
        self.assertGreater(len(instances_resp["instances"]), 0)
        instance = instances_resp["instances"][0]
        self.assertIn("instance", instance)
        self.assertIn("typeTag", instance["instance"])
        self.assertIn("objectID", instance["instance"])

    def test_reference_type_class_file_version(self):
        class_file_version_resp = self.jdwp.ReferenceType.ClassFileVersion({
                "refType": self.thread_class_id})
        self.assertIn("majorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["majorVersion"], int)
        self.assertIn("minorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["minorVersion"], int)

    def test_reference_type_constant_pool(self):
        constant_pool_resp = self.jdwp.ReferenceType.ConstantPool({
                "refType": self.thread_class_id})
        self.assertIn("count", constant_pool_resp)
        self.assertIn("bytes", constant_pool_resp)
        self.assertGreater(len(constant_pool_resp["bytes"]), 0)
        self.assertIn("cpbytes", constant_pool_resp["bytes"][0])

class ClassTypeTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class ClassTypeTest {
          public Integer integer = 7;
          public String string = "ClassTypeTestString";

          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }"""
        cls.debug_target_main_class = "ClassTypeTest"
        super(ClassTypeTest, cls).setUpClass()

    def setUp(self):
        super(ClassTypeTest, self).setUp()
        self.thread_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})["classes"][0]["typeID"]
        self.integer_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Integer;"})["classes"][0]["typeID"]
        self.system_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/System;"})["classes"][0]["typeID"]
        self.breakpoint_event = self.set_breakpoint_in_main(
                "ClassTypeTest")["events"][0]["Breakpoint"]

    def test_class_type_superclass(self):
        superclass_resp = self.jdwp.ClassType.Superclass({
                "clazz": self.thread_class_id})
        self.assertIn("superclass", superclass_resp)

    def test_class_type_set_values(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.integer_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        field_ids = [{"fieldID": field_ids_by_name["MIN_VALUE"]}]
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": self.integer_class_id,
            "fields": field_ids})
        self.assertEquals(-2147483648, get_values_resp["values"][0]["value"])
        set_values_resp = self.jdwp.ClassType.SetValues({
                "clazz": self.integer_class_id,
                "values": [{
                        "fieldID": field_ids[0]["fieldID"],
                        "value": {
                                "typeTag": self.jdwp.Tag.INT,
                                "value": -2147483643}}]})
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": self.integer_class_id,
            "fields": field_ids})
        self.assertEquals(-2147483643, get_values_resp["values"][0]["value"])

    def test_class_type_invoke_method(self):
        methods_resp = self.jdwp.ReferenceType.Methods({
            "refType": self.system_class_id})
        method_ids_by_name = dict([
                (method["name"], method["methodID"]) for method in
                methods_resp["declared"]])
        current_time_millis_method_id = method_ids_by_name["currentTimeMillis"]
        self.assertIsNotNone(current_time_millis_method_id)
        invocation_resp = self.jdwp.ClassType.InvokeMethod({
                "clazz": self.system_class_id,
                "thread": self.breakpoint_event["thread"],
                "methodID": current_time_millis_method_id,
                "arguments": [],
                "options": 1})
        self.assertIn("exception", invocation_resp)
        self.assertIn("objectID", invocation_resp["exception"])
        self.assertIn("typeTag", invocation_resp["exception"])
        self.assertIn("returnValue", invocation_resp)
        self.assertIsInstance(invocation_resp["returnValue"], int)

    def test_class_type_new_instance(self):
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": self.integer_class_id})
        for method in methods_resp["declared"]:
            if method["name"] == u"<init>" and method["signature"] == u"(I)V":
                constructor_id = method["methodID"]
        self.assertIsNotNone(constructor_id)
        new_instance_resp = self.jdwp.ClassType.NewInstance({
            "clazz": self.integer_class_id,
            "thread": self.breakpoint_event["thread"],
            "methodID": constructor_id,
            "arguments": [{
                "arg": {
                    "typeTag": self.jdwp.Tag.INT,
                    "value": 1234}}],
            "options": self.jdwp.InvokeOptions.INVOKE_SINGLE_THREADED})
        self.assertIn("exception", new_instance_resp)
        self.assertIn("objectID", new_instance_resp["exception"])
        self.assertIn("typeTag", new_instance_resp["exception"])
        self.assertIn("newObject", new_instance_resp)
        self.assertIn("objectID", new_instance_resp["newObject"])
        self.assertIn("typeTag", new_instance_resp["newObject"])
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.integer_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        field_ids = [{"fieldID": field_ids_by_name[u"value"]}]
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": new_instance_resp["newObject"]["objectID"],
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"], 1234)

class ArrayTypeTest(PyjdbTestBase):
    def test_array_type_new_instance(self):
        all_classes_response = self.jdwp.VirtualMachine.AllClasses()
        self.assertIn("classes", all_classes_response)
        for cls in all_classes_response["classes"]:
            if cls["signature"] == "[I":
                int_array_type_id = cls["typeID"]
        self.assertIsNotNone(int_array_type_id)
        new_instance_resp = self.jdwp.ArrayType.NewInstance({
                "arrType": int_array_type_id,
                "length": 20000000})
        self.assertIn("newArray", new_instance_resp)
        self.assertIn("objectID", new_instance_resp["newArray"])
        self.assertIn("typeTag", new_instance_resp["newArray"])

class MethodTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class MethodTest {
            public static void main(String[] args) throws Exception {
                Thing thing = new Thing();
                while (true) {
                    Thread.sleep(1000);
                }
            }

            static class Thing {
                public int propertyA = 10;
                public int propertyB = 20;

                public int sumOfSquares() {
                    int propertyASquared = propertyA * propertyA;
                    int propertyBSquared = propertyB * propertyB;
                    int result = propertyASquared + propertyBSquared;
                    return result;
                }
            }
        }
        """
        cls.debug_target_main_class = "MethodTest"
        super(MethodTest, cls).setUpClass()

    def setUp(self):
        super(MethodTest, self).setUp()
        class_prepare_event = self.resume_and_await_class_load("MethodTest$Thing")
        self.thing_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": thing_class_id})
        self.methods = methods_resp["declared"]
        for method in methods_resp["declared"]:
            if method["name"] == u"sumOfSquares":
                self.sum_of_squares_method_id = method["methodID"]

    def test_method_line_table(self):
        line_table_resp = self.jdwp.Method.LineTable({
                "refType": self.thing_class_id,
                "methodID": self.sum_of_squares_method_id})
        self.assertIn("start", line_table_resp)
        self.assertIn("end", line_table_resp)
        self.assertIn("lines", line_table_resp)
        self.assertGreater(len(line_table_resp["lines"]), 0)
        for line in line_table_resp["lines"]:
            self.assertIn("lineCodeIndex", line)
            self.assertIsInstance(line["lineCodeIndex"], int)
            self.assertIn("lineNumber", line)
            self.assertIsInstance(line["lineNumber"], int)

    def test_method_variable_table(self):
        variable_table_resp = self.jdwp.Method.VariableTable({
                "refType": self.thing_class_id,
                "methodID": self.sum_of_squares_method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])

    def test_method_bytecodes(self):
        bytecode_resp = self.jdwp.Method.Bytecodes({
                "refType": self.thing_class_id,
                "methodID": self.sum_of_squares_method_id})
        self.assertIn("bytes", bytecode_resp)
        self.assertGreater(len(bytecode_resp["bytes"]), 0)
        self.assertIn("bytecode", bytecode_resp["bytes"][0])

    def test_method_is_obsolete(self):
        is_obsolete_resp = self.jdwp.Method.IsObsolete({
                "refType": self.thing_class_id,
                "methodID": self.sum_of_squares_method_id})
        self.assertIn("isObsolete", is_obsolete_resp)

    def test_method_variable_table_with_generic(self):
        variable_table_resp = self.jdwp.Method.VariableTableWithGeneric({
                "refType": self.thing_class_id,
                "methodID": self.sum_of_squares_method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])
        self.assertIn("genericSignature", variable_table_resp["slots"][0])

class ObjectReferenceTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class ObjectReferenceTest {
          public int integer = 7;

          public void update() {
            this.integer = 100;
          }

          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }"""
        cls.debug_target_main_class = "ObjectReferenceTest"
        super(ObjectReferenceTest, cls).setUpClass()

    def setUp(self):
        super(ObjectReferenceTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_main(
                "ObjectReferenceTest")["events"][0]["Breakpoint"]
        self.test_class_id = self.breakpoint_event["classID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": self.test_class_id})
        for method in methods_resp["declared"]:
            if method["name"] == u"<init>":
                constructor_id = method["methodID"]
        self.test_object = self.jdwp.ClassType.NewInstance({
            "clazz": self.test_class_id,
            "thread": self.breakpoint_event["thread"],
            "methodID": constructor_id,
            "arguments": [],
            "options": self.jdwp.InvokeOptions.INVOKE_SINGLE_THREADED})[
                    "newObject"]
        self.test_object_id = self.test_object["objectID"]

    def test_object_reference_reference_type(self):
        reference_type_resp = self.jdwp.ObjectReference.ReferenceType({
                "object": self.test_object_id})
        self.assertIn("refTypeTag", reference_type_resp)
        self.assertIn("typeID", reference_type_resp)
        self.assertEquals(reference_type_resp["typeID"], self.test_class_id)

    def test_object_reference_get_values(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.test_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        field_ids = [{"fieldID": field_ids_by_name["integer"]}]
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": self.test_object_id,
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"], 7)

    def test_object_reference_set_values(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.test_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        integer_field_id = field_ids_by_name["integer"]
        field_ids = [{"fieldID": integer_field_id}]
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": self.test_object_id,
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"], 7)
        set_values_resp = self.jdwp.ObjectReference.SetValues({
            "object": self.test_object_id,
            "values": [{
                    "fieldID": integer_field_id,
                    "value": {
                        "typeTag": "I",
                        "value": 42}}]})
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": self.test_object_id,
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"], 42)

    def test_object_reference_monitor_info(self):
        monitor_info_resp = self.jdwp.ObjectReference.MonitorInfo({
            "object": self.test_object_id})
        self.assertIn("owner", monitor_info_resp)
        self.assertIn("entryCount", monitor_info_resp)
        self.assertIn("waiters", monitor_info_resp)

    def test_object_reference_invoke_method(self):
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": self.test_class_id})
        method_ids_by_name = dict([(method["name"], method["methodID"]) for
                method in methods_resp["declared"]])
        update_method_id = method_ids_by_name["update"]
        self.jdwp.ObjectReference.InvokeMethod({
            "object": self.test_object_id,
            "thread": self.breakpoint_event["thread"],
            "clazz": self.test_class_id,
            "methodID": update_method_id,
            "arguments": [],
            "options": self.jdwp.InvokeOptions.INVOKE_SINGLE_THREADED})
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.test_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        integer_field_id = field_ids_by_name["integer"]
        field_ids = [{"fieldID": integer_field_id}]
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": self.test_object_id,
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"], 100)

    def test_object_reference_disable_collection(self):
        resp = self.jdwp.ObjectReference.DisableCollection({
            "object": self.test_object_id})
        self.assertIsNotNone(resp)

    def test_object_reference_enable_collection(self):
        resp = self.jdwp.ObjectReference.EnableCollection({
            "object": self.test_object_id})
        self.assertIsNotNone(resp)

    def test_object_reference_is_collected(self):
        resp = self.jdwp.ObjectReference.IsCollected({
            "object": self.test_object_id})
        self.assertIn("isCollected", resp)

    def test_object_reference_referring_objects(self):
        resp = self.jdwp.ObjectReference.ReferringObjects({
            "object": self.test_object_id,
            "maxReferrers": 0})
        self.assertIn("referringObjects", resp)

class StringReferenceTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        class StringReferenceTest {
          public static String string = "Hello";

          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }"""
        cls.debug_target_main_class = "StringReferenceTest"
        super(StringReferenceTest, cls).setUpClass()

    def setUp(self):
        super(StringReferenceTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_main(
                "StringReferenceTest")["events"][0]["Breakpoint"]
        self.test_class_id = self.breakpoint_event["classID"]

    def test_string_reference_value(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
            "refType": self.test_class_id})
        string_field = fields_resp["declared"][0]
        field_ids = [{
            "fieldID": string_field["fieldID"]}]
        string_object_id = self.jdwp.ReferenceType.GetValues({
            "refType": self.test_class_id,
            "fields": field_ids})["values"][0]["value"]
        resp = self.jdwp.StringReference.Value({
            "stringObject": string_object_id})
        self.assertEquals(resp["stringValue"], u"Hello")

class ThreadReferenceTest(PyjdbTestBase):
    def test_thread_reference_name(self):
        pass
    #def test_thread_reference_suspend(self):
    #def test_thread_reference_resume(self):
    #def test_thread_reference_status(self):
    #def test_thread_reference_thread_group(self):
    #def test_thread_reference_frames(self):
    #def test_thread_reference_frame_count(self):
    #def test_thread_reference_owned_monitors(self):
    #def test_thread_reference_current_contended_monitor(self):
    #def test_thread_reference_stop(self):
    #def test_thread_reference_interrupt(self):
    #def test_thread_reference_suspend_count(self):
    #def test_thread_reference_owned_monitors_stack_depth_info(self):
    #def test_thread_reference_force_early_return(self):
    #def test_thread_group_reference_name(self):
    #def test_thread_group_reference_parent(self):
    #def test_thread_group_reference_children(self):
    #def test_array_reference_length(self):
    #def test_array_reference_get_values(self):
    #def test_array_reference_set_values(self):
    #def test_class_loader_reference_visible_classes(self):
    #def test_event_request_set(self):
    #def test_event_request_clear(self):
    #def test_event_request_clear_all_breakpoints(self):
    #def test_stack_frame_get_values(self):
    #def test_stack_frame_set_values(self):
    #def test_stack_frame_this_object(self):
    #def test_stack_frame_pop_frames(self):
    #def test_class_object_reference_reflected_type(self):
    #def test_event_composite(self):

if __name__ == "__main__":
    unittest.main()
