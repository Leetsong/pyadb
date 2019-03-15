from __future__ import print_function

import tempfile
import shlex
from typing import List, Callable
from subprocess import check_output, CalledProcessError, call


__author__ = 'Simon Lee, Viktor Malyi'
__email__ = 'leetsong.lc@gmail.com, v.stratus@gmail.com'
__version__ = '1.3.0'


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

class AdbCommands:
    SHELL = 'shell'
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
# Adb Implementation
#########################################

class Adb:

    EXECUTABLE = 'adb'
    GLOBAL_OPTIONS: list = [
        AdbGlobalOption_s(),
    ]

    def __init__(self, enabled=True):
        self._serial = None
        self._is_connected = False
        self._is_log_enabled = enabled
        self._reset()

    def enable_log(self, enabled: bool=True):
        """
        Enable or disable logging
        :param enabled: enable or not
        :return:
        """
        self._is_log_enabled = enabled

    def s(self, serial):
        """
        Temporarily set global option -s <serial>, not connected
        :param serial: <serial>
        :return: self
        """
        self._serial = serial
        return self

    def connect(self, serial):
        """
        Permanently connect to an emulator with serial
        :param serial: <serial>
        :return: self
        """
        self._serial = serial
        self._is_connected = True
        return self

    def version(self):
        """
        Display the version of pyadb
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.VERSION]
        return self._exec_command(adb_sub_cmd)

    def bugreport(self, dest_file: str="default.log"):
        """
        Prints dumpsys, dumpstate, and logcat data to the screen, for the purposes of bug reporting
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.BUGREPORT]
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
        adb_sub_cmd = [AdbCommands.PUSH, src, dest]
        return self._exec_command(adb_sub_cmd)

    def pull(self, src: str, dest: str):
        """
        Pull object from target to host
        :param src: string path of object on target
        :param dest: string destination path on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.PULL, src, dest]
        return self._exec_command(adb_sub_cmd)

    def devices(self, opts: [None, list]=None):
        """
        Get list of all available devices including emulators
        :param opts: list command options (e.g. ["-l"])
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.DEVICES, self._convert_opts(opts)]
        return self._exec_command(adb_sub_cmd)

    def shell(self, cmd: str):
        """
        Execute shell command on target
        :param cmd: string shell command to execute
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.SHELL]
        adb_sub_cmd.extend(shlex.split(cmd))
        return self._exec_command(adb_sub_cmd)

    def install(self, apk: str, opts: [None, list]=None):
        """
        Install *.apk on target
        :param apk: string path to apk on host to install
        :param opts: list command options (e.g. ["-r", "-a"])
        :return: result of _exec_command() execution
        """
        if opts is None:
            opts = list()
        adb_sub_cmd = [AdbCommands.INSTALL, self._convert_opts(opts), apk]
        return self._exec_command(adb_sub_cmd)

    def uninstall(self, app: str, opts: [None, list]=None):
        """
        Uninstall app from target
        :param app: app name to uninstall from target (e.g. "com.example.android.valid")
        :param opts: list command options (e.g. ["-r", "-a"])
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.UNINSTALL, self._convert_opts(opts), app]
        return self._exec_command(adb_sub_cmd)

    def get_serialno(self):
        """
        Get serial number for all available target devices
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.GET_SERIALNO]
        return self._exec_command(adb_sub_cmd)

    def wait_for_device(self):
        """
        Block execution until the device is online
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.WAIT_FOR_DEVICE]
        return self._exec_command(adb_sub_cmd)

    def sync(self):
        """
        Copy host->device only if changed
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.SHELL , AdbCommands.SYNC]
        return self._exec_command(adb_sub_cmd)

    def start_server(self):
        """
        Startd pyadb server daemon on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.START_SERVER]
        return self._exec_command(adb_sub_cmd)

    def kill_server(self):
        """
        Kill pyadb server daemon on host
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.KILL_SERVER]
        return self._exec_command(adb_sub_cmd)

    def get_state(self):
        """
        Get state of device connected per pyadb
        :return: result of _exec_command() execution
        """
        adb_sub_cmd = [AdbCommands.GET_STATE]
        return self._exec_command(adb_sub_cmd)

    def _reset(self):
        if not self._is_connected:
            self._serial = None

    def _prepare(self):
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
        if result[1].strip() == "unknown":
            return False
        else:
            return True

    def _convert_opts(self, opts: [None, list]):
        """
        Convert list with command options to single string value
        with 'space' delimiter
        :param opts: list with space-delimited values
        :return: string with space-delimited values
        """
        return ' '.join(opts) if opts is not None else ''

    def _exec_command(self, adb_cmd: list):
        """
        Format pyadb command and execute it in shell
        :param adb_cmd: list pyadb command to execute
        :return: string '0' and shell command output if successful, otherwise
        raise CalledProcessError exception and return error code
        """
        t = tempfile.TemporaryFile()
        final_adb_cmd = self._prepare()
        for e in adb_cmd:
            if e != '':  # avoid items with empty string...
                final_adb_cmd.append(e)  # ... so that final command doesn't
                # contain extra spaces
        if self._is_log_enabled:
            print(self._u('-> ' + ' '.join(final_adb_cmd) + '\n'))

        try:
            output = check_output(final_adb_cmd, stderr=t)
        except CalledProcessError as e:
            t.seek(0)
            result = e.returncode, str(t.read(), encoding='utf-8').strip(' \t\n')
        else:
            result = 0, str(output, encoding='utf-8').strip(' \t\n')
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
        if self._is_log_enabled:
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

    def _u(self, s: str):
        """
        Underline a string
        :param s: string to be underlined
        :return: underlined string
        """
        return '\033[4m' + s + '\033[0m'
