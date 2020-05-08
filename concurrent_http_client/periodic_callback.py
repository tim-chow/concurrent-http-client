# coding: utf8

# 本段代码修改自：tornado

import math


class PeriodicCallback(object):
    def __init__(self, event_loop, callback, callback_time, jitter=0):
        self.event_loop = event_loop
        self.callback = callback
        if callback_time <= 0:
            raise ValueError("Periodic callback must have a positive callback_time")
        self.callback_time = callback_time
        self.jitter = jitter
        self._running = False
        self._timeout = None

    def start(self):
        """Starts the timer."""
        self._running = True
        self._next_timeout = self.event_loop.time()
        self._schedule_next()

    def stop(self):
        """Stops the timer."""
        self._running = False
        if self._timeout is not None:
            self.event_loop.remove_timeout(self._timeout)
            self._timeout = None

    def is_running(self):
        return self._running

    def _run(self):
        if not self._running:
            return
        try:
            return self.callback()
        except:
            self.event_loop.handle_callback_exception(self.callback)
        finally:
            self._schedule_next()

    def _schedule_next(self):
        if self._running:
            self._update_next(self.event_loop.time())
            self._timeout = self.event_loop.add_timeout(self._next_timeout, self._run)

    def _update_next(self, current_time):
        callback_time_sec = self.callback_time / 1000.0
        if self.jitter:
            # apply jitter fraction
            callback_time_sec *= 1 + (self.jitter * (random.random() - 0.5))
        if self._next_timeout <= current_time:
            # The period should be measured from the start of one call
            # to the start of the next. If one call takes too long,
            # skip cycles to get back to a multiple of the original
            # schedule.
            self._next_timeout += (math.floor((current_time - self._next_timeout) /
                                              callback_time_sec) + 1) * callback_time_sec
        else:
            # If the clock moved backwards, ensure we advance the next
            # timeout instead of recomputing the same value again.
            # This may result in long gaps between callbacks if the
            # clock jumps backwards by a lot, but the far more common
            # scenario is a small NTP adjustment that should just be
            # ignored.
            #
            # Note that on some systems if time.time() runs slower
            # than time.monotonic() (most common on windows), we
            # effectively experience a small backwards time jump on
            # every iteration because PeriodicCallback uses
            # time.time() while asyncio schedules callbacks using
            # time.monotonic().
            # https://github.com/tornadoweb/tornado/issues/2333
            self._next_timeout += callback_time_sec

