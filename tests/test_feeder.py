# SPDX-License-Identifier: GPL-3.0-or-later
"""Feed-loop tests with a fake controller: the fans must never be left without a feed."""
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "coolercontrol-plugin", "corsair-a600")
sys.path[:0] = [PLUGIN_DIR, os.path.join(PLUGIN_DIR, "gen")]

try:
    import corsair_a600_plugin as plugin
except ImportError as e:  # grpc not installed
    plugin = None
    IMPORT_ERROR = str(e)


class FakeCooling:
    def __init__(self, fail_status_at=(), error=ValueError("not a status reply")):
        self.connected = False
        self.path = "/dev/fake"
        self.pushes = []
        self.opens = 0
        self.status_calls = 0
        self.fail_status_at = set(fail_status_at)
        self.error = error

    def open(self):
        self.opens += 1
        self.connected = True

    def close(self):
        self.connected = False

    def push_temps(self, gpu_c, cpu_c):
        self.pushes.append((gpu_c, cpu_c))

    def mode(self):
        return 1

    def set_mode(self, mode):
        pass

    def status(self):
        self.status_calls += 1
        if self.status_calls in self.fail_status_at:
            raise self.error
        return {name: (1000, 1000) for name in plugin.FAN_LABELS}, (3000, 3000)


class FakeSensor:
    def __init__(self, value=40.0, fail_first=0, error=None):
        self.value, self.fail_left = value, fail_first
        self.error = error or plugin.SensorError("sensor away")
        self.reads = 0

    def read(self):
        self.reads += 1
        if self.fail_left:
            self.fail_left -= 1
            raise self.error
        return self.value


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@unittest.skipIf(plugin is None, "plugin not importable" if plugin is None else "")
class FeedLoop(unittest.TestCase):
    def setUp(self):
        self.saved = (plugin.FEED_INTERVAL_S, plugin.RETRY_INTERVAL_S)
        plugin.FEED_INTERVAL_S, plugin.RETRY_INTERVAL_S = 0.01, 0.01
        self.feeder = None

    def tearDown(self):
        if self.feeder and self.feeder.is_alive():
            self.feeder.stop()
        plugin.FEED_INTERVAL_S, plugin.RETRY_INTERVAL_S = self.saved

    def start(self, cooling, cpu=None, gpu=None):
        self.state = plugin.State()
        self.feeder = plugin.Feeder(self.state, plugin.Config())
        self.feeder.cooling = cooling
        self.feeder.cpu, self.feeder.gpu = cpu or FakeSensor(50.0), gpu or FakeSensor(40.0)
        self.feeder.start()
        return self.feeder

    def test_feeds_sensor_temperatures(self):
        cooling = FakeCooling()
        self.start(cooling)
        self.assertTrue(wait_for(lambda: len(cooling.pushes) >= 3))
        self.assertEqual(cooling.pushes[0], (40, 50))  # (GPU, CPU)
        self.assertTrue(self.state.connected)

    def test_unexpected_error_does_not_stop_the_feed(self):
        cooling = FakeCooling(fail_status_at={2})
        with self.assertLogs("corsair-a600", level="WARNING"):
            feeder = self.start(cooling)
            self.assertTrue(wait_for(lambda: cooling.status_calls >= 6))
        self.assertTrue(feeder.is_alive())
        self.assertEqual(cooling.opens, 2)  # reconnected after the bad reply
        self.assertTrue(wait_for(lambda: self.state.connected))

    def test_device_error_is_retried(self):
        cooling = FakeCooling(fail_status_at={1, 2}, error=OSError("no reply"))
        with self.assertLogs("corsair-a600", level="WARNING") as logs:
            feeder = self.start(cooling)
            self.assertTrue(wait_for(lambda: cooling.status_calls >= 5))
        self.assertTrue(feeder.is_alive())
        # The same failure twice in a row is reported once.
        self.assertEqual(sum("no reply" in line for line in logs.output), 1)

    def test_unreadable_sensor_sends_failsafe_and_logs_once(self):
        cooling = FakeCooling()
        gpu = FakeSensor(40.0, fail_first=10 ** 6)
        with self.assertLogs("corsair-a600", level="WARNING") as logs:
            self.start(cooling, gpu=gpu)
            self.assertTrue(wait_for(lambda: len(cooling.pushes) >= 5))
        self.assertEqual(cooling.pushes[0], (plugin.FAILSAFE_C, 50))
        self.assertEqual(sum("GPU temperature unavailable" in line for line in logs.output), 1)

    def test_sensor_recovers(self):
        cooling = FakeCooling()
        gpu = FakeSensor(40.0, fail_first=2)
        with self.assertLogs("corsair-a600", level="INFO") as logs:
            self.start(cooling, gpu=gpu)
            n = plugin.SMOOTHING_SAMPLES + 3
            self.assertTrue(wait_for(lambda: len(cooling.pushes) >= n))
        self.assertEqual(cooling.pushes[n - 1], (40, 50))
        self.assertTrue(any("GPU temperature is readable again" in line for line in logs.output))

    def test_garbled_sensor_value_counts_as_failure(self):
        cooling = FakeCooling()
        cpu = FakeSensor(50.0, fail_first=1, error=ValueError("invalid literal for int()"))
        with self.assertLogs("corsair-a600", level="WARNING"):
            feeder = self.start(cooling, cpu=cpu)
            self.assertTrue(wait_for(lambda: len(cooling.pushes) >= 2))
        self.assertEqual(cooling.pushes[0], (40, plugin.FAILSAFE_C))
        self.assertTrue(feeder.is_alive())

    def test_stop_sends_failsafe_last(self):
        cooling = FakeCooling()
        feeder = self.start(cooling)
        self.assertTrue(wait_for(lambda: len(cooling.pushes) >= 2))
        feeder.stop()
        self.assertFalse(feeder.is_alive())
        self.assertEqual(cooling.pushes[-1], (plugin.FAILSAFE_C, plugin.FAILSAFE_C))

    def test_stop_sends_failsafe_even_if_disconnected(self):
        cooling = FakeCooling()
        feeder = self.start(cooling)
        self.assertTrue(wait_for(lambda: len(cooling.pushes) >= 1))
        feeder.stop_event.set()
        feeder.join(timeout=2)
        cooling.close()
        feeder.stop()
        self.assertEqual(cooling.pushes[-1], (plugin.FAILSAFE_C, plugin.FAILSAFE_C))


@unittest.skipIf(plugin is None, "plugin not importable" if plugin is None else "")
class GpuSensorRetry(unittest.TestCase):
    def test_failed_start_is_retried_after_the_interval(self):
        sensor = plugin.GpuSensor()
        attempts = []

        def failing_init():
            attempts.append(1)
            raise plugin.SensorError("NVML unavailable: test")

        sensor._init = failing_init
        for _ in range(3):
            with self.assertRaises(plugin.SensorError):
                sensor.read()
        self.assertEqual(len(attempts), 1)  # not retried on every read
        sensor.retry_at = 0.0  # interval over
        with self.assertRaises(plugin.SensorError):
            sensor.read()
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
