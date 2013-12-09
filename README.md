pyjdb - python library for debugging java programs

Currently limited in scope; barebones implementation of JDWP spec in python is
working. In functional tests, a breakpoint in a simple java program is
successfully set and hit.

Contents:
 * java_sample/ - sample java target code and build script for functional tests.
 * pyjdb/
   + pyjdb.py - library
   + pyjdb_test.py - functional tests
 * test.sh - test script. run to test. install dependencies first (see below)
 * setup.py - use to install on your system

Dependencies:
 * pretty recent jdk
 * python2.7
 * pyparsing
