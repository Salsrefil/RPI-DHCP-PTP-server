#!/usr/bin/python
# -*- coding:utf-8 -*-
import subprocess
import dbus
import epd2in7
from signal import pause, signal, SIGTERM, SIGINT
from PIL import Image, ImageDraw, ImageFont
from gpiozero import Button


def write_text(text):
    epd.init()
    image = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    draw.text((0, 0), text)
    epd.display(epd.getbuffer(image))
    epd.sleep()


refresh_button = Button(5)
restart_button = Button(6)
button3 = Button(13)
button4 = Button(19)
system_bus = dbus.SystemBus()
epd = epd2in7.EPD()
write_text("Ready!")


def restart():
    subprocess.run(["reboot"])


restart_button.when_pressed = restart


def end_program(signum, frame):
    epd.init()
    epd.Clear()
    epd.sleep()
    epd2in7.epdconfig.module_exit(cleanup=True)
    exit()


signal(SIGTERM, end_program)
signal(SIGINT, end_program)


def refresh():
    link = (
        subprocess.run(
            ["ip --oneline link show dev eth0 | cut -f 1 -d:"],
            capture_output=True,
            shell=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    # TODO: handle UnknownProperty
    leases = system_bus.get_object(
        "org.freedesktop.network1", "/org/freedesktop/network1/link/" + link
    ).Get(
        "org.freedesktop.network1.DHCPServer",
        "Leases",
        dbus_interface="org.freedesktop.DBus.Properties",
    )
    lease_string = "\n".join(
        map(
            lambda l: ".".join(map(str, map(int, l[2])))
            + " "
            + ":".join(map(lambda n: "%x" % n, l[4][:6])),
            leases,
        )
    )
    if lease_string:
        write_text(lease_string)
    else:
        write_text("No leases")


refresh_button.when_pressed = refresh
pause()
