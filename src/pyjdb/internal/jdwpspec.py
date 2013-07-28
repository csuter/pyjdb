#!/usr/bin/env python
"""jdwpspec.py: API and helper methods for working with JDWP spec"""

import re

import pyparsing as pp

from pyjdb.internal import jdwpspectext
# JdwpSpec
#
#
# The structure of the jdwp spec tree is
#
# Spec
#  | - CommandSet
#  |    | - Command
#  |    |    | - Out (what is sent by the caller)
#  |    |    | - Reply (what is returned by the callee)
#  |    |    | - Error (errors codes that may be returned)
#  | - CommandSet
#  .
#  .
#  | - ConstantSet
#  |    | - Constant
#  |    | - Constant
#  |    .
#  |    .
#
# Each section is labeled with its type, e.g.:
#  (CommandSet VirtualMachine=1
#    (Command Version=1 "Returns the JDWP version...."
#      (Out 
#      )
#      (Reply 
#      	 (string description "Text information on the VM version")
#      	 (int    jdwpMajor   "Major JDWP Version number")
#      	 (int    jdwpMinor   "Minor JDWP Version number")
#      	 (string vmVersion   "Target VM JRE version...")
#      	 (string vmName      "Target VM name...")
#      )
#      (ErrorSet
#        (Error VM_DEAD "Error description")   
#      )
#    )
#    ... more commands ...
#  )

def ConstructFromText(text):
  return JdwpSpec(GRAMMAR_JDWP_SPEC.parseString(text))

def ConstructFromRawSpecText():
  # cleanup space around equal signs, parse, and return
  clean_spec_text = re.sub("\s*=\s*", "=", jdwpspectext.RAW_JDWP_TEXT)
  return JdwpSpec(GRAMMAR_JDWP_SPEC.parseString(clean_spec_text))

class JdwpSpec:
  def __init__(self, parsed_spec):
    self.__internal_spec = parsed_spec
    self.__command_sets = [entry[1:] for entry in self.__internal_spec
                           if entry[0] == 'CommandSet']
    self.__command_sets_by_name = dict([
        (entry[0].partition('=')[0], entry) for entry in self.__command_sets])
    self.__constant_sets = [entry[1:] for entry in self.__internal_spec
                            if entry[0] == 'ConstantSet']
    self.__constant_sets_by_name = dict([
        (entry[0], entry) for entry in self.__constant_sets])

  def Recognizes(self, attr):
    return self.HasCommandSet(attr) or self.HasConstantSet(attr)

  def HasCommandSet(self, attr):
    return attr in self.__command_sets_by_name

  def HasConstantSet(self, attr):
    return attr in self.__constant_sets_by_name

  def CommandSetByName(self, name):
    try:
      return self.__command_sets_by_name[name]
    except KeyError:
      raise LookupError("No command set with name '%s'" % name)

  def CommandDictByCommandSetName(self, name):
    # 0th element of cmd is name; build dict from (name, rest-of-cmd) pairs
    return dict([
        (cmd[1].partition('=')[0], cmd[1:])
        for cmd in self.CommandSetByName(name)[1:]])

  def ConstantSetByName(self, name):
    try:
      return self.__constant_sets_by_name[name]
    except KeyError:
      raise LookupError("No constant set with name '%s'" % name)

  def ConstantDictByConstantSetName(self, name):
    return dict([
        (cnst[1], cnst[2:]) for cnst in self.ConstantSetByName(name)[1:]])

  def OutStructureForCommand(self, service, method):
    out = [ entry for entry in self.CommandDictByCommandSetName(service)[method]
            if entry[0] == 'Out' ][0]
    return [entry[0:2] for entry in out[1:]]

  def ReplyStructureForCommand(self, service, method):
    reply = [ entry for entry in self.CommandDictByCommandSetName(service)[method]
              if entry[0] == 'Reply' ][0]
    return [entry[0:2] for entry in reply[1:]]

  def ErrorSetStructureForCommand(self, service, method):
    error_set = [ entry for entry in self.CommandDictByCommandSetName(service)[method]
            if entry[0] == 'ErrorSet' ][0]
    return [entry[1:] for entry in error_set[1:]]


SPEC_GRAMMAR_OPEN_PAREN = pp.Literal("(").suppress()
SPEC_GRAMMAR_CLOSE_PAREN = pp.Literal(")").suppress()
SPEC_GRAMMAR_QUOTED_STRING = pp.dblQuotedString
SPEC_GRAMMAR_QUOTED_STRING = SPEC_GRAMMAR_QUOTED_STRING
SPEC_GRAMMAR_SPEC_STRING =\
    pp.OneOrMore(SPEC_GRAMMAR_QUOTED_STRING)\
        .addParseAction(pp.removeQuotes)\
        .addParseAction(lambda s,l,t : ''.join(t))
SPEC_GRAMMAR_S_EXP = pp.Forward()
SPEC_GRAMMAR_STRING = SPEC_GRAMMAR_SPEC_STRING | pp.Regex("([^()\s])+")
SPEC_GRAMMAR_S_EXP_LIST = pp.Group(SPEC_GRAMMAR_OPEN_PAREN +
    pp.ZeroOrMore(SPEC_GRAMMAR_S_EXP) + SPEC_GRAMMAR_CLOSE_PAREN)
SPEC_GRAMMAR_S_EXP << ( SPEC_GRAMMAR_STRING | SPEC_GRAMMAR_S_EXP_LIST )
GRAMMAR_JDWP_SPEC = pp.OneOrMore(SPEC_GRAMMAR_S_EXP)

SPECMAP_STRUCT_FMTS = dict([
    ("string", "S"),
    ("boolean", "b"),
    ("byte", "B"),
    ("int", "I"),
    ("long", "L"),
    ("referenceType", "R"),
    ("referenceTypeID", "R"),
    ("threadObject", "O"),
    ("threadGroupObject", "O"),
    ("stringObject", "O"),
    ("object", "O"),
    ("classLoaderObject", "O"),
    ("field", "F"),
    ("method", "M"),
    ("value", "V"),
    ("interfaceType", "R"),
    ("classObject", "R"),
    ("tagged-object", "T"),
    ("classType", "R"),
    ("untagged-value", "U"),
    ("arrayType", "R"),
    ("frame", "f"),
    ("location", "X"),
    ("arrayObject", "L"),
    ("typed-sequence", "A") ])

SIZE_LOOKUPS_BY_TYPE_NAME = {
    "byte":	lambda id_sizes: 1,
    "boolean":	lambda id_sizes: 1,
    "int":	lambda id_sizes: 4,
    "long":	lambda id_sizes: 8,
    "objectID":	lambda id_sizes: id_sizes['objectIDSize'],
    "tagged-objectID":	lambda id_sizes: 1 + id_sizes['objectIDSize'],
    "threadID":	lambda id_sizes: id_sizes['objectIDSize'],
    "threadGroupID":	lambda id_sizes: id_sizes['objectIDSize'],
    "stringID":	lambda id_sizes: id_sizes['objectIDSize'],
    "classLoaderID":	lambda id_sizes: id_sizes['objectIDSize'],
    "classObjectID":	lambda id_sizes: id_sizes['objectIDSize'],
    "arrayID":	lambda id_sizes: id_sizes['objectIDSize'],
    "referenceTypeID":	lambda id_sizes: id_sizes[referenceTypeIDSize],
    "classID":	lambda id_sizes: id_sizes[referenceTypeIDSize],
    "interfaceID":	lambda id_sizes: id_sizes[referenceTypeIDSize],
    "arrayTypeID":	lambda id_sizes: id_sizes[referenceTypeIDSize],
    "methodID":	lambda id_sizes: id_sizes['methodIDSize'],
    "fieldID":	lambda id_sizes: id_sizes['fieldIDSize'],
    "frameID":	lambda id_sizes: id_sizes['frameIDSize'] }
