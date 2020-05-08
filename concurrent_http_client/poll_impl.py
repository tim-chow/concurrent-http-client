# coding: utf8

# 本段代码源自：tornado

import select
from .event_loop import EventLoop

if hasattr(select, 'epoll'):
    PollImpl = select.epoll
elif hasattr(select, "kqueue"):
    class PollImpl(object):
        def __init__(self):
            self._kqueue = select.kqueue()
            self._active = {}

        def fileno(self):
            return self._kqueue.fileno()

        def close(self):
            self._kqueue.close()

        def register(self, fd, events):
            if fd in self._active:
                raise IOError("fd %s already registered" % fd)
            self._control(fd, events, select.KQ_EV_ADD)
            self._active[fd] = events

        def modify(self, fd, events):
            self.unregister(fd)
            self.register(fd, events)

        def unregister(self, fd):
            events = self._active.pop(fd)
            self._control(fd, events, select.KQ_EV_DELETE)

        def _control(self, fd, events, flags):
            kevents = []
            if events & EventLoop.WRITE:
                kevents.append(select.kevent(
                    fd, filter=select.KQ_FILTER_WRITE, flags=flags))
            if events & EventLoop.READ:
                kevents.append(select.kevent(
                    fd, filter=select.KQ_FILTER_READ, flags=flags))
            # Even though control() takes a list, it seems to return EINVAL
            # on Mac OS X (10.6) when there is more than one event in the list.
            for kevent in kevents:
                self._kqueue.control([kevent], 0)

        def poll(self, timeout):
            kevents = self._kqueue.control(None, 1000, timeout)
            events = {}
            for kevent in kevents:
                fd = kevent.ident
                if kevent.filter == select.KQ_FILTER_READ:
                    events[fd] = events.get(fd, 0) | EventLoop.READ
                if kevent.filter == select.KQ_FILTER_WRITE:
                    if kevent.flags & select.KQ_EV_EOF:
                        # If an asynchronous connection is refused, kqueue
                        # returns a write event with the EOF flag set.
                        # Turn this into an error for consistency with the
                        # other EventLoop implementations.
                        # Note that for read events, EOF may be returned before
                        # all data has been consumed from the socket buffer,
                        # so we only check for EOF on write events.
                        events[fd] = EventLoop.ERROR
                    else:
                        events[fd] = events.get(fd, 0) | EventLoop.WRITE
                if kevent.flags & select.KQ_EV_ERROR:
                    events[fd] = events.get(fd, 0) | EventLoop.ERROR
            return events.items()
else:
    class PollImpl(object):
        def __init__(self):
            self.read_fds = set()
            self.write_fds = set()
            self.error_fds = set()
            self.fd_sets = (self.read_fds, self.write_fds, self.error_fds)

        def close(self):
            pass

        def register(self, fd, events):
            if fd in self.read_fds or fd in self.write_fds or fd in self.error_fds:
                raise IOError("fd %s already registered" % fd)
            if events & EventLoop.READ:
                self.read_fds.add(fd)
            if events & EventLoop.WRITE:
                self.write_fds.add(fd)
            if events & EventLoop.ERROR:
                self.error_fds.add(fd)
                # Closed connections are reported as errors by epoll and kqueue,
                # but as zero-byte reads by select, so when errors are requested
                # we need to listen for both read and error.
                # self.read_fds.add(fd)

        def modify(self, fd, events):
            self.unregister(fd)
            self.register(fd, events)

        def unregister(self, fd):
            self.read_fds.discard(fd)
            self.write_fds.discard(fd)
            self.error_fds.discard(fd)

        def poll(self, timeout):
            readable, writeable, errors = select.select(
                self.read_fds, self.write_fds, self.error_fds, timeout)
            events = {}
            for fd in readable:
                events[fd] = events.get(fd, 0) | EventLoop.READ
            for fd in writeable:
                events[fd] = events.get(fd, 0) | EventLoop.WRITE
            for fd in errors:
                events[fd] = events.get(fd, 0) | EventLoop.ERROR
            return events.items()

