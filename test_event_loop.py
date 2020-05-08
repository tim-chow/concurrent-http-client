from concurrent_http_client.event_loop import \
    EventLoop

def callback(event_loop):
    print("callback")
    event_loop.stop()

def timeout_callback(event_loop):
    print("timeout_callback")
    event_loop.add_callback(callback, event_loop)

def test():
    print("start testing")
    event_loop = EventLoop()
    event_loop.call_later(
        2,
        timeout_callback,
        event_loop)
    try:
        event_loop.start()
    finally:
        event_loop.close()
    print("end testing")

if __name__ == "__main__":
    test()

