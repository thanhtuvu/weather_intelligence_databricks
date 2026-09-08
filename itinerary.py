import json
import uuid
import sys

if sys.version_info >= (3, 11):
    from typing import Required
else:
    from typing_extensions import Required

from typing_extensions import TypedDict
import lakebase
import psycopg

VALID_STATUSES = {"draft", "confirmed", "completed", "cancelled"}
VALID_TIMES_OF_DAY = {"morning", "afternoon", "night"}


class ItineraryItemInput(TypedDict, total=False):
    day_number: Required[int]
    sequence_order: Required[int]
    attraction_id: Required[str]
    time_in_day: str
    weather_context: dict
    notes: str


ITEM_INSERT_SQL = """
    INSERT INTO itinerary_items (
        id, itinerary_id, day_number, sequence_order,
        attraction_id, time_in_day, weather_context, notes
    )
    VALUES (
        %s, %s, %s, %s,
        %s, %s, %s::jsonb, %s
    )
"""


def _item_row(itinerary_id: str, item: ItineraryItemInput) -> tuple:
    time_in_day = item.get("time_in_day")
    if time_in_day is not None and time_in_day not in VALID_TIMES_OF_DAY:
        raise ValueError(
            f"time_in_day must be one of {VALID_TIMES_OF_DAY}, got {time_in_day!r}"
        )

    return (
        str(uuid.uuid4())
        ,itinerary_id
        ,item["day_number"]
        ,item["sequence_order"]
        ,item["attraction_id"]
        ,time_in_day
        ,json.dumps(item["weather_context"]) if item.get("weather_context") else None
        ,item.get("notes")
    )


def _insert_items(cur, itinerary_id: str, items: list[ItineraryItemInput]) -> None:
    try:
        cur.executemany(
            ITEM_INSERT_SQL
            ,[_item_row(itinerary_id, item) for item in items]
        )
    except psycopg.errors.ForeignKeyViolation as e:
        raise ValueError(
            "One or more attraction_id values were not found in "
            "destination_documents. Only use ids returned by "
            "search_destinations — never invent a place."
        ) from e


def create_itinerary(
    user_id: str
    ,destination: str
    ,start_date: str
    ,end_date: str
    ,items: list[ItineraryItemInput]
    ,preferences: dict
) -> dict:

    if not items:
        raise ValueError("create_itinerary requires at least one item")

    itinerary_id = str(uuid.uuid4())

    header_sql = """
        INSERT INTO itineraries (
            id, user_id, destination, start_date, end_date, preferences
        )
        VALUES (
            %s, %s, %s, %s, %s, %s::jsonb
        )
    """

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                header_sql
                ,(itinerary_id, user_id, destination, start_date, end_date, json.dumps(preferences))
            )
            _insert_items(cur, itinerary_id, items)
        conn.commit()

    return get_itinerary(itinerary_id)


def add_itinerary_items(itinerary_id: str, items: list[ItineraryItemInput]) -> int:
    if not items:
        return 0

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            _insert_items(cur, itinerary_id, items)
        conn.commit()

    return len(items)


def get_itinerary(itinerary_id: str) -> dict | None:
    header_sql = """
        SELECT id, user_id, destination, start_date, end_date,
               preferences, status, created_at, updated_at
        FROM itineraries
        WHERE id = %s
    """

    items_sql = """
        SELECT
            ii.id, ii.day_number, ii.sequence_order, ii.attraction_id,
            dd.name AS title, dd.category AS item_type, dd.address,
            ii.time_in_day, ii.weather_context, ii.notes, ii.created_at
        FROM itinerary_items ii
        JOIN destination_documents dd ON dd.id = ii.attraction_id
        WHERE ii.itinerary_id = %s
        ORDER BY ii.day_number, ii.sequence_order
    """

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(header_sql, (itinerary_id,))
            header = cur.fetchone()

            if header is None:
                return None

            cur.execute(items_sql, (itinerary_id,))
            header["items"] = cur.fetchall()

    return header


def list_itineraries(user_id: str) -> list[dict]:
    sql = """
        SELECT id, destination, start_date, end_date, status, created_at
        FROM itineraries
        WHERE user_id = %s
        ORDER BY created_at DESC
    """

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            return cur.fetchall()


def update_itinerary_status(itinerary_id: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")

    sql = """
        UPDATE itineraries
        SET status = %s, updated_at = NOW()
        WHERE id = %s
    """

    with lakebase.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, itinerary_id))
            updated = cur.rowcount
        conn.commit()

    return updated == 1