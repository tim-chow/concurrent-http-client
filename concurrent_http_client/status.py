import threading
from contextlib import contextmanager


class Status(object):
    INITIALIZATION = 0b1
    STARTING       = 0b10
    STARTED        = 0b100
    STOPPING       = 0b1000
    STOPPED        = 0b10000

    def __init__(self):
        self._lock = threading.RLock()
        self._current_status = self.INITIALIZATION

    def _run_predicate(self,
                       old_status,
                       new_status,
                       predicate,
                       *args,
                       **kwargs):
        try:
            if predicate == None or predicate(*args, **kwargs):
                with self._lock:
                    self._current_status = new_status
                return True
        except:
            with self._lock:
                self._current_status = old_status
            raise
        else:
            with self._lock:
                self._current_status = old_status
            return False

    def start(self, predicate=None, *args, **kwargs):
        with self._lock:
            status = self._current_status
            if not any((status & self.INITIALIZATION,
                        status & self.STOPPED)):
                return False
            self._current_status = self.STARTING
        return self._run_predicate(
                    status,
                    self.STARTED,
                    predicate,
                    *args,
                    **kwargs)

    def stop(self, predicate=None, *args, **kwargs):
        with self._lock:
            status = self._current_status
            if not status & self.STARTED:
                return False
            self._current_status = self.STOPPING
        return self._run_predicate(
                    status,
                    self.STOPPED,
                    predicate,
                    *args,
                    **kwargs)

    def transfer_to_stopping(self):
        with self._lock:
            if self._current_status & self.STARTED:
                self._current_status = self.STOPPING
                return True
            return False

    def transfer_to_stopping_if_necessary(self):
        with self._lock:
            if self._current_status & self.STOPPING:
                return True
            if self._current_status & self.STARTED:
                self._current_status = self.STOPPING
                return True
            return False

    def transfer_to_stopped(self):
        with self._lock:
            if self._current_status & self.STOPPING:
                self._current_status = self.STOPPED
                return True
            return False

    def ensure_start_once(self, predicate=None, *args, **kwargs):
        with self._lock:
            status = self._current_status
            if any((status & self.STARTING,
                    status & self.STARTED)):
                return True
            if status & self.STOPPING:
                return False
            self._current_status = self.STARTING
        return self._run_predicate(
                    status,
                    self.STARTED,
                    predicate,
                    *args,
                    **kwargs)

    @contextmanager
    def expect(self, expected_status):
        self._lock.acquire()
        ret = expected_status & self._current_status \
            and True or False
        try:
            yield ret
        finally:
            self._lock.release()

    def __enter__(self):
        self._lock.acquire()

    def __exit__(self, exc_typ, exc, tb):
        self._lock.release()

