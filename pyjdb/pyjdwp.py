import logging
import pkg_resources
import pyparsing
import re
import socket
import struct
import threading
import time

class Error(Exception):
    """Pyjdwp module-level error"""
    pass

class Timeout(Error):
    """Pyjdwp module-level error used specificallly for timeouts"""
    pass

JDWP_PACKET_HEADER_LENGTH = 11

STRUCT_FMTS_BY_SIZE_UNSIGNED = {1: "B", 4: "I", 8: "Q"}

STRUCT_FMT_BY_TYPE_TAG = {
        '[': "?",
        'B': "B",
        'C': "H",  # H = 2 byte ushort
        'L': "?",
        'F': "f",
        'D': "d",
        'I': "i",
        'J': "q",
        'S': "h",
        'Z': "B",
        's': "?",
        't': "?",
        'g': "?",
        'l': "?",
        'c': "?"}


class GenericService(object):
    def __init__(self, jdwp, command_set):
        self.__jdwp = jdwp
        self.__command_set = command_set
        for cmd_name in self.__command_set.commands:
            def create_lambda(name):
                return lambda data={}: self.__jdwp.command_request(
                        self.__command_set.name, name, data)
            setattr(self, cmd_name, create_lambda(cmd_name))


class GenericConstantSet(object):
    def __init__(self, constant_set):
        for constant_name in constant_set.constants:
            constant = constant_set.constants[constant_name]
            setattr(self, constant_name, constant.value)


class RequestIdGenerator(object):
    def __init__(self):
        self.__lock = threading.RLock()
        self._next_id = 1

    @property
    def next_id(self):
        with self.__lock:
            result = self._next_id
            self._next_id += 1
        return result

    @next_id.setter
    def next_id(self, value):
        with self.__lock:
            self._next_id = value


class Jdwp(object):
    def __init__(self, host="localhost", port=5005, timeout=10):
        logging.info("Create jdwp object for %s:%d", host, port)
        self.__timeout = timeout
        self.__request_id_generator = RequestIdGenerator()
        self.__event_cbs = []
        self.__conn = JdwpConnection(host, port, self.handle_packet)
        self.__event_cv = threading.Condition()
        self.__reply_cv = threading.Condition()
        self.__replies = {}
        self.__events = []
        # background thread for calling self.__event_cbs as new events come in.
        # we use a separate thread for this so that JdwpConnection's
        # __reader_thread need not block while we handle events.
        self.__notifier_thread = threading.Thread(
                target = self.__event_notify_loop, name = "jdwp_event_notifier")
        self.__notifier_thread.setDaemon(True)
        # lock for synchronizing access to self.__notifier_running
        self.__running_lock = threading.Lock()
        logging.info("Jdwp object created")

    def register_event_callback(self, event_cb):
        logging.info("Register event callback")
        with self.__event_cv:
            self.__event_cbs.append(event_cb)

    def unregister_event_callback(self, event_cb):
        logging.info("Unregister event callback")
        with self.__event_cv:
            self.__event_cbs.remove(event_cb)

    def initialize(self):
        logging.info("Unregister event callback")
        # As soon as we call this, events (e.g., vm_start) may be incoming.
        self.__conn.initialize()
        self.__await_vm_start()
        version = self.__hardcoded_version_request()
        id_sizes = self.__hardcoded_id_sizes_request()
        self.jdwp_spec = JdwpSpec(version, id_sizes)
        for command_set_name in self.jdwp_spec.command_sets:
            command_set = self.jdwp_spec.command_sets[command_set_name]
            setattr(self, command_set_name, GenericService(self, command_set))
        for constant_set_name in self.jdwp_spec.constant_sets:
            constant_set = self.jdwp_spec.constant_sets[constant_set_name]
            setattr(self, constant_set_name, GenericConstantSet(constant_set))
        self.__notifier_running = True
        self.__notifier_thread.start()

    def command_request(self, command_set_name, command_name, data):
        command = self.jdwp_spec.lookup_command(command_set_name, command_name)
        req_id = self.__request_id_generator.next_id
        command_set_id = command.command_set_id
        command_id = command.id
        payload = command.encode(data)
        self.__conn.send(req_id, command_set_id, command_id, payload)
        reply_payload = self.__await_reply(req_id)
        return command.decode(reply_payload)

    def disconnect(self):
        self.__conn.disconnect()

    def handle_packet(self, req_id, flags, err, payload):
        #print("PACKET: %d, %d, %d, %d" % (req_id, flags, err, len(payload)))
        if err == 0x4064:
            with self.__event_cv:
                self.__events.append((req_id, payload))
                self.__event_cv.notify()
            return
        with self.__reply_cv:
            if req_id in self.__replies:
                raise Error("More than one reply packet for req_id %d" % req_id)
            self.__replies[req_id] = (err, payload)
            self.__reply_cv.notify()

    def await_event(self, matcher_fn):
        cv = threading.Condition()
        found_events = []
        def callback(event, found=found_events):
            with cv:
                if matcher_fn(event):
                    found.append(event)
                    cv.notify()
        self.register_event_callback(callback)
        with cv:
            while not found_events:
                cv.wait(.1)
        self.unregister_event_callback(callback)
        return found_events[0]

    def __event_notify_loop(self):
        while True:
            with self.__running_lock:
                if not self.__notifier_running:
                    return
            with self.__event_cv:
                while not self.__events:
                    self.__event_cv.wait(.1)
                self.__event_notify()

    # this must only ever be called with a lock on self.__event_cv already held.
    def __event_notify(self):
        notified = []
        command = self.jdwp_spec.lookup_command("Event", "Composite")
        for jvm_req_id, event_payload in self.__events:
            event = command.decode(event_payload)
            for event_cb in self.__event_cbs:
                try:
                    event_cb(event)
                except Exception as e:
                    print("Event notification failed for %s " % event_cb)
                    print(e)
                    # TODO(cgs): should we remove event_cb? think about this
                    continue
            notified.append((jvm_req_id, event_payload))
        for entry in notified:
            self.__events.remove(entry)

    def __await_reply(self, req_id):
        """Blocks until a reply is received for "req_id"; raises pyjdwp.Error
        if err != 0, returns reply otherwise"""
        start_time = time.time()
        with self.__reply_cv:
            while req_id not in self.__replies:
                if time.time() >= start_time + self.__timeout:
                    raise Timeout("Timed out")
                self.__reply_cv.wait(.1)
            err, reply = self.__replies[req_id]
            del self.__replies[req_id]
        if err != 0:
            raise Error("JDWP error: %s" % err)
        return reply

    def __await_vm_start(self):
        found_event = False
        with self.__event_cv:
            while not found_event:
                for jvm_req_id, payload in self.__events:
                    if len(payload) < 6:
                        continue
                    _, _, event_kind = struct.unpack(">BIB", payload[0 : 6])
                    if event_kind == 90:  # vm_start
                        found_event = True
                        break
                self.__event_cv.wait(.1)

    def __hardcoded_version_request(self):
        req_id = self.__request_id_generator.next_id
        self.__conn.send(req_id, 1, 1)
        version_data = self.__await_reply(req_id)
        desc_len = 4 + struct.unpack(">I", version_data[0:4])[0]
        minor_version = struct.unpack(
                ">I", version_data[desc_len + 4: desc_len + 8])[0]
        return minor_version

    def __hardcoded_id_sizes_request(self):
        req_id = self.__request_id_generator.next_id
        self.__conn.send(req_id, 1, 7)
        id_size_data = self.__await_reply(req_id);
        id_size_names = [
                "fieldIDSize",
                "methodIDSize",
                "objectIDSize",
                "referenceTypeIDSize",
                "frameIDSize"]
        id_sizes = list(struct.unpack(">IIIII", id_size_data))
        return dict(zip(id_size_names, id_sizes))


class JdwpConnection(object):
    def __init__(self, host, port, packet_callback=None):
        # the host:port our target jvm is listening on for jdwp connections
        self.__host = host
        self.__port = port
        # the socket we use to communicate with the jvm (connection is later)
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.__socket.settimeout(1.0)
        # callback for notifying of received jdwp packet (may be an event or
        # a response to a previous request). this should return quickly, as it
        # blocks self.__reader_thread
        self.__packet_callback = packet_callback
        # lock for synchronizing requests (only one at a time outgoing to jvm)
        self.__request_lock = threading.Lock()
        # background thread for receiving packets from jvm. runs as long as
        # self.__listening == True
        self.__reader_thread = threading.Thread(
                target = self.__listen, name = "jdwp_listener")
        self.__reader_thread.setDaemon(True)
        # lock for synchronizing access to self.__listening
        self.__listening_lock = threading.Lock()

    def initialize(self):
        logging.info("Initializing socket connection to jdwp host")
        # open socket to jvm
        tries = 100
        while True:
            tries -= 1
            try:
                self.__socket.connect((self.__host, self.__port))
                break
            except socket.error as e:
                if tries > 0:
                    time.sleep(.1)
                    continue
                logging.error("Failed after many retries; this isn't gonna work")
                raise e
        # jdwp handshake
        handshake = b"JDWP-Handshake"
        logging.info("Sending handshake")
        self.__socket.send(handshake)
        logging.info("Awaiting handshake")
        data = self.__socket.recv(len(handshake))
        if data != handshake:
            logging.error("Handshake failed; got something else.")
            self.__socket.close()
            raise Error("Handshake failed")
        # start listening for jdwp packets
        self.__listening = True
        logging.info("Starting reader thread")
        self.__reader_thread.start()

    def send(self, req_id, cmd_set_id, cmd_id, payload=None):
        if payload is None:
            payload = bytearray()
        length = JDWP_PACKET_HEADER_LENGTH + len(payload)
        header = struct.pack(">IIBBB", length, req_id, 0, cmd_set_id, cmd_id)
        with self.__request_lock:
            self.__socket.send(header + payload)

    def disconnect(self):
        self.__socket.close();
        with self.__listening_lock:
            self.__listening = False
        self.__reader_thread.join(1.0)

    def __listen(self):
        while True:
            with self.__listening_lock:
                if not self.__listening:
                    return
            try:
                header = self.__socket.recv(JDWP_PACKET_HEADER_LENGTH);
            except socket.error as e:
                continue
            if len(header) != JDWP_PACKET_HEADER_LENGTH:
                continue
            length, req_id, flags, err = struct.unpack(">IIBH", header)
            remaining = length - JDWP_PACKET_HEADER_LENGTH
            msg = bytearray()
            while remaining > 0:
                chunk = self.__socket.recv(min(remaining, 4096))
                msg.extend(chunk)
                remaining -= len(chunk)
            # TODO(cgs): why do we need to do this string voodoo?
            payload = "".join([chr(x) for x in msg])
            self.__packet_callback(req_id, flags, err, payload)
                

class JdwpSpec(object):
    def __init__(self, version, id_sizes):
        spec_file_name = "specs/jdwp.spec_openjdk_%d" % version
        jdwp_text = pkg_resources.resource_string(__name__, spec_file_name)
        self.__clean_spec_text = re.sub("\s*=\s*", "=", jdwp_text)
        self.__spec = GRAMMAR_JDWP_SPEC.parseString(self.__clean_spec_text)
        self.id_sizes = id_sizes
        self.command_sets = {}
        self.constant_sets = {}
        for entry in self.__spec:
            if entry[0] == "ConstantSet":
                constant_set = ConstantSet(entry)
                self.constant_sets[constant_set.name] = constant_set
        for entry in self.__spec:
            if entry[0] == "CommandSet":
                command_set = CommandSet(self, entry)
                self.command_sets[command_set.name] = command_set

    def lookup_command(self, command_set_name, command_name):
        if command_set_name not in self.command_sets:
            raise Error("Unknown command set: %s" % command_set_name)
        command_set = self.command_sets[command_set_name]
        if command_name not in command_set.commands:
            raise Error("Unknown command: %s, %s" % (
                    command_set_name, command_name))
        return command_set.commands[command_name]

    def lookup_constant(self, constant_set_name, constant_name):
        if constant_set_name not in self.constant_sets:
            raise Error("Unknown constant set: %s" % constant_set_name)
        constant_set = self.constant_sets[constant_set_name]
        if constant_name not in constant_set.constants:
            raise Error("Unknown constant: %s, %s" % (
                    constant_set_name, constant_name))
        return constant_set.constants[constant_name]

    def lookup_id_size(self, type_name):
        lookup_fn_by_type = {
            "byte":    lambda id_sizes: 1,
            "boolean":    lambda id_sizes: 1,
            "int":    lambda id_sizes: 4,
            "long":    lambda id_sizes: 8,
            "object":    lambda id_sizes: id_sizes["objectIDSize"],
            "objectID":    lambda id_sizes: id_sizes["objectIDSize"],
            "threadID":    lambda id_sizes: id_sizes["objectIDSize"],
            "threadObject":    lambda id_sizes: id_sizes["objectIDSize"],
            "threadGroupID":    lambda id_sizes: id_sizes["objectIDSize"],
            "threadGroupObject":    lambda id_sizes: id_sizes["objectIDSize"],
            "stringID":    lambda id_sizes: id_sizes["objectIDSize"],
            "stringObject":    lambda id_sizes: id_sizes["objectIDSize"],
            "classLoaderID":    lambda id_sizes: id_sizes["objectIDSize"],
            "classLoaderObject":    lambda id_sizes: id_sizes["objectIDSize"],
            "classObjectID":    lambda id_sizes: id_sizes["objectIDSize"],
            "arrayID":    lambda id_sizes: id_sizes["objectIDSize"],
            "referenceType":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "referenceTypeID":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "classID":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "classType":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "classObject":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "interfaceID":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "interfaceType":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "arrayObject":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "arrayType":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "arrayTypeID":    lambda id_sizes: id_sizes["referenceTypeIDSize"],
            "method":    lambda id_sizes: id_sizes["methodIDSize"],
            "methodID":    lambda id_sizes: id_sizes["methodIDSize"],
            "field":    lambda id_sizes: id_sizes["fieldIDSize"],
            "fieldID":    lambda id_sizes: id_sizes["fieldIDSize"],
            "frame":    lambda id_sizes: id_sizes["frameIDSize"],
            "frameID":    lambda id_sizes: id_sizes["frameIDSize"] }
        return lookup_fn_by_type[type_name](self.id_sizes)

    def lookup_value_size_by_type_tag(self, type_tag):
        # These are copied from the *comments* of the TagType constant_set in
        # the spec
        lookup_fn_by_type_tag = {
            '[': lambda id_sizes: id_sizes["objectIDSize"],  # ARRAY
            'B': lambda id_sizes: 1,  # BYTE
            'C': lambda id_sizes: 2,  # CHAR
            'L': lambda id_sizes: id_sizes["objectIDSize"],  # OBJECT
            'F': lambda id_sizes: 4,  # FLOAT
            'D': lambda id_sizes: 8,  # DOUBLE
            'I': lambda id_sizes: 4,  # INT
            'J': lambda id_sizes: 8,  # LONG
            'S': lambda id_sizes: 2,  # SHORT
            'V': lambda id_sizes: 0,  # VOID
            'Z': lambda id_sizes: 1,  # BOOLEAN
            's': lambda id_sizes: id_sizes["objectIDSize"],  # STRING
            't': lambda id_sizes: id_sizes["objectIDSize"],  # THREAD
            'g': lambda id_sizes: id_sizes["objectIDSize"],  # THREAD_GROUP
            'l': lambda id_sizes: id_sizes["objectIDSize"],  # CLASS_LOADER
            'c': lambda id_sizes: id_sizes["objectIDSize"],  # CLASS_OBJECT
        }
        return lookup_fn_by_type_tag[type_tag](self.id_sizes)

    def decode_value_bytes_for_type_tag(self, type_tag, value_bytes, count=1):
        void_tag = self.lookup_constant("Tag", "VOID").value
        if type_tag == void_tag or value_bytes is None:
            return (None,)
        value_len = self.lookup_value_size_by_type_tag(type_tag)
        struct_fmt = STRUCT_FMT_BY_TYPE_TAG[type_tag]
        if struct_fmt == "?":
            struct_fmt = "B%s" % STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len]
            value_len += 1
            unpack_fmt = ">%s" % (struct_fmt * count)
            result = struct.unpack(unpack_fmt, value_bytes[0 : count * value_len])
            result = zip(result[::2], result[1::2])
        else:
            unpack_fmt = ">%s" % (struct_fmt * count)
            result = struct.unpack(unpack_fmt, value_bytes[0 : count * value_len])
        return result

    def encode_value_bytes_for_type_tag(self, type_tag, value):
        if type_tag == 'V' and value is None:
            return bytearray()
        value_len = self.lookup_value_size_by_type_tag(type_tag)
        encode_fn_by_type_tag = {
            '[': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            'B': lambda val: struct.pack(">B", val),
            'C': lambda val: chr(struct.pack(">H", val)),  # H = 2 byte ushort
            'L': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            'F': lambda val: struct.pack(">f", val),
            'D': lambda val: struct.pack(">d", val),
            'I': lambda val: struct.pack(">i", val),
            'J': lambda val: struct.pack(">q", val),
            'S': lambda val: struct.pack(">h", val),
            'V': lambda val: None,
            'Z': lambda val: (struct.pack(">B", val) != 0),
            's': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            't': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            'g': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            'l': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
            'c': lambda val: struct.pack(
                    ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len], val),
        }
        value_bytes = encode_fn_by_type_tag[type_tag](value)
        return bytearray(value_bytes)

class ConstantSet(object):
    def __init__(self, constant_set):
        self.name = constant_set[1]
        self.constants = {}
        for constant_entry in constant_set[2 : ]:
            constant = Constant(constant_entry)
            self.constants[constant.name] = constant


class Constant(object):
    def __init__(self, constant):
        [self.name, value_str] = constant[1].split("=")
        if value_str.startswith("0x"):
            self.value = int(value_str, 16)
        elif value_str.startswith("'"):
            self.value = value_str.split("'")[1]
        else:
            try:
                self.value = int(value_str)
            except ValueError:
                self.value = value_str


class CommandSet(object):
    def __init__(self, spec, command_set):
        self.spec = spec
        [self.name, self.id] = command_set[1].split("=")
        self.id = int(self.id)
        self.commands = {}
        for command_entry in command_set[2 : ]:
            command = Command(spec, self.id, command_entry)
            self.commands[command.name] = command


class Command(object):
    def __init__(self, spec, command_set_id, command):
        self.spec = spec
        self.command_set_id = command_set_id
        [self.name, self.id] = command[1].split("=")
        self.id = int(self.id)
        if command[2][0] == "Event":
            self.request = Request(spec, [])
            self.response = Response(spec, command[2])
            self.errors = []
        else:
            self.request = Request(spec, command[2])
            self.response = Response(spec, command[3])
            self.errors = [ ErrorRef(spec, error) for error in command[4] ]

    def encode(self, data):
        return self.request.encode(data)

    def decode(self, data):
        return self.response.decode(data)


def create_arg_from_spec(spec, arg):
    arg_type = arg[0]
    type_map = {
            "Repeat": Repeat,
            "Group": Group,
            "Select": Select,
            "location": Location,
            "string": String,
            "untagged-value": UntaggedValue,
            "value": Value,
            "tagged-object": TaggedObject,
            "typed-sequence": TypedSequence}
    if arg_type in type_map:
        return type_map[arg_type](spec, arg)
    else:
        return Primitive(spec, arg)


class Request(object):
    def __init__(self, spec, request):
        self.spec = spec
        self.args = [ create_arg_from_spec(spec, arg) for arg in request[1 : ] ]

    def encode(self, data):
        result = bytearray()
        for arg in self.args:
            data, result = arg.encode(data, result)
        return result


class Response(object):
    def __init__(self, spec, response):
        self.spec = spec
        self.args = [ create_arg_from_spec(spec, arg) for arg in response[1 : ] ]

    def decode(self, data):
        result = {}
        for arg in self.args:
            data, result = arg.decode(data, result)
        return result

class String(object):
    def __init__(self, spec, string):
        self.spec = spec
        self.name = string[1]

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        strlen = struct.unpack(">I", data[0 : 4])[0]
        fmt = str(strlen) + "s"
        subdata = data[4 : 4 + strlen]
        string_value = struct.unpack(fmt, subdata)[0].decode("UTF-8")
        accum[self.name] = string_value
        return data[4+strlen:], accum

    def encode(self, data, accum):
        value = data[self.name]
        strlen = len(value)
        fmt = str(strlen) + "s"
        accum += struct.pack(">I", len(value))
        accum += bytearray(value, "UTF-8")
        return data, accum


class Value(object):
    def __init__(self, spec, value):
        self.spec = spec
        self.name = value[1]

    def decode(self, data, accum=None):
        # first byte is the tag type
        type_tag = data[0]
        value_len = self.spec.lookup_value_size_by_type_tag(type_tag)
        void_tag = self.spec.lookup_constant("Tag", "VOID").value
        if type_tag == void_tag:
            accum[self.name] = {
                    "typeTag": void_tag,
                    "value": None}
            return data[1 : ], accum
        struct_fmt = STRUCT_FMT_BY_TYPE_TAG[type_tag]
        if struct_fmt == "?":
            struct_fmt = STRUCT_FMTS_BY_SIZE_UNSIGNED[value_len]
        unpack_fmt = ">%s" % struct_fmt
        value = struct.unpack(unpack_fmt, data[1 : 1 + value_len])[0]
        accum[self.name] = {
                "typeTag": type_tag,
                "value": value}
        return data[1 + value_len : ], accum

    def encode(self, data, accum):
        value = data[self.name]
        accum += bytearray(value["typeTag"])
        accum += self.spec.encode_value_bytes_for_type_tag(
                 value["typeTag"], value["value"])
        return data, accum


class UntaggedValue(object):
    def __init__(self, spec, untagged_value):
        self.spec = spec
        self.name = untagged_value[1]

    def encode(self, data, accum):
        accum += self.spec.encode_value_bytes_for_type_tag(
                data["value"]["typeTag"], data["value"]["value"])
        return data, accum


class TaggedObject(object):
    def __init__(self, spec, tagged_object):
        self.spec = spec
        self.name = tagged_object[1]

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        type_tag = data[0]
        object_id_size = self.spec.id_sizes["objectIDSize"]
        object_id = struct.unpack(
                ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[object_id_size],
                data[1 : 1 + object_id_size])[0],
        accum[self.name] = {
                "typeTag": type_tag,
                "objectID": object_id[0]}
        return data[1 + object_id_size : ], accum


class TypedSequence(object):
    def __init__(self, spec, typed_sequence):
        self.spec = spec
        self.name = typed_sequence[1]

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        type_tag = data[0]
        entry_count = struct.unpack(">I", data[1:5])[0]
        value_len = self.spec.lookup_value_size_by_type_tag(type_tag)
        if STRUCT_FMT_BY_TYPE_TAG[type_tag] == "?":
            value_len += 1
        value = self.spec.decode_value_bytes_for_type_tag(
                type_tag,
                data[5 : ],
                count=entry_count)
        accum[self.name] = value
        return data[5 + entry_count * value_len : ], accum


class Primitive(object):
    def __init__(self, spec, simple):
        self.spec = spec
        self.type = simple[0]
        self.name = simple[1]

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        if self.type == "binary":
            accum[self.name] = (struct.unpack(">B", data[0])[0] != 0)
            return data[1 : ], accum
        size = self.spec.lookup_id_size(self.type)
        fmt = ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[size]
        accum[self.name] = struct.unpack(fmt, data[0 : size])[0]
        return data[size:], accum

    def encode(self, data, accum):
        value = data[self.name]
        if self.type == "binary":
            accum += bytearray(struct.pack(">B", int(value)))
        elif self.type == "int":
            fmt = ">i"
            accum += bytearray(struct.pack(fmt, value))
        else:
            size = self.spec.lookup_id_size(self.type)
            fmt = ">" + STRUCT_FMTS_BY_SIZE_UNSIGNED[size]
            accum += bytearray(struct.pack(fmt, value))
        return data, accum


class Repeat(object):
    def __init__(self, spec, repeat):
        self.spec = spec
        self.name = repeat[1]
        self.arg = create_arg_from_spec(spec, repeat[2])

    def encode(self, data, accum):
        values = data[self.name]
        accum += struct.pack(">I", len(values))
        for value in values:
            _, accum = self.arg.encode(value, accum)
        return data, accum

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        count = struct.unpack(">I", data[0 : 4])[0]
        accum[self.name] = []
        data = data[4 : ]
        for i in range(count):
            data, subaccum = self.arg.decode(data, {})
            accum[self.name].append(subaccum)
        return data, accum


class Group(object):
    def __init__(self, spec, group):
        self.spec = spec
        self.name = group[1]
        self.args = [ create_arg_from_spec(spec, arg) for arg in group[2 : ] ]

    def encode(self, data, accum):
        for arg in self.args:
            _, accum = arg.encode(data, accum)
        return data, accum

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        for arg in self.args:
            data, accum = arg.decode(data, accum)
        return data, accum


class Location(Group):
    def __init__(self, spec, loc):
        self.spec = spec
        self.name = loc[1]
        self.args = [
                Primitive(spec, ("byte", "typeTag")),
                Primitive(spec, ("referenceTypeID", "classID")),
                Primitive(spec, ("methodID", "methodID")),
                Primitive(spec, ("long", "index"))]

class Select(object):
    def __init__(self, spec, select):
        self.spec = spec
        self.name = select[1]
        self.choice_arg = create_arg_from_spec(spec, select[2])
        self.alts = {}
        for alt_spec in select[3 : ]:
            alt = Alt(spec, alt_spec)
            self.alts[int(alt.position)] = alt

    def encode(self, data, accum):
        choice = data[self.choice_arg.name]
        data, accum = self.choice_arg.encode(data, accum)
        alt = self.alts[choice]
        _, accum = alt.encode(data, accum)
        return data, accum

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        # pop the choice byte off the top
        data, result = self.choice_arg.decode(data)
        choice = result[self.choice_arg.name]
        alt = self.alts[choice]
        return alt.decode(data, result)


class Alt(object):
    def __init__(self, spec, alt):
        self.spec = spec
        [self.name, self.position] = alt[1].split("=")
        # some spec alternates are identified by constant name, so we do the
        # lookup here.
        if not re.match("[0-9]+", self.position):
            val_name = self.position.split(".")[2]
            constant = spec.lookup_constant("EventKind", val_name)
            self.position = constant.value
        self.args = []
        for arg_spec in alt[2 : ]:
            self.args.append(create_arg_from_spec(spec, arg_spec))

    def encode(self, data, accum):
        result = bytearray()
        for arg in self.args:
            data, result = arg.encode(data, result)
        accum += result
        return data, accum

    def decode(self, data, accum=None):
        if accum is None:
            accum = {}
        result = {}
        for arg in self.args:
            data, result = arg.decode(data, result)
        accum[self.name] = result
        return data, accum


class ErrorRef(object):
  def __init__(self, spec, error):
    self.spec = spec
    self.name = error[1]


SPEC_GRAMMAR_OPEN_PAREN = pyparsing.Literal("(").suppress()
SPEC_GRAMMAR_CLOSE_PAREN = pyparsing.Literal(")").suppress()
SPEC_GRAMMAR_QUOTED_STRING = pyparsing.dblQuotedString
SPEC_GRAMMAR_QUOTED_STRING = SPEC_GRAMMAR_QUOTED_STRING.suppress()
SPEC_GRAMMAR_SPEC_STRING = pyparsing.OneOrMore(SPEC_GRAMMAR_QUOTED_STRING)
SPEC_GRAMMAR_S_EXP = pyparsing.Forward()
SPEC_GRAMMAR_STRING = SPEC_GRAMMAR_SPEC_STRING | pyparsing.Regex("([^()\s])+")
SPEC_GRAMMAR_S_EXP_LIST = pyparsing.Group(SPEC_GRAMMAR_OPEN_PAREN +
    pyparsing.ZeroOrMore(SPEC_GRAMMAR_S_EXP) + SPEC_GRAMMAR_CLOSE_PAREN)
SPEC_GRAMMAR_S_EXP << ( SPEC_GRAMMAR_STRING | SPEC_GRAMMAR_S_EXP_LIST )
GRAMMAR_JDWP_SPEC = pyparsing.OneOrMore(SPEC_GRAMMAR_S_EXP)

ACCESS_MODIFIER_PUBLIC = 0x0001
ACCESS_MODIFIER_FINAL = 0x0010
ACCESS_MODIFIER_SUPER = 0x0020 # old invokespecial instruction semantics (Java 1.0x?)
ACCESS_MODIFIER_INTERFACE = 0x0200
ACCESS_MODIFIER_ABSTRACT = 0x0400
ACCESS_MODIFIER_SYNTHETIC = 0x1000 
ACCESS_MODIFIER_ANNOTATION = 0x2000
ACCESS_MODIFIER_ENUM = 0x4000
ACCESS_MODIFIERS = {
    0x0001: "public",
    0x0010: "final",
    0x0020: "super",
    0x0200: "interface",
    0x0400: "abstract",
    0x1000: "synthetic",
    0x2000: "annotation",
    0x4000: "enum"
}

