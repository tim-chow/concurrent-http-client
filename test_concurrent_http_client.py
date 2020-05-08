# coding: utf8

import logging
import time

from concurrent_http_client.manager import \
    CurlAsyncHTTPClientManager
from concurrent_http_client.httpclient import \
    HTTPRequest

LOGGER = logging.getLogger(__name__)

def log_response(response, log_body=False, max_bytes=None):
    LOGGER.info("response code: %d", response.code)
    LOGGER.info("effective url: %s", response.effective_url)
    LOGGER.info("response time_info:\n%s", response.time_info)
    LOGGER.info("primary ip: %s", response.primary_ip)
    LOGGER.info("speed download: %f", response.speed_download)
    if response.error:
        LOGGER.info("error:\n%s", response.error)
    if log_body and response.body != None:
        LOGGER.info(
            "response body:\n%s",
            response.body[:max_bytes or len(response.body)])

def test(url, max_queue_size,
        max_clients, worker_count,
        request_count, *args,
        **kwargs):
    success_count = 0
    start_time = time.time()

    manager = CurlAsyncHTTPClientManager(
        max_clients=max_clients,
        max_queue_size=max_queue_size,
        worker_count=worker_count)
    manager.start()

    try:
        fs = []
        for _ in range(request_count):
            f = manager.fetch(
                    HTTPRequest(url, *args, **kwargs))
            fs.append(f)

        response = None
        for f in fs:
            try:
                response = f.result()
            except Exception as e:
                LOGGER.error(
                    "Error downloading",
                    exc_info=True)
            else:
                code = response.code
                if code == 200:
                    success_count = success_count + 1
                else:
                    log_response(response)
        else:
            if response != None:
                LOGGER.info("last response is shown as below:")
                log_response(response, log_body=True, max_bytes=200)
    finally:
        manager.stop()
        time_elapsed = time.time() - start_time
        LOGGER.info(
            "time elapsed %fs",
            time_elapsed)
        LOGGER.info(
            "total count %d",
            request_count)
        LOGGER.info(
            "success count %d",
            success_count)
        LOGGER.info(
            "average time: %fs/r",
            time_elapsed / request_count)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s %(filename)s:"
            "%(lineno)d %(message)s",
        datefmt="%F %T")
    url = "https://www.baidu.com/"
    max_queue_size = 10000
    worker_count = 2
    max_clients = 250
    request_count = 5000
    test(
        url,
        max_queue_size=max_queue_size,
        worker_count=worker_count,
        max_clients=max_clients,
        request_count=request_count,
        connect_timeout=4,
        request_timeout=10,
        allow_ipv6=False)

