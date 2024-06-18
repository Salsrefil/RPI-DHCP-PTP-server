#!/usr/bin/python
# -*- coding:utf-8 -*-
import subprocess
import dbus
import re
import shutil
import epd2in7
import flask
import scapy.all as scapy
from datetime import datetime, timezone
from signal import signal, SIGTERM, SIGINT
from PIL import Image, ImageDraw, ImageFont
from gpiozero import Button

font = ImageFont.truetype("/usr/share/fonts/truetype/DejaVuSansMono.ttf")
refresh_button = Button(5)
view_button = Button(6)
mode_button = Button(13)
aux_button = Button(19)
system_bus = dbus.SystemBus()
epd = epd2in7.EPD()
ptp_daemon = None
ptp_master_active = False
dhcp_server_active = False
foreign_dhcp_server = None
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
    ptp_daemon = subprocess.Popen(
        ["ptp4l", "-f", "/home/pi/program/ptpconfig", "-S", "-i", "eth0", "-s"]
    )


def start_ptp_master():
    global ptp_daemon
    if ptp_daemon:
        ptp_daemon.terminate()
    ptp_daemon = subprocess.Popen(
        ["ptp4l", "-f", "/home/pi/program/ptpconfig", "-S", "-i", "eth0"]
    )
    while True:
        result = subprocess.run(
            ["pmc", "-u", "-b", "0", "SET PRIORITY1 0"], capture_output=True, text=True
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "priority1" in line and line.split()[-1] == "0":
                    return


def start_eth_dhcp():
    shutil.copyfile("/home/pi/program/ethdhcp", "/etc/systemd/network/wired.network")
    subprocess.run(["networkctl", "reload"], capture_output=True, text=True)


def start_eth_static():
    shutil.copyfile("/home/pi/program/ethstatic", "/etc/systemd/network/wired.network")
    subprocess.run(["networkctl", "reload"], capture_output=True, text=True)


def dhcp_scan():
    global foreign_dhcp_server
    scapy.conf.checkIPaddr = False
    fam, hw = scapy.get_if_raw_hwaddr("eth0")
    dhcp_discover = (
        scapy.Ether(dst="ff:ff:ff:ff:ff:ff")
        / scapy.IP(src="0.0.0.0", dst="255.255.255.255")
        / scapy.UDP(sport=68, dport=67)
        / scapy.BOOTP(chaddr=hw)
        / scapy.DHCP(options=[("message-type", "discover"), "end"])
    )
    ans, unans = scapy.srp(
        dhcp_discover, multi=True, timeout=5, verbose=0, iface="eth0"
    )
    for snd, rcv in ans:
        if scapy.DHCP in rcv and rcv[scapy.DHCP].options[0][1] == 2:
            dhcp_server_ip = rcv[scapy.IP].src
            foreign_dhcp_server = dhcp_server_ip
            if dhcp_server_active:
                toggle_dhcp_server()
            elif current_view == "dhcp":
                refresh()
            return
    foreign_dhcp_server = None
    if current_view == "dhcp":
        refresh()


def get_dhcp_info():
    info = {
        "dhcp_server_active": dhcp_server_active,
        "my_ip": None,
        "leases": None,
        "foreign_dhcp_server": foreign_dhcp_server,
    }
    if dhcp_server_active:
        info.update({"my_ip": "10.0.0.1"})
        try:
            link = subprocess.run(
                ["ip --oneline link show dev eth0 | cut -f 1 -d:"],
                capture_output=True,
                shell=True,
                text=True,
            ).stdout.strip()
            lease_struct = system_bus.get_object(
                "org.freedesktop.network1", "/org/freedesktop/network1/link/" + link
            ).Get(
                "org.freedesktop.network1.DHCPServer",
                "Leases",
                dbus_interface="org.freedesktop.DBus.Properties",
            )
            leases = list(
                map(
                    lambda l: ".".join(map(str, map(int, l[2])))
                    + " "
                    + ":".join(map(lambda n: "%x" % n, l[4][:6])),
                    lease_struct,
                )
            )
            if leases:
                info.update({"leases": leases})
        except dbus.exceptions.DBusException:
            return info
    else:
        result = subprocess.run(
            ["networkctl", "status"], capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if re.match(r".*\d+\.\d+\.\d+\.\d+ on eth0", line):
                info.update({"my_ip": line.split()[-3]})
                break
    return info


def clock_identity_to_mac(clock_identity):
    parts = clock_identity.strip().split(".")
    parts = parts[0] + parts[2]
    return ":".join(a + b for a, b in zip(parts[::2], parts[1::2]))


def get_ptp_info():
    info = {
        "ptp_master_active": ptp_master_active,
        "foreign_master": False,
        "current_time": None,
        "current_offset": None,
        "current_master": None,
        "master_description": None,
        "clock_count": None,
    }
    result = subprocess.run(
        ["pmc", "-u", "-b", "0", "GET TIME_STATUS_NP"], capture_output=True, text=True
    )
    if result.returncode == 0:
        time = 0
        for line in result.stdout.split("\n"):
            if not ptp_master_active:
                if "gmPresent" in line and "true" in line:
                    info.update({"foreign_master": True})
                if "ingress_time" in line:
                    time += int(line.split()[-1])
                if "master_offset" in line:
                    time -= int(line.split()[-1])
                    info.update({"current_offset": line.split()[-1]})
            if "gmIdentity" in line:
                info.update({"current_master": clock_identity_to_mac(line.split()[-1])})
        if not ptp_master_active:
            info.update(
                {
                    "current_time": datetime.fromtimestamp(
                        time / 1e9, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S.%f")
                }
            )
        else:
            info.update(
                {
                    "current_time": datetime.now(tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S.%f"
                    )
                }
            )
    else:
        return None
    result = subprocess.run(
        ["pmc", "-u", "-b", "1000", "GET CLOCK_DESCRIPTION"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        master_found = False
        client_count = -1
        for line in result.stdout.split("\n"):
            if re.match(r"^\t[a-f\d]{6}\.[a-f\d]{4}\.[a-f\d]{6}", line):
                client_count += 1
            if (
                not info["master_description"]
                and info["foreign_master"]
                and info["current_master"]
            ):
                if (
                    not master_found
                    and "physicalAddress" in line
                    and info["current_master"] in line
                ):
                    master_found = True
                if master_found and "productDescription" in line:
                    master_description = line.strip().split(maxsplit=1)[-1].split(";")
                    if master_description[0] or master_description[1]:
                        info.update(
                            {
                                "master_description": master_description[0]
                                + ":"
                                + master_description[1]
                            }
                        )
        info.update({"clock_count": client_count})
    else:
        return None
    return info


def draw_labels(image, label1, label2, label3, label4):
    # 264 × 176
    button_labels = Image.new("1", (176, font.size + 10), 255)
    button_labels_draw = ImageDraw.Draw(button_labels)
    button_labels_draw.text((22, 5), label1, font=font, anchor="ma")
    button_labels_draw.text((66, 5), label2, font=font, anchor="ma")
    button_labels_draw.text((110, 5), label3, font=font, anchor="ma")
    button_labels_draw.text((154, 5), label4, font=font, anchor="ma")
    button_labels_draw.rectangle([0, 0, 44, font.size + 10])
    button_labels_draw.rectangle([44, 0, 88, font.size + 10])
    button_labels_draw.rectangle([88, 0, 132, font.size + 10])
    button_labels_draw.rectangle([132, 0, 176, font.size + 10])
    button_labels = button_labels.rotate(-90, expand=1)
    image.paste(button_labels, (0, 0))


def show_dhcp():
    info = get_dhcp_info()
    image = Image.new("1", (epd.height, epd.width), 255)
    if dhcp_server_active:
        draw_labels(image, "Refresh", "PTP", "Client", "Scan")
    else:
        if not foreign_dhcp_server:
            draw_labels(image, "Refresh", "PTP", "Server", "Scan")
        else:
            draw_labels(image, "Refresh", "PTP", "", "Scan")
    draw = ImageDraw.Draw(image)
    if dhcp_server_active:
        if info["leases"]:
            leases = "\n".join(info["leases"])
        else:
            leases = "None"
        response = f"Working as DHCP server\nMy IP:\n{info['my_ip']}\nLeases:\n{leases}"
    else:
        response = f"Working as DHCP client\nDHCP server IP:\n{info['foreign_dhcp_server']}\nLeased IP:\n{info['my_ip']}"
    draw.text((font.size + 20, 10), response, font=font)
    show_image(image)


def show_ptp():
    image = Image.new("1", (epd.height, epd.width), 255)
    if ptp_master_active:
        draw_labels(image, "Refresh", "DHCP", "Slave", "")
    else:
        draw_labels(image, "Refresh", "DHCP", "Master", "Sync")
    draw = ImageDraw.Draw(image)
    info = get_ptp_info()
    if ptp_master_active:
        response = f"Working as PTP master\nMy MAC:\n{info['current_master']}\nCurrent time:\n{info['current_time']}\nClock count:\n{info['clock_count']}"
    else:
        if info["foreign_master"]:
            response = f"Working as PTP slave\nMaster MAC:\n{info['current_master']}\nMaster description:\n{info['master_description']}\nCurrent time:\n{info['current_time']}\nCurrent offset:\n{info['current_offset']}ns\nClock count:\n{info['clock_count']}"
        else:
            response = f"Working as PTP slave\n(No foreign master found)\nClock count:\n{info['clock_count']}"
    draw.text((font.size + 20, 10), response, font=font)
    show_image(image)


def refresh():
    if current_view == "dhcp":
        if foreign_dhcp_server:
            mode_button.when_pressed = None
        else:
            mode_button.when_pressed = toggle_dhcp_server
        aux_button.when_pressed = dhcp_scan
        show_dhcp()
    elif current_view == "ptp":
        mode_button.when_pressed = toggle_ptp_master
        if ptp_master_active:
            aux_button.when_pressed = None
        else:
            aux_button.when_pressed = sync_time
        show_ptp()


def switch_view():
    global current_view
    if current_view == "dhcp":
        current_view = "ptp"
    elif current_view == "ptp":
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
    if current_view == "ptp":
        refresh()


def toggle_dhcp_server():
    global dhcp_server_active
    if dhcp_server_active:
        start_eth_dhcp()
        dhcp_server_active = False
    else:
        if not foreign_dhcp_server:
            start_eth_static()
            dhcp_server_active = True
    if current_view == "dhcp":
        refresh()


def set_time(datetime):
    subprocess.run(
        [
            "timedatectl",
            "set-time",
            datetime.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
        ],
        capture_output=True,
        text=True,
    )
    if current_view == "ptp":
        refresh()


def sync_time():
    if ptp_master_active:
        return
    result = subprocess.run(
        ["pmc", "-u", "-b", "0", "GET TIME_STATUS_NP"], capture_output=True, text=True
    )
    if result.returncode == 0:
        time = 0
        foreign = False
        for line in result.stdout.split("\n"):
            if "gmPresent" in line and "true" in line:
                foreign = True
            if "ingress_time" in line:
                time += int(line.split()[-1])
            if "master_offset" in line:
                time -= int(line.split()[-1])
        if foreign:
            set_time(datetime.fromtimestamp(time / 1e9, tz=timezone.utc))
            if current_view == "ptp":
                refresh()


# connect to network for development
subprocess.run(
    ["/home/pi/program/switch_ap"], capture_output=True, shell=True, text=True
)
dhcp_scan()
start_eth_dhcp()
start_ptp_slave()
refresh_button.when_pressed = refresh
view_button.when_pressed = switch_view
signal(SIGTERM, end_program)
signal(SIGINT, end_program)
refresh()
app = flask.Flask(
    __name__,
    static_url_path="",
    static_folder="static",
)


@app.get("/ptp_info")
def ptp_info_handler():
    return flask.jsonify(get_ptp_info())


@app.get("/dhcp_info")
def dhcp_info_handler():
    return flask.jsonify(get_dhcp_info())


@app.post("/dhcp_toggle")
def dhcp_toggle_handler():
    toggle_dhcp_server()
    return flask.Response(status=200)


@app.post("/dhcp_scan")
def dhcp_scan_handler():
    dhcp_scan()
    return flask.Response(status=200)


@app.post("/ptp_toggle")
def ptp_toggle_handler():
    toggle_ptp_master()
    return flask.Response(status=200)


@app.post("/set_time")
def set_time_handler():
    set_time(datetime.fromisoformat(flask.request.json["time"]))
    return flask.Response(status=200)


@app.post("/sync_time")
def sync_time_handler():
    sync_time()
    return flask.Response(status=200)


@app.errorhandler(404)
def spa_handler(error):
    return flask.send_file("static/index.html")


app.run(host="0.0.0.0", port="80")
