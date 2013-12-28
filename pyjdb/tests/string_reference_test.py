# pylint: disable=R0904,C0111
"""Functional tests for JDWP StringReference CommandSet"""
import harness


class StringReferenceTest(harness.TestBase):
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

    def test_value(self):
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
