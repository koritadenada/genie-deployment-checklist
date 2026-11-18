"""Create the example's sales tables in one environment's catalog (idempotent).

Only for this example: in a real project your data pipelines own these tables. The agent needs its
tables to exist before the first deployment, so CI runs this before `databricks bundle deploy`.

    python scripts/seed_demo_data.py --catalog dev --schema genie_sales --warehouse-id <id>

Builds customers and orders from samples.tpch, shifted by 28 years so orders run from 2020 to 2026,
with table and column comments and primary and foreign keys (Genie uses them).
"""
import argparse

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState


def sql(w, wh, stmt):
    r = w.statement_execution.execute_statement(statement=stmt, warehouse_id=wh, wait_timeout="50s")
    while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"{r.status.state}: {r.status.error.message if r.status.error else ''}\n{stmt[:300]}")
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", default="genie_sales")
    p.add_argument("--warehouse-id", required=True)
    p.add_argument("--force", action="store_true", help="rebuild the tables even if they exist")
    a = p.parse_args()
    w = WorkspaceClient()
    s = f"`{a.catalog}`.`{a.schema}`"

    sql(w, a.warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {s} COMMENT 'Sales tables for the Genie Agent CI/CD example'")
    exists = sql(w, a.warehouse_id, f"SHOW TABLES IN {s} LIKE 'orders'").result
    if exists and exists.data_array and not a.force:
        print(f"{s}.orders already exists: nothing to do (use --force to rebuild)")
        return

    statements = [
        f"DROP TABLE IF EXISTS {s}.orders",
        f"DROP TABLE IF EXISTS {s}.customers",
        f"""CREATE TABLE {s}.customers (
  customer_id BIGINT NOT NULL COMMENT 'Unique customer identifier',
  customer_name STRING COMMENT 'Customer company name',
  market_segment STRING COMMENT 'Industry segment: AUTOMOBILE, BUILDING, FURNITURE, HOUSEHOLD or MACHINERY',
  country STRING COMMENT 'Country of the customer',
  region STRING COMMENT 'Sales region: AFRICA, AMERICA, ASIA, EUROPE or MIDDLE EAST',
  CONSTRAINT customers_pk PRIMARY KEY (customer_id)
) COMMENT 'One row per customer, with segment, country and region'""",
        f"""INSERT INTO {s}.customers
SELECT c.c_custkey, c.c_name, c.c_mktsegment, n.n_name, r.r_name
FROM samples.tpch.customer c JOIN samples.tpch.nation n ON c.c_nationkey = n.n_nationkey
JOIN samples.tpch.region r ON n.n_regionkey = r.r_regionkey""",
        f"""CREATE TABLE {s}.orders (
  order_id BIGINT NOT NULL COMMENT 'Unique order identifier',
  customer_id BIGINT NOT NULL COMMENT 'Customer who placed the order (customers.customer_id)',
  order_date DATE COMMENT 'Date the order was placed',
  order_amount DECIMAL(18,2) COMMENT 'Order value in USD; revenue is the sum of order_amount',
  order_status STRING COMMENT 'Open, Fulfilled or Partial',
  order_priority STRING COMMENT 'Priority from 1-URGENT to 5-LOW',
  CONSTRAINT orders_pk PRIMARY KEY (order_id),
  CONSTRAINT orders_customers_fk FOREIGN KEY (customer_id) REFERENCES {s}.customers
) COMMENT 'One row per sales order'""",
        f"""INSERT INTO {s}.orders
SELECT o_orderkey, o_custkey, add_months(o_orderdate, 12 * 28), o_totalprice,
       CASE o_orderstatus WHEN 'O' THEN 'Open' WHEN 'F' THEN 'Fulfilled' ELSE 'Partial' END,
       o_orderpriority
FROM samples.tpch.orders""",
    ]
    for st in statements:
        sql(w, a.warehouse_id, st)
    print(f"Seeded {s}.customers and {s}.orders")


if __name__ == "__main__":
    main()
