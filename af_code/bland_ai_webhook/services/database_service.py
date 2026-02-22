import logging
import pyodbc
import os
from typing import List, Dict, Optional, Any, Tuple

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


def _get_pyodbc_connection() -> pyodbc.Connection:
    """Create pyodbc connection using Managed Identity via ActiveDirectoryMsi."""
    conn_str = os.environ.get("SqlConnectionString", "")

    params = {}
    for part in conn_str.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()

    server = params.get("Server", "").replace("tcp:", "").split(",")[0]
    database = params.get("Database", "") or params.get("Initial Catalog", "")

    connection_string = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server={server};"
        f"Database={database};"
        "Authentication=ActiveDirectoryMsi;"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
        "Login Timeout=30;"
    )
    return pyodbc.connect(connection_string)


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
            conn = _get_pyodbc_connection()
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(query, params)
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
            conn = _get_pyodbc_connection()
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
