#
# @APP@: Red Pitaya App generated with rp_dummy2 (new_project.py).
#
#   source settings.sh ; LANG=C make     C controller + FPGA + packages (archive/)
#   make clean                           remove build products
#   make upload                          copy the App to the board of _settings.env (RPIP)
#

APP=@APP@

-include _settings.env
-include _build_number

# Versioning system
BUILD_NUMBER ?= 0
REVISION ?= devbuild
VER:=$(shell cat $(APP)/info/info.json | grep version | sed -e 's/.*:\ *\"//' | sed -e 's/-.*//')

INSTALL_DIR ?= .

CFLAGS += -DVERSION=$(VER)-$(BUILD_NUMBER) -DREVISION=$(REVISION)
export CFLAGS


.PHONY: all clean upload

all:
	mkdir -p archive
	$(MAKE) -C $(APP) all
	$(MAKE) -C $(APP) zip
	$(MAKE) -C $(APP) tar

clean:
	$(MAKE) -C $(APP) clean

upload:
	$(MAKE) -C $(APP) upload
