# pylint: disable=R0904,C0111
"""Functional tests for JDWP ReferenceType CommandSet"""
import harness

class ReferenceTypeTest(harness.TestBase):
    """Test all RPCs in ReferenceType CommandSet"""
    def setUp(self):
        super(ReferenceTypeTest, self).setUp()
        self.string_class_sig = u"Ljava/lang/String;"
        self.string_class_id = self.jdwp.ReferenceType.ClassesBySignature({
            "signature": self.string_class_sig})["classes"][0]["typeID"]
        self.integer_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": "Ljava/lang/Integer;"})["classes"][0]["typeID"]
        self.thread_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
            "signature": "Ljava/lang/Thread;"})["classes"][0]["typeID"]
        self.array_list_class_id = self.jdwp.VirtualMachine.ClassesBySignature({
                "signature": "Ljava/util/ArrayList;"})["classes"][0]["typeID"]

    def test_signature(self):
        resp = self.jdwp.ReferenceType.Signature({
            "refType": self.string_class_id})
        self.assertEquals(self.string_class_sig, resp["signature"])

    def test_class_loader(self):
        resp = self.jdwp.ReferenceType.ClassLoader({
            "refType": self.string_class_id})
        self.assertIn("classLoader", resp)

    def test_modifiers(self):
        resp = self.jdwp.ReferenceType.Modifiers({
            "refType": self.string_class_id})
        self.assertIn("modBits", resp)

    def test_fields(self):
        resp = self.jdwp.ReferenceType.Fields({"refType": self.string_class_id})
        self.assertIn("declared", resp)
        self.assertGreater(len(resp["declared"]), 0)
        field_entry = resp["declared"][0]
        self.assertIn("modBits", field_entry)
        self.assertIn("fieldID", field_entry)
        self.assertIn("name", field_entry)
        self.assertIn("signature", field_entry)

    def test_methods(self):
        resp = self.jdwp.ReferenceType.Methods({
            "refType": self.string_class_id})
        self.assertIn("declared", resp)
        self.assertGreater(len(resp["declared"]), 0)
        method_entry = resp["declared"][0]
        self.assertIn("modBits", method_entry)
        self.assertIn("methodID", method_entry)
        self.assertIn("name", method_entry)
        self.assertIn("signature", method_entry)

    def test_get_values(self):
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
        values = [entry["value"]["value"] for
                entry in get_values_resp["values"]]
        self.assertIn(-2147483648, values)
        self.assertIn(2147483647, values)

    def test_source_file(self):
        source_file_resp = self.jdwp.ReferenceType.SourceFile({
                "refType": self.integer_class_id})
        self.assertEquals("Integer.java", source_file_resp["sourceFile"])

    def test_nested_types(self):
        nested_types_resp = self.jdwp.ReferenceType.NestedTypes({
                "refType": self.thread_class_id})
        self.assertIn("classes", nested_types_resp)
        self.assertGreater(len(nested_types_resp["classes"]), 0)
        cls = nested_types_resp["classes"][0]
        self.assertIn("typeID", cls)
        self.assertIn("refTypeTag", cls)

    def test_status(self):
        status_resp = self.jdwp.ReferenceType.Status({
                "refType": self.thread_class_id})
        self.assertIn("status", status_resp)
        self.assertIsInstance(status_resp["status"], int)

    def test_interfaces(self):
        interfaces_resp = self.jdwp.ReferenceType.Interfaces({
            "refType": self.thread_class_id})
        signatures = []
        for interface in interfaces_resp["interfaces"]:
            ref_type_signature = self.jdwp.ReferenceType.Signature({
                "refType": interface["interfaceType"]})
            signatures.append(ref_type_signature["signature"])
        self.assertIn(u"Ljava/lang/Runnable;", signatures)

    def test_class_object(self):
        class_object_resp = self.jdwp.ReferenceType.ClassObject({
                "refType": self.thread_class_id})
        self.assertIn("classObject", class_object_resp)
        self.assertIsInstance(class_object_resp["classObject"], int)

    def test_source_debug_extension(self):
        # not clear whether this is implemented or useful. jsr045
        pass

    def test_signature_with_generic(self):
        resp = self.jdwp.ReferenceType.SignatureWithGeneric({
                "refType": self.array_list_class_id})
        self.assertIn("genericSignature", resp)
        self.assertIn("signature", resp)

    def test_fields_with_generic(self):
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

    def test_methods_with_generic(self):
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

    def test_instances(self):
        instances_resp = self.jdwp.ReferenceType.Instances({
                "refType": self.thread_class_id,
                "maxInstances": 0})
        self.assertIn("instances", instances_resp)
        self.assertGreater(len(instances_resp["instances"]), 0)
        instance = instances_resp["instances"][0]
        self.assertIn("instance", instance)
        self.assertIn("typeTag", instance["instance"])
        self.assertIn("objectID", instance["instance"])

    def test_class_file_version(self):
        class_file_version_resp = self.jdwp.ReferenceType.ClassFileVersion({
                "refType": self.thread_class_id})
        self.assertIn("majorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["majorVersion"], int)
        self.assertIn("minorVersion", class_file_version_resp)
        self.assertIsInstance(class_file_version_resp["minorVersion"], int)

    def test_constant_pool(self):
        constant_pool_resp = self.jdwp.ReferenceType.ConstantPool({
                "refType": self.thread_class_id})
        self.assertIn("count", constant_pool_resp)
        self.assertIn("bytes", constant_pool_resp)
        self.assertGreater(len(constant_pool_resp["bytes"]), 0)
        self.assertIn("cpbytes", constant_pool_resp["bytes"][0])
