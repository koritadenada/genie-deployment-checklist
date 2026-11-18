# The commands live in cicd-example/Makefile; this forwards them, so `make help`, `make pull` and the others
# also work from the repository root. Options pass through: make pull TARGET=dev PROFILE=<profile>
.DEFAULT_GOAL := help
.PHONY: help

help:
	@$(MAKE) --no-print-directory -C cicd-example help

%:
	@$(MAKE) --no-print-directory -C cicd-example $@
