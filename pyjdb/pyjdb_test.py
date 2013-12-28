import logging 
import os
import pyjdb
import signal
import socket
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

    def setUp(self):
        # boot up the sample java program in target jvm
        self.devnull = open(subprocess.os.devnull, "r")
        self.test_target_subprocess = subprocess.Popen([
            "/usr/bin/java", "-cp", TEST_TMP_DIRNAME,
            "-Xrunjdwp:transport=dt_socket,server=y,suspend=y,address=5005",
            self.debug_target_main_class],
            stdout = self.devnull, stderr = self.devnull)
        try:
            self.wait_for_server("localhost", 5005)
        except socket.error as e:
            # something's wrong; let's try to kill the target jvm (tearDown
            # won't be called if we fail) and bail.
            self.test_target_subprocess.send_signal(signal.SIGKILL)
            raise e
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
        return test_class_prepare_event["events"][0]["ClassPrepare"]

    def set_breakpoint_in_method(self, class_name, method_name):
        self.resume_and_await_class_load(class_name, self.jdwp.SuspendPolicy.ALL)
        signature = "L%s;" % class_name
        resp = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": "L%s;" % class_name})
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
            _, event = event_raw
            for event in event["events"]:
                if event["eventKind"] == self.jdwp.EventKind.BREAKPOINT:
                    return True
        self.jdwp.VirtualMachine.Resume()
        _, breakpoint_events = self.jdwp.await_event(matcher)
        return breakpoint_events["events"][0]["Breakpoint"]

    def set_breakpoint_in_main(self, main_class_name):
        return self.set_breakpoint_in_method(main_class_name, "main")

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
        values = [entry["value"]["value"] for entry in get_values_resp["values"]]
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
        print(self.thread_class_id)
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
        self.breakpoint_event = self.set_breakpoint_in_main("ClassTypeTest")

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
        self.assertEquals(
                -2147483648, get_values_resp["values"][0]["value"]["value"])
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
        self.assertEquals(
                -2147483643, get_values_resp["values"][0]["value"]["value"])

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
        self.assertIn("value", invocation_resp["returnValue"])
        self.assertIn("typeTag", invocation_resp["returnValue"])
        self.assertIsInstance(invocation_resp["returnValue"]["value"], int)

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
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 1234)


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
            public static int getNumber() {
                int a = 10;
                int b = 5;
                int result = a + b;
                return result;
            }

            public static void main(String[] args) throws Exception {
                while (true) {
                    Thread.sleep(1000);
                }
            }
        }
        """
        cls.debug_target_main_class = "MethodTest"
        super(MethodTest, cls).setUpClass()

    def setUp(self):
        super(MethodTest, self).setUp()
        class_prepare_event = self.resume_and_await_class_load("MethodTest")
        self.test_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": self.test_class_id})
        self.methods = methods_resp["declared"]
        for method in methods_resp["declared"]:
            if method["name"] == u"getNumber":
                self.get_number_method_id = method["methodID"]

    def test_method_line_table(self):
        line_table_resp = self.jdwp.Method.LineTable({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("start", line_table_resp)
        self.assertIn("end", line_table_resp)
        self.assertIn("lines", line_table_resp)
        self.assertGreater(len(line_table_resp["lines"]), 0)
        line = line_table_resp["lines"][0]
        self.assertIn("lineCodeIndex", line)
        self.assertIsInstance(line["lineCodeIndex"], int)
        self.assertIn("lineNumber", line)
        self.assertIsInstance(line["lineNumber"], int)

    def test_method_variable_table(self):
        variable_table_resp = self.jdwp.Method.VariableTable({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])

    def test_method_bytecodes(self):
        bytecode_resp = self.jdwp.Method.Bytecodes({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("bytes", bytecode_resp)
        self.assertGreater(len(bytecode_resp["bytes"]), 0)
        self.assertIn("bytecode", bytecode_resp["bytes"][0])

    def test_method_is_obsolete(self):
        is_obsolete_resp = self.jdwp.Method.IsObsolete({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("isObsolete", is_obsolete_resp)

    def test_method_variable_table_with_generic(self):
        variable_table_resp = self.jdwp.Method.VariableTableWithGeneric({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
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
                "ObjectReferenceTest")
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
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 7)

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
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 7)
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
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 42)

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
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 100)

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
                "StringReferenceTest")
        self.test_class_id = self.breakpoint_event["classID"]

    def test_string_reference_value(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
            "refType": self.test_class_id})
        string_field = fields_resp["declared"][0]
        field_ids = [{
            "fieldID": string_field["fieldID"]}]
        string_object_id = self.jdwp.ReferenceType.GetValues({
            "refType": self.test_class_id,
            "fields": field_ids})["values"][0]["value"]["value"]
        resp = self.jdwp.StringReference.Value({
            "stringObject": string_object_id})
        self.assertEquals(resp["stringValue"], u"Hello")


class ThreadReferenceTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class ThreadReferenceTest {
          public static Thread childThread = new Thread(new Runnable() {
            public void run() {
              synchronized (this) {
                while (true) {
                  try {
                    Thread.sleep(1000);
                  } catch (InterruptedException e) {
                    return;
                  }
                }
              }
            }
          }, "childThread");
          
          static {
            childThread.start();
          }

          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }"""
        cls.debug_target_main_class = "ThreadReferenceTest"
        super(ThreadReferenceTest, cls).setUpClass()

    def setUp(self):
        super(ThreadReferenceTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_main(
                "ThreadReferenceTest")
        self.threads = self.jdwp.VirtualMachine.AllThreads()["threads"]
        self.threads_by_name = {}
        for thread in self.threads:
            name = self.jdwp.ThreadReference.Name({
                    "thread": thread["thread"]})["threadName"]
            self.threads_by_name[name] = thread
        self.child_thread_id = self.threads_by_name["childThread"]["thread"]
        self.main_thread_id = self.threads_by_name["main"]["thread"]

    def test_name(self):
        self.assertIn("childThread", self.threads_by_name)

    def test_suspend(self):
        suspend_count = self.jdwp.ThreadReference.SuspendCount({
                "thread": self.child_thread_id})["suspendCount"]
        # the thread should already be suspended due to breakpoint
        self.assertEquals(suspend_count, 1)
        self.jdwp.ThreadReference.Suspend({
                "thread": self.child_thread_id})
        suspend_count = self.jdwp.ThreadReference.SuspendCount({
                "thread": self.child_thread_id})["suspendCount"]
        # the thread should already be suspended due to breakpoint
        self.assertEquals(suspend_count, 2)

    def test_resume(self):
        suspend_count = self.jdwp.ThreadReference.SuspendCount({
                "thread": self.child_thread_id})["suspendCount"]
        # the thread should already be suspended due to breakpoint
        self.assertEquals(suspend_count, 1)
        self.jdwp.ThreadReference.Resume({
                "thread": self.child_thread_id})
        suspend_count = self.jdwp.ThreadReference.SuspendCount({
                "thread": self.child_thread_id})["suspendCount"]
        # the thread should already be suspended due to breakpoint
        self.assertEquals(suspend_count, 0)

    def test_status(self):
        resp = self.jdwp.ThreadReference.Status({
                "thread": self.child_thread_id})
        self.assertIn("threadStatus", resp)
        self.assertIn("suspendStatus", resp)

    def test_thread_group(self):
        resp = self.jdwp.ThreadReference.ThreadGroup({
                "thread": self.child_thread_id})
        self.assertIn("group", resp)

    def test_frames(self):
        resp = self.jdwp.ThreadReference.Frames({
                "thread": self.main_thread_id,
                "startFrame": 0,
                "length": -1})
        self.assertIn("frames", resp)
        self.assertGreater(len(resp["frames"]), 0)
        self.assertIn("classID", resp["frames"][0])
        self.assertIn("index", resp["frames"][0])
        self.assertIn("typeTag", resp["frames"][0])
        self.assertIn("methodID", resp["frames"][0])
        self.assertIn("frameID", resp["frames"][0])

    def test_frame_count(self):
        resp = self.jdwp.ThreadReference.FrameCount({
                "thread": self.main_thread_id})
        self.assertIn("frameCount", resp)

    def test_owned_monitors(self):
        resp = self.jdwp.ThreadReference.OwnedMonitors({
                "thread": self.child_thread_id})
        self.assertIn("owned", resp)

    def test_current_contended_monitor(self):
        resp = self.jdwp.ThreadReference.CurrentContendedMonitor({
                "thread": self.child_thread_id})
        self.assertIn("monitor", resp)
        self.assertIn("objectID", resp["monitor"])
        self.assertIn("typeTag", resp["monitor"])

    def test_stop(self):
        exception_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": "Ljava/lang/Exception;"})["classes"][0]["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": exception_class_id})
        for method in methods_resp["declared"]:
            if method["name"] == u"<init>" and method["signature"] == u"()V":
                exception_constructor_id = method["methodID"]
        self.assertIsNotNone(exception_constructor_id)
        exception_instance = self.jdwp.ClassType.NewInstance({
                "clazz": exception_class_id,
                "thread": self.breakpoint_event["thread"],
                "methodID": exception_constructor_id,
                "arguments": [],
                "options": self.jdwp.InvokeOptions.INVOKE_SINGLE_THREADED})[
                        "newObject"]
        exception_object_id = exception_instance["objectID"]
        self.jdwp.ThreadReference.Stop({
                "thread": self.child_thread_id,
                "throwable": exception_object_id})

    def test_interrupt(self):
        self.jdwp.ThreadReference.Interrupt({
                "thread": self.child_thread_id})

    def test_suspend_count(self):
        suspend_count = self.jdwp.ThreadReference.SuspendCount({
                "thread": self.child_thread_id})["suspendCount"]
        self.assertEquals(suspend_count, 1)

    def test_owned_monitors_stack_depth_info(self):
        resp = self.jdwp.ThreadReference.OwnedMonitorsStackDepthInfo({
                "thread": self.child_thread_id})
        self.assertIn("owned", resp)

    def test_force_early_return(self):
        resp = self.jdwp.ThreadReference.ForceEarlyReturn({
                "thread": self.main_thread_id,
                "value": {
                        "typeTag": self.jdwp.Tag.VOID,
                        "value": None}})
        self.assertIsNotNone(resp)


class ThreadGroupReferenceTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class ThreadGroupReferenceTest {
          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }"""
        cls.debug_target_main_class = "ThreadGroupReferenceTest"
        super(ThreadGroupReferenceTest, cls).setUpClass()

    def setUp(self):
        super(ThreadGroupReferenceTest, self).setUp()
        resp = self.jdwp.VirtualMachine.TopLevelThreadGroups()
        self.main_thread_group_id = resp["groups"][0]["group"]

    def test_name(self):
        resp = self.jdwp.ThreadGroupReference.Name({
                "group": self.main_thread_group_id})
        self.assertIn("groupName", resp)

    def test_parent(self):
        resp = self.jdwp.ThreadGroupReference.Parent({
                "group": self.main_thread_group_id})
        self.assertIn("parentGroup", resp)

    def test_children(self):
        resp = self.jdwp.ThreadGroupReference.Children({
                "group": self.main_thread_group_id})
        self.assertIn("childGroups", resp)
        self.assertGreater(len(resp["childGroups"]), 0)
        self.assertIn("childGroup", resp["childGroups"][0])
        self.assertIn("childThreads", resp)
        self.assertGreater(len(resp["childThreads"]), 0)
        self.assertIn("childThread", resp["childThreads"][0])


class ArrayReferenceTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class ArrayReferenceTest {
          public static int[] integers = {1, 1, 2, 3, 5};
          public static String[] strings = {
              "Hello", "Goodbye", "Huh?", null, "..."};

          public static void main(String[] args) throws Exception {
            while (true) {
              Thread.sleep(1000);
            }
          }
        }
        """
        cls.debug_target_main_class = "ArrayReferenceTest"
        super(ArrayReferenceTest, cls).setUpClass()

    def setUp(self):
        super(ArrayReferenceTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_main(
                "ArrayReferenceTest")
        fields = self.jdwp.ReferenceType.Fields({
                "refType": self.breakpoint_event["classID"]})["declared"]
        field_ids = [{"fieldID": field["fieldID"]} for field in fields]
        resp = self.jdwp.ReferenceType.GetValues({
                "refType": self.breakpoint_event["classID"],
                "fields": field_ids})
        self.integers_array_reference = resp["values"][0]["value"]["value"]
        self.strings_array_reference = resp["values"][1]["value"]["value"]

    def test_length(self):
        resp = self.jdwp.ArrayReference.Length({
                "arrayObject": self.integers_array_reference})
        self.assertIn("arrayLength", resp)
        self.assertEquals(resp["arrayLength"], 5)
        resp = self.jdwp.ArrayReference.Length({
                "arrayObject": self.strings_array_reference})
        self.assertIn("arrayLength", resp)
        self.assertEquals(resp["arrayLength"], 5)

    def test_get_values(self):
        resp = self.jdwp.ArrayReference.GetValues({
                "arrayObject": self.integers_array_reference,
                "firstIndex": 0,
                "length": 4})
        self.assertIn("values", resp)
        self.assertEquals(resp["values"], (1, 1, 2, 3))
        resp = self.jdwp.ArrayReference.GetValues({
                "arrayObject": self.strings_array_reference,
                "firstIndex": 0,
                "length": 4})
        self.assertIn("values", resp)

    def test_set_values(self):
        resp = self.jdwp.ArrayReference.SetValues({
                "arrayObject": self.integers_array_reference,
                "firstIndex": 1,
                "values": [{
                        "value": {
                                "typeTag": self.jdwp.Tag.INT,
                                "value": 2}}]})
        resp = self.jdwp.ArrayReference.GetValues({
                "arrayObject": self.integers_array_reference,
                "firstIndex": 0,
                "length": 5})
        self.assertIn("values", resp)
        self.assertEquals(resp["values"], (1, 2, 2, 3, 5))


class ClassLoaderReferenceTest(PyjdbTestBase):
    def setUp(self):
        super(ClassLoaderReferenceTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_main("PyjdbTest")
        self.test_class_id = self.breakpoint_event["classID"]

    def test_visible_classes(self):
        resp = self.jdwp.ReferenceType.ClassLoader({
                "refType": self.test_class_id})
        class_loader_id = resp["classLoader"]
        resp = self.jdwp.ClassLoaderReference.VisibleClasses({
                "classLoaderObject": class_loader_id})
        self.assertIn("classes", resp)
        self.assertGreater(len(resp["classes"]), 0)
        cls = resp["classes"][0]
        self.assertIn("typeID", cls)
        self.assertIn("refTypeTag", cls)


class StackFrameTest(PyjdbTestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class StackFrameTest {
          public static void main(String[] args) throws Exception {
            int i = 10;
            method1(i);
          }

          public static void method1(int a) throws Exception {
            int j = a + 10;
            method2(j);
          }

          public static void method2(int b) throws Exception {
            int k = b + 10;
            method3(k);
          }

          public static void method3(int c) throws Exception {
            int l = c + 10;
            while (true) {
              Thread.sleep(1000);
              l += 10;
            }
          }
        }"""
        cls.debug_target_main_class = "StackFrameTest"
        super(StackFrameTest, cls).setUpClass()

    def setUp(self):
        super(StackFrameTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_method(
                "StackFrameTest", "method3")
        self.thread_id = self.breakpoint_event["thread"]
        self.frames = self.jdwp.ThreadReference.Frames({
                "thread": self.thread_id,
                "startFrame": 0,
                "length": -1})["frames"]

    def test_get_values(self):
        for frame in self.frames:
            resp = self.jdwp.Method.VariableTable({
                    "refType": frame["classID"],
                    "methodID": frame["methodID"]})
            frame_index = frame["index"]
            slots = [{
                    "slot": slot["slot"],
                    "sigbyte": ord(slot["signature"][0])} for
                            slot in resp["slots"]
                    if slot["codeIndex"] <= frame_index and
                            frame_index < slot["codeIndex"] + slot["length"]]
            for slot in slots:
                resp = self.jdwp.StackFrame.GetValues({
                        "thread": self.thread_id,
                        "frame": frame["frameID"],
                        "slots": slots})
                for value in resp["values"]:
                    self.assertIn("slotValue", value)
                    self.assertIn("value", value["slotValue"])
                    self.assertIn("typeTag", value["slotValue"])

    def test_set_values(self):
        frame = self.frames[0]
        frame_index = frame["index"]
        resp = self.jdwp.Method.VariableTable({
                "refType": frame["classID"],
                "methodID": frame["methodID"]})
        slots = [{
                "slot": slot["slot"],
                "sigbyte": ord(slot["signature"][0])} for slot in resp["slots"]
                if slot["codeIndex"] <= frame_index and
                        frame_index < slot["codeIndex"] + slot["length"]]
        resp = self.jdwp.StackFrame.GetValues({
                "thread": self.thread_id,
                "frame": frame["frameID"],
                "slots": slots})
        self.assertEquals(resp["values"][0]["slotValue"]["value"], 30)
        for slot in slots:
            self.jdwp.StackFrame.SetValues({
                    "thread": self.thread_id,
                    "frame": frame["frameID"],
                    "slotValues": [{
                            "slot": slot["slot"],
                            "slotValue": {
                                    "typeTag": self.jdwp.Tag.INT,
                                    "value": 55}}]})
        resp = self.jdwp.StackFrame.GetValues({
                "thread": self.thread_id,
                "frame": frame["frameID"],
                "slots": slots})
        self.assertEquals(resp["values"][0]["slotValue"]["value"], 55)

    def test_this_object(self):
        frame = self.frames[0]
        resp = self.jdwp.StackFrame.ThisObject({
                "thread": self.thread_id,
                "frame": frame["frameID"]})
        self.assertIn("objectThis", resp)

    def test_pop_frames(self):
        top_frame_id = self.frames[0]["frameID"]
        self.assertEquals(len(self.frames), 4)
        self.jdwp.StackFrame.PopFrames({
                "thread": self.thread_id,
                "frame": top_frame_id})
        resp = self.jdwp.ThreadReference.Frames({
                "thread": self.thread_id,
                "startFrame": 0,
                "length": -1})["frames"]
        # now there should only be 3 frames
        self.assertEquals(len(resp), 3)

if __name__ == "__main__":
    unittest.main()
