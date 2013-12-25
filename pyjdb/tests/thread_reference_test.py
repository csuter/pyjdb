# pylint: disable=R0904,C0111
"""Functional tests for JDWP ThreadReference CommandSet"""
import harness


class ThreadReferenceTest(harness.TestBase):
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

