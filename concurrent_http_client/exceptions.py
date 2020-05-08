class BaseException(Exception):
    pass


class ManagerNotStartedException(BaseException):
    pass


class QueueFullException(BaseException):
    pass


class ManagerStoppedException(BaseException):
    pass


class CurlAsyncHTTPClientException(BaseException):
    pass


class CurlSetupException(CurlAsyncHTTPClientException):
    def __init__(self, exc, *args, **kwargs):
        CurlAsyncHTTPClientException.__init__(self, *args, **kwargs)
        self.exc = exc

    def __str__(self):
        return "%s{exc=%s}" % (self.__class__.__name__, self.exc)

    def __repr__(self):
        return "%s{exc=%r}" % (self.__class__.__name__,
            self.exc) + "@" + hex(id(self))


class CurlException(CurlAsyncHTTPClientException):
    def __init__(self, errno, message, *args, **kwargs):
        CurlAsyncHTTPClientException.__init__(self, *args, **kwargs)
        self.code = 599
        self.errno = errno
        self.message = message

    def __str__(self):
        return "%s{code=%d, errno=%d, message=%s}" % (
            self.__class__.__name__, self.code, self.errno, self.message)

    def __repr__(self):
        return self.__str__() + "@" + hex(id(self))


class HTTPInputException(CurlAsyncHTTPClientException):
    pass


class HTTPException(CurlAsyncHTTPClientException):
    def __init__(self, code, message=None, response=None):
        self.code = code
        from . import httputil
        self.message = message or httputil.responses.get(code, "Unknown")
        self.response = response
        super(HTTPException, self).__init__(code, message, response)

    def __str__(self):
        return "HTTP %d: %s" % (self.code, self.message)

    # There is a cyclic reference between self and self.response,
    # which breaks the default __repr__ implementation.
    # (especially on pypy, which doesn't have the same recursion
    # detection as cpython).
    __repr__ = __str__

