#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import threading
import time

import frida

from lib.core.frida_thread import FridaThread
from lib.core.thread_manager import thread_manager
from lib.core.types import FakeDevice
from lib.utils.shell import Shell


class WatchThread(threading.Thread):

    def __init__(self, install: bool, port: int, regexps: list, spawn: bool):
        super().__init__()

        self.log = logging.getLogger(self.__class__.__name__)

        self.install = install
        self.port = port
        self.regexps = regexps
        self.spawn = spawn
        self.frida_threads = []
        self.stop_flag = False

        thread_manager.add_thread(self)

    def run(self) -> None:
        self.log.debug('{} start'.format(self.__class__.__name__))

        while True:
            if self.stop_flag:
                break

            devices = frida.enumerate_devices()

            # usb devices from frida api
            usb_devices = [device for device in devices if device.type == 'usb']
            usb_devices_ids = [device.id for device in usb_devices]

            # devices strings from "adb devices"
            adb_devices_strings = Shell().cmd_and_debug('adb devices', debug=False)['out'].split('\n')[1:]
            adb_devices_strings = [_.split('\t')[0] for _ in adb_devices_strings]

            # we need to access these devices remotely
            remote_devices_strings = set(adb_devices_strings) - set(usb_devices_ids)
            remote_devices = []

            for _ in remote_devices_strings:
                new_device = FakeDevice()
                new_device.id = _
                remote_devices.append(new_device)

            for device in usb_devices + remote_devices:
                duplicated = False

                for t in self.frida_threads:
                    if t.device.id == device.id:
                        if not t.is_alive():
                            self.frida_threads.remove(t)
                            break

                        duplicated = True
                        break

                if duplicated:
                    continue

                try:
                    frida_thread = FridaThread(device, self.install, self.port, self.regexps, self.spawn)
                except RuntimeError as e:
                    self.log.error('error occurred when init frida thread: {}'.format(e))
                else:
                    frida_thread.start()
                    self.frida_threads.append(frida_thread)

            time.sleep(0.1)

        self.shutdown()
        self.log.debug('watch thread exit')

    def cancel(self):
        self.stop_flag = True

    def shutdown(self):
        for frida_thread in self.frida_threads:
            if frida_thread.is_alive():
                frida_thread.cancel()

        thread_manager.del_thread(self)
