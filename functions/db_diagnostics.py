"""
DB Diagnostics HTTP Endpoint — IOE-SERVICES-DEV

Mirrors the exact pyodbc + Managed Identity connection pattern used in Test_AI-dbdev
to isolate whether MSI → Azure SQL works from this Function App.

Route:  GET /api/db-diagnostics
Auth:   ANONYMOUS (no function key required)
"""

import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import pyodbc

logger = logging.getLogger(__name__)

db_diagnostics_bp = func.Blueprint()


@db_diagnostics_bp.function_name(name="DbDiagnostics")
@db_diagnostics_bp.route(route="db-diagnostics", methods=[func.HttpMethod.GET], auth_level=func.AuthLevel.ANONYMOUS)
def run_db_diagnostics(req: func.HttpRequest) -> func.HttpResponse:
    """
    Diagnostic endpoint that tests Key Vault access and SQL connectivity.

    Mirrors the exact connection pattern from Test_AI-dbdev/function_app.py.

    BusinessCaseID: DIAG-001
    """
    logger.info("🔍 [DB-DIAG] DB Diagnostics endpoint called")

    lines = [
        "🔍 IOE-SERVICES-DEV DB Diagnostics",
        "━" * 40,
        "",
    ]
    errors = []
    sql_conn_str = None

    # ── Step 1: Managed Identity credential ──────────────────────────────────
    try:
        credential = DefaultAzureCredential()
        logger.info("✅ [DB-DIAG] DefaultAzureCredential acquired")
    except Exception as e:
        msg = f"DefaultAzureCredential FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        lines += [f"❌ Credential", f"   {msg}", ""]
        return _respond(lines, errors=[msg], ok=False)

    # ── Step 2: Key Vault → list secrets + fetch connection string ────────────
    key_vault_url = os.environ.get("KEY_VAULT_URL", "")
    db_secret_name = os.environ.get("DB_SECRET_NAME", "SqlConnectionString")

    if not key_vault_url:
        msg = "KEY_VAULT_URL environment variable is not set"
        logger.error(f"❌ [DB-DIAG] {msg}")
        lines += [f"❌ Key Vault", f"   {msg}", ""]
        return _respond(lines, errors=[msg], ok=False)

    try:
        secret_client = SecretClient(vault_url=key_vault_url, credential=credential)
        # List secrets to verify Secrets User RBAC (same as Test_AI-dbdev)
        secret_properties = list(secret_client.list_properties_of_secrets())
        secret_count = len(secret_properties)
        # Fetch the DB connection string
        sql_conn_str = secret_client.get_secret(db_secret_name).value
        lines += [
            "✅ Key Vault",
            f"   URL: {key_vault_url}",
            f"   Secrets accessible: {secret_count}",
            f"   Secret fetched: {db_secret_name} ✅",
            "",
        ]
        logger.info(f"✅ [DB-DIAG] Key Vault OK — {secret_count} secrets, '{db_secret_name}' retrieved")
    except Exception as e:
        msg = f"Key Vault FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        lines += ["❌ Key Vault", f"   URL: {key_vault_url}", f"   Error: {e}", ""]
        return _respond(lines, errors=[msg], ok=False)

    # ── Step 3: Parse connection string ──────────────────────────────────────
    # The Key Vault secret starts with a bare server address (no 'Server=' key):
    #   tcp:hostname,1433;Database=MGNEXUSdev;Authentication=...
    params = {}
    server = ''
    for part in sql_conn_str.split(';'):
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip()] = value.strip()
        elif part:
            # Bare segment — treat as server address
            server = part.replace('tcp:', '').split(',')[0]

    # Fallback: if server was in a standard 'Server=...' key
    if not server:
        server = params.get('Server', '').replace('tcp:', '').split(',')[0]

    database = params.get('Database', '')

    # Debug: show raw keys and masked value prefix so we can see the format
    raw_preview = sql_conn_str[:120].replace('\n', '\\n').replace('\r', '\\r')
    logger.info(f"🔍 [DB-DIAG] Conn string keys: {list(params.keys())}")
    logger.info(f"🔍 [DB-DIAG] Parsed server='{server}' database='{database}'")
    logger.info(f"🔍 [DB-DIAG] Raw preview (120 chars): {raw_preview}")

    # ── Step 4: pyodbc connection (exact Test_AI-dbdev pattern) ──────────────
    db_schema = os.environ.get("DB_SCHEMA", "ioe")
    db_schema_stg = os.environ.get("DB_SCHEMA_STG", "ioe_stg")

    if not server:
        msg = (
            f"Server not found in connection string. "
            f"Keys found: {list(params.keys())}. "
            f"Raw (120 chars): {raw_preview}"
        )
        logger.error(f"❌ [DB-DIAG] {msg}")
        lines += ["❌ SQL Database", f"   {msg}", ""]
        return _respond(lines, errors=[msg], ok=False)

    connection_string = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        f"Authentication=ActiveDirectoryMsi;"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
        f"Login Timeout=30"
    )

    try:
        logger.info("🔄 [DB-DIAG] Opening pyodbc connection (ActiveDirectoryMsi) …")
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        logger.info("✅ [DB-DIAG] pyodbc connection established")

        cursor.execute("SELECT 1 AS test")
        cursor.fetchone()

        cursor.execute(f"SELECT COUNT(*) FROM {db_schema}.members")
        members_count = cursor.fetchone()[0]

        cursor.execute(f"SELECT COUNT(*) FROM {db_schema}.member_devices")
        member_devices_count = cursor.fetchone()[0]

        stg_detail = ""
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {db_schema_stg}.stg_device_activation_delta")
            stg_count = cursor.fetchone()[0]
            stg_detail = f"\n   {db_schema_stg}.stg_device_activation_delta: {stg_count} records"
        except Exception as stg_err:
            stg_detail = f"\n   {db_schema_stg}.stg_device_activation_delta: inaccessible — {stg_err}"
            logger.warning(f"⚠️ [DB-DIAG] stg table: {stg_err}")

        cursor.close()
        conn.close()

        lines += [
            "✅ SQL Database",
            f"   Server:   {server}",
            f"   Database: {database}",
            f"   {db_schema}.members: {members_count} records",
            f"   {db_schema}.member_devices: {member_devices_count} records"
            + stg_detail,
            "",
        ]
        logger.info(f"✅ [DB-DIAG] SQL OK — {members_count} members, {member_devices_count} devices")
        return _respond(lines, errors=[], ok=True)

    except Exception as e:
        msg = f"pyodbc connection FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        lines += [
            "❌ SQL Database",
            f"   Server:   {server}",
            f"   Database: {database}",
            f"   Error: {e}",
            "",
        ]
        return _respond(lines, errors=[msg], ok=False)


def _respond(lines: list, errors: list, ok: bool) -> func.HttpResponse:
    sep = "━" * 40
    if errors:
        lines += ["❌ Errors:"]
        for err in errors:
            lines.append(f"   • {err}")
        lines.append("")
    lines += [sep, f"Overall Status: {'2/2 ✅' if ok else '1/2 ⚠️'}"]
    body = "\n".join(lines) + "\n"
    return func.HttpResponse(body=body, status_code=200 if ok else 206, mimetype="text/plain")
