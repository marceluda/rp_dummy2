#
# Red Pitaya specific application Makefile.
#

APP=dummy

-include _settings.env
-include _build_number

# If you want to set specific variables use the file: settings.env
#
# i.e.

# Versioning system
REVISION ?= devbuild

INSTALL_DIR ?= .

folder=$(CURDIR:%/=%)


# -DVERSION/-DREVISION are added to CFLAGS by the Makefile of the App (from its info.json, ../_build_number and
# ../_settings.env); here they are only passed down (adding them here too gave them twice on every gcc line)
export BUILD_NUMBER REVISION


.PHONY: clean upload

all:
	$(MAKE) -C $(APP) all
	$(MAKE) -C $(APP) zip
	$(MAKE) -C $(APP) tar

clean:
	$(MAKE) -C $(APP) clean

upload:
	$(MAKE) -C $(APP) upload
