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
              public static void main(String[] args) {
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
    def test_reference_type_signature(self):
        classes = self.jdwp.VirtualMachine.AllClasses()
        for class_entry in classes["classes"]:
            signature = class_entry["signature"]
            resp = self.jdwp.ReferenceType.Signature({
                "refType": class_entry["typeID"]})
            self.assertEquals(signature, resp["signature"])

    def test_reference_type_class_loader(self):
        classes = self.jdwp.VirtualMachine.AllClasses()
        for class_entry in classes["classes"]:
            resp = self.jdwp.ReferenceType.ClassLoader({
                "refType": class_entry["typeID"]})
            self.assertIn("classLoader", resp)

    def test_reference_type_modifiers(self):
        classes = self.jdwp.VirtualMachine.AllClasses()
        for class_entry in classes["classes"]:
            signature = class_entry["signature"]
            resp = self.jdwp.ReferenceType.Modifiers({
                "refType": class_entry["typeID"]})
            self.assertIn("modBits", resp)

    def test_reference_type_fields(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        string_class_id = classes_by_sig["classes"][0]["typeID"]
        resp = self.jdwp.ReferenceType.Fields({"refType": string_class_id})
        for field_entry in resp["declared"]:
            self.assertIn("modBits", field_entry)
            self.assertIn("fieldID", field_entry)
            self.assertIn("name", field_entry)
            self.assertIn("signature", field_entry)

    def test_reference_type_methods(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        string_class_id = classes_by_sig["classes"][0]["typeID"]
        resp = self.jdwp.ReferenceType.Methods({
            "refType": string_class_id})
        for method_entry in resp["declared"]:
            self.assertIn("modBits", method_entry)
            self.assertIn("methodID", method_entry)
            self.assertIn("name", method_entry)
            self.assertIn("signature", method_entry)

    def test_reference_type_get_values(self):
        # TODO(cgs): add more value types; verify edge cases of signed/unsigned
        # integer types, etc.
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Integer;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        integer_class_id = classes_by_sig["classes"][0]["typeID"]
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": integer_class_id})
        fields = fields_resp["declared"]
        field_ids = []
        for field in fields:
            if field["name"] == "MIN_VALUE":
                field_ids.append({"fieldID": field["fieldID"]})
            elif field["name"] == "MAX_VALUE":
                field_ids.append({"fieldID": field["fieldID"]})
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": integer_class_id,
            "fields": field_ids})
        values = [entry["value"] for entry in get_values_resp["values"]]
        self.assertIn(-2147483648, values)
        self.assertIn(2147483647, values)

    def test_reference_type_source_file(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Integer;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        integer_class_id = classes_by_sig["classes"][0]["typeID"]
        source_file_resp = self.jdwp.ReferenceType.SourceFile({
                "refType": integer_class_id})
        self.assertEquals("Integer.java", source_file_resp["sourceFile"])

    def test_reference_type_nested_types(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        nested_types_resp = self.jdwp.ReferenceType.NestedTypes({
                "refType": thread_class_id})
        classes = nested_types_resp["classes"]
        exception_sig = "Ljava/lang/Thread$UncaughtExceptionHandler;"
        for cls in classes:
            self.assertIn("typeID", cls)
            self.assertIn("refTypeTag", cls)

    def test_reference_type_status(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        status_resp = self.jdwp.ReferenceType.Status({
                "refType": thread_class_id})
        self.assertIn("status", status_resp)
        self.assertIsInstance(status_resp["status"], int)

    def test_reference_type_interfaces(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        interfaces_resp = self.jdwp.ReferenceType.Interfaces({
            "refType": thread_class_id})
        signatures = []
        for interface in interfaces_resp["interfaces"]:
            ref_type_signature = self.jdwp.ReferenceType.Signature({
                "refType": interface["interfaceType"]})
            signatures.append(ref_type_signature["signature"])
        self.assertIn(u"Ljava/lang/Runnable;", signatures)

    def test_reference_type_class_object(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        class_object_resp = self.jdwp.ReferenceType.ClassObject({
                "refType": thread_class_id})
        self.assertIn("classObject", class_object_resp)
        self.assertIsInstance(class_object_resp["classObject"], int)

    def test_reference_type_source_debug_extension(self):
        # not clear whether this is implemented or useful. jsr045
        pass

    def test_reference_type_signature_with_generic(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/util/List;"})
        list_class_id = classes_by_sig["classes"][0]["typeID"]
        signature_with_generic_resp = self.jdwp.ReferenceType.SignatureWithGeneric({
                "refType": list_class_id})
        self.assertIn("genericSignature", signature_with_generic_resp)
        self.assertIn("signature", signature_with_generic_resp)

    def test_reference_type_fields_with_generic(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/util/ArrayList;"})
        arraylist_class_id = classes_by_sig["classes"][0]["typeID"]
        fields_with_generic_resp = self.jdwp.ReferenceType.FieldsWithGeneric({
                "refType": arraylist_class_id})
        self.assertIn("declared", fields_with_generic_resp)
        self.assertGreater(len(fields_with_generic_resp["declared"]), 0)
        for field in fields_with_generic_resp["declared"]:
            self.assertIn("genericSignature", field)
            self.assertIn("fieldID", field)
            self.assertIn("name", field)
            self.assertIn("modBits", field)
            self.assertIn("signature", field)

    def test_reference_type_methods_with_generic(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/util/ArrayList;"})
        arraylist_class_id = classes_by_sig["classes"][0]["typeID"]
        methods_with_generic_resp = self.jdwp.ReferenceType.MethodsWithGeneric({
                "refType": arraylist_class_id})
        self.assertIn("declared", methods_with_generic_resp)
        self.assertGreater(len(methods_with_generic_resp["declared"]), 0)
        for method in methods_with_generic_resp["declared"]:
            self.assertIn("genericSignature", method)
            self.assertIn("methodID", method)
            self.assertIn("name", method)
            self.assertIn("modBits", method)
            self.assertIn("signature", method)

    def test_reference_type_instances(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        instances_resp = self.jdwp.ReferenceType.Instances({
                "refType": thread_class_id,
                "maxInstances": 0})
        self.assertIn("instances", instances_resp)
        self.assertGreater(len(instances_resp["instances"]), 0)
        for instance in instances_resp["instances"]:
            self.assertIn("instance", instance)
            self.assertIn("tagType", instance["instance"])
            self.assertIn("objectID", instance["instance"])

    def test_reference_type_class_file_version(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        class_file_version_resp = self.jdwp.ReferenceType.ClassFileVersion({
                "refType": thread_class_id})
        self.assertIn("majorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["majorVersion"], int)
        self.assertIn("minorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["minorVersion"], int)

    def test_reference_type_constant_pool(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Thread;"})
        thread_class_id = classes_by_sig["classes"][0]["typeID"]
        constant_pool_resp = self.jdwp.ReferenceType.ConstantPool({
                "refType": thread_class_id})
        self.assertIn("count", constant_pool_resp)
        self.assertIn("bytes", constant_pool_resp)
        self.assertGreater(len(constant_pool_resp["bytes"]), 0)
        self.assertIn("cpbytes", constant_pool_resp["bytes"][0])

class ClassTypeTest(PyjdbTestBase):
    def test_class_type_superclass(self):
        classes_by_sig = self.jdwp.virtualmachine.classesbysignature({
            "signature": u"ljava/lang/thread;"})
        thread_class_id = classes_by_sig["classes"][0]["typeid"]
        superclass_resp = self.jdwp.classtype.superclass({
                "clazz": thread_class_id})
        self.assertin("superclass", superclass_resp)

    def test_class_type_set_values(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/Integer;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        integer_class_id = classes_by_sig["classes"][0]["typeID"]
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": integer_class_id})
        fields = fields_resp["declared"]
        field_ids = []
        for field in fields:
            if field["name"] == "MIN_VALUE":
                field_ids.append({"fieldID": field["fieldID"]})
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": integer_class_id,
            "fields": field_ids})
        values = [entry["value"] for entry in get_values_resp["values"]]
        self.assertIn(-2147483648, values)
        set_values_resp = self.jdwp.ClassType.SetValues({
                "clazz": integer_class_id,
                "values": [{
                        "fieldID": field_ids[0]["fieldID"],
                        "value": {
                                "tagType": self.jdwp.Tag.INT,
                                "value": -2147483643}}]})
        self.assertIsNotNone(set_values_resp)
        get_values_resp = self.jdwp.ReferenceType.GetValues({
            "refType": integer_class_id,
            "fields": field_ids})
        values = [entry["value"] for entry in get_values_resp["values"]]
        self.assertIn(-2147483643, values)

    def test_class_type_invoke_method(self):
        # TODO(cgs): revisit this once event setting/catchin is well-tested
        all_threads_resp = self.jdwp.VirtualMachine.AllThreads()
        self.assertIn("threads", all_threads_resp)
        self.assertGreater(len(all_threads_resp["threads"]), 0)
        thread_id = all_threads_resp["threads"][2]["thread"]

        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/System;"})
        self.assertIn("classes", classes_by_sig)
        self.assertGreater(len(classes_by_sig["classes"]), 0)
        system_class_id = classes_by_sig["classes"][0]["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
            "refType": system_class_id})
        for method_entry in methods_resp["declared"]:
            if method_entry["name"] == u"currentTimeMillis":
                current_time_millis_method_id = method_entry["methodID"]
        self.assertIsNotNone(current_time_millis_method_id)
        # TODO(cgs): fix this. as written, the below will cause an
        # "INVALID_THREAD" error. we must first properly set and catch an
        # event, then we can test invoation of static methods
        #invocation_resp = self.jdwp.ClassType.InvokeMethod({
        #        "clazz": system_class_id,
        #        "thread": thread_id,
        #        "methodID": current_time_millis_method_id,
        #        "arguments": [],
        #        "options": 1})

    def test_class_type_new_instance(self):
        # TODO(cgs): as above, revisit after events tested
        #classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
        #    "signature": u"Ljava/lang/Integer;"})
        #self.assertIn("classes", classes_by_sig)
        #self.assertGreater(len(classes_by_sig["classes"]), 0)
        #integer_class_id = classes_by_sig["classes"][0]["typeID"]
        #methods_resp = self.jdwp.ReferenceType.Methods({
        #        "refType": integer_class_id})
        #for method in methods_resp["declared"]:
        #    if method["name"] == u"<init>" and method["signature"] == u"(I)V":
        #        constructor_id = method["methodID"]
        #self.assertIsNotNone(constructor_id)
        pass

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
        self.assertIn("tagType", new_instance_resp["newArray"])

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

    def test_method_line_table(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        string_class_id = classes_by_sig["classes"][0]["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": string_class_id})

        for method in methods_resp["declared"]:
            if method["name"] == u"length":
                length_method_id = method["methodID"]
        self.assertIsNotNone(length_method_id)
        line_table_resp = self.jdwp.Method.LineTable({
                "refType": string_class_id,
                "methodID": length_method_id})
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
        event_req_set_resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
        self.assertIsNotNone(event_req_set_resp)
        self.jdwp.VirtualMachine.Resume()
        def matcher(event_raw):
            req_id, event_data = event_raw
            for event in event_data["events"]:
                if event["eventKind"] == self.jdwp.EventKind.CLASS_PREPARE:
                    if event["ClassPrepare"]["signature"] == "LMethodTest$Thing;":
                        return True
            return False
        _, test_class_prepare_event = self.jdwp.await_event(matcher)
        self.assertIn("events", test_class_prepare_event)
        self.assertEquals(1, len(test_class_prepare_event["events"]))
        self.assertIn("ClassPrepare", test_class_prepare_event["events"][0])
        class_prepare_event = test_class_prepare_event["events"][0]["ClassPrepare"]
        self.assertIn("typeID", class_prepare_event)
        thing_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": thing_class_id})
        self.assertIn("declared", methods_resp)
        for method in methods_resp["declared"]:
            if method["name"] == u"sumOfSquares":
                method_id = method["methodID"]
        self.assertIsNotNone(method_id)
        variable_table_resp = self.jdwp.Method.VariableTable({
                "refType": thing_class_id,
                "methodID": method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])

    def test_method_bytecodes(self):
        event_req_set_resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
        self.assertIsNotNone(event_req_set_resp)
        self.jdwp.VirtualMachine.Resume()
        def matcher(event_raw):
            req_id, event_data = event_raw
            for event in event_data["events"]:
                if event["eventKind"] == self.jdwp.EventKind.CLASS_PREPARE:
                    if event["ClassPrepare"]["signature"] == "LMethodTest$Thing;":
                        return True
            return False
        _, test_class_prepare_event = self.jdwp.await_event(matcher)
        self.assertIn("events", test_class_prepare_event)
        self.assertEquals(1, len(test_class_prepare_event["events"]))
        self.assertIn("ClassPrepare", test_class_prepare_event["events"][0])
        class_prepare_event = test_class_prepare_event["events"][0]["ClassPrepare"]
        self.assertIn("typeID", class_prepare_event)
        thing_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": thing_class_id})
        self.assertIn("declared", methods_resp)
        for method in methods_resp["declared"]:
            if method["name"] == u"sumOfSquares":
                method_id = method["methodID"]
        self.assertIsNotNone(method_id)
        bytecode_resp = self.jdwp.Method.Bytecodes({
                "refType": thing_class_id,
                "methodID": method_id})
        self.assertIn("bytes", bytecode_resp)
        self.assertGreater(len(bytecode_resp["bytes"]), 0)
        self.assertIn("bytecode", bytecode_resp["bytes"][0])

    def test_method_is_obsolete(self):
        classes_by_sig = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": u"Ljava/lang/String;"})
        string_class_id = classes_by_sig["classes"][0]["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": string_class_id})
        for method in methods_resp["declared"]:
            if method["name"] == u"length":
                length_method_id = method["methodID"]
        self.assertIsNotNone(length_method_id)
        is_obsolete_resp = self.jdwp.Method.IsObsolete({
                "refType": string_class_id,
                "methodID": length_method_id})
        self.assertIn("isObsolete", is_obsolete_resp)

    def test_method_variable_table_with_generic(self):
        event_req_set_resp = self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
        self.assertIsNotNone(event_req_set_resp)
        self.jdwp.VirtualMachine.Resume()
        def matcher(event_raw):
            req_id, event_data = event_raw
            for event in event_data["events"]:
                if event["eventKind"] == self.jdwp.EventKind.CLASS_PREPARE:
                    if event["ClassPrepare"]["signature"] == "LMethodTest$Thing;":
                        return True
            return False
        _, test_class_prepare_event = self.jdwp.await_event(matcher)
        self.assertIn("events", test_class_prepare_event)
        self.assertEquals(1, len(test_class_prepare_event["events"]))
        self.assertIn("ClassPrepare", test_class_prepare_event["events"][0])
        class_prepare_event = test_class_prepare_event["events"][0]["ClassPrepare"]
        self.assertIn("typeID", class_prepare_event)
        thing_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": thing_class_id})
        self.assertIn("declared", methods_resp)
        for method in methods_resp["declared"]:
            if method["name"] == u"sumOfSquares":
                method_id = method["methodID"]
        self.assertIsNotNone(method_id)
        variable_table_resp = self.jdwp.Method.VariableTableWithGeneric({
                "refType": thing_class_id,
                "methodID": method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])
        self.assertIn("genericSignature", variable_table_resp["slots"][0])

class ObjectReferenceTest(PyjdbTestBase):
    def setUp(self):
        super(ObjectReferenceTest, self).setUp()
        string_class_resp = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": "Ljava/lang/String;"})
        self.string_class_id = string_class_resp["classes"][0]["typeID"]
        class_object_resp = self.jdwp.ReferenceType.ClassObject({
                "refType": self.string_class_id})
        self.string_class_object_id = class_object_resp["classObject"]
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.string_class_id})
        self.string_class_fields = fields_resp["declared"]

    def test_object_reference_reference_type(self):
        reference_type_resp = self.jdwp.ObjectReference.ReferenceType({
                "object": self.string_class_object_id})
        self.assertIn("refTypeTag", reference_type_resp)
        self.assertIn("typeID", reference_type_resp)

    def test_object_reference_get_values(self):
        serial_version_uid_field_id = dict([
                (field["name"], field["fieldID"]) for field in
                self.string_class_fields])["CASE_INSENSITIVE_ORDER"]
        req = {
                "object": self.string_class_object_id,
                "fields": [{"fieldID": serial_version_uid_field_id}]}
        print(req)
        get_values_resp = self.jdwp.ObjectReference.GetValues(req)
        print(get_values_resp)

    #def test_object_reference_set_values(self):
    #def test_object_reference_monitor_info(self):
    #def test_object_reference_invoke_method(self):
    #def test_object_reference_disable_collection(self):
    #def test_object_reference_enable_collection(self):
    #def test_object_reference_is_collected(self):
    #def test_object_reference_referring_objects(self):
    #def test_string_reference_value(self):
    #def test_thread_reference_name(self):
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
    #def test_stack_frame_pop_frames	(self):
    #def test_class_object_reference_reflected_type(self):
    #def test_event_composite(self):

if __name__ == "__main__":
    unittest.main()
