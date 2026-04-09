import asyncio

from core.websocket_worker import BaseWebSocketWorker


class DummyWebSocketWorker(BaseWebSocketWorker):
    def __init__(self):
        super().__init__(["BTC-USDT"])
        self.connect_calls = 0
        self.states: list[str] = []
        self.connection_state_changed.connect(self._record_state)

    def _record_state(self, state: str, _message: str, _retry_count: int):
        self.states.append(state)

    async def _connect_and_subscribe(self):
        self.connect_calls += 1
        self._connection_start_time = 1000 + self.connect_calls
        self._subscribed_pairs = set(self.pairs)

        if self.connect_calls >= 2:
            self._running = False

    async def _update_subscriptions(self):
        self._subscribed_pairs = set(self.pairs)


async def _run_reconnect_test(monkeypatch):
    worker = DummyWebSocketWorker()
    worker._running = True
    worker._connection_timeout = 5
    worker._ping_interval = 999

    class FakeClock:
        def __init__(self):
            self.now = 1000.0

        def time(self):
            return self.now

    clock = FakeClock()
    original_sleep = asyncio.sleep

    async def fake_sleep(duration: float):
        clock.now += duration

        # Prevent the test from hanging if reconnect logic regresses.
        if clock.now > 1010 and worker.connect_calls < 2:
            worker._running = False

        await original_sleep(0)

    monkeypatch.setattr("core.websocket_worker.time.time", clock.time)
    monkeypatch.setattr("core.websocket_worker.asyncio.sleep", fake_sleep)

    await worker._maintain_connection()

    assert worker.connect_calls >= 2
    assert "reconnecting" in worker.states


def test_reconnects_when_no_message_arrives_after_connect(monkeypatch):
    asyncio.run(_run_reconnect_test(monkeypatch))
