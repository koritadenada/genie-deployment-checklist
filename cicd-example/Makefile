# Shortcuts for the Genie Agent CI/CD example. Run `make help` for the list.
#
# Sign in first (databricks auth login --profile <name>), then pass PROFILE=<name>, or export
# DATABRICKS_CONFIG_PROFILE. Bundle variables come from BUNDLE_VAR_<name> environment variables
# or VARS, for example: make deploy VARS="--var warehouse_id=1234567890abcdef".

# Personal settings (PROFILE, VARS) go in local.mk, which is not committed: cp local.mk.example local.mk
-include local.mk

TARGET  ?= dev
PROFILE ?=
VARS    ?=
AGENT   ?= sales_agent
VENV    ?= .venv

PY  := $(VENV)/bin/python
CLI := databricks
ifneq ($(PROFILE),)
export DATABRICKS_CONFIG_PROFILE := $(PROFILE)
endif

.DEFAULT_GOAL := help
.PHONY: help setup validate deploy seed gate pull clean check-auth

# Stop with a clear message instead of falling back to the DEFAULT CLI profile.
check-auth:
	@if [ -z "$(PROFILE)$(DATABRICKS_CONFIG_PROFILE)$(DATABRICKS_HOST)" ]; then \
	  echo "No Databricks profile set. Add PROFILE=<name> to local.mk (cp local.mk.example local.mk) or run make $(MAKECMDGOALS) PROFILE=<name>."; \
	  echo "Sign in first with: databricks auth login --profile <name>"; exit 1; fi

help: ## Show the available commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'
	@echo ""
	@echo "  Options: TARGET=dev|staging|prod (default dev), PROFILE=<cli profile>, VARS=\"--var name=value\""

setup: $(VENV)/.installed ## Create .venv and install the Python requirements
	@echo "Python environment ready: $(VENV) ($$($(PY) -c 'import databricks.sdk, yaml; print("databricks-sdk " + databricks.sdk.version.__version__ + ", PyYAML " + yaml.__version__)'))"

$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt
	@touch $@

validate: check-auth ## Validate the bundle for TARGET
	$(CLI) bundle validate -t $(TARGET) $(VARS)

deploy: check-auth ## Deploy the agent, its benchmarks and the gate job to TARGET
	$(CLI) bundle deploy -t $(TARGET) $(VARS)

seed: check-auth setup ## Example only: create the sales tables in TARGET's catalog
	@CATALOG=$$($(CLI) bundle summary -t $(TARGET) $(VARS) -o json | $(PY) scripts/bundle_value.py variables.catalog.value) && \
	SCHEMA=$$($(CLI) bundle summary -t $(TARGET) $(VARS) -o json | $(PY) scripts/bundle_value.py variables.schema.value) && \
	WAREHOUSE=$$($(CLI) bundle summary -t $(TARGET) $(VARS) -o json | $(PY) scripts/bundle_value.py variables.warehouse_id.value) && \
	$(PY) scripts/seed_demo_data.py --catalog $$CATALOG --schema $$SCHEMA --warehouse-id $$WAREHOUSE

gate: check-auth ## Run the benchmarks on TARGET; fails when accuracy is not above the threshold
	scripts/run_gate.sh $(TARGET) $(VARS)

pull: check-auth setup ## Pull edits made in the Genie UI on TARGET's agent back into its resource file (resources/<agent>.genie.yml)
	@SUMMARY=$$($(CLI) bundle summary -t $(TARGET) $(VARS) -o json) && \
	SPACE_ID=$${SPACE_ID:-$$(echo "$$SUMMARY" | $(PY) scripts/bundle_value.py resources.genie_spaces.$(AGENT).id)} && \
	CATALOG=$$(echo "$$SUMMARY" | $(PY) scripts/bundle_value.py variables.catalog.value) && \
	SCHEMA=$$(echo "$$SUMMARY" | $(PY) scripts/bundle_value.py variables.schema.value) && \
	echo "Pulling agent $$SPACE_ID ($(TARGET): $$CATALOG.$$SCHEMA)" && \
	$(PY) scripts/pull_agent.py --space-id $$SPACE_ID --catalog $$CATALOG --schema $$SCHEMA \
	  --file resources/$(AGENT).genie.yml --agent $(AGENT) $(if $(OUT),--out $(OUT))

clean: ## Remove .venv
	rm -rf $(VENV)
