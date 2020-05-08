# coding: utf8

# 本段代码源自：tornado

import sys

PY3 = sys.version_info >= (3, )

if PY3:
    unicode_type = str
else:
    unicode_type = unicode

def errno_from_exception(e):
    """Provides the errno from an Exception object.
    There are cases that the errno attribute was not set so we pull
    the errno out of the args but if someone instantiates an Exception
    without any args you will get a tuple error. So this function
    abstracts all that behavior to give you a safe way to get the
    errno.
    """

    if hasattr(e, 'errno'):
        return e.errno
    elif e.args:
        return e.args[0]
    else:
        return None

