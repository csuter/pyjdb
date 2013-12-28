# pylint: disable=R0904,C0111
"""Functional tests for JDWP Method CommandSet"""
import harness


class MethodTest(harness.TestBase):
    @classmethod
    def setUpClass(cls):
        cls.debug_target_code = """
        public class MethodTest {
            public static int getNumber() {
                int a = 10;
                int b = 5;
                int result = a + b;
                return result;
            }

            public static void main(String[] args) throws Exception {
                while (true) {
                    Thread.sleep(1000);
                }
            }
        }
        """
        cls.debug_target_main_class = "MethodTest"
        super(MethodTest, cls).setUpClass()

    def setUp(self):
        super(MethodTest, self).setUp()
        class_prepare_event = self.resume_and_await_class_load("MethodTest")
        self.test_class_id = class_prepare_event["typeID"]
        methods_resp = self.jdwp.ReferenceType.Methods({
                "refType": self.test_class_id})
        self.methods = methods_resp["declared"]
        for method in methods_resp["declared"]:
            if method["name"] == u"getNumber":
                self.get_number_method_id = method["methodID"]

    def test_line_table(self):
        line_table_resp = self.jdwp.Method.LineTable({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("start", line_table_resp)
        self.assertIn("end", line_table_resp)
        self.assertIn("lines", line_table_resp)
        self.assertGreater(len(line_table_resp["lines"]), 0)
        line = line_table_resp["lines"][0]
        self.assertIn("lineCodeIndex", line)
        self.assertIsInstance(line["lineCodeIndex"], int)
        self.assertIn("lineNumber", line)
        self.assertIsInstance(line["lineNumber"], int)

    def test_variable_table(self):
        variable_table_resp = self.jdwp.Method.VariableTable({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])

    def test_bytecodes(self):
        bytecode_resp = self.jdwp.Method.Bytecodes({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("bytes", bytecode_resp)
        self.assertGreater(len(bytecode_resp["bytes"]), 0)
        self.assertIn("bytecode", bytecode_resp["bytes"][0])

    def test_is_obsolete(self):
        is_obsolete_resp = self.jdwp.Method.IsObsolete({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("isObsolete", is_obsolete_resp)

    def test_variable_table_with_generic(self):
        variable_table_resp = self.jdwp.Method.VariableTableWithGeneric({
                "refType": self.test_class_id,
                "methodID": self.get_number_method_id})
        self.assertIn("slots", variable_table_resp)
        self.assertGreater(len(variable_table_resp["slots"]), 1)
        self.assertIn("codeIndex", variable_table_resp["slots"][0])
        self.assertIn("slot", variable_table_resp["slots"][0])
        self.assertIn("length", variable_table_resp["slots"][0])
        self.assertIn("name", variable_table_resp["slots"][0])
        self.assertIn("signature", variable_table_resp["slots"][0])
        self.assertIn("genericSignature", variable_table_resp["slots"][0])

