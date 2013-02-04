import pyparsing as pp
import struct

def to_bytestring(fmt, source):
  return ''.join([
    chr(x) for x in to_bytearray(fmt, source) ])

def to_bytearray(fmt, source):
  return transform(fmt, source, bytearray(), get_packer)[0]

def from_bytearray(fmt, source):
  return transform(fmt, source, [], get_unpacker)[0]

def transform(fmt, source, initial, getter):
  if fmt == "":
    return (initial, [])
  parsed_fmt = fmt_grammar().parseString(fmt)
  return create_composite_from_parsed_fmt(parsed_fmt, getter)(initial, source)

def compose_binary_functions(f1, f2):
  return lambda a, b : f2(*f1(a, b))

def create_composite_from_parsed_fmt(parsed_fmt, getter):
  return lambda a, b : \
      reduce(compose_binary_functions, [ getter(x) for x in parsed_fmt ])(a, b)

def get_transform_spec(fmt_spec):
  if fmt_spec in transform_specs:
    return transform_specs[fmt_spec]
  else:
    return transform_specs[fmt_spec[0]](fmt_spec[1:])

def get_unpacker(fmt_spec):
  return general_unpacker(get_transform_spec(fmt_spec))

def get_packer(fmt_spec):
  return general_packer(get_transform_spec(fmt_spec))

rest = lambda s : s[1:]

def general_transform(to_or_from, restfunc=rest):
  return lambda output, source : \
      (output + to_or_from(source), restfunc(source))

def general_packer(transform_spec):
  return general_transform(transform_spec['to_bytearray'])

def general_unpacker(transform_spec):
  return general_transform(
      transform_spec['from_bytearray'],
      transform_spec['restfunc'])

def string_from_bytearray(source):
  strlen = struct.unpack(">I", source[0:4])[0]
  fmtstr = str(strlen) + "s"
  string_subarray = source[4:4 + strlen]
  return [struct.unpack(fmtstr, string_subarray)[0].decode("UTF-8")]

boolean = {
    'to_bytearray' : lambda s : bytearray(struct.pack(">B", s[0])),
    'from_bytearray' : lambda s : [struct.unpack(">B", s[0:1])[0] != 0],
    'restfunc' : rest }

string = {
    'to_bytearray' : lambda s : \
        struct.pack(">I", len(s[0])) + bytearray(s[0], "UTF-8"),
    'from_bytearray' : string_from_bytearray,
    'restfunc' : lambda s : s[4+struct.unpack(">I", s[0:4])[0]:] }


struct_pack_fmt_sizes = { 'I': 4,
                          'B': 1,
                          'Q': 8 }

def fixed_length_transform_spec(fmtstr):
  length = sum([struct_pack_fmt_sizes[c] for c in fmtstr])
  if len(fmtstr) == 1:
    return {
        'to_bytearray' : lambda s : \
            bytearray(struct.pack(">" + fmtstr, s[0])),
        'from_bytearray' :
            lambda s : list(struct.unpack(">" + fmtstr, s[0:length])),
        'restfunc' : lambda s : s[length:]
        }
  return {
      'to_bytearray' : lambda s : bytearray(struct.pack(">" + fmtstr, *s[0])),
      'from_bytearray' :
          lambda s : [struct.unpack(">" + fmtstr, s[0:length])],
      'restfunc' : lambda s : s[length:]
      }

def transform_spec_from_base_functions(to_bytearray_base,
                                       from_bytearray_base,
                                       restfunc_base):
  return lambda subfmt : {
      'to_bytearray' :
          lambda s : to_bytearray_base(subfmt, s),
      'from_bytearray' :
          lambda s : from_bytearray_base(subfmt, s),
      'restfunc' :
          lambda s : restfunc_base(subfmt, s),
      }

def repeat_from_bytearray_base(subfmt, s):
  unpacker = create_composite_from_parsed_fmt(subfmt, get_unpacker)
  count = struct.unpack(">I", s[0:4])[0]
  result = []
  sub = s[4:]
  for i in range(count):
    (sub_result, sub) = unpacker([], sub)
    result.append(sub_result)
  return result

def repeat_to_bytearray_base(subfmt, s):
  packer = create_composite_from_parsed_fmt(subfmt, get_packer)
  result = bytearray(struct.pack(">I", len(s)))
  if len(s) == 0:
    return result
  for entry in s:
    result += packer(bytearray(), entry)[0]
  return result

def repeat_restfunc_base(subfmt, s):
  unpacker = create_composite_from_parsed_fmt(subfmt, get_unpacker)
  count = struct.unpack(">I", s[0:4])[0]
  sub = s[4:]
  for i in range(count):
    sub = unpacker([], sub)[1]
  return sub

def select_subfmt_to_dict(subfmt):
  return dict(map(lambda x : (x[0], x[1:]), subfmt[1:]))

def select_from_bytearray_base(subfmt, s):
  return select_parse_base(subfmt, s)[0]

def select_restfunc_base(subfmt, s):
  return select_parse_base(subfmt, s)[1] 

def select_parse_base(subfmt, s):
  # unpack decider
  decider_unpacker = create_composite_from_parsed_fmt(subfmt[0:1], get_unpacker)
  (decider_output, decider_source) = decider_unpacker([], s)
  decision = decider_output[0]
  # get subfmt and pack sub message
  sub_unpacker_fmt = select_subfmt_to_dict(subfmt)[str(decision)]
  sub_unpacker = \
      create_composite_from_parsed_fmt(sub_unpacker_fmt, get_unpacker)
  (sub_output, sub_source) = sub_unpacker([], decider_source)
  # return outputs
  return [decision, sub_output], sub_source

def select_to_bytearray_base(subfmt, s):
  # pack decider
  decider_packer = create_composite_from_parsed_fmt(subfmt[0:1], get_packer)
  decision = s[0]
  decider_output = decider_packer(bytearray(), [decision])[0]
  # get subfmt and pack sub message
  sub_packer_fmt =  select_subfmt_to_dict(subfmt)[str(decision)]
  sub_packer = create_composite_from_parsed_fmt(sub_packer_fmt, get_packer)
  (sub_output, sub_structure) = sub_packer(bytearray(), s[1])
  return decider_output + sub_output

def fmt_grammar():
  open_paren = pp.Literal("(").suppress()
  close_paren = pp.Literal(")").suppress()
  string = pp.Literal("S")
  int32 = pp.Literal("I")
  boolean = pp.Literal("b")
  byte = pp.Literal("B")
  int64 = pp.Literal("L")
  array_region = pp.Literal("A")
  tagged_value = pp.Literal("V")
  tagged_object_id = pp.Literal("T")
  location = pp.Literal("X")
  atomic = (string | int32 | boolean | byte | int64 | location |
      tagged_object_id | tagged_value | array_region)
  fmt_type = pp.Forward()
  repeat = pp.Group( pp.Literal("R") + open_paren + fmt_type + close_paren)
  option = pp.Group(pp.Regex("[0-9]+") + pp.Literal("=").suppress() + fmt_type)
  or_symbol = pp.Literal("|").suppress()
  select = pp.Group(pp.Literal("?") + pp.Literal("B") +
      open_paren + option + pp.ZeroOrMore(or_symbol + option) + close_paren)
  fmt_type << pp.ZeroOrMore(atomic | repeat | select)
  return fmt_type

transform_specs = { 'I': fixed_length_transform_spec("I"),
                    'B': fixed_length_transform_spec("B"),
                    'L': fixed_length_transform_spec("Q"),
                    'T': fixed_length_transform_spec("BQ"),
                    'X': fixed_length_transform_spec("BQQQ"),
                    'b': boolean,
                    'S': string,
                    'R': transform_spec_from_base_functions(
                             repeat_to_bytearray_base,
                             repeat_from_bytearray_base,
                             repeat_restfunc_base),
                    '?': transform_spec_from_base_functions(
                             select_to_bytearray_base,
                             select_from_bytearray_base,
                             select_restfunc_base) }
