import logging
import struct
import pyodbc
from typing import List, Dict, Optional, Any, Tuple

from azure.identity import DefaultAzureCredential

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

# pyodbc attribute for passing a pre-obtained AAD access token to the ODBC driver
_SQL_COPT_SS_ACCESS_TOKEN = 1256


def _get_pyodbc_connection(conn_str: str) -> pyodbc.Connection:
    """Create pyodbc connection using AAD access token via DefaultAzureCredential.

    Uses the Azure Identity SDK to obtain the token (same path as Key Vault access),
    then injects it via SQL_COPT_SS_ACCESS_TOKEN. This avoids the ODBC driver's own
    ActiveDirectoryMsi implementation, which does not work on Azure Functions Consumption plan.
    """
    params = {}
    for part in conn_str.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()

    server = params.get("Server", "").replace("tcp:", "").split(",")[0]
    database = params.get("Database", "") or params.get("Initial Catalog", "")

    # Acquire AAD token using the Azure Identity SDK (respects Function MSI endpoint)
    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")
    token_bytes = token.token.encode("UTF-16-LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    connection_string = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(connection_string, attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: token_struct})


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
