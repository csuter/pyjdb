pyjdb - python library for debugging java programs

Provides
 + Pythonic interface to manipulate a running java program, good for quick
   scripts or more extensive debugging applications
 + Access (if desired) to lower-level jdwp spec implementation in python

Consists internally of
 + a parser for the jdwp spec (see
   http://docs.oracle.com/javase/7/docs/technotes/guides/jpda/jdwp-spec.html)
 + a jdwp wire format serializer/deserializer library
 + some fun metaclass magic to provide on-the-fly implementation of jdwp spec
