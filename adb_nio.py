from queue import Queue, Empty

from adb_thread import InterruptableThread


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
