# pylint: disable=R0904,C0111
"""Functional tests for JDWP ArrayType CommandSet"""
import harness

class ArrayTypeTest(harness.TestBase):
    def test_new_instance(self):
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
