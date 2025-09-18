import logging
import pymssql
from typing import List, Dict, Optional, Any
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# Corrected absolute import paths
from ..utils.config import KEY_VAULT_URL, DB_SECRET_NAME

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for database operations using pymssql"""

    def __init__(self):
        self._db_connection_params: Optional[Dict[str, Any]] = None
        logger.info("🔧 [DatabaseService] Initializing database service with pymssql")

    def _get_connection_params_from_keyvault(self) -> Dict[str, Any]:
        """Securely fetch and parse the database connection string from Azure Key Vault."""
        logger.info("🔐 [DatabaseService] Starting database connection parameter retrieval")

        if self._db_connection_params:
            logger.info("⚡ [DatabaseService] Using cached database connection parameters")
            return self._db_connection_params

        try:
            if not KEY_VAULT_URL:
                logger.error("❌ [DatabaseService] Environment variable 'KEY_VAULT_URL' is not set")
                raise ValueError("Environment variable 'KEY_VAULT_URL' is not set")

            logger.info(f"🏠 [DatabaseService] Key Vault URL: {KEY_VAULT_URL[:30]}...")
            logger.info(f"🔑 [DatabaseService] Secret name: {DB_SECRET_NAME}")

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)

            logger.info(f"📥 [DatabaseService] Retrieving secret: {DB_SECRET_NAME}")
            secret = client.get_secret(DB_SECRET_NAME)

            if not secret or not secret.value:
                logger.error(f"❌ [DatabaseService] Secret '{DB_SECRET_NAME}' was retrieved but is empty")
                raise ValueError(f"Secret '{DB_SECRET_NAME}' is empty")

            self._db_connection_params = self._parse_to_pymssql_params(secret.value)
            logger.info("✅ [DatabaseService] Database connection parameters retrieved and cached")
            return self._db_connection_params

        except Exception as e:
            logger.error(f"💥 [DatabaseService] Failed to fetch/parse connection string: {str(e)}")
            raise

    def _parse_to_pymssql_params(self, conn_string: str) -> Dict[str, Any]:
        """Parse Azure-style connection string into a dictionary for pymssql."""
        logger.info("🔍 [DatabaseService] Parsing raw connection string for pymssql")
        conn_params = {}
        for param in conn_string.split(";"):
            if "=" not in param:
                continue
            key, value = param.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "server":
                server_value = value
                if server_value.lower().startswith("tcp:"):
                    server_value = server_value[4:]
                if "," in server_value:
                    host, port = server_value.split(",", 1)
                    conn_params["server"] = host
                    conn_params["port"] = int(port)
                else:
                    conn_params["server"] = server_value
            elif key in ("initial catalog", "database"):
                conn_params["database"] = value
            elif key == "user id":
                conn_params["user"] = value
            elif key == "password":
                conn_params["password"] = value

        logger.info("✅ [DatabaseService] Connection string parsed successfully")
        return conn_params

    def execute_query(self, query: str, params: tuple = None, fetch_results: bool = True) -> Optional[
        List[Dict[str, Any]]]:
        """Execute a database query using pymssql."""
        logger.info(f"💾 [DatabaseService] Executing query (fetch_results={fetch_results})")

        try:
            conn_params = self._get_connection_params_from_keyvault()
            # Note: pymssql uses login_timeout, not a general timeout in the connect call
            with pymssql.connect(**conn_params, login_timeout=30) as conn:
                conn.autocommit(True)  # Set autocommit after connection
                with conn.cursor(as_dict=True) as cursor:  # as_dict=True simplifies fetching
                    cursor.execute(query, params if params else None)

                    if fetch_results:
                        return cursor.fetchall()
                    # For non-SELECT queries, rowcount gives the number of affected rows
                    return cursor.rowcount

        except pymssql.Error as e:
            logger.error(f"💥 [DatabaseService] Database error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"💥 [DatabaseService] Unexpected error executing query: {str(e)}")
            raise