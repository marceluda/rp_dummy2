#
# @APP@: Red Pitaya App generated with rp_dummy2 (new_project.py).
#
#   source settings.sh ; LANG=C make     C controller + FPGA + packages (archive/)
#   make clean                           remove build products
#   make upload                          copy the App to the board of _settings.env (RPIP)
#   make eco1                            optional (Vivado 2015.2): red_pitaya.bit with the 0.9x scope for
#                                        Ecosystem 0.9x/1.0; then "make" puts it in the packages
#   make clean_eco1                      remove it (the packages take the Vivado 2020.1 red_pitaya.bit again)
#

APP=@APP@

-include _settings.env
-include _build_number

# Versioning system
BUILD_NUMBER ?= 0
REVISION ?= devbuild

INSTALL_DIR ?= .

# -DVERSION/-DREVISION are added to CFLAGS by the Makefile of the App (from its info.json, ../_build_number and
# ../_settings.env); here they are only passed down (adding them here too gave them twice on every gcc line)
export BUILD_NUMBER REVISION


.PHONY: all clean upload eco1 clean_eco1

all:
	mkdir -p archive
	$(MAKE) -C $(APP) all
	$(MAKE) -C $(APP) zip
	$(MAKE) -C $(APP) tar

clean:
	$(MAKE) -C $(APP) clean

upload:
	$(MAKE) -C $(APP) upload

eco1:
	$(MAKE) -C $(APP) eco1

clean_eco1:
	$(MAKE) -C $(APP) clean_eco1
