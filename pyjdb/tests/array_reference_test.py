# pylint: disable=R0904,C0111
"""Functional tests for JDWP ArrayReference CommandSet"""
import harness


class ArrayReferenceTest(harness.TestBase):
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
