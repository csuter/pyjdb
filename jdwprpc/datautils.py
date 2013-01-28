import jdwprpc
import pyparsing as pp
import struct

def pack_jdwp_request(cmd_set_id, cmd_id, request_data_unpacked):
  key = jdwprpc.command_specs_key(cmd_set_id, cmd_id)
  fmt = jdwprpc.COMMAND_SPECS[key][2]
  return pack_jdwp_data(fmt, request_data_unpacked)

def unpack_jdwp_reply(cmd_set_id, cmd_id, reply_data_packed):
  key = jdwprpc.command_specs_key(cmd_set_id, cmd_id)
  fmt = jdwprpc.COMMAND_SPECS[key][3]
  result, size = unpack_jdwp_data(fmt, reply_data_packed)
  return result

def unpack_jdwp_data(fmt, packed_data):
  '''somehow, magically unpacks wire data structures correctly most of the
  time, using this ill-defined weird little shorthand I (cgs) invented. should
  be rewritten using pyparsing and a well-defined weird little shorthand. this
  is sort of an inverse to pack_jdwp_data.'''
  #print("fmt: %s" % fmt)
  #print("packed_data: %s" % bytes_to_hex_string(packed_data))
  result = []
  pos = 0
  in_paren = 0
  size = 0
  idx = 0
  while idx < len(fmt):
    c = fmt[idx]
    if in_paren > 0:
      if c == '(':
        in_paren += 1
      elif c == ')':
        in_paren -= 1
      idx += 1
      continue
    if c == 'S':
      strlen = struct.unpack(">I", packed_data[pos:pos+4])[0]
      result.append(struct.unpack(str(strlen) + "s",
          packed_data[pos+4:pos+strlen+4])[0].decode('UTF-8'))
      size += 4 + strlen
      pos += 4 + strlen
    elif c == 'I':
      result.append(struct.unpack(">I", packed_data[pos:pos+4])[0])
      size += 4
      pos += 4
    elif c == 'b':
      result.append(struct.unpack(">B", packed_data[pos:pos+1])[0] != 0)
      size += 1
      pos += 1
    elif c == 'B':
      result.append(struct.unpack(">B", packed_data[pos:pos+1])[0])
      size += 1
      pos += 1
    elif c == 'L':
      result.append(struct.unpack(">Q", packed_data[pos:pos+8])[0])
      size += 8
      pos += 8
    elif c == 'V':
      tag = struct.unpack(">B", packed_data[0])
      data_size = tag_constants_data_sizes[tag]
      fmt = ">" + "B" * data_size
      value = struct.unpack(fmt, packed_data[1:])
      result.append(tag, value)
      size += 1 + data_size
      pos += 1 + data_size
    elif c == 'T':
      type_tag, object_id = struct.unpack(">BQ", packed_data[pos:pos+9])
      result.append((type_tag, object_id))
      size += 9
      pos += 9
    elif c == 'X':
      type_tag, class_id, method_id, index = \
          struct.unpack(">BQQQ", packed_data[pos:pos+25])
      result.append((type_tag, class_id, method_id, index))
      size += 25
      pos += 25
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION UNPACKING")
    elif c == '?':
      event_kind = struct.unpack(">B", packed_data[pos:pos+1])[0]
      result.append(event_kind)
      sub_data_fmt = get_paren_substr_after(fmt, idx+1)
      clauses = dict((int(k), v)
          for (k, v) in (x.split("=") for x in sub_data_fmt.split("|")))
      sub_result, sub_result_size = unpack_jdwp_data(
          clauses[event_kind], packed_data[pos+1:])
      result.append(sub_result)
      size += 1 + sub_result_size
      idx += 1
      pos += 1
    elif c == 'R':
      num = struct.unpack(">I", packed_data[pos:pos+4])[0]
      pos += 4
      sub_result = []
      if fmt[idx+1] != '(':
        raise Exception("jdi_data fmt exception: expect '(' after 'R'")
      close_paren = find_close_paren(fmt, idx+1)
      if close_paren == -1:
        raise Exception("jdi_data fmt exception: no matching ')'")
      sub_data_fmt = fmt[idx+2:close_paren]
      for i in range(num):
        sub_data, sub_size = unpack_jdwp_data(
            sub_data_fmt, packed_data[pos:])
        pos += sub_size
        size += sub_size
        sub_result.append(sub_data)
      result.extend(sub_result)
    elif c == '(':
      in_paren = 1
    idx += 1
  return result, size

def pack_jdwp_data(fmt, unpacked_data):
  '''somehow, magically packs data structures correctly for wire transport most
  of the time, using this ill-defined weird little shorthand I (cgs) invented.
  should be rewritten using pyparsing and a well-defined weird little
  shorthand. this is sort of an inverse to unpack_jdwp_data.'''
  result = bytearray()
  pos = 0
  in_paren = 0
  idx = 0
  while idx < len(fmt):
    c = fmt[idx]
    if in_paren > 0:
      if c == '(':
        in_paren += 1
      elif c == ')':
        in_paren -= 1
      idx += 1
      continue
    elif c == 'B':
      result.extend(struct.pack(">B", unpacked_data[pos]))
      pos += 1
    elif c == 'b':
      result.extend(struct.pack(">B", unpacked_data[pos]))
      pos += 1
    elif c == 'I':
      result.extend(struct.pack(">I", unpacked_data[pos]))
      pos += 1
    elif c == 'L':
      result.extend(struct.pack(">Q", unpacked_data[pos]))
      pos += 1
    elif c == 'S':
      strlen = len(unpacked_data[pos])
      result.extend(struct.pack(">I", strlen))
      result.extend(bytearray(unpacked_data[pos],"UTF-8"))
      pos += 1
    elif c == 'A':
      raise Exception("IMPLEMENT ARRAY REGION PACKING")
    elif c == '?':
      type_tag = unpacked_data[0]
      rest = unpacked_data[1:]
      type_tag_fmt = fmt[idx+1:idx+2]
      result.extend(pack_jdwp_data(type_tag_fmt, [type_tag]))
      sub_data_fmt = get_paren_substr_after(fmt, idx+1)
      clauses = dict((int(k), v) for (k, v) in (x.split("=") \
          for x in sub_data_fmt.split("|")))
      result.extend(pack_jdwp_data(clauses[type_tag], rest))
      idx += 1
      pos += 1
    elif c == 'R':
      num = len(unpacked_data[pos])
      result.extend(struct.pack(">I", num))
      sub_result = bytearray()
      sub_data_fmt = get_paren_substr_after(fmt, idx)
      for i in range(num):
        sub_data = pack_jdwp_data(sub_data_fmt, unpacked_data[pos][i])
        sub_result.extend(sub_data)
      pos += 1
      result.extend(sub_result)
    elif c == '(':
      in_paren = 1
    else:
      raise Exception(
          "Unrecognized fmt char %s at %s in \"%s\" unpacked_data: \"%s\"" % \
              (c, idx, fmt, unpacked_data))
    idx += 1
  #print("fmt: %s" % fmt)
  #print("packed_data: %s" % bytes_to_hex_string(result))
  return result

def proto_to_unpacked_data(proto):
  fields = []
  if hasattr(proto, '_fields'):
    for field in proto._fields:
      value = proto._fields[field]
      if field.label == 3:
        unpacked_data = [ proto_to_data(entry) for entry in value ]
      else:
        unpacked_data = proto_to_unpacked_data(value)
      fields.append((field.number, unpacked_data))
    fields = [ entry[1] for entry in sorted(fields, key = lambda k:k[0]) ]
  else:
    fields = [ proto ]
  return fields

def find_close_paren(string, start):
  count = 1
  if string[start] == '(':
    idx = start + 1
  else:
    idx = start
  while count > 0:
    if string[idx] == '(':
      count += 1
    elif string[idx] == ')':
      count -= 1
    idx += 1
  return idx-1

def get_paren_substr_after(fmt, idx):
  if fmt[idx+1] != '(':
    raise Exception(
        "jdwp data fmt exception: expected ( at %d of '%s'" % (idx, fmt))
  close_paren = find_close_paren(fmt, idx+1)
  if close_paren == -1:
    raise Exception(
        "jdwp data fmt exception: no matching ) for ( at %d of '%s'" % \
            (idx, fmt))
  return fmt[idx+2:close_paren]

def bytes_to_hex_string(some_bytes):
  try:
    return ''.join([ "%02X " % ord(x) for x in some_bytes ]).strip()
  except Exception, e:
    return ''.join([ "%02X " % x for x in some_bytes ]).strip()
