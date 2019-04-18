from __future__ import print_function

import tempfile
import shlex
from typing import List, Callable, Optional
from subprocess import \
    check_output, \
    CalledProcessError, \
    call, \
    Popen, \
    PIPE


__author__ = 'Simon Lee, Viktor Malyi'
__email__ = 'leetsong.lc@gmail.com, v.stratus@gmail.com'
__version__ = '1.3.0'


#########################################
# Helper functions
#########################################

def _underline(s: str) -> str:
    """
    Underline a string
    :param s: string to be underlined
    :return: underlined string
    """
    return '\033[4m' + s + '\033[0m'


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
    PULL = 'pull'
    PUSH = 'push'
    UNINSTALL = 'uninstall'
    INSTALL = 'install'
    DEVICES = 'devices'
    GET_SERIALNO = 'get-serialno'
    WAIT_FOR_DEVICE = 'wait-for-device'
    KILL_SERVER = 'kill-server'
    START_SERVER = 'start-server'
    GET_STATE = 'get-state'
    SYNC = 'sync'
    VERSION = 'version'
    BUGREPORT = 'bugreport'


#########################################
# Adb Command Handles, and Exceptions
#########################################

# An AdbCommandHandle is a function which accepts
# the output of the command as input, and returns a
# flag to terminate the execution (True for terminating,
# and o.w. False)
AdbCommandHandle = Callable[[str], bool]


class AdbNoCommandHandleException(Exception):
    """
    Any unterminated shell command should give an
    AdbShellCommandHandler as the output handle,
    or an AdbNoCommandHandleException will be raised
    """
    def __init__(self, message: str):
        super().__init__(message)


#########################################
# Adb Implementation
#########################################

class Adb:

    EXECUTABLE = 'adb'
    GLOBAL_OPTIONS: list = [
        AdbGlobalOption_s(),
    ]
    DEFAULT_EXEC_HANDLER: AdbCommandHandle = lambda s: True

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

    def push(self, src: str, dest: str):
        """
        Push object from host to target
        :param src: string path to source object on host
        :param dest: string destination path on target
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.PUSH, src, dest]
        return self._exec_command(adb_sub_cmd)

    def pull(self, src: str, dest: str):
        """
        Pull object from target to host
        :param src: string path of object on target
        :param dest: string destination path on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.PULL, src, dest]
        return self._exec_command(adb_sub_cmd)

    def devices(self, opts: Optional[list] = None):
        """
        Get list of all available devices including emulators
        :param opts: list command options (e.g. ["-l"])
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommand.DEVICES, self._convert_opts(opts)]
        return self._exec_command(adb_sub_cmd)

    def exec_out(self, cmd: str,
                 timeout: Optional[int] = None,
                 handle: Optional[AdbCommandHandle] = None,
                 in_background: bool = True):
        """
        Execute command using exec-out on target, when timeout is -1 (means for
        unterminated command), a handle should be given
        :param cmd: string shell command to execute
        :param timeout: timeout for the command, -1 for unterminated command
        :param handle: handle for unterminated shell command
        :param in_background: whether asynchronously execute this command when unterminated
        :return: result of _exec_command() execution
        """
        return self._shell_or_exec_out(False, cmd,
                                       timeout=timeout,
                                       handle=handle,
                                       in_background=in_background)

    def shell(self, cmd: str,
              timeout: Optional[int] = None,
              handle: Optional[AdbCommandHandle] = None,
              in_background: bool = True):
        """
        Execute command using shell on target, when timeout is -1 (means for
        unterminated command), a handle should be given
        :param cmd: string shell command to execute
        :param timeout: timeout for the command, -1 for unterminated command
        :param handle: handle for unterminated shell command
        :param in_background: whether asynchronously execute this command when unterminated
        :return: result of _exec_command() execution
        """
        return self._shell_or_exec_out(True, cmd,
                                       timeout=timeout,
                                       handle=handle,
                                       in_background=in_background)

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

    def _shell_or_exec_out(self, shell: bool, cmd: str,
                           timeout: Optional[int] = None,
                           handle: Optional[AdbCommandHandle] = None,
                           in_background: bool = True):
        """
        Execute shell command on target, when timeout is -1 (means for
        unterminated command), a handle should be given
        :param shell: run it using 'shell' or 'exec-out'
        :param cmd: string shell command to execute
        :param timeout: timeout for the command, -1 for unterminated command
        :param handle: handle for unterminated shell command
        :param in_background: whether asynchronously execute this command when unterminated
        :return: result of _exec_command() execution
        """
        if timeout == -1 and handle is None:
            raise AdbNoCommandHandleException('No AdbShellCommandHandler is given')

        adb_sub_cmd = [AdbCommand.SHELL if shell else AdbCommand.EXEC_OUT]
        adb_sub_cmd.extend(shlex.split(cmd))
        return self._exec_command(adb_sub_cmd,
                                  timeout=timeout,
                                  handle=handle,
                                  in_background=in_background)

    def _exec_command(self, adb_cmd: list,
                      timeout: Optional[int] = None,
                      handle: Optional[AdbCommandHandle] = None,
                      in_background: bool = True):
        """
        Format pyadb command and execute it in shell
        :param adb_cmd: list pyadb command to execute
        :param handle: handle for unterminated shell command
        :param in_background: whether asynchronously execute this command when unterminated
        :return: 0 and shell command output if successful, otherwise
        raise CalledProcessError exception and return error code
        """
        t = tempfile.TemporaryFile()
        final_adb_cmd = self._prepare()
        for e in adb_cmd:
            if e != '':  # avoid items with empty string...
                final_adb_cmd.append(e)  # ... so that final command doesn't
                # contain extra spaces
        if self._is_log_command_enabled:
            print(_underline('-> ' + ' '.join(final_adb_cmd) + '\n'))

        if timeout == -1:  # unterminated
            proc = Popen(final_adb_cmd, stdout=PIPE, stderr=t, universal_newlines=True)
            if in_background:  # asynchronously execute it
                # TODO add thread pool to handle background tasks
                raise Exception('Background tasks are not implemented by far')
            else:
                while True:
                    line = proc.stdout.readline()
                    if handle(line):
                        break
            return 0, ''
        else:
            try:
                output = check_output(final_adb_cmd, stderr=t)
            except CalledProcessError as e:
                t.seek(0)
                result = e.returncode, str(t.read(), encoding='utf-8').strip(' \t\n')
            else:
                result = 0, str(output, encoding='utf-8').strip(' \t\n')
                if self._is_log_output_enabled:
                    print(result[1] + '\n')
            self._reset()  # reset state after each command
            return result

    def _exec_command_to_file(self, adb_cmd, dest_file_handler):
        """
        Format pyadb command and execute it in shell and redirects to a file
        :param adb_cmd: list pyadb command to execute
        :param dest_file_handler: file handler to which output will be redirected
        :return: string '0' and writes shell command output to file if successful, otherwise
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
            output = call(final_adb_cmd, stdout=dest_file_handler, stderr=t)
        except CalledProcessError as e:
            t.seek(0)
            result = e.returncode, str(t.read(), encoding='utf-8').strip(' \t\n')
        else:
            result = output
            dest_file_handler.close()
        self._reset()  # reset state after each command
        return result
