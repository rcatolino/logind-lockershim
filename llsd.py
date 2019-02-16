#!/usr/bin/python3

import os
import dbus
import subprocess
import signal
import sys
import time

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
loop = GLib.MainLoop()

class PMProxy:
    name = "org.freedesktop.PowerManagement"
    path = "/org/freedesktop/PowerManagement"
    interface = "org.freedesktop.PowerManagement.Inhibit"
    def __init__(self, bus, session_id):
        self.bus = bus
        dbobj = bus.get_object(PMProxy.name, PMProxy.path)
        self.dbif = dbus.Interface(dbobj, dbus_interface=PMProxy.interface)

    def has_inhibit(self):
        return self.dbif.HasInhibit()

class AlreadyRunningError(Exception):
    pass

class LogindManagerProxy:
    name = "org.freedesktop.login1"
    path = "/org/freedesktop/login1"
    properties = "org.freedesktop.DBus.Properties"
    interface = "org.freedesktop.login1.Manager"

    def __init__(self, bus, session_id, locker_args, pmproxy):
        self.bus = bus
        dbobj = bus.get_object(LogindManagerProxy.name, LogindManagerProxy.path)
        self.dbif = dbus.Interface(dbobj, dbus_interface=LogindManagerProxy.interface)
        self.props = dbus.Interface(dbobj, dbus_interface=LogindSessionProxy.properties)
        self.props.connect_to_signal("PropertiesChanged", lambda ifname, changed_prop, _ :
                self.on_prop_change(ifname, changed_prop))
        session_path = self.dbif.GetSession(session_id)
        self.session_proxy = LogindSessionProxy(self.bus, session_path, locker_args, pmproxy)
        for i in self.dbif.ListInhibitors():
            if i[1] == "Screenlock Manager":
                print("Error LLSD has already been started.")
                raise AlreadyRunningError
        self.get_inhibitor()
        self.dbif.connect_to_signal("PrepareForSleep", lambda before: self.on_sleep(before))

    def on_prop_change(self, interface, changed_prop):
        print("Properties changed : {}/{}".format(interface, changed_prop))

    def get_inhibitor(self):
        self.inhibitor = self.dbif.Inhibit("sleep", "Screenlock Manager",
                "Start the lock screen before going to sleep", "delay")

    def on_sleep(self, before_sleep):
        if before_sleep:
            print("Going to sleep signal, locking")
            self.session_proxy.do_lock()
            time.sleep(0.5) # hum.
            os.close(self.inhibitor.take())
        else:
            self.get_inhibitor()

    def get_user_session_proxy(self):
        return self.session_proxy

class LogindSessionProxy:
    name = "org.freedesktop.login1"
    interface = "org.freedesktop.login1.Session"
    properties = "org.freedesktop.DBus.Properties"

    def __init__(self, bus, path, locker_args, pmproxy):
        dbobj = bus.get_object(LogindSessionProxy.name, path)
        self.dbif = dbus.Interface(dbobj, dbus_interface=LogindSessionProxy.interface)
        self.props = dbus.Interface(dbobj, dbus_interface=LogindSessionProxy.properties)
        signal.signal(signal.SIGCHLD, lambda signum, _: self.reap_locker())
        self.dbif.connect_to_signal("Lock", lambda: self.on_lock())
        self.dbif.connect_to_signal("Unlock", lambda: self.on_unlock())
        self.locker_args = locker_args
        self.pmproxy = pmproxy
        self.locker = None

    def reap_locker(self):
        if self.locker is None:
            return
        result = self.locker.poll()
        print("Locker process returned status {}".format(result))
        self.locker = None

    def is_locked(self):
        return self.locker is not None and self.locker.poll() is None

    def on_lock(self):
        if self.pmproxy.has_inhibit():
            print("Session pm is inhibited, ignoring lock request")
        else:
            self.do_lock()
            time.sleep(1)
            subprocess.run(["swaymsg", "output * dpms off"])

    def do_lock(self):
        print("Lock signal")
        if self.is_locked():
            print("Already locked, ignoring lock request")
            return

        self.locker = subprocess.Popen(self.locker_args)

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

locker_args = sys.argv[1:]
if len(locker_args) == 0 or locker_args[0] == "-h" or locker_args[0] == "--help":
    print("Usage : {} <locker exec> <locker args>".format(sys.argv[0]))
    print("Example : {} /usr/bin/swaylock -i picture.png --scaling stretch".format(sys.argv[0]))
    exit(0)

system_bus = dbus.SystemBus()
session_bus = dbus.SessionBus()
pmproxy = PMProxy(session_bus, os.environ['XDG_SESSION_ID'])
manager = LogindManagerProxy(system_bus, os.environ['XDG_SESSION_ID'], locker_args, pmproxy)
proxy = manager.get_user_session_proxy()

print("{}\t{}\t{}\t{}\t{}".format(proxy.get_prop("Id"), proxy.get_prop("Name"),
    proxy.get_prop("TTY"), proxy.get_prop("Type"), proxy.get_prop("LockedHint")))

loop.run()
