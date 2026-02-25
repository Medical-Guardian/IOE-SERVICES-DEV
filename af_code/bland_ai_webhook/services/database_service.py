import logging
import struct
import pyodbc
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _get_pyodbc_connection(conn_str: str) -> pyodbc.Connection:
    """Create pyodbc connection using Managed Identity (ActiveDirectoryMsi).

    Matches the working connection approach in Test_AI-dbdev/function_app.py.
    """
    params = {}
    raw_server = ""
    for part in conn_str.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()
        elif part.startswith("tcp:") and not raw_server:
            # Capture bare tcp:host,port segment (no "Server=" key prefix)
            raw_server = part

    # Prefer explicit "Server=" key; fall back to the bare tcp: segment
    server = (params.get("Server", "") or raw_server).replace("tcp:", "").split(",")[0]
    # Support both "Database=" (ODBC) and "Initial Catalog=" (ADO.NET) key names
    database = params.get("Database", "") or params.get("Initial Catalog", "")

    logger.info(f"🔌 [DB-SERVICE] Connecting to server='{server}' database='{database}'")

    connection_string = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        "Authentication=ActiveDirectoryMsi;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
        "Login Timeout=30"
    )
    conn = pyodbc.connect(connection_string)
    conn.add_output_converter(-155, _handle_datetimeoffset)  # DATETIMEOFFSET → datetime
    logger.info(f"✅ [DB-SERVICE] TCP connection established to '{server}'")
    return conn


def _handle_datetimeoffset(dto_value: bytes) -> datetime:
    """Deserialize a SQL Server DATETIMEOFFSET value received as raw bytes from pyodbc.

    pyodbc does not natively support ODBC type -155 (DATETIMEOFFSET). This converter
    is registered via conn.add_output_converter(-155, ...) so every DATETIMEOFFSET
    column on the connection is automatically deserialized into a timezone-aware datetime.

    Binary layout (little-endian): year(2) month(2) day(2) hour(2) min(2) sec(2)
                                   nanoseconds(4) tz_hour(2) tz_min(2)
    """
    tup = struct.unpack("<6hI2h", dto_value)
    return datetime(
        tup[0], tup[1], tup[2],  # year, month, day
        tup[3], tup[4], tup[5],  # hour, minute, second
        tup[6] // 1000,           # nanoseconds → microseconds
        timezone(timedelta(hours=tup[7], minutes=tup[8])),
    )


def _fetchall_as_dicts(cursor: pyodbc.Cursor) -> list[dict]:
    """Convert pyodbc cursor results to a list of dicts (replaces cursor(as_dict=True))."""
    if not cursor.description:
        return []
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


class DatabaseService:
    """
    Handles all database interactions, including single queries and atomic transactions.
    This is the sole authority for database connections in the application.
    Uses pyodbc with Azure Managed Identity (ActiveDirectoryMsi) for authentication.
    """

    def __init__(self, config_manager: ConfigManager):
        """Initializes with the required ConfigManager dependency."""
        self.config_manager = config_manager
        logger.info(
            "🔧 [DB-SERVICE] Initialized. Uses pyodbc with Managed Identity for DB connections."
        )

    def execute_query(
        self, query: str, params: tuple = None, fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Executes a single, auto-committed SQL query."""
        logger.info(f"💾 [DB-SERVICE] Executing single query (Fetch={fetch_results}).")
        conn = None
        try:
            conn_str = self.config_manager.get_db_connection_string()
            conn = _get_pyodbc_connection(conn_str)
            conn.autocommit = True
            with conn.cursor() as cursor:
                if params is not None:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                if fetch_results:
                    return _fetchall_as_dicts(cursor)
                else:
                    return cursor.rowcount
        except pyodbc.Error as db_err:
            logger.error(f"💥 [DB-SERVICE] pyodbc error during single query: {db_err}")
            raise
        except Exception as e:
            logger.error(f"💥 [DB-SERVICE] Unexpected error during single query: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def execute_transaction(self, queries: List[Tuple[str, tuple]]) -> int:
        """
        Executes a list of queries within a single atomic transaction.
        Rolls back all changes if any single query fails.

        Args:
            queries: A list where each item is a tuple of (query_string, parameters).

        Returns:
            The total number of rows affected across all queries.
        """
        logger.info(f"🔄 [DB-SERVICE] Starting transaction with {len(queries)} queries.")
        total_rows_affected = 0
        conn = None
        try:
            conn_str = self.config_manager.get_db_connection_string()
            conn = _get_pyodbc_connection(conn_str)
            conn.autocommit = False
            with conn.cursor() as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
                    total_rows_affected += cursor.rowcount
            conn.commit()
            logger.info(
                f"✅ [DB-SERVICE] Transaction committed successfully. Rows affected: {total_rows_affected}."
            )
            return total_rows_affected
        except pyodbc.Error as db_err:
            logger.error(f"💥 [DB-SERVICE] Transaction failed: {db_err}. Rolling back.")
            if conn:
                conn.rollback()
            raise
        except Exception as e:
            logger.error(f"💥 [DB-SERVICE] Unexpected transaction error: {e}. Rolling back.")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
