#
#

APP=$(notdir $(CURDIR:%/=%))

-include ../_settings.env
-include ../_build_number


# Versioning system
BUILD_NUMBER ?= 0
REVISION ?= devbuild
VER:=$(shell cat info/info.json | grep version | sed -e 's/.*:\ *\"//' | sed -e 's/-.*//')

INSTALL_DIR ?= .


CONTROLLERHF   = controllerhf.so
CONTROLLER_DBG = controllerhf_dbg.so
CONTROLLER_RLD = controllerhf_rld.so


# Ecosystem 2.0: the FPGA is loaded from fpga.bit.bin by fpga.sh (fpgautil). bootgen (Vivado 2020.1)
# converts fpga.bit (a copy of red_pitaya.bit, synthesized with Vivado 2015.2) into fpga.bit.bin.
# Ecosystem 0.9x/1.0 load red_pitaya.bit (fpga.conf). Both files go in the packages.
FPGA_BIN         = fpga.bit.bin
BOOTGEN_SETTINGS ?= /tools/Xilinx/Vivado/2020.1/settings64.sh


CFLAGS += -DVERSION=$(VER)-$(BUILD_NUMBER) -DREVISION=$(REVISION)
export CFLAGS


# fpga/app are PHONY: with fpga.sh present, make's implicit rule '%: %.sh' would
# otherwise turn the target 'fpga' (a directory) into 'cat fpga.sh > fpga'
.PHONY: clean clean_fpga clean_app clean_target app fpga zip tar

all: $(CONTROLLERHF) fpga

# The three controllers: src/Makefile compiles each one in its own object folder
# (controllerhf_dbg.so with -DDEBUG=1, controllerhf_rld.so with -DRELOAD)
$(CONTROLLERHF):
	$(MAKE) -C src ../$(CONTROLLERHF)

$(CONTROLLER_DBG):
	$(MAKE) -C src ../$(CONTROLLER_DBG)

$(CONTROLLER_RLD):
	$(MAKE) -C src ../$(CONTROLLER_RLD)


app: $(CONTROLLERHF)

fpga: red_pitaya.bit fpga.bit $(FPGA_BIN)

red_pitaya.bit:
	cd fpga && $(MAKE) out/red_pitaya.bit
	cp fpga/out/red_pitaya.bit .

fpga.bit: red_pitaya.bit
	cp red_pitaya.bit ./fpga.bit

# .bit -> .bin for Ecosystem 2.0 (bash: make runs /bin/sh, which has no 'source')
$(FPGA_BIN): fpga.bit
	@test -f "$(BOOTGEN_SETTINGS)" || { echo "ERROR: Vivado 2020.1 (bootgen) not found: $(BOOTGEN_SETTINGS) (set BOOTGEN_SETTINGS=...)"; exit 1; }
	printf "all:{ fpga.bit }\n" > fpga.bif
	bash -c '. $(BOOTGEN_SETTINGS) > /dev/null && bootgen -image fpga.bif -arch zynq -process_bitstream bin -w on'

# Files of the App on the board (the controller is renamed to controllerhf.so in each package)
APP_FILES = fpga.conf info py css js index.html nginx.conf

target/$(APP): red_pitaya.bit $(FPGA_BIN) $(CONTROLLERHF) index.html
	mkdir -p target/$(APP)
	cp -r $(CONTROLLERHF) $(APP_FILES) fpga.sh $(FPGA_BIN) red_pitaya.bit target/$(APP)
	chmod 755 target/$(APP)/fpga.sh  # 2.0 runs it with system(): needs the exec bit
	rm target/$(APP)/info/icon_*.png
	cp -r upload_app.sh target/
	cp -r ../resources target/
	cp ../CHANGELOG.md ../README.md target/
	find target -name __pycache__ -type d -prune -exec rm -rf {} +
	sed -i target/$(APP)/info/info.json -e 's/REVISION/$(REVISION)/'
	sed -i target/$(APP)/info/info.json -e 's/BUILD_NUMBER/$(BUILD_NUMBER)/'
	sed -i target/$(APP)/index.html -e "s/\(\\s*\)var\\s*app_version\\s*=\\s*'VERSION'\\s*;\\s*/\\1var app_version = '$(VER)-$(BUILD_NUMBER)-$(REVISION)';/"

target_dbg/$(APP)_DEBUG: red_pitaya.bit $(FPGA_BIN) $(CONTROLLER_DBG) index.html
	mkdir -p target_dbg/$(APP)_DEBUG
	cp -r $(CONTROLLER_DBG) $(APP_FILES) fpga.sh $(FPGA_BIN) red_pitaya.bit target_dbg/$(APP)_DEBUG
	chmod 755 target_dbg/$(APP)_DEBUG/fpga.sh
	cat target_dbg/$(APP)_DEBUG/info/icon_DEBUG.png > target_dbg/$(APP)_DEBUG/info/icon.png
	rm  target_dbg/$(APP)_DEBUG/info/icon_*.png
	mv  target_dbg/$(APP)_DEBUG/$(CONTROLLER_DBG) target_dbg/$(APP)_DEBUG/$(CONTROLLERHF)
	cp -r upload_app.sh target_dbg/
	cp -r ../resources target_dbg/
	cp ../CHANGELOG.md ../README.md target_dbg/
	find target_dbg -name __pycache__ -type d -prune -exec rm -rf {} +
	sed -i target_dbg/upload_app.sh -e 's?^APP="$(APP)"?APP="$(APP)_DEBUG"?'
	sed -i target_dbg/$(APP)_DEBUG/info/info.json -e 's/REVISION/$(REVISION)_DEBUG/'
	sed -i target_dbg/$(APP)_DEBUG/info/info.json -e 's/BUILD_NUMBER/$(BUILD_NUMBER)/'
	sed -i target_dbg/$(APP)_DEBUG/index.html -e "s/\(\\s*\)var\\s*app_version\\s*=\\s*'VERSION'\\s*;\\s*/\\1var app_version = '$(VER)-$(BUILD_NUMBER)-$(REVISION)_DEBUG';/"
	sed -i target_dbg/$(APP)_DEBUG/index.html -e "s/\(\\s*\)var\\s*app_id\\s*=\\s*'$(APP)'\\s*;\\s*/\\1var app_id = '$(APP)_DEBUG';/"
	sed -i target_dbg/$(APP)_DEBUG/fpga.conf  -e "s?/apps/$(APP)/?/apps/$(APP)_DEBUG/?"
	sed -i target_dbg/$(APP)_DEBUG/fpga.sh    -e "s?/apps/$(APP)/?/apps/$(APP)_DEBUG/?"
	sed -i target_dbg/$(APP)_DEBUG/nginx.conf -e "s? /$(APP)/? /$(APP)_DEBUG/?g"

# _RELOAD keeps the FPGA already loaded: empty fpga.conf, no fpga.sh / bitstreams
target_rld/$(APP)_RELOAD: $(CONTROLLER_RLD) index.html
	mkdir -p target_rld/$(APP)_RELOAD
	cp -r $(CONTROLLER_RLD) $(APP_FILES) target_rld/$(APP)_RELOAD
	: > target_rld/$(APP)_RELOAD/fpga.conf
	cat   target_rld/$(APP)_RELOAD/info/icon_RELOAD.png > target_rld/$(APP)_RELOAD/info/icon.png
	rm    target_rld/$(APP)_RELOAD/info/icon_*.png
	mv    target_rld/$(APP)_RELOAD/$(CONTROLLER_RLD) target_rld/$(APP)_RELOAD/$(CONTROLLERHF)
	cp -r upload_app.sh target_rld/
	cp -r ../resources target_rld/
	cp ../CHANGELOG.md ../README.md target_rld/
	find target_rld -name __pycache__ -type d -prune -exec rm -rf {} +
	sed -i target_rld/upload_app.sh -e 's?^APP="$(APP)"?APP="$(APP)_RELOAD"?'
	sed -i target_rld/$(APP)_RELOAD/info/info.json -e 's/REVISION/$(REVISION)_RELOAD/'
	sed -i target_rld/$(APP)_RELOAD/info/info.json -e 's/BUILD_NUMBER/$(BUILD_NUMBER)/'
	sed -i target_rld/$(APP)_RELOAD/index.html -e "s/\(\\s*\)var\\s*app_version\\s*=\\s*'VERSION'\\s*;\\s*/\\1var app_version = '$(VER)-$(BUILD_NUMBER)-$(REVISION)_RELOAD';/"
	sed -i target_rld/$(APP)_RELOAD/index.html -e "s/\(\\s*\)var\\s*app_id\\s*=\\s*'$(APP)'\\s*;\\s*/\\1var app_id = '$(APP)_RELOAD';/"
	sed -i target_rld/$(APP)_RELOAD/nginx.conf -e "s? /$(APP)/? /$(APP)_RELOAD/?g"


zip: $(CONTROLLERHF) target/$(APP) target_dbg/$(APP)_DEBUG target_rld/$(APP)_RELOAD
	mkdir -p ../archive
	cd target; zip -r $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION).zip *
	mv target/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION).zip ../archive/.
	cd target_dbg; zip -r $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_DEBUG.zip *
	mv target_dbg/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_DEBUG.zip ../archive/.
	cd target_rld; zip -r $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_RELOAD.zip *
	mv target_rld/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_RELOAD.zip ../archive/.

tar: $(CONTROLLERHF) target/$(APP) target_dbg/$(APP)_DEBUG target_rld/$(APP)_RELOAD
	mkdir -p ../archive
	cd target; tar -czf $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION).tar.gz *
	mv target/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION).tar.gz ../archive/.
	cd target_dbg; tar -czf $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_DEBUG.tar.gz *
	mv target_dbg/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_DEBUG.tar.gz ../archive/.
	cd target_rld; tar -czf $(INSTALL_DIR)/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_RELOAD.tar.gz *
	mv target_rld/$(APP)-$(VER)-$(BUILD_NUMBER)-$(REVISION)_RELOAD.tar.gz ../archive/.

clean_target:
	-$(RM) target -rf
	-$(RM) target_dbg -rf
	-$(RM) target_rld -rf

clean_app:
	$(MAKE) -C src clean
	-$(RM) target -rf
	-$(RM) target_dbg -rf
	-$(RM) target_rld -rf
	-$(RM) *.so
	echo "BUILD_NUMBER=$$(( $(BUILD_NUMBER) + 1 ))" > ../_build_number

clean_fpga:
	$(MAKE) -C fpga clean
	-$(RM) target -rf
	-$(RM) target_dbg -rf
	-$(RM) target_rld -rf
	-$(RM) -f red_pitaya.bit fpga.bit fpga.bif $(FPGA_BIN)
	echo "BUILD_NUMBER=$$(( $(BUILD_NUMBER) + 1 ))" > ../_build_number

clean: clean_app clean_fpga clean_target



# Upload to a Red Pitaya (never run by the build): RPIP (and RPOPTS/RPSCP) from ../_settings.env or the
# command line, e.g.  make upload RPIP=rp-XXXXXX.local
# The file system is made writable with the rw script of the OS: /opt/redpitaya/sbin/rw in Ecosystem 2.0,
# /boot/sbin/rw in 0.9x (it needs PATH_REDPITAYA exported). fpga.sh keeps its exec bit (2.0 runs it).
# After an upload, stop and start the App (bazaar?stop / bazaar?start, or open it from the menu).
RPOPTS ?= -l root
RP_RW   = export PATH_REDPITAYA=/opt/redpitaya ; if [ -x /opt/redpitaya/sbin/rw ] ; then /opt/redpitaya/sbin/rw ; else /boot/sbin/rw ; fi

.PHONY: upload upload_bit upload_debug upload_reload upload_html check_rpip

check_rpip:
	@test -n "$(RPIP)" -a "$(RPIP)" != "rp-XXXXXX.local" || { echo "ERROR: set RPIP (e.g. make upload RPIP=rp-XXXXXX.local, or in ../_settings.env)"; exit 1; }

# FPGA images only (red_pitaya.bit for 0.9x/1.0 and fpga.bit.bin for 2.0)
upload_bit: check_rpip red_pitaya.bit $(FPGA_BIN)
	ssh $(RPIP) $(RPOPTS) "$(RP_RW) ; rm -f /opt/redpitaya/www/apps/$(APP)/red_pitaya.bit /opt/redpitaya/www/apps/$(APP)/$(FPGA_BIN)"
	scp $(RPSCP) red_pitaya.bit $(FPGA_BIN) root@$(RPIP):/opt/redpitaya/www/apps/$(APP)/

upload: check_rpip target/$(APP)
	ssh $(RPIP) $(RPOPTS) "$(RP_RW) ; rm -rf /opt/redpitaya/www/apps/$(APP) ; mkdir -p /opt/redpitaya/www/apps/$(APP)"
	cd target/$(APP) ; scp $(RPSCP) -r controllerhf.so $(APP_FILES) fpga.sh $(FPGA_BIN) red_pitaya.bit root@$(RPIP):/opt/redpitaya/www/apps/$(APP)/
	ssh $(RPIP) $(RPOPTS) "chmod 755 /opt/redpitaya/www/apps/$(APP)/fpga.sh"

upload_debug: check_rpip target_dbg/$(APP)_DEBUG
	ssh $(RPIP) $(RPOPTS) "$(RP_RW) ; rm -rf /opt/redpitaya/www/apps/$(APP)_DEBUG ; mkdir -p /opt/redpitaya/www/apps/$(APP)_DEBUG"
	cd target_dbg/$(APP)_DEBUG; scp $(RPSCP) -r controllerhf.so $(APP_FILES) fpga.sh $(FPGA_BIN) red_pitaya.bit root@$(RPIP):/opt/redpitaya/www/apps/$(APP)_DEBUG/
	ssh $(RPIP) $(RPOPTS) "chmod 755 /opt/redpitaya/www/apps/$(APP)_DEBUG/fpga.sh"

upload_reload: check_rpip target_rld/$(APP)_RELOAD
	ssh $(RPIP) $(RPOPTS) "$(RP_RW) ; rm -rf /opt/redpitaya/www/apps/$(APP)_RELOAD ; mkdir -p /opt/redpitaya/www/apps/$(APP)_RELOAD"
	cd target_rld/$(APP)_RELOAD; scp $(RPSCP) -r controllerhf.so $(APP_FILES) root@$(RPIP):/opt/redpitaya/www/apps/$(APP)_RELOAD/

# Web interface only: index.html (with the version of the target), css and js
upload_html: check_rpip target/$(APP)
	ssh $(RPIP) $(RPOPTS) "$(RP_RW) ; rm -rf /opt/redpitaya/www/apps/$(APP)/index.html /opt/redpitaya/www/apps/$(APP)/js /opt/redpitaya/www/apps/$(APP)/css"
	cd target/$(APP); scp $(RPSCP) -r index.html css js root@$(RPIP):/opt/redpitaya/www/apps/$(APP)/
