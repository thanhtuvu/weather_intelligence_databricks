import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient


_w = WorkspaceClient()

_PGHOST = os.environ["PGHOST"]
_PGPORT = os.environ.get("PGPORT", "5432")
_PGDATABASE = os.environ.get("PGDATABASE", "databricks_postgres")
_PGSSLMODE = os.environ.get("PGSSLMODE", "require")
_PGUSER = os.environ["PGUSER"]

_ENDPOINT = os.environ["LAKEBASE_ENDPOINT"]


def _fresh_token() -> str:
    cred = _w.postgres.generate_database_credential(
        endpoint=_ENDPOINT
    )
    return cred.token


@contextmanager
def get_connection():
    conn = psycopg.connect(
        host=_PGHOST
        ,port=_PGPORT
        ,dbname=_PGDATABASE
        ,user=_PGUSER
        ,password=_fresh_token()
        ,sslmode=_PGSSLMODE
        ,row_factory=dict_row
    )

    try:
        yield conn
    finally:
        conn.close()


def run_query(
    sql: str
    ,params: tuple | dict | None = None
) -> list[dict]:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def run_write(
    sql: str
    ,params: tuple | dict | None = None
) -> int:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount