#!/usr/bin/python
# -*- coding:utf-8 -*-
import subprocess
import dbus
import re
import epd2in7
from datetime import datetime, timezone
from signal import pause, signal, SIGTERM, SIGINT
from PIL import Image, ImageDraw, ImageFont
from gpiozero import Button

font = ImageFont.truetype("/usr/share/fonts/truetype/DejaVuSansMono.ttf")
refresh_button = Button(5)
restart_button = Button(6)
view_switch_button = Button(13)
server_button = Button(19)
system_bus = dbus.SystemBus()
epd = epd2in7.EPD()
ptp_daemon = None
ptp_master_active = False
current_view = "ptp"


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


def start_ptp_slave():
    global ptp_daemon
    if ptp_daemon:
        ptp_daemon.terminate()
    ptp_daemon = subprocess.Popen(["ptp4l", "-f", "/home/pi/program/ptpconfig", "-S", "-i", "eth0", "-s"])


def start_ptp_master():
    global ptp_daemon
    if ptp_daemon:
        ptp_daemon.terminate()
    ptp_daemon = subprocess.Popen(["ptp4l", "-f", "/home/pi/program/ptpconfig", "-S", "-i", "eth0"])
    while True:
        result = subprocess.run(["pmc", "-u", "-b", "0", "SET PRIORITY1 0"], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if "priority1" in line and line.split()[-1] == "0":
                    return


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
            return "(no leases)"
    except dbus.exceptions.DBusException:
        return "Interface not configured yet"


def clock_identity_to_mac(clock_identity):
    parts = clock_identity.strip().split(".")
    parts = parts[0]+parts[2]
    return ':'.join(
        a + b for a, b in zip(parts[::2], parts[1::2]))


def get_master():
    info = {
        "foreign_master": False,
        "current_time": None,
        "current_offset": None,
        "current_master": None,
        "master_description": None,
        "clock_count": None
    }
    result = subprocess.run(
        ["pmc", "-u", "-b", "0", "GET TIME_STATUS_NP"], capture_output=True, text=True)
    if result.returncode == 0:
        time = 0
        for line in result.stdout.split('\n'):
            if "gmPresent" in line:
                if "true" in line:
                    info.update({"foreign_master": True})
            if "ingress_time" in line:
                time += int(line.split()[-1])
            if "master_offset" in line:
                time -= int(line.split()[-1])
                info.update({"current_offset": line.split()[-1]})
            if "gmIdentity" in line:
                info.update(
                    {"current_master": clock_identity_to_mac(line.split()[-1])})
        info.update({"current_time": datetime.fromtimestamp(time/1e9, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")})
    else:
        return None
    result = subprocess.run(
        ["pmc", "-u", "-b", "1000", "GET CLOCK_DESCRIPTION"], capture_output=True, text=True)
    if result.returncode == 0:
        master_found = False
        client_count = -1
        for line in result.stdout.split('\n'):
            if re.match(r"^\t[a-f\d]{6}.[a-f\d]{4}.[a-f\d]{6}", line):
                client_count += 1
            if not info["master_description"] and info["foreign_master"] and info["current_master"]:
                if not master_found and "physicalAddress" in line and info["current_master"] in line:	
                    master_found = True
                if master_found and "productDescription" in line:
                    master_description = line.strip().split(maxsplit=1)[-1].split(';')
                    if master_description[0] or master_description[1]:
                        info.update({"master_description": master_description[0]+":"+master_description[1]})
        info.update({"clock_count": client_count})
    else:
        return None
    return info


def draw_labels(image, label1, label2, label3, label4):
    # 264 × 176
    button_labels = Image.new("1", (176, font.size+10), 255)
    button_labels_draw = ImageDraw.Draw(button_labels)
    button_labels_draw.text((22, 5), label1, font=font, anchor="ma")
    button_labels_draw.text((66, 5), label2, font=font, anchor="ma")
    button_labels_draw.text((110, 5), label3, font=font, anchor="ma")
    button_labels_draw.text((154, 5), label4, font=font, anchor="ma")
    button_labels_draw.rectangle([0, 0, 44, font.size+10])
    button_labels_draw.rectangle([44, 0, 88, font.size+10])
    button_labels_draw.rectangle([88, 0, 132, font.size+10])
    button_labels_draw.rectangle([132, 0, 176, font.size+10])
    button_labels = button_labels.rotate(-90, expand=1)
    image.paste(button_labels, (0, 0))


def show_dhcp():
    image = Image.new("1", (epd.height, epd.width), 255)
    draw_labels(image, "Refresh", "Reboot", "PTP", "")
    draw = ImageDraw.Draw(image)
    draw.text((font.size+20, 10), "DHCP Info:\n"+get_leases(), font=font)
    show_image(image)


def show_ptp():
    image = Image.new("1", (epd.height, epd.width), 255)
    if ptp_master_active:
        draw_labels(image, "Refresh", "Reboot", "DHCP", "Slave")
    else:
        draw_labels(image, "Refresh", "Reboot", "DHCP", "Master")
    draw = ImageDraw.Draw(image)
    info = get_master()
    if ptp_master_active:
        response = f"Working as PTP master\nMy MAC:\n{info['current_master']}\nClock count:\n{info['clock_count']}"
    else:
        response = "Working as PTP slave\n"
        if info["foreign_master"]:
            response += f"Master MAC:\n{info['current_master']}\nMaster description:\n{info['master_description']}\nCurrent time:\n{info['current_time']}\nCurrent offset:\n{info['current_offset']}ns\nClock count:\n{info['clock_count']}"
        else:
            response += "(No foreign master found)"
    draw.text((font.size+20, 10), response, font=font)
    show_image(image)


def refresh():
    if current_view == "dhcp":
        show_dhcp()
    elif current_view == "ptp":
        show_ptp()


def switch_view():
    global current_view
    if current_view == "dhcp":
        server_button.when_pressed = toggle_ptp_master
        current_view = "ptp"
    elif current_view == "ptp":
        server_button.when_pressed = None
        current_view = "dhcp"
    refresh()


def toggle_ptp_master():
    global ptp_master_active
    if ptp_master_active:
        start_ptp_slave()
        ptp_master_active = False
    else:
        start_ptp_master()
        ptp_master_active = True
    refresh()


start_ptp_slave()
restart_button.when_pressed = restart
refresh_button.when_pressed = refresh
view_switch_button.when_pressed = switch_view
server_button.when_pressed = toggle_ptp_master
signal(SIGTERM, end_program)
signal(SIGINT, end_program)
refresh()
pause()
