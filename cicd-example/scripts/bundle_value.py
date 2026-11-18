"""Print one value from `databricks bundle summary -o json` read on stdin, for the Makefile.

    databricks bundle summary -t dev -o json | python scripts/bundle_value.py resources.genie_spaces.sales_agent.id
    databricks bundle summary -t dev -o json | python scripts/bundle_value.py variables.catalog.value
"""
import json
import sys

value = json.load(sys.stdin)
for key in sys.argv[1].split("."):
    value = value.get(key) if isinstance(value, dict) else None
if value in (None, ""):
    sys.exit(f"{sys.argv[1]} not found: is the bundle deployed to this target?")
print(value)
