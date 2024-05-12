#!/usr/bin/python
# -*- coding:utf-8 -*-
import subprocess
import dbus
import epd2in7
from signal import pause, signal, SIGTERM, SIGINT
from PIL import Image, ImageDraw, ImageFont
from gpiozero import Button

font = ImageFont.truetype("/usr/share/fonts/truetype/DejaVuSansMono.ttf")
refresh_button = Button(5)
restart_button = Button(6)
dhcp_button = Button(13)
ptp_button = Button(19)
system_bus = dbus.SystemBus()
epd = epd2in7.EPD()
current_view = "dhcp"


def show_image(image):
    epd.init()
    epd.display(epd.getbuffer(image))
    epd.sleep()


def restart():
    subprocess.run(["reboot"])


def end_program(signum, frame):
    epd.init()
    epd.Clear()
    epd.sleep()
    epd2in7.epdconfig.module_exit(cleanup=True)
    exit()


def get_leases():
    try:
        link = (
            subprocess.run(
                ["ip --oneline link show dev eth0 | cut -f 1 -d:"],
                capture_output=True,
                shell=True,
                text=True
            )
            .stdout
            .strip()
        )
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
            return lease_string
        else:
            return "No leases"
    except dbus.exceptions.DBusException:
        return "Interface not configured yet"


def get_ptp_info():
    result = subprocess.run(
        ["pmc", "-u", "GET TIME_STATUS_NP"], capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.split('\n'):
            if "gmIdentity" in line:
                grandmaster_id = line.split()[-1].strip().split(".")
                grandmaster_id = grandmaster_id[0]+grandmaster_id[2]
                grandmaster_id = ':'.join(
                    a + b for a, b in zip(grandmaster_id[::2], grandmaster_id[1::2]))
                return f"Grandmaster: {grandmaster_id}"
    else:
        return "Failed to get data"


def draw_labels(image):
    # 264 × 176
    button_labels = Image.new("1", (176, font.size+10), 255)
    button_labels_draw = ImageDraw.Draw(button_labels)
    button_labels_draw.text((22, 5), "Refresh", font=font, anchor="ma")
    button_labels_draw.text((66, 5), "Reboot", font=font, anchor="ma")
    button_labels_draw.text((110, 5), "DHCP", font=font, anchor="ma")
    button_labels_draw.text((154, 5), "PTP", font=font, anchor="ma")
    button_labels_draw.rectangle([0, 0, 44, font.size+10])
    button_labels_draw.rectangle([44, 0, 88, font.size+10])
    button_labels_draw.rectangle([88, 0, 132, font.size+10])
    button_labels_draw.rectangle([132, 0, 176, font.size+10])
    button_labels = button_labels.rotate(-90, expand=1)
    image.paste(button_labels, (0, 0))


def show_dhcp():
    image = Image.new("1", (epd.height, epd.width), 255)
    draw_labels(image)
    draw = ImageDraw.Draw(image)
    draw.text((font.size+20, 10), "DHCP Info:\n"+get_leases(), font=font)
    show_image(image)


def show_ptp():
    image = Image.new("1", (epd.height, epd.width), 255)
    draw_labels(image)
    draw = ImageDraw.Draw(image)
    draw.text((font.size+20, 10), "PTP Info:\n"+get_ptp_info(), font=font)
    show_image(image)


def refresh():
    if current_view == "dhcp":
        show_dhcp()
    elif current_view == "ptp":
        show_ptp()


def set_view(view):
    global current_view
    current_view = view
    refresh()


restart_button.when_pressed = restart
refresh_button.when_pressed = refresh
dhcp_button.when_pressed = lambda: set_view("dhcp")
ptp_button.when_pressed = lambda: set_view("ptp")
signal(SIGTERM, end_program)
signal(SIGINT, end_program)
refresh()
pause()
