#!/usr/bin/env python3
# This software is distributed under the terms of the MIT License.
# Copyright (c) 2023-2024 Dmitry Ponomarev.
# Author: Dmitry Ponomarev <ponomarevda96@gmail.com>

import os
import sys
import time
import datetime
import math
import asyncio
import pathlib
import numpy as np
import random


repo_dir = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_dir / "build/nunavut_out"))
sys.path.insert(0, str(repo_dir / "cyphal"))
# pylint: disable=import-error
import uavcan.register.Access_1_0
import uavcan.node.Heartbeat_1_0
import uavcan.primitive.array.Natural16_1_0

import uavcan.si.sample.pressure.Scalar_1_0
import uavcan.si.sample.temperature.Scalar_1_0
import uavcan.si.sample.magnetic_field_strength.Vector3_1_1
import uavcan.primitive.scalar.Integer16_1_0
import uavcan.time.SynchronizedTimestamp_1_0

import reg.udral.physics.optics.HighColor_0_1
import reg.udral.service.actuator.common.sp.Vector31_0_1
import reg.udral.service.common.Readiness_0_1

import pycyphal.application

from utils import NodeFinder, PortRegisterInterface

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class Colorizer:
    @staticmethod
    def normal(origin_string):
        return origin_string

    @staticmethod
    def header(origin_string):
        """Purple"""
        return f"{Colors.HEADER}{origin_string}{Colors.ENDC}"

    @staticmethod
    def warning(origin_string):
        "Orange"
        return f"{Colors.WARNING}{origin_string}{Colors.ENDC}"

    @staticmethod
    def okcyan(origin_string):
        return f"{Colors.OKCYAN}{origin_string}{Colors.ENDC}"

    @staticmethod
    def okgreen(origin_string):
        return f"{Colors.OKGREEN}{origin_string}{Colors.ENDC}"


class HighColorPub:
    def __init__(self, node, node_id) -> None:
        self.node = node
        self.node_id = node_id
        self.msg = reg.udral.physics.optics.HighColor_0_1()
        self.red = int(0)
        self.green = int(0)
        self.blue = int(0)
    async def init(self):
        self._pub = self.node.make_publisher(reg.udral.physics.optics.HighColor_0_1, 2107)
        self._pub_counter = 0
    async def process_publisher(self):
        self.red += random.randint(0,1)
        self.green += random.randint(0,2)
        self.blue += random.randint(0,1)

        self.msg.red   = self.red   % 32 if self.red   % 64  < 32 else 63 -  self.red   % 64
        self.msg.green = self.green % 64 if self.green % 128 < 64 else 127 - self.green % 128
        self.msg.blue  = self.blue  % 32 if self.blue  % 64  < 32 else 63 -  self.blue  % 64
        print("Lights:")
        print(f"- HighColor: red={self.msg.red}, green={self.msg.green}, blue={self.msg.blue}")
        self._pub_counter += 1
        await self._pub.publish(self.msg)


class BaseSubscriber:
    def __init__(self, node, node_id, def_id, reg_name, data_type) -> None:
        self.node = node
        self.data = None
        self._id = None
        self.id_updated = False
        self.node_id = node_id
        self.def_id = def_id
        self.reg_name = reg_name
        self.data_type = data_type
        self.port_interface = PortRegisterInterface(self.node)
    async def init(self):
        self._id = await self.port_interface.get_id(self.node_id, self.reg_name)
        assert self._id is not None, f"{self.reg_name} is not exist"
        self.id_updated = (self._id == 0) or (self._id > 8191)

        if self.id_updated:
            self._id = self.port_interface.set_id(self.node_id, self.reg_name, self.def_id)
        assert isinstance(self._id, int), self.reg_name
        self.sub = self.node.make_subscriber(self.data_type, self._id).receive_in_background(self.callback)

    async def callback(self, data, transfer_from):
        self.data = data
        self._transfer_from = transfer_from
    def get_id_string(self):
        if not self.id_updated:
            string =  str(self._id)
        else:
            toggle = bool(int(time.time() * 1000) % 1000 > 500)
            string =  f"{Colors.OKCYAN}{self._id}{Colors.ENDC}" if toggle else str(self._id)
        return string

class CircuitStatusTemperatureSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2102, reg_name="uavcan.pub.crct.temp.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.si.sample.temperature.Scalar_1_0)
    def print_data(self):
        print("CircuitStatus:")
        if self.data is not None:
            kelvin = self.data.kelvin
            celcius = kelvin - 273
        else:
            kelvin = 0
            celcius = 0
        print(f"- crct.temp ({self.get_id_string()}): {kelvin} Kelvin ({celcius} Celcius)")

class GpsSatsSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2001, reg_name="uavcan.pub.zubax.gps.sats.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.primitive.scalar.Integer16_1_0)
    def print_data(self):
        print("GNSS:")
        value = self.data.value if self.data is not None else None
        if value == 0:
            value = Colorizer.header(value)
        print(f"- sats ({self.get_id_string()}): {value}")
        print("- lat:")
        print("- lon:")

class GpsTimeUtcSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2002, reg_name="uavcan.pub.gps.time_utc.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.time.SynchronizedTimestamp_1_0)
    def print_data(self):
        seconds = int(self.data.microsecond / 1000000) if self.data is not None else 0
        print(f"- time_utc ({self.get_id_string()}): {seconds} ({datetime.datetime.fromtimestamp(seconds)})")

class MagnetometerSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2000, reg_name="uavcan.pub.zubax.mag.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.si.sample.magnetic_field_strength.Vector3_1_1)
        self.data = None
    def print_data(self):
        if self.data is not None:
            print(f"Magnetometer zubax.mag ({self.get_id_string()}):")
            mag_field = self.data.ampere_per_meter.tolist()
            print(f"- norm: {np.sqrt(np.sum(np.array(mag_field)**2)):.3f} Amper/meter")
            print(f"- x: {mag_field[0]:.3f} Amper/meter")
            print(f"- y: {mag_field[1]:.3f} Amper/meter")
            print(f"- z: {mag_field[1]:.3f} Amper/meter")
        else:
            print(f"Magnetometer ({self.get_id_string()}) : {Colors.WARNING}NO DATA{Colors.ENDC}")

class BaroPressureSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2100, reg_name="uavcan.pub.zubax.baro.press.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.si.sample.pressure.Scalar_1_0)
    def print_data(self):
        print("Barometer:")
        value = self.data.pascal if self.data is not None else 0.0
        print(f"- zubax.baro.press ({self.get_id_string()}): {value:.2f} Pascal")

class BaroTemperatureSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2101, reg_name="uavcan.pub.zubax.baro.temp.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, uavcan.si.sample.temperature.Scalar_1_0)
    def print_data(self):
        print(f"- zubax.baro.temp ({self.get_id_string()}): {self.data.kelvin:.2f} Kelvin")

class SetpointSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2342, reg_name="uavcan.pub.udral.esc.0.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, reg.udral.service.actuator.common.sp.Vector31_0_1)
        self.max_recv_length = 0
    def print_data(self):
        for idx in range(30, self.max_recv_length - 1, -1):
            is_zero = math.isclose(self.data.value[idx], 0.0, rel_tol=1e-5)
            if not is_zero:
                self.max_recv_length = idx + 1
                break
        print("Actuators:")
        print(f"- udral.esc.0 ({self.get_id_string()}): {self.data.value[0:self.max_recv_length]}")

class ReadinessSub(BaseSubscriber):
    def __init__(self, node, node_id, def_id=2343, reg_name="uavcan.pub.udral.readiness.0.id") -> None:
        super().__init__(node, node_id, def_id, reg_name, reg.udral.service.common.Readiness_0_1)
        self.max_recv_length = 0
    def print_data(self):
        mapping = {
            None:   "-",
            0:      "SLEEP = DISARMED",
            2:      "STANDBY = DISARMED",
            3:      Colorizer.okgreen("ENGAGED = ARMED"),
        }
        value = self.data.value
        print(f"- udral.readiness.0 ({self.get_id_string()}): {value} ({mapping[value]})")

class BaseMonitor:
    def __init__(self, node) -> None:
        self.subs = []
        self.pubs = []
        self.node = node

    async def init(self):
        for sub in self.subs:
            await sub.init()
        for pub in self.pubs:
            await pub.init()

    async def process(self):
        for pub in self.pubs:
            await pub.process_publisher()
        for sub in self.subs:
            sub.print_data()

    @staticmethod
    def get_latest_sw_version() -> int:
        return 0

    @staticmethod
    def get_vssc_meaning(vssc : int) -> str:
        return f"{vssc} (meaning unknown)"


class GpsMagBaroMonitor(BaseMonitor):
    def __init__(self, node, node_id) -> None:
        super().__init__(node)
        self.node_id = node_id

        self.subs = [
            GpsSatsSub(node, node_id),
            GpsTimeUtcSub(node, node_id),
            MagnetometerSub(node, node_id),
            BaroPressureSub(node, node_id),
            BaroTemperatureSub(node, node_id)
        ]

    @staticmethod
    def get_latest_sw_version() -> int:
        return 0xc78d47c3c9744f55

    def get_vssc_meaning(self, vssc: int) -> str:
        bitmask = [
            "cyphal",
            "baro",
            "gps",
            "mag",
            "crct",
            "sys",
        ]

        errors = []
        for number, bit_meaning in enumerate(bitmask):
            if vssc & np.left_shift(1, number):
                errors.append(bit_meaning)

        if len(errors) > 0:
            string = ", ".join(str(error) for error in errors)
            string = f"{Colors.WARNING}{vssc}: ({string}){Colors.ENDC}"
        else:
            string = f"{vssc}"
        return string

class UavLightsMonitor(BaseMonitor):
    def __init__(self, node, node_id) -> None:
        super().__init__(node)
        self.node_id = node_id

        self.subs = [
            CircuitStatusTemperatureSub(node, node_id),
        ]

        self.pubs = [
            HighColorPub(node, node_id),
        ]

class PX4Monitor(BaseMonitor):
    def __init__(self, node, node_id) -> None:
        super().__init__(node)
        self.node_id = node_id
        self.subs = [
            SetpointSub(node, node_id),
            ReadinessSub(node, node_id),
        ]


class RLConfigurator:
    def __init__(self) -> None:
        self.node_id = None
        self.heartbeat = uavcan.node.Heartbeat_1_0()

    async def main(self):
        self.node = pycyphal.application.make_node(uavcan.node.GetInfo_1_0.Response(
                uavcan.node.Version_1_0(major=1, minor=0),
                name="co.raccoonlab.spec_checker"
        ))
        self.node.heartbeat_publisher.mode = uavcan.node.Mode_1_0.OPERATIONAL
        self.node.start()

        heartbeat_sub = self.node.make_subscriber(uavcan.node.Heartbeat_1_0)
        heartbeat_sub.receive_in_background(self._heartbeat_callback)

        info, name, node_monitor = await self._find_node()

        await asyncio.sleep(0.1)
        while True:
            os.system('clear')
            print("RaccoonLab monitor")
            print("Node info:")
            print(f"- Name: {name}")

            print(f"- SW: ", end='')
            sw_version_string = f"v{info['sw_version'][0]}.{info['sw_version'][1]}_{hex(info['git_hash'])[2:]}"
            if node_monitor.get_latest_sw_version() == 0:
                print(f"{sw_version_string} (SW history is unknown)")
            elif info['git_hash'] == node_monitor.get_latest_sw_version():
                print(f"{sw_version_string} (latest)")
            else:
                print(f"{Colors.FAIL}{sw_version_string} (need update){Colors.ENDC}")

            hw_version_string = f"v{info['hw_version'][0]}.{info['hw_version'][1]}"
            print(f"- HW: {hw_version_string}")


            print(f"- ID: {self.node_id}")
            print(f"- Health: {RLConfigurator._health_to_string(self.heartbeat.health.value)}")
            print(f"- Mode: {RLConfigurator._mode_to_string(self.heartbeat.mode.value)}")
            print(f"- VSSC: {node_monitor.get_vssc_meaning(self.heartbeat.vendor_specific_status_code)}")

            print(f"- UID: {info['uid']}")
            print(f"- Uptime: {self.heartbeat.uptime}")
            await node_monitor.process()
            await asyncio.sleep(0.1)

    async def _find_node(self) -> BaseMonitor:
        # 1. Define node ID
        node_finder = NodeFinder(self.node)
        self.node_id = await node_finder.find_online_node(timeout=5.0)
        while self.node_id is None:
            self.node_id = await node_finder.find_online_node(timeout=5.0)

        # 2. Define node name
        info = await node_finder.get_tested_node_info()
        name = info['name']
        if name == 'co.raccoonlab.gps_mag_baro':
            print(f"Node `{name}` has been found.")
            node = GpsMagBaroMonitor(self.node, self.node_id)
        elif name == 'co.raccoonlab.lights':
            print(f"Node `{name}` has been found.")
            node = UavLightsMonitor(self.node, self.node_id)
        elif name == 'PX4_FMU_V5':
            print(f"Node `{name}` has been found.")
            node = PX4Monitor(self.node, self.node_id)
        else:
            print(f"Unknown node `{name}` has been found. Exit")
            sys.exit(0)

        await node.init()
        return info, name, node

    async def _heartbeat_callback(self, data, transfer_from):
        if self.node_id == transfer_from.source_node_id:
            self.heartbeat = data

    @staticmethod
    def _health_to_string(value : int) -> str:
        assert isinstance(value, int)
        mapping = {
            0 : "NOMINAL (0)",
            1 : f"{Colors.HEADER}ADVISORY (1){Colors.ENDC}",
            2 : f"{Colors.WARNING}CAUTION (2){Colors.ENDC}",
            3 : f"{Colors.FAIL}WARNING (3){Colors.ENDC}",
        }
        assert value in mapping
        return mapping[value]

    @staticmethod
    def _mode_to_string(value : int) -> str:
        assert isinstance(value, int)
        mapping = {
            0: "OPERATIONAL",
            1: Colorizer.okcyan("INITIALIZATION"),
            2: Colorizer.header("MAINTENANCE"),
            3: Colorizer.warning("SOFTWARE_UPDATE"),
        }

        return mapping[value]

if __name__ == "__main__":
    rl_configurator = RLConfigurator()
    try:
        asyncio.run(rl_configurator.main())
    except KeyboardInterrupt:
        print("Aborted by KeyboardInterrupt.")
