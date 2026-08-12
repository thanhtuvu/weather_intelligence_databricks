import base64
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient


_w = WorkspaceClient()


_SCOPE = os.environ.get("LAKEBASE_SECRET_SCOPE", "database")
_KEY = os.environ.get("LAKEBASE_SECRET_KEY", "lakebase-url")


def _lakebase_url() -> str:
    secret = _w.secrets.get_secret(
        scope=_SCOPE,
        key=_KEY,
    )
    return base64.b64decode(secret.value).decode("utf-8")


@contextmanager
def get_connection():
    """
    1. Gets the Lakebase connection URL from Databricks Secrets.
    2. Creates a new psycopg connection.
    3. Returns that connection.
    4. Closes it when the context exits.
    """
    conn = psycopg.connect(
        _lakebase_url(),
        row_factory=dict_row,
    )

    try:
        yield conn
    finally:
        conn.close()


def run_query(
    sql: str,
    params: tuple | dict | None = None,
) -> list[dict]:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def run_write(
    sql: str,
    params: tuple | dict | None = None,
) -> int:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount