import logging
import pyodbc
import os
from typing import List, Dict, Optional, Any

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
    """Service for database operations using pyodbc with Managed Identity."""

    def __init__(self):
        logger.info(
            "🔧 [DatabaseService] Initializing database service with pyodbc (Managed Identity)"
        )

    def execute_query(
        self, query: str, params: tuple = None, fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute a database query using pyodbc."""
        logger.info(f"💾 [DatabaseService] Executing query (fetch_results={fetch_results})")

        conn = None
        try:
            conn = _get_pyodbc_connection()
            conn.autocommit = True
            with conn.cursor() as cursor:
                cursor.execute(query, params if params else None)

                if fetch_results:
                    return _fetchall_as_dicts(cursor)
                return cursor.rowcount

        except pyodbc.Error as e:
            logger.error(f"💥 [DatabaseService] Database error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"💥 [DatabaseService] Unexpected error executing query: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
