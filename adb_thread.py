import ctypes
import inspect
import threading


Thread = threading.Thread
ThreadError = threading.ThreadError


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


if __name__ == '__main__':
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
