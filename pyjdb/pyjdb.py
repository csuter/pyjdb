"""Python library for debugging java programs. Backed by pyjdwp, a wrapper of
the Java Debug Wire Protocol (jdwp)"""
import pyjdwp
import threading


class Error(Exception):
    """Pyjdb module-level error"""
    pass


class Pyjdb(object):

    def __init__(self, host="localhost", port=5005, sourcepath="."):
        self.__debug_state_lock = threading.Condition()
        self.jdwp = pyjdwp.Jdwp(host, port)
        self.sourcepath = sourcepath
        self.class_blacklist = ["Lsun/misc/PostVMInitHook;"]
        self.classes_by_id = {}
        self.class_ids_by_sig = {}
        self.threads = {}
        self.line_index = {}
        self.class_prepare_listeners = []

    def initialize(self):
        try:
            self.jdwp.initialize()
        except pyjdwp.Error as e:
            raise e
        self.jdwp.register_event_callback(self.handle_event)
        # load up runtime metadata like known classes and running threads
        self.__initialize_event_subscriptions()
        self.__initialize_jvm_state()

    def resume(self):
        with self.__debug_state_lock:
            self.jdwp.VirtualMachine.Resume()
            for thread_id in self.threads.keys():
                self.__update_thread_status(thread_id)

    def set_breakpoint_at_line(self, filename, line_number):
        print("Setting breakpoint at %s:%d" % (filename, line_number))
        index_key = (filename, line_number)
        with self.__debug_state_lock:
            if index_key in self.line_index:
                line_index_entry = self.line_index[(filename, line_number)]
                event_request_modifier = {
                        "modKind": 7,
                        "typeTag": self.jdwp.TypeTag.CLASS,
                        "classID": line_index_entry[0],
                        "methodID": line_index_entry[1],
                        "index": line_index_entry[2]}
                resp = self.jdwp.EventRequest.Set({
                    "eventKind": self.jdwp.EventKind.BREAKPOINT,
                    "suspendPolicy": self.jdwp.SuspendPolicy.ALL,
                    "modifiers": [event_request_modifier]})
                return
        # if we get here we should set the deferred breakpoint
        self.set_deferred_breakpoint_at_line(filename, line_number)

    def set_deferred_breakpoint_at_line(self, filename, line_number):
        index_key = (filename, line_number)
        print("Setting deferred breakpoint at %s:%d" % index)
        def matches(cls, filename=filename):
            if cls["source_file"] != filename:
                return False
        def notify(cls, filename=filename, line_number=line_number):
            should_set_breakpoint = False
            with self.__debug_state_lock:
                if index_key in self.line_index:
                    should_set_breakpoint = True
            if should_set_breakpoint:
                self.set_breakpoint_at_line(filename, line_number)
        self.class_prepare_listeners.append((matches, notify))

    def disconnect(self):
        self.jdwp.disconnect()

    def handle_event(self, event_list):
        with self.__debug_state_lock:
            print("EVENT: %s", event_list)
            for event in event_list["events"]:
                if event["eventKind"] in [self.jdwp.EventKind.CLASS_PREPARE,
                        self.jdwp.EventKind.CLASS_UNLOAD]:
                    self.__update_class_metadata(event["ClassPrepare"])
                elif event["eventKind"] == self.jdwp.EventKind.THREAD_START:
                    self.__update_thread_status(event["ThreadStart"]["thread"])
                elif event["eventKind"] == self.jdwp.EventKind.THREAD_END:
                    self.__update_thread_status(event["ThreadEnd"]["thread"])
                elif event["eventKind"] == self.jdwp.EventKind.THREAD_DEATH:
                    self.__update_thread_status(event["ThreadDeath"]["thread"])

    def __class_name_to_signature(self, class_name):
        return "L%s;" % class_name.replace(".", "/")

    def __initialize_event_subscriptions(self):
        with self.__debug_state_lock:
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_UNLOAD,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.CLASS_PREPARE,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.THREAD_START,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.THREAD_END,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.THREAD_DEATH,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})
            self.jdwp.EventRequest.Set({
                "eventKind": self.jdwp.EventKind.EXCEPTION,
                "suspendPolicy": self.jdwp.SuspendPolicy.NONE,
                "modifiers": []})

    def __initialize_jvm_state(self):
        with self.__debug_state_lock:
            self.threads = {}
            threads_resp = self.jdwp.VirtualMachine.AllThreads()
            for entry in threads_resp["threads"]:
                thread_id = entry["thread"]
                thread_name = self.jdwp.ThreadReference.Name({
                    "thread": thread_id})["threadName"]
                thread_group_id = self.jdwp.ThreadReference.ThreadGroup({
                    "thread": thread_id})["group"]
                self.threads[thread_id] = {
                    "name": thread_name,
                    "thread_group_id": thread_group_id}
                self.__update_thread_status(thread_id)
            classes = self.jdwp.VirtualMachine.AllClassesWithGeneric()["classes"]
            for entry in classes:
                self.__update_class_metadata(entry)

    def __update_class_metadata(self, class_entry):
        if class_entry["signature"] in self.class_blacklist:
            return
        class_id = class_entry["typeID"]
        if class_id not in self.classes_by_id:
            self.classes_by_id[class_id] = {"typeID": class_id}
        self.class_ids_by_sig[class_entry["signature"]] = class_id
        cls = self.classes_by_id[class_id]
        cls["signature"] = class_entry["signature"]
        cls["refTypeTag"] = class_entry["signature"]
        self.__fetch_class_info(cls)
        try:
            cls["source_file"] = self.jdwp.ReferenceType.SourceFile({
                "refType": cls["typeID"]})["sourceFile"]
        except pyjdwp.Error as e:
            # No source info for class
            return
        source_file = cls["source_file"]
        for method_entry in cls["methods"]:
            try:
                self.__fetch_method_info(cls, method_entry)
            except pyjdwp.Error as e:
                continue
        # we save these to notify outside of the lock we're holding
        to_notify = []
        for matches, notify in self.class_prepare_listeners:
            if matches(cls):
                to_notify.append(notify)
        for notify in to_notify:
            notify(cls)

    def __fetch_class_info(self, cls):
        cls["access_modifier_bits"] = self.jdwp.ReferenceType.Modifiers({
            "refType": cls["typeID"]})["modBits"]
        cls["fields"] = self.jdwp.ReferenceType.FieldsWithGeneric({
            "refType": cls["typeID"]})["declared"]
        cls["methods"] = self.jdwp.ReferenceType.MethodsWithGeneric({
            "refType": cls["typeID"]})["declared"]

    def __fetch_method_info(self, cls, method_entry):
        method_id = method_entry["methodID"]
        method_entry["line_table"] = self.jdwp.Method.LineTable({
            "refType": cls["typeID"],
            "methodID": method_id})["lines"]
        for line in method_entry["line_table"]:
            line_number = line["lineNumber"]
            line_code_index = line["lineCodeIndex"]
            index_key = (cls["source_file"], line_number)
            if index_key not in self.line_index:
                self.line_index[index_key] = []
            self.line_index[index_key].append(
                    (cls["typeID"], method_id, line_code_index))

    def __update_thread_status(self, thread_id):
        with self.__debug_state_lock:
            thread = self.threads[thread_id]
            thread_status = self.jdwp.ThreadReference.Status({
                "thread": thread_id})
            thread["status"] = thread_status["threadStatus"]
            thread["is_suspended"] = thread_status["suspendStatus"]
            thread["frames"] = []
            if thread["is_suspended"]:
                frames = self.jdwp.ThreadReference.Frames({
                    "thread": thread_id,
                    "startFrame": 0,
                    "length": -1})["frames"]
