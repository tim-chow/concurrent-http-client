# coding: utf8

# 本段代码修改自：tornado
# 与 tornado 的 IOLoop 不同，EventLoop是线程安全的

import logging
import time
import os
import threading
import heapq
import functools
import numbers
import datetime
import errno
import collections

from .waker import Waker
from .util import errno_from_exception
from .status import Status

LOGGER = logging.getLogger(__name__)
_POLL_TIMEOUT = 3600.0

def close_fd(fd):
    try:
        try:
            fd.close()
        except AttributeError:
            os.close(fd)
    except OSError:
        pass

def split_fd(fd):
    try:
        return fd.fileno(), fd
    except AttributeError:
        return fd, fd

def timedelta_to_seconds(td):
    return (td.microseconds + 
            (td.seconds +
                td.days * 24 * 3600) * 10 ** 6) \
            / float(10 ** 6)


class EventLoop(object):
    # Constants from the epoll module
    _EPOLLIN      = 0x001
    _EPOLLPRI     = 0x002
    _EPOLLOUT     = 0x004
    _EPOLLERR     = 0x008
    _EPOLLHUP     = 0x010
    _EPOLLRDHUP   = 0x2000
    _EPOLLONESHOT = (1 << 30)
    _EPOLLET      = (1 << 31)

    # Our events map exactly to the epoll events
    NONE  = 0
    READ  = _EPOLLIN
    WRITE = _EPOLLOUT
    ERROR = _EPOLLERR | _EPOLLHUP

    def __init__(self, time_func=None):
        self._status = Status()
        self.time_func = time_func or time.time
        self._pid = os.getpid()
        self._timeout_lock = threading.Lock()
        self._timeouts = []
        self._cancellations = 0
        self._timeout_id_lock = threading.Lock()
        self._current_timeout_id = 0
        self._callbacks = collections.deque()
        self._handler_lock = threading.Lock()
        self._handlers = {}
        # 避免循环导入
        from .poll_impl import PollImpl
        self._impl = PollImpl()
        self._waker_lock = threading.Lock()
        self._waker = Waker()
        self.add_handler(
            self._waker.fileno(),
            lambda fd, events: self._waker.consume(),
            self.READ)

    def time(self):
        return self.time_func()

    def wake(self):
        with self._waker_lock:
            self._waker.wake()

    def call_later(self, delay,
                   callback, *args,
                   **kwargs):
        return self.call_at(
                    self.time() + delay,
                    callback,
                    *args,
                    **kwargs)

    def call_at(self, deadline,
                callback, *args,
                **kwargs):
        timeout = _Timeout(
            deadline,
            functools.partial(
                callback, *args, **kwargs),
            self)
        with self._timeout_lock:
            heapq.heappush(self._timeouts, timeout)
        self.wake()
        return timeout

    def add_timeout(self, deadline,
                    callback, *args,
                    **kwargs):
        if isinstance(deadline, numbers.Real):
            return self.call_at(
                    deadline,
                    callback,
                    *args,
                    **kwargs)
        elif isinstance(deadline, datetime.timedelta):
            return self.call_at(
                    self.time() + timedelta_to_seconds(deadline),
                    callback,
                    *args,
                    **kwargs)
        else:
            raise TypeError("Unsupported deadline %r" % deadline)

    def remove_timeout(self, timeout):
        with self._timeout_lock:
            # Removing from a heap is complicated, so just leave the defunct
            # timeout object in the queue (see discussion in
            # http://docs.python.org/library/heapq.html).
            # If this turns out to be a problem, we could add a garbage
            # collection pass whenever there are too many dead timeouts.
            timeout.callback = None
            self._cancellations = self._cancellations + 1

    def get_timeout_id(self):
        with self._timeout_id_lock:
            self._current_timeout_id = \
                self._current_timeout_id + 1
            return self._current_timeout_id

    def add_callback(self, callback, *args, **kwargs):
        with self._status.expect(
                self._status.STARTED) as ret:
            if not ret:
                return False
            self._callbacks.append(
                functools.partial(
                            callback,
                            *args,
                            **kwargs))
        self.wake()
        return True

    def _run_callback(self, callback):
        if callback == None:
            return

        try:
            callback()
        except:
            self.handle_callback_exception(callback)

    def add_handler(self, fd, handler, events):
        fd, obj = split_fd(fd)
        with self._handler_lock:
            self._handlers[fd] = (obj, handler)
            self._impl.register(fd, events | self.ERROR)

    def update_handler(self, fd, events):
        fd, obj = split_fd(fd)
        with self._handler_lock:
            self._impl.modify(fd, events | self.ERROR)

    def remove_handler(self, fd):
        fd, obj = split_fd(fd)
        with self._handler_lock:
            self._handlers.pop(fd, None)
            try:
                self._impl.unregister(fd)
            except Exception:
                LOGGER.error(
                    "Error deleting fd %d from EventLoop",
                    fd,
                    exc_info=True)

    def _start_predicate(self):
        if os.getpid() != self._pid:
            raise RuntimeError("Cannot share "
                "EventLoops across processes")
        return True

    def _schedule_timeouts(self):
        due_timeouts = []
        with self._timeout_lock:
            # Add any timeouts that have come due to the callback list.
            # Do not run anything until we have determined which ones
            # are ready, so timeouts that call add_timeout cannot
            # schedule anything in this iteration.
            if self._timeouts:
                now = self.time()
                while self._timeouts:
                    if self._timeouts[0].callback is None:
                        # The timeout was cancelled.  Note that the
                        # cancellation check is repeated below for timeouts
                        # that are cancelled by another timeout or callback.
                        heapq.heappop(self._timeouts)
                        self._cancellations = self._cancellations - 1
                    elif self._timeouts[0].deadline <= now:
                        due_timeouts.append(heapq.heappop(self._timeouts))
                    else:
                        break
                if (self._cancellations > 512 and
                        self._cancellations > (len(self._timeouts) >> 1)):
                    # Clean up the timeout queue when it gets large and it's
                    # more than half cancellations.
                    self._cancellations = 0
                    self._timeouts = [x for x in self._timeouts
                                      if x.callback is not None]
                    heapq.heapify(self._timeouts)

        for timeout in due_timeouts:
            cb = timeout.callback
            if cb == None:
                continue
            try:
                cb()
            except:
                self.handle_callback_exception(cb)

    def _poll(self, poll_timeout):
        try:
            event_pairs = self._impl.poll(poll_timeout)
        except Exception as e:
            # Depending on python version and EventLoop implementation,
            # different exception types may be thrown and there are
            # two ways EINTR might be signaled:
            # * e.errno == errno.EINTR
            # * e.args is like (errno.EINTR, 'Interrupted system call')
            if errno_from_exception(e) == errno.EINTR:
                return
            else:
                raise

        while event_pairs:
            fd, events = event_pairs.pop(0)
            with self._handler_lock:
                # 如果 fd 不在 self._handlers 中，说明已经被移除了
                if fd not in self._handlers:
                    LOGGER.debug(
                        "fd %d is ready, but it is removed "
                        "from EventLoop already",
                        fd)
                    continue
                fd_obj, handler_func = self._handlers[fd]
            try:
                handler_func(fd_obj, events)
            except (OSError, IOError) as e:
                if errno_from_exception(e) == errno.EPIPE:
                    # Happens when the client closes the connection
                    pass
                else:
                    self.handle_callback_exception(
                        (fd_obj, handler_func))
            except:
                self.handle_callback_exception(
                    (fd_obj, handler_func))

    def start(self):
        if not self._status.start(self._start_predicate):
            raise RuntimeError("fail to start EventLoop")

        LOGGER.info("start EventLoop")

        try:
            while True:
                ncallbacks = len(self._callbacks)

                # 调度定时器
                self._schedule_timeouts()

                # 调度回调函数
                for _ in range(ncallbacks):
                    self._run_callback(self._callbacks.popleft())

                # 判断是否需要退出
                if self._status.transfer_to_stopped():
                    break

                # 事件轮询
                poll_timeout = _POLL_TIMEOUT
                with self._timeout_lock:
                    if self._timeouts:
                        poll_timeout = min(
                            poll_timeout,
                            max(0, self._timeouts[0].deadline -
                                self.time()))
                self._poll(poll_timeout)
        except:
            self._status.transfer_to_stopping_if_necessary()
            self._status.transfer_to_stopped()
            raise
        finally:
            LOGGER.info("EventLoop is stopped")

    def stop(self):
        if self._status.transfer_to_stopping():
            self.wake()

    # 清理资源。只应该在程序关闭时调用一次
    def close(self, all_fds=False):
        self.remove_handler(self._waker.fileno())
        if all_fds:
            for fd, handler in list(self._handlers.values()):
                close_fd(fd)
        self._waker.close()
        self._impl.close()
        del self._timeouts[:]

    def handle_callback_exception(self, callback):
        LOGGER.error(
            "Exception in callback %r",
            callback,
            exc_info=True)


class _Timeout(object):
    # Reduce memory overhead when there are lots of pending callbacks
    __slots__ = ['deadline', 'callback', 'tdeadline']

    def __init__(self, deadline, callback, event_loop):
        if not isinstance(deadline, numbers.Real):
            raise TypeError("Unsupported deadline %r" % deadline)
        self.deadline = deadline
        self.callback = callback
        self.tdeadline = (deadline, event_loop.get_timeout_id())

    # Comparison methods to sort by deadline, with object id as a tiebreaker
    # to guarantee a consistent ordering.  The heapq module uses __le__
    # in python2.5, and __lt__ in 2.6+ (sort() and most other comparisons
    # use __lt__).
    def __lt__(self, other):
        return self.tdeadline < other.tdeadline

    def __le__(self, other):
        return self.tdeadline <= other.tdeadline

