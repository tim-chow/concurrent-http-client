# coding: utf8

# 本段代码修改自：tornado

import time

from . import httputil
from .escape import utf8
from .exceptions import HTTPException


class HTTPResponse(object):
    def __init__(self, request, code, headers=None, buffer=None,
                 effective_url=None, error=None, request_time=None,
                 time_info=None, reason=None, start_time=None,
                 primary_ip=None, speed_download=None, speed_upload=None):
        if isinstance(request, _RequestProxy):
            self.request = request.request
        else:
            self.request = request
        self.code = code
        self.reason = reason or httputil.responses.get(code, "Unknown")
        if headers is not None:
            self.headers = headers
        else:
            self.headers = httputil.HTTPHeaders()
        self.buffer = buffer
        self._body = None
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        self._error_is_response_code = False
        if error is None:
            if self.code < 200 or self.code >= 300:
                self._error_is_response_code = True
                self.error = HTTPException(self.code, message=self.reason,
                                       response=self)
            else:
                self.error = None
        else:
            self.error = error
        self.start_time = start_time
        self.request_time = request_time
        self.time_info = time_info or {}
        self.primary_ip = primary_ip
        self.speed_download = speed_download
        self.speed_upload = speed_upload

    @property
    def body(self):
        if self.buffer is None:
            return None
        elif self._body is None:
            self._body = self.buffer.getvalue()

        return self._body

    def rethrow(self):
        """If there was an error on the request, raise an `HTTPException`."""
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in sorted(self.__dict__.items()))
        return "%s(%s)" % (self.__class__.__name__, args)


class HTTPRequest(object):
    _DEFAULTS = dict(
        connect_timeout=20.0,
        request_timeout=20.0,
        follow_redirects=True,
        max_redirects=5,
        decompress_response=True,
        proxy_password='',
        allow_nonstandard_methods=False,
        validate_cert=True)

    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None, auth_mode=None,
                 connect_timeout=None, request_timeout=None,
                 if_modified_since=None, follow_redirects=None,
                 max_redirects=None, user_agent=None, use_gzip=None,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 proxy_host=None, proxy_port=None, proxy_username=None,
                 proxy_password=None, proxy_auth_mode=None,
                 allow_nonstandard_methods=None, validate_cert=None,
                 ca_certs=None, allow_ipv6=None, client_key=None,
                 client_cert=None, body_producer=None,
                 expect_100_continue=False, decompress_response=None,
                 ssl_options=None, max_body_length=None,
                 resolve_list=None, connect_to_list=None,
                 dns_servers=None, dns_cache_timeout=None,
                 dns_use_global_cache=None):
        # Note that some of these attributes go through property setters
        # defined below.
        self.headers = headers
        if if_modified_since:
            self.headers["If-Modified-Since"] = httputil.format_timestamp(
                if_modified_since)
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.proxy_auth_mode = proxy_auth_mode
        self.url = url
        self.method = method
        self.body = body
        self.body_producer = body_producer
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.auth_mode = auth_mode
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        if decompress_response is not None:
            self.decompress_response = decompress_response
        else:
            self.decompress_response = use_gzip
        self.network_interface = network_interface
        self.streaming_callback = streaming_callback
        self.header_callback = header_callback
        self.prepare_curl_callback = prepare_curl_callback
        self.allow_nonstandard_methods = allow_nonstandard_methods
        self.validate_cert = validate_cert
        self.ca_certs = ca_certs
        self.allow_ipv6 = allow_ipv6
        self.client_key = client_key
        self.client_cert = client_cert
        self.ssl_options = ssl_options
        self.expect_100_continue = expect_100_continue
        self.start_time = time.time()
        self.max_body_length = max_body_length
        self.resolve_list = resolve_list
        self.connect_to_list = connect_to_list
        self.dns_servers = dns_servers
        self.dns_cache_timeout = dns_cache_timeout
        self.dns_use_global_cache = dns_use_global_cache

    @property
    def headers(self):
        return self._headers

    @headers.setter
    def headers(self, value):
        if value is None:
            self._headers = httputil.HTTPHeaders()
        else:
            self._headers = value

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value):
        self._body = utf8(value)

    @property
    def body_producer(self):
        return self._body_producer

    @body_producer.setter
    def body_producer(self, value):
        self._body_producer = value

    @property
    def streaming_callback(self):
        return self._streaming_callback

    @streaming_callback.setter
    def streaming_callback(self, value):
        self._streaming_callback = value

    @property
    def header_callback(self):
        return self._header_callback

    @header_callback.setter
    def header_callback(self, value):
        self._header_callback = value

    @property
    def prepare_curl_callback(self):
        return self._prepare_curl_callback

    @prepare_curl_callback.setter
    def prepare_curl_callback(self, value):
        self._prepare_curl_callback = value


class _RequestProxy(object):
    def __init__(self, request, defaults):
        self.request = request
        self.defaults = defaults

    def __getattr__(self, name):
        request_attr = getattr(self.request, name)
        if request_attr is not None:
            return request_attr
        elif self.defaults is not None:
            return self.defaults.get(name, None)
        else:
            return None

