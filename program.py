#!/usr/bin/python
# -*- coding:utf-8 -*-
import subprocess
import json
import epd2in7
from PIL import Image,ImageDraw,ImageFont
from gpiozero import Button

try:
    button = Button(5)
    epd = epd2in7.EPD() 
    while True:
        button.wait_for_press()
        result = subprocess.run(['link_id="$(ip --oneline link show dev eth0 | cut -f 1 -d:)";busctl -j get-property org.freedesktop.network1 "/org/freedesktop/network1/link/${link_id}" org.freedesktop.network1.DHCPServer Leases'],capture_output=True,shell=True)
        leases=json.loads(result.stdout)["data"]
        lease_string = '\n'.join(map(lambda l:'.'.join(map(str,l[2]))+' '+':'.join(map(lambda n:'%x' % n,l[4][:6])),leases))
        epd.init()
        image = Image.new('1',(epd.height,epd.width),255)
        draw = ImageDraw.Draw(image)
        draw.text((0,0),lease_string)
        epd.display(epd.getbuffer(image)) 
        epd.sleep()
except KeyboardInterrupt:    
    epd2in7.epdconfig.module_exit(cleanup=True)
    exit()
