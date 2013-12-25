# pylint: disable=R0904,C0111
"""Functional tests for JDWP ThreadGroupReference CommandSet"""
import harness


class ThreadGroupReferenceTest(harness.TestBase):
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
