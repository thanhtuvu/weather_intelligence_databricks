import os
import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import sql as sdk_sql

_w = WorkspaceClient()

_TERMINAL_STATES = {
    sdk_sql.StatementState.SUCCEEDED
    ,sdk_sql.StatementState.FAILED
    ,sdk_sql.StatementState.CANCELED
    ,sdk_sql.StatementState.CLOSED
}

def add_tracked_location(location: str) -> None:
    """
    Add `location` to weather_intelligence.bronze.tracked_locations
    so the next scheduled Bronze job refreshes it too.
    """
    warehouse_id = os.environ["DATABRICKS_SQL_WAREHOUSE_ID"]
    target_table = os.environ["UC_TABLE_NAME"]

    statement = f"""
        MERGE INTO {target_table} AS target
        USING (SELECT :location_placeholder AS location) AS source
        ON target.location = source.location
        WHEN NOT MATCHED THEN INSERT (location, added_at, active)
        VALUES (source.location, current_timestamp(), true)
    """

    response = _w.statement_execution.execute_statement(
        warehouse_id=warehouse_id  # which compute runs this
        ,statement=statement
        ,parameters=[
            sdk_sql.StatementParameterListItem(name="location_placeholder", value=location, type="STRING")
        ] # binds :location_placeholder safely
        ,wait_timeout="50s"  
    )

    # A cold serverless warehouse can still take longer than 50s to wake up.
    # If so, execute_statement returns early with a non-terminal state instead
    # of raising — poll until it actually finishes, so a slow warehouse can't
    # look identical to a successful write.
    deadline = time.monotonic() + 120
    while response.status.state not in _TERMINAL_STATES and time.monotonic() < deadline:
        time.sleep(3)
        response = _w.statement_execution.get_statement(response.statement_id)

    if response.status.state != sdk_sql.StatementState.SUCCEEDED:
        raise RuntimeError(
            f"tracked_locations MERGE for '{location}' did not succeed: "
            f"{response.status.state} — {response.status.error}"
        )