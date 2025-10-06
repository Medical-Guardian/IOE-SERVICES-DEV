import logging
import pymssql
import os
from typing import List, Dict, Optional, Any, Tuple

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

# Verify critical environment variables
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")
DB_SECRET_NAME = os.environ.get("DB_SECRET_NAME", "SqlConnectionStringIOE")

logger.info(f"🔍 [DB-SERVICE] Environment check:")
logger.info(f"   KEY_VAULT_URL: {'✅ Set' if KEY_VAULT_URL else '❌ Missing'}")
logger.info(f"   DB_SECRET_NAME: {'✅ Set' if DB_SECRET_NAME else '❌ Missing'}")

if not KEY_VAULT_URL:
    logger.error("❌ [DB-SERVICE] CRITICAL: KEY_VAULT_URL environment variable is not set!")
    logger.error("   This will cause database connections to fail.")


class DatabaseService:
    """
    Handles all database interactions, including single queries and atomic transactions.
    This is the sole authority for database connections in the application.
    """

    def __init__(self, config_manager: ConfigManager):
        """Initializes with the required ConfigManager dependency."""
        self.config_manager = config_manager
        self._db_connection_params: Optional[Dict[str, Any]] = None
        logger.info("🔧 [DB-SERVICE] Initialized. Depends on ConfigManager for connection details.")

    def _get_connection_params(self) -> Dict[str, Any]:
        """Gets and parses the connection string from ConfigManager, caching the result."""
        if self._db_connection_params:
            return self._db_connection_params
        try:
            connection_string = self.config_manager.get_db_connection_string()
            self._db_connection_params = self._parse_to_pymssql_params(connection_string)
            logger.info("✅ [DB-SERVICE] Database connection parameters parsed and cached.")
            return self._db_connection_params
        except Exception as e:
            logger.error(f"💥 [DB-SERVICE] Failed to get or parse connection string: {str(e)}")
            raise

    def _parse_to_pymssql_params(self, conn_string: str) -> Dict[str, Any]:
        """Parses a standard Azure SQL connection string into a pymssql-compatible dictionary."""
        params = {}
        for part in conn_string.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key_map = {
                "server": "server",
                "database": "database",
                "initial catalog": "database",
                "user id": "user",
                "password": "password",
            }
            std_key = key_map.get(key.strip().lower())
            if std_key:
                if std_key == "server" and "," in value:
                    server_val, port_val = value.replace("tcp:", "").split(",")
                    params["server"] = server_val
                    params["port"] = port_val
                else:
                    params[std_key] = value.replace("tcp:", "")
        return params

    def execute_query(
        self, query: str, params: tuple = None, fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Executes a single, auto-committed SQL query."""
        logger.info(f"💾 [DB-SERVICE] Executing single query (Fetch={fetch_results}).")
        try:
            conn_params = self._get_connection_params()
            with pymssql.connect(**conn_params, login_timeout=30) as conn:
                with conn.cursor(as_dict=True) as cursor:
                    cursor.execute(query, params)
                    if fetch_results:
                        return cursor.fetchall()
                    else:
                        conn.commit()
                        return cursor.rowcount
        except pymssql.Error as db_err:
            logger.error(f"💥 [DB-SERVICE] pymssql error during single query: {db_err}")
            raise
        except Exception as e:
            logger.error(f"💥 [DB-SERVICE] Unexpected error during single query: {e}")
            raise

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
            conn_params = self._get_connection_params()
            conn = pymssql.connect(**conn_params, login_timeout=30)
            with conn.cursor(as_dict=True) as cursor:
                for query, params in queries:
                    cursor.execute(query, params)
                    total_rows_affected += cursor.rowcount
            conn.commit()
            logger.info(
                f"✅ [DB-SERVICE] Transaction committed successfully. Rows affected: {total_rows_affected}."
            )
            return total_rows_affected
        except pymssql.Error as db_err:
            logger.error(f"💥 [DB-SERVICE] Transaction failed: {db_err}. Rolling back.")
            if conn:
                conn.rollback()
            raise  # Re-raise to be handled by the orchestrator
        except Exception as e:
            logger.error(f"💥 [DB-SERVICE] Unexpected transaction error: {e}. Rolling back.")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
