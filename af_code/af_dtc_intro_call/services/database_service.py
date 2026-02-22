import logging
import struct
import pyodbc
from typing import List, Dict, Optional, Any

from azure.identity import DefaultAzureCredential

from af_code.bland_ai_webhook.services.config_manager import ConfigManager

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
