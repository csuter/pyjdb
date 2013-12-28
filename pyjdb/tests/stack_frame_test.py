# pylint: disable=R0904,C0111
"""Functional tests for JDWP StackFrame CommandSet"""
import harness


class StackFrameTest(harness.TestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class StackFrameTest {
          public static void main(String[] args) throws Exception {
            int i = 10;
            method1(i);
          }

          public static void method1(int a) throws Exception {
            int j = a + 10;
            method2(j);
          }

          public static void method2(int b) throws Exception {
            int k = b + 10;
            method3(k);
          }

          public static void method3(int c) throws Exception {
            int l = c + 10;
            while (true) {
              Thread.sleep(1000);
              l += 10;
            }
          }
        }"""
        cls.debug_target_main_class = "StackFrameTest"
        super(StackFrameTest, cls).setUpClass()

    def setUp(self):
        super(StackFrameTest, self).setUp()
        self.breakpoint_event = self.set_breakpoint_in_method(
                "StackFrameTest", "method3")
        self.thread_id = self.breakpoint_event["thread"]
        self.frames = self.jdwp.ThreadReference.Frames({
                "thread": self.thread_id,
                "startFrame": 0,
                "length": -1})["frames"]

    def test_get_values(self):
        for frame in self.frames:
            resp = self.jdwp.Method.VariableTable({
                    "refType": frame["classID"],
                    "methodID": frame["methodID"]})
            frame_index = frame["index"]
            slots = [{
                    "slot": slot["slot"],
                    "sigbyte": ord(slot["signature"][0])} for
                            slot in resp["slots"]
                    if slot["codeIndex"] <= frame_index and
                            frame_index < slot["codeIndex"] + slot["length"]]
            for slot in slots:
                resp = self.jdwp.StackFrame.GetValues({
                        "thread": self.thread_id,
                        "frame": frame["frameID"],
                        "slots": slots})
                for value in resp["values"]:
                    self.assertIn("slotValue", value)
                    self.assertIn("value", value["slotValue"])
                    self.assertIn("typeTag", value["slotValue"])

    def test_set_values(self):
        frame = self.frames[0]
        frame_index = frame["index"]
        resp = self.jdwp.Method.VariableTable({
                "refType": frame["classID"],
                "methodID": frame["methodID"]})
        slots = [{
                "slot": slot["slot"],
                "sigbyte": ord(slot["signature"][0])} for slot in resp["slots"]
                if slot["codeIndex"] <= frame_index and
                        frame_index < slot["codeIndex"] + slot["length"]]
        resp = self.jdwp.StackFrame.GetValues({
                "thread": self.thread_id,
                "frame": frame["frameID"],
                "slots": slots})
        self.assertEquals(resp["values"][0]["slotValue"]["value"], 30)
        for slot in slots:
            self.jdwp.StackFrame.SetValues({
                    "thread": self.thread_id,
                    "frame": frame["frameID"],
                    "slotValues": [{
                            "slot": slot["slot"],
                            "slotValue": {
                                    "typeTag": self.jdwp.Tag.INT,
                                    "value": 55}}]})
        resp = self.jdwp.StackFrame.GetValues({
                "thread": self.thread_id,
                "frame": frame["frameID"],
                "slots": slots})
        self.assertEquals(resp["values"][0]["slotValue"]["value"], 55)

    def test_this_object(self):
        frame = self.frames[0]
        resp = self.jdwp.StackFrame.ThisObject({
                "thread": self.thread_id,
                "frame": frame["frameID"]})
        self.assertIn("objectThis", resp)

    def test_pop_frames(self):
        top_frame_id = self.frames[0]["frameID"]
        self.assertEquals(len(self.frames), 4)
        self.jdwp.StackFrame.PopFrames({
                "thread": self.thread_id,
                "frame": top_frame_id})
        resp = self.jdwp.ThreadReference.Frames({
                "thread": self.thread_id,
                "startFrame": 0,
                "length": -1})["frames"]
        # now there should only be 3 frames
        self.assertEquals(len(resp), 3)
