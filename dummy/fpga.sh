#!/bin/sh
# Ecosystem 2.0: the bazaar runs this script (with system()) when the App starts, if fpga.conf is not
# empty. It removes the device tree overlay of the previous FPGA and loads the bitstream of the App
# (fpga.bit.bin, made by bootgen from red_pitaya.bit). Ecosystem 0.9x/1.0 do not use it: they load
# the file named in fpga.conf (red_pitaya.bit).
# new_project.py writes the App name in the path; the Makefile changes it for the _DEBUG package.
rmdir /configfs/device-tree/overlays/Full 2> /dev/null
rm /tmp/loaded_fpga.inf 2> /dev/null
sleep 0.5s
/opt/redpitaya/bin/fpgautil -b /opt/redpitaya/www/apps/dummy/fpga.bit.bin
