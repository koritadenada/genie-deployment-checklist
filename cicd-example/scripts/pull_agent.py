"""Pull edits made in the Genie UI (dev) back into resources/sales_agent.genie.yml.

Tune the agent in your dev copy, then run:
    python scripts/pull_agent.py --space-id <dev space id> --catalog dev --schema genie_sales
It downloads the agent definition, turns the dev catalog and schema back into ${var.catalog} and
${var.schema}, and rewrites serialized_space in the resource file. Review the diff and open a pull request.
Needs CAN EDIT on the agent, and PyYAML.
"""
import argparse
import json
import pathlib
import re

import yaml
from databricks.sdk import WorkspaceClient

RES = pathlib.Path(__file__).resolve().parent.parent / "resources" / "sales_agent.genie.yml"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--space-id", required=True)
    p.add_argument("--catalog", required=True, help="catalog used by the agent you edited, for example dev")
    p.add_argument("--schema", default="genie_sales")
    a = p.parse_args()

    w = WorkspaceClient()
    space = w.api_client.do("GET", f"/api/2.0/genie/spaces/{a.space_id}", query={"include_serialized_space": "true"})
    raw = space["serialized_space"]
    for pat in (rf"`?{re.escape(a.catalog)}`?\.`?{re.escape(a.schema)}`?\.",):
        raw = re.sub(pat, "${var.catalog}.${var.schema}.", raw)
    ss = json.loads(raw)

    text = RES.read_text()
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    doc = yaml.safe_load(text)
    doc["resources"]["genie_spaces"]["sales_agent"]["serialized_space"] = ss
    RES.write_text(header + yaml.safe_dump(doc, sort_keys=False, width=140, allow_unicode=True))
    print(f"Updated {RES.relative_to(RES.parent.parent)}: review with git diff, then open a pull request")


if __name__ == "__main__":
    main()
