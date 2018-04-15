#!/usr/bin/python3

import os
import dbus
import subprocess
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
loop = GLib.MainLoop()

class LogindManagerProxy:
    name = "org.freedesktop.login1"
    path = "/org/freedesktop/login1"
    interface = "org.freedesktop.login1.Manager"
    def __init__(self, bus):
        self.bus = bus
        dbobj = bus.get_object(LogindManagerProxy.name, LogindManagerProxy.path)
        self.dbif = dbus.Interface(dbobj, dbus_interface=LogindManagerProxy.interface)

    def get_user_session_proxy(self, session_id):
        session_path = self.dbif.GetSession(session_id)
        return LogindSessionProxy(self.bus, session_path)

class LogindSessionProxy:
    name = "org.freedesktop.login1"
    interface = "org.freedesktop.login1.Session"
    properties = "org.freedesktop.DBus.Properties"

    def __init__(self, bus, path):
        dbobj = bus.get_object(LogindSessionProxy.name, path)
        self.dbif = dbus.Interface(dbobj, dbus_interface=LogindSessionProxy.interface)
        self.props = dbus.Interface(dbobj, dbus_interface=LogindSessionProxy.properties)
        self.dbif.connect_to_signal("Lock", lambda: self.on_lock())
        self.dbif.connect_to_signal("Unlock", lambda: self.on_unlock())
        self.locker = None

    def is_locked(self):
        return self.locker is not None and self.locker.poll() is None

    def on_lock(self):
        print("Lock signal")
        if self.is_locked():
            print("Already locked, ignoring lock request")
            return

        self.locker = subprocess.Popen(["/usr/bin/swaylock", "-i", "/boot/background.png", "--scaling", "stretch"])

    def on_unlock(self):
        print("Unlock signal")
        if self.is_locked():
            self.locker.terminate()
        else:
            print("Not locked, ignoring unlock request")

    def get_all(self):
        return self.props.GetAll(LogindSessionProxy.interface)

    def get_prop(self, pname):
        return self.props.Get(LogindSessionProxy.interface, pname)

system_bus = dbus.SystemBus()
manager = LogindManagerProxy(system_bus)
proxy = manager.get_user_session_proxy(os.environ['XDG_SESSION_ID'])

print("{}\t{}\t{}\t{}\t{}".format(proxy.get_prop("Id"), proxy.get_prop("Name"),
    proxy.get_prop("TTY"), proxy.get_prop("Type"), proxy.get_prop("LockedHint")))

loop.run()
