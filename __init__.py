from __future__ import print_function

import ctypes
import inspect
import shlex
import tempfile
import threading
from queue import Queue, Empty
from typing import List, Callable, Optional
from subprocess import \
    CalledProcessError, \
    call, \
    Popen, \
    PIPE


__author__ = 'Simon Lee, Viktor Malyi'
__email__ = 'leetsong.lc@gmail.com, v.stratus@gmail.com'
__version__ = '1.3.0'


Thread = threading.Thread
ThreadError = threading.ThreadError


#########################################
# Utilities
#########################################

def _underline(s: str) -> str:
    """
    Underline a string
    :param s: string to be underlined
    :return: underlined string
    """
    return '\033[4m' + s + '\033[0m'


def _from_proc_output(output: bytes) -> str:
    """
    Convert proc output from bytes to str, and trim heading-
    and tailing-spaces
    :param output: output in bytes
    :return: output in str
    """
    return str(output, encoding='utf-8').strip(' \t\n')


def _async_raise(tid, exctype):
    """
    Raises an exception in the threads with id tid
    :param tid: it of a thread
    :param exctype: type of exception to be thrown
    """
    if not inspect.isclass(exctype):
        raise TypeError("Only types can be raised (not instances)")
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid),
                                                     ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class InterruptableThread(Thread):

    class _InterruptThread(Exception):
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._interrupted = threading.Event()

    def interrupted(self):
        return self._interrupted.is_set()

    def interrupt(self):
        self._raise_exc(self._InterruptThread)

    def run(self):
        try:
            super().run()
        except self._InterruptThread:
            self._interrupted.set()

    def _get_my_tid(self):
        """
        Determines this (self's) thread id

        CAREFUL : this function is executed in the context of the caller
        thread, to get the identity of the thread represented by this
        instance.
        """
        if not self.is_alive():
            raise ThreadError("the thread is not active")

        # do we have it cached?
        if hasattr(self, "_thread_id"):
            return self._thread_id

        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid

        # TODO: in python 2.6, there's a simpler way to do : self.ident

        raise AssertionError("Could not determine the thread's id")

    def _raise_exc(self, exctype):
        """
        Raises the given exception type in the context of this thread.

        If the thread is busy in a system call (time.sleep(),
        socket.accept(), ...), the exception is simply ignored.

        If you are sure that your exception should terminate the thread,
        one way to ensure that it works is:

            t = ThreadWithExc( ... )
            ...
            t.raiseExc( SomeException )
            while t.isAlive():
                time.sleep( 0.1 )
                t.raiseExc( SomeException )

        If the exception is to be caught by the thread, you need a way to
        check that your thread has caught it.

        CAREFUL : this function is executed in the context of the
        caller thread, to raise an excpetion in the context of the
        thread represented by this instance.
        """
        _async_raise(self._get_my_tid(), exctype)


class NonBlockingReader:

    class TimeoutException(Exception):
        pass

    def __init__(self, stream):
        self._stream = stream
        self._queue = Queue()
        self._thread = InterruptableThread(target=self._run)
        self._thread.start()

    def empty(self):
        return self._queue.empty()

    def readline(self, timeout=None):
        """
        Read one line within time limit
        :param timeout: time limit
        :return: None for done reading, or throw a TimeoutException
        """
        try:
            return self._queue.get(block=timeout is not None, timeout=timeout)
        except Empty:
            if self._thread.is_alive():  # actually empty, and timeout
                raise self.TimeoutException()
            else:  # thread is not alive, read done
                return None

    def close(self):
        if self._thread.is_alive():
            self._thread.interrupt()
            self._thread.join()

    def _run(self):
        for line in self._stream:
            self._queue.put(line)


#########################################
# Pre-declaration
#########################################

class Adb:
    pass


#########################################
# Global Options
#########################################

AdbGlobalOption = Callable[[Adb], List[str]]


class AdbGlobalOption_s(AdbGlobalOption):

    # TODO: I have no idea by far how to dismiss this warning
    def __call__(self, adb: Adb) -> List[str]:
        return ['-s', adb._serial] if adb._serial is not None else []


#########################################
# Adb Commands
#########################################

class AdbCommand:
    SHELL = 'shell'
    EXEC_OUT = 'exec-out'
    LOGCAT = 'logcat'
    PULL = 'pull'
    PUSH = 'push'
    UNINSTALL = 'uninstall'
    INSTALL = 'install'
    DEVICES = 'devices'
    FORWARD = 'forward'
    REVERSE = 'reverse'
    GET_SERIALNO = 'get-serialno'
    WAIT_FOR_DEVICE = 'wait-for-device'
    KILL_SERVER = 'kill-server'
    START_SERVER = 'start-server'
    GET_STATE = 'get-state'
    REBOOT = 'reboot'
    ROOT = 'root'
    SYNC = 'sync'
    EMU = 'emu'
    VERSION = 'version'
    BUGREPORT = 'bugreport'


##########################################
# Adb Poll Command Callback
##########################################

# An AdbPollCommandCallback is a function which accepts
# (whether timeout, the output of the command) as
# inputs, and returns a flag to terminate the execution
# (True for terminating, and o.w. False)
AdbPollCommandCallback = Callable[[bool, str], bool]


#########################################
# Adb Implementation
#########################################

class Adb:

    EXECUTABLE = 'adb'
    GLOBAL_OPTIONS: list = [
        AdbGlobalOption_s(),
    ]

    def __init__(self, log_command=True, log_output=True):
        """
        Adb is a python interface for adb
        :param log_command: whether enable logging the invoked adb command
        :param log_output: whether enable logging the output of the invoked adb command
        """
        self._serial = None
        self._is_log_output_enabled = log_output
        self._is_log_command_enabled = log_command
        self._reset()

    def enable_logging_command(self, enabled: bool = True):
        """
        Enable or disable logging command
        :param enabled: enable or not
        :return:
        """
        self._is_log_command_enabled = enabled
        return self

    def enable_logging_output(self, enabled: bool = True):
        """
        Enable or disable logging output
        :param enabled: enable or not
        :return:
        """
        self._is_log_output_enabled = enabled
        return self

    def is_log_output_enabled(self):
        """
        As name shows
        :return: as name shows
        """
        return self._is_log_output_enabled

    def is_log_command_enabled(self):
        """
        As name shows
        :return: as name shows
        """
        return self._is_log_command_enabled

    def s(self, serial):
        """
        Temporarily set global option -s <serial>, not connected
        :param serial: <serial>
        :return: self
        """
        self._serial = serial
        return self

    def is_connected(self):
        """
        Whether connected an emulator or a device
        :return: True if connected
        """
        return self._serial is not None

    def connect(self, serial: str):
        """
        Permanently connect to an emulator with serial
        :param serial: <serial>
        :return: self
        """
        if self.is_connected():
            print('Error: already connect to %s' % self._serial)
            return False
        else:
            self._serial = serial
            return True

    def disconnect(self):
        """
        Disconnect from the connected devices/emulators
        :return: True if successfully disconnected
        """
        if self.is_connected():
            self._serial = None
            return True
        else:
            print('Error: no connection by far')
            return False

    def reconnect(self, serial: str):
        """
        Reconnect to a new device/emulator
        :param serial: serial no of the emulator/device
        :return: True if successfully connected
        """
        if self.is_connected():
            self.disconnect()
        return self.connect(serial)

    def version(self):
        """
        Display the version of pyadb
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.VERSION]
        return self._exec_command(adb_sub_cmd)

    def bugreport(self, dest_file: str = "default.log"):
        """
        Prints dumpsys, dumpstate, and logcat data to the screen, for the purposes of bug reporting
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.BUGREPORT]
        try:
            dest_file_handler = open(dest_file, "w")
        except IOError:
            print("IOError: Failed to create a log file")
            dest_file_handler = None

        # We have to check if device is available or not before executing this command
        # as pyadb bugreport will wait-for-device infinitely and does not come out of
        # loop
        # Execute only if device is available only
        if self._is_device_available():
            result = self._exec_command_to_file(adb_sub_cmd, dest_file_handler)
            return result, "Success: Bug report saved to: " + dest_file
        else:
            return 0, "Device Not Found"

    def push(self, src: List[str], dest: str, opts: Optional[list] = None):
        """
        Push object from host to target
        :param src: list of paths to source objects on host
        :param dest: destination path on target
        :param opts: options
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.PUSH, *src, dest, self._convert_opts(opts)]
        return self._exec_command(adb_sub_cmd)

    def pull(self, src: List[str], dest: str, opts: Optional[list] = None):
        """
        Pull object from target to host
        :param src: list of paths of objects on target
        :param dest: destination path on host
        :param opts: options
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.PULL, *src, dest, self._convert_opts(opts)]
        return self._exec_command(adb_sub_cmd)

    def devices(self, opts: Optional[list] = None):
        """
        Get list of all available devices including emulators
        :param opts: list command options (e.g. ["-l"])
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.DEVICES, self._convert_opts(opts)]
        return self._exec_command(adb_sub_cmd)

    def logcat(self, args):
        """
        Display logcat logs
        :param args: arguments to logcat
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.LOGCAT]
        adb_sub_cmd.extend(shlex.split(args))
        return self._exec_command(adb_sub_cmd)

    def poll_logcat(self, args, callback: AdbPollCommandCallback, timeout: int):
        """
        Display logcat logs
        :param args: arguments to logcat
        :param callback: callback to handle each line
        :param timeout: timeout for polling
        """
        adb_sub_cmd = [AdbCommand.LOGCAT]
        adb_sub_cmd.extend(shlex.split(args))
        try:
            self._poll_cmd_output(adb_sub_cmd, timeout=timeout, callback=callback)
        except CalledProcessError:
            pass

    def exec_out(self, cmd: str):
        """
        Execute command until finished using exec-out on target
        :param cmd: string shell command to execute
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.EXEC_OUT]
        adb_sub_cmd.extend(shlex.split(cmd))
        return self._exec_command(adb_sub_cmd)

    def shell(self, cmd: str):
        """
        Execute command until finished using shell on target
        :param cmd: string shell command to execute
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.SHELL]
        adb_sub_cmd.extend(shlex.split(cmd))
        return self._exec_command(adb_sub_cmd)

    def poll_out(self, cmd: str, callback: AdbPollCommandCallback,
                 timeout, shell=False):
        """
        Execute command until finished using shell on target
        :param cmd: string shell command to execute
        :param callback: callback to handle each line
        :param timeout: timeout for polling
        :param shell: True for using shell else exec-out
        :return: return code
        """
        adb_sub_cmd = [AdbCommand.SHELL if shell else AdbCommand.EXEC_OUT]
        adb_sub_cmd.extend(shlex.split(cmd))
        return self._poll_cmd_output(adb_sub_cmd, timeout=timeout,
                                     callback=callback)

    def install(self, apk: str, opts: Optional[list] = None):
        """
        Install *.apk on target
        :param apk: string path to apk on host to install
        :param opts: list command options (e.g. ["-r", "-a"])
        :return: result of _exec_command() execution
        """
        if opts is None:
            opts = list()
        adb_sub_cmd = [AdbCommand.INSTALL, self._convert_opts(opts), apk]
        return self._exec_command(adb_sub_cmd)

    def uninstall(self, app: str, opts: Optional[list] = None):
        """
        Uninstall app from target
        :param app: app name to uninstall from target (e.g. "com.example.android.valid")
        :param opts: list command options (e.g. ["-r", "-a"])
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.UNINSTALL, self._convert_opts(opts), app]
        return self._exec_command(adb_sub_cmd)

    def forward(self, args):
        """
        Forward local (host machine) port to remote (android device) port
        :param args: arguments to forward
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.FORWARD]
        adb_sub_cmd.extend(shlex.split(args))
        return self._exec_command(adb_sub_cmd)

    def reverse(self, args):
        """
        Reverse remote (android device) port to local (host machine) port
        :param args: arguments to forward
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.REVERSE]
        adb_sub_cmd.extend(shlex.split(args))
        return self._exec_command(adb_sub_cmd)

    def reboot(self):
        """
        Reboot the device
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.REBOOT]
        return self._exec_command(adb_sub_cmd)

    def root(self):
        """
        Run adb using root user
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.ROOT]
        return self._exec_command(adb_sub_cmd)

    def get_serialno(self):
        """
        Get serial number for all available target devices
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.GET_SERIALNO]
        return self._exec_command(adb_sub_cmd)

    def wait_for_device(self):
        """
        Block execution until the device is online
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.WAIT_FOR_DEVICE]
        return self._exec_command(adb_sub_cmd)

    def sync(self):
        """
        Copy host->device only if changed
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.SHELL, AdbCommand.SYNC]
        return self._exec_command(adb_sub_cmd)

    def emu(self, args):
        """
        Run emulator commands
        :param args: arguments to emu
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.EMU]
        adb_sub_cmd.extend(shlex.split(args))
        return self._exec_command(adb_sub_cmd)

    def start_server(self):
        """
        Startd pyadb server daemon on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.START_SERVER]
        return self._exec_command(adb_sub_cmd)

    def kill_server(self):
        """
        Kill pyadb server daemon on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.KILL_SERVER]
        return self._exec_command(adb_sub_cmd)

    def get_state(self):
        """
        Get state of device connected per pyadb
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.GET_STATE]
        return self._exec_command(adb_sub_cmd)

    def _reset(self):
        """
        Reset self
        :return: None
        """
        if not self.is_connected():
            self._serial = None

    def _prepare(self):
        """
        Prepare for executable and global options
        :return: [executable, ...global_options]
        """
        p = [Adb.EXECUTABLE]
        for gop in Adb.GLOBAL_OPTIONS:
            p.extend(gop(self))
        return p

    def _is_device_available(self):
        """
        Private Function to check if device is available;
        To be used by only functions inside module
        :return: True or False
        """
        result = self.get_serialno()
        if result[1].strip() == "error: no devices/emulators found":
            return False
        else:
            return True

    def _convert_opts(self, opts: Optional[list]):
        """
        Convert list with command options to single string value
        with 'space' delimiter
        :param opts: list with space-delimited values
        :return: string with space-delimited values
        """
        return ' '.join(opts) if opts is not None else ''

    def _exec_command(self, adb_cmd: list):
        """
        Execute adb_cmd and get return code and output
        :param adb_cmd: list pyabd command to execute
        :return: (returncode, output)
        """
        buf = []

        def callback(timeout, line):
            if timeout:
                return False
            buf.append(line)
            return False

        try:
            self._poll_cmd_output(adb_cmd, timeout=0, callback=callback)
        except CalledProcessError as e:
            return e.returncode, e.stderr

        return 0, ''.join(buf)

    def _poll_cmd_output(self, adb_cmd: list, timeout: int = 0,
                         callback: AdbPollCommandCallback = lambda _, __: False):
        """
        Format pyadb command and execute it in shell, _poll_cmd_output will poll
        stdout of adb_command for timeout ms to fetch the output each time,
        :param adb_cmd: list pyadb command to execute
        :param timeout: timeout in millisecond for polling
        :param callback: for handling output
        """
        t = tempfile.TemporaryFile()
        final_adb_cmd = self._prepare()
        for e in adb_cmd:
            if e != '':  # avoid items with empty string...
                final_adb_cmd.append(e)  # ... so that final command doesn't
                # contain extra spaces
        if self._is_log_command_enabled:
            print(_underline('-> ' + ' '.join(final_adb_cmd) + '\n'))

        proc = Popen(final_adb_cmd, stdout=PIPE, stderr=t, universal_newlines=True)
        reader = NonBlockingReader(proc.stdout)
        while True:
            try:
                line = reader.readline(timeout)  # read one line
            except reader.TimeoutException:
                if callback(True, ''):  # callback to give opportunity for termination
                    break
                continue
            if line is None:  # done reading
                rc = proc.poll()  # check return code
                if rc == 0:  # succeeded
                    break
                # failed, raise an exception
                t.seek(0)  # seek to 0 position of err
                err = _from_proc_output(t.read())
                reader.close()
                t.close()
                proc.terminate()
                raise CalledProcessError(returncode=rc, cmd=' '.join(final_adb_cmd),
                                         output=None, stderr=err)
            if callback(False, line):
                break

        reader.close()
        t.close()
        proc.terminate()
        self._reset()  # reset state after each command

    def _exec_command_to_file(self, adb_cmd, dest_file_handler):
        """
        Format pyadb command and execute it in shell and redirects to a file
        :param adb_cmd: list pyadb command to execute
        :param dest_file_handler: file handler to which output will be redirected
        :return: 0 and writes shell command output to file if successful, otherwise
        raise CalledProcessError exception and return error code
        """
        t = tempfile.TemporaryFile()
        final_adb_cmd = self._prepare()
        for e in adb_cmd:
            if e != '':  # avoid items with empty string...
                final_adb_cmd.append(e)  # ... so that final command doesn't
                # contain extra spaces
        if self._is_log_command_enabled:
            print('-> ' + ' '.join(final_adb_cmd) + '\n')

        try:
            call(final_adb_cmd, stdout=dest_file_handler, stderr=t)
        except CalledProcessError as e:
            raise e
        finally:
            t.close()
            dest_file_handler.close()
        self._reset()  # reset state after each command
        return 0


if __name__ == '__main__':
    adb = Adb(False, False)

    def test_thread():
        from time import sleep

        def never_stop():
            counter = 1
            while True:
                print(counter)
                sleep(1)
                counter += 1

        thread = InterruptableThread(target=never_stop)
        thread.start()

        sleep(5)
        thread.interrupt()

        print(thread.interrupted())
        thread.join()
        print(thread.interrupted())

        print('Exit')

    def test_logcat():
        from threading import Thread

        interrupted = False

        def on_logcat(timeout, line) -> bool:
            if timeout:
                return False
            if line is None or line == '':
                return False
            print(line.strip())
            return False

        thread = Thread(target=lambda: adb.poll_logcat('-s DroidTrace', callback=on_logcat, timeout=0))
        try:
            thread.start()
            thread.join()
        except KeyboardInterrupt:
            interrupted = True
            thread.join()
            print('Exit')

    def test_succeeded_shell():
        rc, msg = adb.shell('cat /data/local/tmp/mnky')
        print(rc)
        print(msg)

    def test_failed_shell():
        rc, msg = adb.shell('cat /dta/local/tmp/mnky')
        print(rc)
        print(msg)

    def test_getevent():
        def on_event(timeout, line) -> bool:
            if timeout:
                return False
            if line is None or line == '':
                return False
            print(line.strip())
            return False
        adb.poll_out('getevent -tlq', callback=on_event, timeout=0, shell=False)

    test_logcat()
