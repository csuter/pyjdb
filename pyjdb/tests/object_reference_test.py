# pylint: disable=R0904,C0111
"""Functional tests for JDWP ObjectReference CommandSet"""
import harness


class ObjectReferenceTest(harness.TestBase):
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

    def test_reference_type(self):
        reference_type_resp = self.jdwp.ObjectReference.ReferenceType({
                "object": self.test_object_id})
        self.assertIn("refTypeTag", reference_type_resp)
        self.assertIn("typeID", reference_type_resp)
        self.assertEquals(reference_type_resp["typeID"], self.test_class_id)

    def test_get_values(self):
        fields_resp = self.jdwp.ReferenceType.Fields({
                "refType": self.test_class_id})
        field_ids_by_name = dict([(field["name"], field["fieldID"]) for
                field in fields_resp["declared"]])
        field_ids = [{"fieldID": field_ids_by_name["integer"]}]
        get_values_resp = self.jdwp.ObjectReference.GetValues({
            "object": self.test_object_id,
            "fields": field_ids})
        self.assertEquals(get_values_resp["values"][0]["value"]["value"], 7)

    def test_set_values(self):
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
        self.jdwp.ObjectReference.SetValues({
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

    def test_monitor_info(self):
        monitor_info_resp = self.jdwp.ObjectReference.MonitorInfo({
            "object": self.test_object_id})
        self.assertIn("owner", monitor_info_resp)
        self.assertIn("entryCount", monitor_info_resp)
        self.assertIn("waiters", monitor_info_resp)

    def test_invoke_method(self):
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

    def test_disable_collection(self):
        resp = self.jdwp.ObjectReference.DisableCollection({
            "object": self.test_object_id})
        self.assertIsNotNone(resp)

    def test_enable_collection(self):
        resp = self.jdwp.ObjectReference.EnableCollection({
            "object": self.test_object_id})
        self.assertIsNotNone(resp)

    def test_is_collected(self):
        resp = self.jdwp.ObjectReference.IsCollected({
            "object": self.test_object_id})
        self.assertIn("isCollected", resp)

    def test_referring_objects(self):
        resp = self.jdwp.ObjectReference.ReferringObjects({
            "object": self.test_object_id,
            "maxReferrers": 0})
        self.assertIn("referringObjects", resp)
