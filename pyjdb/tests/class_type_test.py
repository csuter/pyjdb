# pylint: disable=R0904,C0111
"""Functional tests for JDWP ClassType CommandSet"""
import harness


class ClassTypeTest(harness.TestBase):
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
        self.jdwp.ClassType.SetValues({
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
                -2147483643,
                get_values_resp["values"][0]["value"]["value"])

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
