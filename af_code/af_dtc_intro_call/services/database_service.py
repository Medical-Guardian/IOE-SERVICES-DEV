import logging
import pyodbc
from typing import List, Dict, Optional, Any

from af_code.bland_ai_webhook.services.config_manager import ConfigManager

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
    logger.info(f"✅ [DB-SERVICE] TCP connection established to '{server}'")
    return conn


def _fetchall_as_dicts(cursor: pyodbc.Cursor) -> list[dict]:
    """Convert pyodbc cursor results to a list of dicts (replaces cursor(as_dict=True))."""
    if not cursor.description:
        return []
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


class DatabaseService:
    """Service for database operations using pyodbc with Managed Identity."""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
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
