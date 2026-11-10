#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""CoolerControl device plugin for the Corsair ONE a600 cooling controller (1b1c:0d27).

The controller runs Corsair's own Quiet/Balanced curves, but only on temperatures the host
sends it. This plugin feeds it the CPU (k10temp Tctl) and NVIDIA GPU temperatures once per
second, keeps the chosen mode set, and reports the five fans and two pumps to CoolerControl.
Fans are monitoring-only there: the controller has no fixed-duty command, and custom curve
uploads are not used.

Settings come from config.json in the plugin folder (edited on the plugin's page in
CoolerControl): {"mode": "balanced" | "quiet"}.
"""
import collections
import ctypes
import glob
import json
import logging
import os
import signal
import sys
import threading
import time
from concurrent import futures

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "gen")]

import grpc  # noqa: E402

import a600hw  # noqa: E402
from coolercontrol.device_service.v1 import device_service_pb2_grpc as ds_grpc  # noqa: E402
from coolercontrol.device_service.v1 import (  # noqa: E402
    enable_manual_fan_control_pb2,
    health_pb2,
    initialize_device_pb2,
    list_devices_pb2,
    reset_channel_pb2,
    shutdown_pb2,
)
from coolercontrol.device_service.v1 import status_pb2 as status_rpc  # noqa: E402
from coolercontrol.models.v1 import (  # noqa: E402
    channel_info_pb2,
    device_info_pb2,
    device_pb2,
    driver_info_pb2,
    speed_options_pb2,
    status_pb2,
    temp_info_pb2,
)

VERSION = "0.3.1"
SOCKET = "/tmp/corsair-a600.sock"
CONFIG_PATH = os.path.join(HERE, "config.json")
DEFAULT_CONFIG = {"mode": "balanced"}

COOLING_ID = "a600-cooling"

FAILSAFE_C = 85
SMOOTHING_SAMPLES = 3
FEED_INTERVAL_S = 1.0
RETRY_INTERVAL_S = 5.0
SENSOR_RETRY_S = 30.0
MODE_CHECK_EVERY_S = 60

FAN_LABELS = {"gpu1": "GPU fan 1", "gpu2": "GPU fan 2", "gpu3": "GPU fan 3",
              "cpu1": "CPU fan 1", "cpu2": "CPU fan 2"}
PUMP_LABELS = {"pump1": "Pump 1", "pump2": "Pump 2"}
TEMP_LABELS = {"cpu_feed": "CPU (sent to controller)", "gpu_feed": "GPU (sent to controller)"}

log = logging.getLogger("corsair-a600")


# ---------------------------------------------------------------- temperature sources

class SensorError(Exception):
    """A temperature can't be read right now."""


class CpuSensor:
    """AMD Tctl from k10temp, found by name since hwmon numbers change between boots."""

    def __init__(self):
        self.path = None

    @staticmethod
    def _find():
        for h in glob.glob("/sys/class/hwmon/hwmon*"):
            try:
                with open(os.path.join(h, "name")) as f:
                    if f.read().strip() != "k10temp":
                        continue
                for label in glob.glob(os.path.join(h, "temp*_label")):
                    with open(label) as f:
                        if f.read().strip() == "Tctl":
                            return label.replace("_label", "_input")
            except OSError:
                continue
        return None

    def read(self):
        if not self.path:
            self.path = self._find()
            if not self.path:
                raise SensorError("k10temp Tctl not found")
        try:
            with open(self.path) as f:
                return int(f.read()) / 1000
        except (OSError, ValueError):
            self.path = None  # look it up again next time
            raise


class GpuSensor:
    """NVIDIA GPU temperature through NVML.

    NVML can be unavailable for a while (driver not loaded yet at boot, driver updated
    without a reboot, GPU reset), so a failed start is retried instead of being final.
    """

    def __init__(self):
        self.lib = None
        self.handle = ctypes.c_void_p()
        self.retry_at = 0.0
        self.error = "not initialised"

    def _init(self):
        try:
            lib = ctypes.CDLL("libnvidia-ml.so.1")
            rc = lib.nvmlInit_v2()
            if rc != 0:
                raise SensorError(f"nvmlInit returned {rc}")
            rc = lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.handle))
            if rc != 0:
                raise SensorError(f"nvmlDeviceGetHandleByIndex returned {rc}")
            self.lib = lib
        except (OSError, AttributeError) as e:
            raise SensorError(f"NVML unavailable: {e}") from e

    def read(self):
        if not self.lib:
            if time.monotonic() < self.retry_at:
                raise SensorError(self.error)
            try:
                self._init()
            except SensorError as e:
                self.error = str(e)
                self.retry_at = time.monotonic() + SENSOR_RETRY_S
                raise
        t = ctypes.c_uint()
        rc = self.lib.nvmlDeviceGetTemperature(self.handle, 0, ctypes.byref(t))
        if rc != 0:
            self.lib = None  # start NVML again after the retry interval
            self.error = f"nvmlDeviceGetTemperature returned {rc}"
            self.retry_at = time.monotonic() + SENSOR_RETRY_S
            raise SensorError(self.error)
        return float(t.value)


# ---------------------------------------------------------------- shared state

class Config:
    def __init__(self):
        self.mtime = None
        self.values = dict(DEFAULT_CONFIG)

    def reload_if_changed(self):
        """Returns True when the file changed since the last call."""
        try:
            mtime = os.stat(CONFIG_PATH).st_mtime
        except OSError:
            mtime = None
        if mtime == self.mtime:
            return False
        self.mtime = mtime
        values = dict(DEFAULT_CONFIG)
        if mtime is not None:
            try:
                with open(CONFIG_PATH) as f:
                    loaded = json.load(f)
                if loaded.get("mode") in a600hw.MODES:
                    values["mode"] = loaded["mode"]
            except (OSError, ValueError, AttributeError) as e:
                log.warning("Ignoring unreadable %s: %s", CONFIG_PATH, e)
        self.values = values
        log.info("Settings: mode %s", values["mode"])
        return True


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.fans = {}
        self.pumps = (0, 0)
        self.cpu_c = None
        self.gpu_c = None
        self.connected = False


def clamp_c(v):
    return max(0, min(100, int(round(v))))


# ---------------------------------------------------------------- cooling feed thread

class Feeder(threading.Thread):
    def __init__(self, state, config):
        super().__init__(daemon=True, name="feeder")
        self.state, self.config = state, config
        self.stop_event = threading.Event()
        self.cooling = a600hw.Cooling()
        self.cpu, self.gpu = CpuSensor(), GpuSensor()
        self.sensor_errors = {}

    def _sample(self, sensor, history, name):
        try:
            history.append(sensor.read())
            if self.sensor_errors.pop(name, None):
                log.info("%s temperature is readable again", name)
        except (SensorError, OSError, ValueError) as e:
            # Log each distinct failure once, not every second.
            if self.sensor_errors.get(name) != str(e):
                log.warning("%s temperature unavailable (%s); sending fail-safe %d °C", name, e, FAILSAFE_C)
                self.sensor_errors[name] = str(e)
            history.append(FAILSAFE_C)
        return clamp_c(sum(history) / len(history))

    def run(self):
        cpu_hist = collections.deque(maxlen=SMOOTHING_SAMPLES)
        gpu_hist = collections.deque(maxlen=SMOOTHING_SAMPLES)
        next_mode_check = 0.0
        last_error = None
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                if self.config.reload_if_changed():
                    next_mode_check = 0.0
                if not self.cooling.connected:
                    self.cooling.open()
                    log.info("Cooling controller opened at %s", self.cooling.path)
                    next_mode_check = 0.0
                cpu_c = self._sample(self.cpu, cpu_hist, "CPU")
                gpu_c = self._sample(self.gpu, gpu_hist, "GPU")
                self.cooling.push_temps(gpu_c, cpu_c)
                if started >= next_mode_check:
                    want = a600hw.MODES[self.config.values["mode"]]
                    current = self.cooling.mode()
                    if current != want:
                        log.info("Controller mode %s, switching to %s",
                                 a600hw.MODE_NAMES.get(current, current), a600hw.MODE_NAMES[want])
                        self.cooling.set_mode(want)
                    next_mode_check = started + MODE_CHECK_EVERY_S
                fans, pumps = self.cooling.status()
                with self.state.lock:
                    self.state.fans, self.state.pumps = fans, pumps
                    self.state.cpu_c, self.state.gpu_c = cpu_c, gpu_c
                    self.state.connected = True
                last_error = None
            except Exception as e:
                # Every failure, expected (OSError) or not, is handled the same way: report it,
                # reconnect and keep feeding. If this thread died instead, the controller would
                # keep the last temperature and the fans would stop following load.
                # Each distinct failure is logged once, so a persistent one (e.g. no permission)
                # shows up without flooding the journal.
                if str(e) != last_error:
                    unexpected = not isinstance(e, OSError)
                    if self.cooling.connected:
                        log.warning("Lost cooling controller: %s", e, exc_info=unexpected)
                    else:
                        log.error("Cannot use cooling controller: %s (retrying every %g s)",
                                  e, RETRY_INTERVAL_S, exc_info=unexpected)
                    last_error = str(e)
                self.cooling.close()
                with self.state.lock:
                    self.state.connected = False
                self.stop_event.wait(RETRY_INTERVAL_S)
                continue
            self.stop_event.wait(max(0.0, FEED_INTERVAL_S - (time.monotonic() - started)))

    def stop(self):
        """Stop feeding and leave a high temperature so the fans run fast while unmanaged."""
        self.stop_event.set()
        self.join(timeout=1.5)
        try:
            if not self.cooling.connected:
                self.cooling.open()
            self.cooling.push_temps(FAILSAFE_C, FAILSAFE_C)
            log.info("Sent fail-safe %d °C on stop", FAILSAFE_C)
        except Exception as e:
            log.warning("Could not send the fail-safe temperature on stop: %s", e)
        self.cooling.close()


# ---------------------------------------------------------------- gRPC service

def speed_channel(label):
    return channel_info_pb2.ChannelInfo(
        label=label,
        speed_options=speed_options_pb2.SpeedOptions(min_duty=0, max_duty=100, fixed_enabled=False))


class DeviceService(ds_grpc.DeviceServiceServicer):
    def __init__(self, state, config):
        self.state, self.config = state, config
        self.started = time.monotonic()

    # -- discovery

    def Health(self, request, context):
        with self.state.lock:
            ok = self.state.connected
        return health_pb2.HealthResponse(
            name="Corsair ONE a600", version=VERSION,
            status=health_pb2.HealthResponse.STATUS_OK if ok else health_pb2.HealthResponse.STATUS_WARNING,
            uptime_seconds=int(time.monotonic() - self.started))

    def ListDevices(self, request, context):
        devices = []
        cooling_path = a600hw.find_hidraw(a600hw.COOLING_HID_ID)
        if cooling_path:
            channels = {cid: speed_channel(label) for cid, label in FAN_LABELS.items()}
            channels.update({cid: speed_channel(label) for cid, label in PUMP_LABELS.items()})
            temps = {tid: temp_info_pb2.TempInfo(label=label, number=i + 1)
                     for i, (tid, label) in enumerate(TEMP_LABELS.items())}
            devices.append(device_pb2.Device(
                id=COOLING_ID, name="a600 Cooling", uid_info="corsair-a600-1b1c-0d27",
                info=device_info_pb2.DeviceInfo(
                    channels=channels, temps=temps, model="Corsair ONE a600 cooling controller",
                    driver_info=driver_info_pb2.DriverInfo(
                        name="corsair-a600 plugin", version=VERSION, locations=[cooling_path]))))
        return list_devices_pb2.ListDevicesResponse(devices=devices)

    def InitializeDevice(self, request, context):
        return initialize_device_pb2.InitializeDeviceResponse()

    def Shutdown(self, request, context):
        # The daemon is going away; keep feeding temperatures so the fans keep following load.
        return shutdown_pb2.ShutdownResponse()

    # -- monitoring

    def Status(self, request, context):
        if request.device_id != COOLING_ID:
            return status_rpc.StatusResponse()
        with self.state.lock:
            if not self.state.connected:
                return status_rpc.StatusResponse()
            out = []
            for cid in FAN_LABELS:
                target, actual = self.state.fans.get(cid, (0, 0))
                out.append(status_pb2.Status(id=cid, speed=status_pb2.Status.FanSpeed(
                    rpm=actual, duty=min(100.0, round(100.0 * actual / a600hw.MAX_FAN_RPM, 1)))))
            # Pumps have no duty; report speed as % of their nominal rpm so CoolerControl,
            # which graphs duty only, can draw them and a slowing pump shows as a drop.
            for cid, rpm in zip(PUMP_LABELS, self.state.pumps):
                out.append(status_pb2.Status(id=cid, speed=status_pb2.Status.FanSpeed(
                    rpm=rpm, duty=min(100.0, round(100.0 * rpm / a600hw.PUMP_NOMINAL_RPM, 1)))))
            out.append(status_pb2.Status(id="cpu_feed", temp=float(self.state.cpu_c)))
            out.append(status_pb2.Status(id="gpu_feed", temp=float(self.state.gpu_c)))
        return status_rpc.StatusResponse(status=out)

    # -- control

    def ResetChannel(self, request, context):
        return reset_channel_pb2.ResetChannelResponse()

    def EnableManualFanControl(self, request, context):
        return enable_manual_fan_control_pb2.EnableManualFanControlResponse()

    def FixedDuty(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "The a600 cooling controller has no fixed-speed command; choose Quiet or "
                      "Balanced on the plugin page.")

    def SpeedProfile(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "Custom fan curves are not supported yet; choose Quiet or Balanced on the plugin page.")

    def Lcd(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "no LCD")

    def CustomFunctionOne(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "not used")


# ---------------------------------------------------------------- main

def log_level():
    """CoolerControl passes its own log level in CC_LOG (e.g. INFO, DEBUG, WARN)."""
    name = os.environ.get("CC_LOG", "INFO").strip().upper()
    name = {"WARN": "WARNING", "TRACE": "DEBUG"}.get(name, name)
    return getattr(logging, name, logging.INFO) if name in logging.getLevelNamesMapping() else logging.INFO


def main():
    logging.basicConfig(level=log_level(), format="%(levelname)s %(message)s", stream=sys.stdout)
    state, config = State(), Config()
    feeder = Feeder(state, config)
    feeder.start()

    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    ds_grpc.add_DeviceServiceServicer_to_server(DeviceService(state, config), server)
    # The socket is created owner-only: the gRPC API has no authentication, and only
    # CoolerControl (root) needs to connect. Other local users must not drive the hardware.
    old_umask = os.umask(0o077)
    try:
        server.add_insecure_port(f"unix:{SOCKET}")
        server.start()
    finally:
        os.umask(old_umask)
    log.info("Corsair ONE a600 plugin %s listening on %s", VERSION, SOCKET)

    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    signal.signal(signal.SIGINT, lambda *_: done.set())
    feed_died = False
    while not done.wait(1.0):
        if not feeder.is_alive():
            # Should be impossible (the feed loop handles every error). Exit non-zero so
            # systemd restarts the plugin rather than leaving the fans without a feed.
            log.critical("Temperature feed stopped unexpectedly; exiting so the service restarts")
            feed_died = True
            break

    # Fail-safe first: systemd only waits a few seconds before killing the plugin.
    feeder.stop()
    server.stop(grace=1).wait()
    try:
        os.unlink(SOCKET)
    except OSError:
        pass
    if feed_died:
        sys.exit(1)


if __name__ == "__main__":
    main()
