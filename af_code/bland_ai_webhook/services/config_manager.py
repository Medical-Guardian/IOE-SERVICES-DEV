import os
import logging
from typing import Optional
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import pytz

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Centralized configuration management for the application.

    This class is the single source of truth for all configuration settings.
    It retrieves values from environment variables and, if configured, from
    Azure Key Vault, caching them for performance.
    """

    def __init__(self):
        """Initializes the ConfigManager, setting up the Key Vault client if available."""
        self._key_vault_url = os.environ.get("KEY_VAULT_URL")
        self._secret_client = None
        self._cache = {}
        self._timezone = pytz.timezone(os.environ.get("TIMEZONE", "UTC"))
        self._initialize_key_vault()
        logger.info(f"🔧 [CONFIG-MANAGER] Initialized. Timezone: {self._timezone}.")

    def _initialize_key_vault(self):
        """Initializes the Azure Key Vault client using DefaultAzureCredential."""
        if self._key_vault_url:
            try:
                credential = DefaultAzureCredential()
                self._secret_client = SecretClient(vault_url=self._key_vault_url, credential=credential)
                logger.info("🔑 [CONFIG-MANAGER] Azure Key Vault client connected successfully.")
            except Exception as e:
                logger.error(f"🚨 [CONFIG-MANAGER] Failed to initialize Key Vault client: {str(e)}")
                self._secret_client = None

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieves a configuration value by its key.

        It checks the local cache first, then Key Vault, and finally the
        environment variables.

        Args:
            key: The name of the configuration setting (e.g., "SERVICE_BUS_QUEUE_NAME").
            default: The value to return if the key is not found anywhere.

        Returns:
            The configuration value as a string, or the default value.
        """
        if key in self._cache:
            return self._cache[key]

        value = None
        # Prioritize Key Vault if available
        if self._secret_client:
            try:
                secret = self._secret_client.get_secret(key.replace("_", "-"))  # Key Vault prefers hyphens
                value = secret.value
                logger.info(f"✅ [CONFIG-MANAGER] Retrieved '{key}' from Key Vault.")
            except Exception:
                logger.debug(f"ℹ️ [CONFIG-MANAGER] '{key}' not in Key Vault, checking environment.")

        # Fall back to environment variables
        if value is None:
            value = os.environ.get(key, default)
            if value is not default:
                logger.info(f"✅ [CONFIG-MANAGER] Retrieved '{key}' from environment.")

        self._cache[key] = value
        return value

    def get_db_connection_string(self) -> str:
        """
        Securely retrieves the database connection string.

        It looks for a secret in Key Vault using a name specified by the
        'DB_CONNECTION_SECRET_NAME' environment variable. If not found, it
        falls back to the 'DB_CONNECTION_STRING' environment variable.

        Returns:
            The database connection string.

        Raises:
            ValueError: If the connection string cannot be found.
        """
        secret_name = self.get_config("DB_CONNECTION_SECRET_NAME", "SqlConnectionStringIOE")

        # Use get_config to handle the logic of checking cache/KV/env
        connection_string = self.get_config(secret_name)

        # For backward compatibility, also check the direct env var if secret fails
        if not connection_string:
            connection_string = self.get_config("DB_CONNECTION_STRING")

        if not connection_string:
            logger.critical("🚨 [CONFIG-MANAGER] Database connection string not found in Key Vault or environment.")
            raise ValueError("Database connection string is not configured.")

        return connection_string

    def get_service_bus_connection_string(self) -> str:
        """Securely retrieves the Service Bus connection string."""
        secret_name = self.get_config("SERVICE_BUS_SECRET_NAME", "IOE-POSTCALL-ANALYSIS-BUS-ENDPOINT")

        connection_string = self.get_config(secret_name)

        if not connection_string:
            connection_string = self.get_config("SERVICE_BUS_CONNECTION_STRING")

        if not connection_string:
            logger.critical("🚨 [CONFIG-MANAGER] Service Bus connection string not configured.")
            raise ValueError("Service Bus connection string is not configured.")

        return connection_string

    def get_timezone(self) -> pytz.timezone:
        """Returns the configured timezone object."""
        return self._timezone
