# coding: utf8

import abc
import threading
import time
import logging

from concurrent.futures import Future

from .exceptions import *
from .status import Status
from .event_loop import EventLoop
from .waker import Waker
from .curl_async_http_client import CurlAsyncHTTPClient

LOGGER = logging.getLogger(__name__)


class AbstractManager(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, max_queue_size, worker_count):
        self._max_queue_size = max_queue_size
        self._worker_count = worker_count
        self._queue_lock = threading.Lock()
        self._queued_requests = []
        self._status = Status()
        self._workers = {}  # Map: worker id -> thread
        self._wakers = {}   # Map: worker id -> waker
        self._context_lock = threading.Lock()
        self._contexts = {}   # Map: worker id -> context
        self._tid_to_wid = {} # Map: thread id -> worker id
        self._quited_worker_count = 0

    def start(self):
        if not self._status.ensure_start_once(
                self._start_predicate):
            raise RuntimeError("fail to start Manager")

    def _start_predicate(self):
        for worker_id in range(self._worker_count):
            LOGGER.debug("initialize worker thread #"
                "%d" % worker_id)
            waker = self.make_waker()
            self._wakers[worker_id] = waker
            thread = threading.Thread(
                        target=self._worker_main,
                        args=(worker_id, waker))
            thread.setName("worker-thread-%d" % worker_id)
            thread.setDaemon(True)
            self._workers[worker_id] = thread

        for worker_id, thread in self._workers.items():
            LOGGER.debug("start worker thread #"
                "%d" % worker_id)
            thread.start()

        return True

    @abc.abstractmethod
    def initialize_context(self, worker_id):
        pass

    def get_context(self):
        """
        @raise KeyError
        """
        with self._context_lock:
            thread_id = threading.currentThread().ident
            worker_id = self._tid_to_wid[thread_id]
            return self._contexts[worker_id]

    @abc.abstractmethod
    def make_waker(self):
        pass

    def stop(self, timeout=None):
        if not self._status.transfer_to_stopping():
            raise RuntimeError("fail to stop Manager")

        while self._workers:
            worker_id, thread = self._workers.popitem()
            with self._context_lock:
                context = self._contexts.pop(worker_id)
            self.destory_context(worker_id, context)
            waker = self._wakers.pop(worker_id)
            waker.wake()
            waker.close()
            thread.join(timeout)
            thread_name = thread.getName()
            if thread.isAlive():
                LOGGER.error("%s is still running" %
                    thread_name)
            else:
                LOGGER.info("%s is stopped" % thread_name)

        with self._queue_lock:
            while self._queued_requests:
                _, f, _ = self._queued_requests.pop(0)
                try:
                    if f.set_running_or_notify_cancel():
                        f.set_exception(
                            ManagerStoppedException(
                                "manager is stopped"))
                except RuntimeError:
                    pass

    @abc.abstractmethod
    def destory_context(self, worker_id, context):
        pass

    def quit_if_necessary(self, force_quit=False):
        with self._status.expect(
                self._status.STOPPING) as ret:
            if not ret:
                return False
            if not force_quit:
                self._quited_worker_count = \
                    self._quited_worker_count + 1
            if self._quited_worker_count < \
                    self._worker_count:
                return True
        self._finalize_manager()
        return True

    def force_quit(self):
        with self._status:
            self._quited_worker_count = \
                self._quited_worker_count + 1
        self.quit_if_necessary(True)

    def _finalize_manager(self):
        self._quited_worker_count = 0
        self._tid_to_wid.clear()
        ret = self._status.transfer_to_stopped()
        if ret:
            LOGGER.debug("manager is stopped")
        else:
            LOGGER.error("status is inconsistent")

    @abc.abstractmethod
    def worker_main(self, worker_id, waker):
        pass

    def _worker_main(self, worker_id, waker):
        with self._context_lock:
            self._contexts[worker_id] = \
                self.initialize_context(worker_id)
            thread_id = threading.currentThread().ident
            self._tid_to_wid[thread_id] = worker_id
        self.worker_main(worker_id, waker)

    def fetch(self, request):
        f = Future()
        with self._status.expect(self._status.STARTED) as ret:
            if not ret:
                raise ManagerNotStartedException(
                        "Manager is not started")
            with self._queue_lock:
                if len(self._queued_requests) >= \
                        self._max_queue_size:
                    f.set_exception(
                        QueueFullException(
                            "queue is full"))
                else:
                    self._queued_requests.append((
                        request,
                        f, 
                        time.time()))
            self._wake_up_workers()
            return f

    def _wake_up_workers(self):
        for waker in self._wakers.values():
            waker.wake()

    def get_request(self):
        with self._queue_lock:
            if self._queued_requests:
                return self._queued_requests.pop(0)
            return None


class CurlAsyncHTTPClientManager(AbstractManager):
    def __init__(self, max_clients=10, *args, **kwargs):
        AbstractManager.__init__(self, *args, **kwargs)
        self._max_clients = max_clients

    def make_waker(self):
        return Waker()

    def initialize_context(self, worker_id):
        context = {}
        context["event_loop"] = EventLoop()
        return context

    def destory_context(self, worker_id, context):
        event_loop = context["event_loop"]
        event_loop.stop()

    def worker_main(self, worker_id, waker):
        context = self.get_context()
        event_loop = context["event_loop"]
        client = CurlAsyncHTTPClient(
                        self._max_clients,
                        event_loop,
                        waker,
                        self.get_request)
        event_loop.add_handler(
                        waker.fileno(),
                        client.wake_up,
                        EventLoop.READ)

        quit_unexpectly = False
        try:
            event_loop.start()
        except:
            LOGGER.error(
                "EventLoop of worker thread "
                    "#%d quited unexpectly",
                worker_id,
                exc_info=True)
            quit_unexpectly = True

        # 获取 client 正在处理的请求，并将其设置为失败
        for _, f, _ in client.get_proccessing_requests():
            try:
                if f.set_running_or_notify_cancel():
                    f.set_exception(
                        ManagerStoppedException(
                            "Manager is stopped"))
            except RuntimeError:
                pass
        client.close()
        event_loop.close()
        LOGGER.info(
            "worker thread #%d quited",
            worker_id)
        if quit_unexpectly:
            self.force_quit()
        else:
            self.quit_if_necessary()

