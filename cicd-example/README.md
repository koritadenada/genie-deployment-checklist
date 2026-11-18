# Genie Agent CI/CD example

Deploy a Genie Agent from Git through **dev, staging and prod**, with its **benchmarks deployed alongside it** and a
**benchmark gate** in the pipeline. The agent reaches prod only after a merge to `main`, and only if benchmark accuracy is
**above 80%**. If it is not, the pipeline prints each failing question with its reason, emails the team, and stops.

```mermaid
flowchart LR
  PR[Pull request] --> D1[Deploy to dev] --> G1{Benchmarks<br/>above 80%?}
  G1 -- no --> X1[Print reasons<br/>email the team<br/>check fails]
  G1 -- yes --> OK1[Check passes, PR can merge]
  M[Merge to main] --> D2[Deploy to staging] --> G2{Benchmarks<br/>above 80%?}
  G2 -- no --> X2[Print reasons<br/>email the team<br/>pipeline stops]
  G2 -- yes --> P[Deploy to prod] --> W[Weekly benchmark run in prod]
```

## What is in here

| Path | What it does |
| --- | --- |
| `databricks.yml` | Bundle with the `dev`, `staging` and `prod` targets. Each target points at its own catalog (`dev`, `staging`, `prod`). |
| `resources/sales_agent.genie.yml` | The Genie Agent as code, written by hand: tables, entity matching, sample questions, instructions, example SQL and **20 benchmark questions** (10 questions, 2 phrasings each). |
| `resources/benchmark_gate.job.yml` | Serverless job that runs the benchmarks and fails below the threshold. Email on failure goes to `alert_email`. In prod it also runs weekly. |
| `src/benchmark_gate.py` | Starts a benchmark evaluation run, waits for it, prints accuracy and the reason for each failing question, and fails the run when accuracy is not above `min_accuracy`. |
| `scripts/run_gate.sh` | Used by CI: runs the gate job, prints its report in the CI log and the GitHub job summary, and exits non-zero on failure. |
| `scripts/pull_agent.py` | Pulls changes you made to your dev agent in the UI back into `sales_agent.genie.yml`. |
| `scripts/seed_demo_data.py` | Example only: creates the `customers` and `orders` tables from `samples.tpch` in each environment. |
| `.github/workflows/genie-pr.yml` | Pull request: deploy to dev, run the benchmarks. |
| `.github/workflows/genie-release.yml` | Merge to `main`: deploy to staging, run the gate, then promote to prod. |

## One definition, three environments

Table names in the agent are written as `${var.catalog}.${var.schema}.orders`. Each target sets its own catalog, so the
same file deploys as `dev.genie_sales.orders` in dev, `staging.genie_sales.orders` in staging and `prod.genie_sales.orders`
in prod. You keep one agent definition in Git and test it against dev and staging data before it ever points at prod data.

The agent is defined inline in YAML (`serialized_space`), not in a `.geniespace.json` file, because bundle variables are
resolved in YAML but not inside an included JSON file.

## Write the agent, or build it in the UI and pull it

The smallest agent you can deploy is just its tables:

```yaml
resources:
  genie_spaces:
    sales_agent:
      title: Sales Analytics
      warehouse_id: ${var.warehouse_id}
      serialized_space:
        version: 2
        data_sources:
          tables:
            - identifier: ${var.catalog}.${var.schema}.customers
            - identifier: ${var.catalog}.${var.schema}.orders
```

Everything else is added as the agent matures. Sample questions, instructions, example SQL, joins, SQL snippets and
benchmarks each need an `id`: 32 lowercase hex characters, unique, with every list sorted by `id`. Any value works, so
number them by hand with one letter per kind of item, as `sales_agent.genie.yml` does (`a...01` for sample questions,
`b...01` for benchmarks, `c...01` for instructions, `d...01` for example SQL). Tables and column settings need no `id`.
Leave the joins out when the tables have primary and foreign keys: Genie uses them.

Two ways teams work in practice:

- **Write it in Git**, as above. Good for small agents and reviewable pull requests.
- **Build in the dev UI, then pull** with `scripts/pull_agent.py` or `databricks bundle generate genie-space`. The UI
  assigns random IDs, so a pulled file has long random IDs instead of the numbered ones above. Both deploy the same way.

## How the gate decides

The benchmarks are part of the agent definition, so every deployment ships the current benchmark set. After each
deployment the gate:

1. starts a benchmark evaluation run on the deployed agent (Genie benchmark API, Beta);
2. waits until the run finishes;
3. computes accuracy as correct answers divided by benchmark questions; answers marked *needs review* count as not correct;
4. passes only when accuracy is **above** `min_accuracy` (default `80`, set in `databricks.yml`).

On failure the report looks like this in the CI log, in the GitHub job summary and in the failure email. This is a real
run in which four benchmark answers were deliberately changed: 16 of 20 correct is 80%, which is not above 80%, so the
gate fails.

```
GENIE BENCHMARK GATE  FAILED
Agent: [dev] Sales Analytics   Target: dev
Accuracy: 80.0% (16/20 correct)   Required: above 80%
 1. [BAD] How many orders were placed in 2024?
    Reason: a value differs from the expected result; a filter is missing or wrong
    Genie answered: SELECT COUNT(*) AS `order_count` FROM `dev`.`genie_sales`.`orders` WHERE YEAR(`order_date`) = 2024
 2. [BAD] What was total revenue in 2025?
    Reason: a value differs from the expected result; a filter is missing or wrong
 ...
Benchmark gate failed on dev: the team was emailed and the pipeline stops here.
```

Because the release workflow's `prod` job `needs: staging`, a failed gate means prod is never deployed.

## Set up

1. **Environments.** Create the catalogs `dev`, `staging` and `prod` (or change the names in `databricks.yml`) and a
   serverless SQL warehouse in each workspace. One workspace or three both work.
2. **Service principals.** Create one service principal per environment, with `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`
   and `SELECT` on its catalog and `CAN USE` on the warehouse.
3. **Sign-in without secrets.** For each service principal, create a
   [GitHub Actions federation policy](https://docs.databricks.com/aws/en/dev-tools/auth/provider-github). Use the entity
   type *Environment* and the subjects `repo:<org>/<repo>:environment:dev`, `...:staging` and `...:prod`.
4. **GitHub environments.** Create the environments `dev`, `staging` and `prod`, each with these variables:
   `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` (the service principal's application ID) and `WAREHOUSE_ID`. Add required
   reviewers on `prod` if you want a manual approval before promotion.
5. **Alert email.** Add the repository secret `GENIE_ALERT_EMAIL` with the address or distribution list that should get
   the failure email. It is kept out of the code.
6. **Branch protection.** On `main`, require the status check **Genie benchmarks (dev)**, so pull requests cannot merge
   while the gate fails.
7. Copy the contents of this folder to the root of your repository and push.

## Develop an agent change

The `Makefile` wraps the commands; run `make help` to list them. Requirements: the
[Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/install) (1.3.0 or later), Python 3.10 or later and
`make`. `make setup` installs the Python packages from `requirements.txt` (`databricks-sdk`, `PyYAML`) into `.venv`.

```bash
# once: sign in, save your settings, install the Python packages
databricks auth login --profile my-dev
cp local.mk.example local.mk        # set PROFILE=my-dev and VARS=--var warehouse_id=<id>
make setup

# deploy your own dev copy (resources get a "[dev <you>]" prefix)
make deploy

# tune the agent in the Genie UI, then pull the changes back into Git
make pull
git diff resources/sales_agent.genie.yml

# run the benchmark gate yourself before opening a pull request
make gate
```

`make pull` finds your dev agent from the bundle, downloads its definition, maps the dev catalog and schema back to
`${var.catalog}.${var.schema}`, and rewrites only `serialized_space`; title, description, warehouse and permissions stay
as they are in Git. If nothing changed in the UI, the file is left untouched. To preview without overwriting, add
`OUT=/tmp/agent.yml`. To pull a different agent, add `SPACE_ID=<id>`.

`local.mk` is not committed. You can also pass the settings per command (`make pull PROFILE=my-dev`) or export
`DATABRICKS_CONFIG_PROFILE` and `BUNDLE_VAR_warehouse_id`. Without a profile, make stops with a message instead of
falling back to your `DEFAULT` CLI profile. The commands also work from the repository root.

Add a benchmark question for every new question pattern the agent should answer, with the SQL you expect.

## Use it with your own agent

- Export an existing agent: `databricks bundle generate genie-space --existing-id <id> --key my_agent`, then move the
  generated `serialized_space` into a resource YAML file and replace the catalog and schema with `${var.catalog}` and
  `${var.schema}` (or run `scripts/pull_agent.py`).
- Point `space_id` in `resources/benchmark_gate.job.yml` at your agent's resource key.
- Remove the seed step from the workflows: in your project, data pipelines own the tables. The tables must exist before
  the first deployment of an agent.

## Notes

- `genie_spaces` needs the direct deployment engine and Databricks CLI 1.3.0 or later
  ([docs](https://docs.databricks.com/aws/en/dev-tools/bundles/resources#genie_space)). This example was tested end to end
  with CLI 1.17.0: dev, staging and prod deployments, a passing gate (20/20) and a failing gate (16/20).
- The benchmark evaluation API is in Beta and may change.
- Users asking the agent are free through January 31, 2027; service principals, including the gate's benchmark runs,
  are billed. See [Genie cost](https://docs.databricks.com/aws/en/genie/monitor-cost).
