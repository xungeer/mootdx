# cython: language_level=3
import time
from threading import Thread

DEFAULT_HEARTBEAT_INTERVAL = 10.0


class HeartBeatThread(Thread):
    """A heartbeat belongs to exactly one socket generation.

    Count requests keep the transport active; they do not certify quote/bar
    capability. Idle time is measured from the last successful API response.
    """
    def __init__(self, client, stop_event, interval=DEFAULT_HEARTBEAT_INTERVAL):
        super().__init__(daemon=True, name="mootdx._protocol-heartbeat")
        self.heartbeat_interval = interval
        self.stop_event = stop_event
        self.client = client.client
        self.api = client
        self.generation = client._generation

    def run(self):
        while not self.stop_event.wait(self.heartbeat_interval):
            with self.api._operation():
                if (self.stop_event.is_set() or self.api._cancel_event.is_set() or self.api.closed
                        or self.api.client is not self.client
                        or self.api._generation != self.generation):
                    return
                if time.monotonic() - self.api._last_ack_monotonic >= self.heartbeat_interval:
                    try:
                        self.api.do_heartbeat()
                    except Exception:
                        # The API stores the structured failure in last_error.
                        # Retry policy is the same as a foreground request.
                        pass
