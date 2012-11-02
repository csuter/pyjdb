#!/usr/bin/python

import re
import spec_structures
import sys
import jdwprpc_structures
import proto_structures
import pyparsing as pp

def main():
  work_root = sys.argv[1]
  specfile = "%s/build-gen/jdwprpc/codegen/jdwp_spec.txt" % work_root
  proto_header = "%s/build-gen/jdwprpc/codegen/jdwp.proto_header.txt" % work_root
  proto_file = "%s/build-gen/jdwprpc/jdwp.proto" % work_root
  jdwprpc_file = "%s/build-gen/jdwprpc/jdwprpc.py" % work_root

  spec = load_spec(specfile)

  generate_protofile(proto_header, spec, proto_file)
  generate_jdwprpc(spec, jdwprpc_file)

def load_spec(specfile, with_strings = False):
  with open(specfile, 'r') as f: spec = f.read()
  spec = re.sub("\s*=\s*", "=", spec)
  parsed_jdwp_spec = spec_file_grammar(with_strings).parseString(spec)
  return spec_structures.Spec(parsed_jdwp_spec)

def spec_file_grammar(with_strings = False):
  open_paren = pp.Literal("(").suppress()
  close_paren = pp.Literal(")").suppress()
  quoted_string = pp.dblQuotedString
  if not with_strings:
    quoted_string = quoted_string.suppress()

  spec_string = pp.OneOrMore(quoted_string)

  sexp = pp.Forward()
  string = spec_string | pp.Regex("([^()\s])+")
  sexp_list = pp.Group(open_paren + pp.ZeroOrMore(sexp) + close_paren)
  sexp << ( string | sexp_list )
  return pp.OneOrMore(sexp)

def generate_protofile(proto_header, spec, proto_file):
  # load proto file header text
  with open(proto_header, 'r') as f: header = f.read()
  # generate pb text
  pb = proto_structures.spec_proto_def(spec)
  # output header and pb text to proto_file
  with open(proto_file, 'w') as f: f.write("\n".join([header, pb]))

def generate_jdwprpc(spec, jdwprpc_file):
  py = jdwprpc_structures.jdwprpc_impl(spec)
  with open(jdwprpc_file, 'w') as f: f.write(py)

if __name__ == '__main__':
  main()