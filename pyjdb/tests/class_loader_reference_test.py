# pylint: disable=R0904,C0111
"""Functional tests for JDWP ClassLoaderReference CommandSet"""
import harness


class ClassLoaderReferenceTest(harness.TestBase):
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
