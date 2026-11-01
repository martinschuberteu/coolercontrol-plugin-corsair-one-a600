#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Talk to the running corsair-a600 plugin the way CoolerControl does (for testing).

Usage: test_client.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "corsair-a600", "gen")]

import grpc  # noqa: E402
from coolercontrol.device_service.v1 import device_service_pb2_grpc as ds_grpc  # noqa: E402
from coolercontrol.device_service.v1 import (  # noqa: E402
    health_pb2, list_devices_pb2, status_pb2)

SOCKET = "unix:/tmp/corsair-a600.sock"


def main():
    stub = ds_grpc.DeviceServiceStub(grpc.insecure_channel(SOCKET))
    h = stub.Health(health_pb2.HealthRequest())
    print(f"Health: {h.name} {h.version} status={health_pb2.HealthResponse.Status.Name(h.status)}")
    for d in stub.ListDevices(list_devices_pb2.ListDevicesRequest()).devices:
        kinds = {cid: c.WhichOneof("options") for cid, c in d.info.channels.items()}
        print(f"Device {d.id} ({d.name}): channels {kinds}, temps {list(d.info.temps)}")
        for s in stub.Status(status_pb2.StatusRequest(device_id=d.id)).status:
            metric = s.WhichOneof("metric")
            if metric == "speed":
                duty = f"{s.speed.duty:5.1f} %" if s.speed.HasField("duty") else "      "
                print(f"    {s.id:<9} {s.speed.rpm:5d} rpm {duty}")
            else:
                print(f"    {s.id:<9} {getattr(s, metric)}")


if __name__ == "__main__":
    main()
