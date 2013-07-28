from pyjdb.internal import jdwpspec
import unittest

SIMPLE_TEST_SPEC_TEXT =\
'''(CommandSet FakeCommandSet=1
     (Command FakeCommand=1 "Fake command description"
       (Out
         (string fakeStringArgument "Fake string argument description")
         (int    fakeIntArgument "Fake int argument description")
       )
       (Reply
         (string fakeStringReply "Fake string reply description")
       )
       (ErrorSet
         (Error FAKE_ERROR)
       )
     )
     (Command OtherFakeCommand=1 "Other fake command description"
       (Out
         (string fakeStringArgument2 "Other fake string argument description")
         (int    fakeIntArgument2 "Other fake int argument description")
       )
       (Reply
         (string fakeStringReply2 "Other fake string reply description")
       )
       (ErrorSet
         (Error OTHER_FAKE_ERROR)
       )
     )
   )
   (ConstantSet Error
     (Constant FAKE_ERROR    =0  "Fake error description")
     (Constant OTHER_FAKE_ERROR    =1  "Other fake error description")
   )
'''

class JdwpSpecTest(unittest.TestCase):
  def setUp(self):
    self.simple_spec =\
        jdwpspec.ConstructFromText(SIMPLE_TEST_SPEC_TEXT)
    self.kBadSetName = 'ASDF'

  def tearDown(self):
    pass

  def test_Recognizes(self):
    self.assertTrue(self.simple_spec.Recognizes('FakeCommandSet'))
    self.assertTrue(self.simple_spec.Recognizes('Error'))
    self.assertFalse(self.simple_spec.Recognizes('Christopher'))

  def test_HasCommandSet(self):
    self.assertTrue(self.simple_spec.HasCommandSet('FakeCommandSet'))
    self.assertFalse(self.simple_spec.HasCommandSet('Error'))
    self.assertFalse(self.simple_spec.HasCommandSet('Christopher'))

  def test_HasConstantSet(self):
    self.assertFalse(self.simple_spec.HasConstantSet('FakeCommandSet'))
    self.assertTrue(self.simple_spec.HasConstantSet('Error'))
    self.assertFalse(self.simple_spec.HasConstantSet('Christopher'))

  def test_CommandSetByName(self):
    self.assertRaisesRegexp(
        LookupError,
        "No command set with name '%s'" % self.kBadSetName,
        self.simple_spec.CommandSetByName,
        self.kBadSetName)
    self.assertIsNotNone(self.simple_spec.CommandSetByName('FakeCommandSet'))

  def test_CommandDictByCommandSetName(self):
    command_dict =\
        self.simple_spec.CommandDictByCommandSetName('FakeCommandSet')
    self.assertIn('FakeCommand', command_dict)
    self.assertIn('OtherFakeCommand', command_dict)
    self.assertNotIn('Reply', command_dict)
    self.assertNotIn('FakeCommandSet', command_dict)

    self.assertRaisesRegexp(
        LookupError,
        "No command set with name '%s'" % self.kBadSetName,
        self.simple_spec.CommandDictByCommandSetName,
        self.kBadSetName)

  def test_ConstantSetByName(self):
    self.assertRaisesRegexp(
        LookupError,
        "No constant set with name '%s'" % self.kBadSetName,
        self.simple_spec.ConstantSetByName,
        self.kBadSetName)
    self.assertIsNotNone(self.simple_spec.ConstantSetByName('Error'))

  def test_ConstantDictByConstantSetName(self):
    constant_dict =\
        self.simple_spec.ConstantDictByConstantSetName('Error')
    self.assertIn('FAKE_ERROR', constant_dict)
    self.assertIn('OTHER_FAKE_ERROR', constant_dict)
    self.assertNotIn('Error', constant_dict)
    self.assertNotIn('FakeCommand', constant_dict)

    self.assertRaisesRegexp(
        LookupError,
        "No constant set with name '%s'" % self.kBadSetName,
        self.simple_spec.ConstantDictByConstantSetName,
        self.kBadSetName)

if __name__ == '__main__':
  unittest.main()
