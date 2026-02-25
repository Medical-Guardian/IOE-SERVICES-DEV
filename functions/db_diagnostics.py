"""
DB Diagnostics HTTP Endpoint — IOE-SERVICES-DEV

Mirrors the exact pyodbc + Managed Identity connection pattern used in Test_AI-dbdev
to isolate whether MSI → Azure SQL works from this Function App.

Route:  GET /api/db-diagnostics
Auth:   ANONYMOUS (no function key required)
"""

import logging
import os
import socket

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
    Diagnostic endpoint that tests Key Vault access and SQL connectivity.`

    Returns a plain-text report showing:
    - MSI credential acquisition status
    - Key Vault secret retrieval status
    - DNS resolution for the SQL server hostname
    - TCP port 1433 reachability
    - Row counts from ioe.members, ioe.member_devices, ioe_stg.stg_device_activation_delta

    BusinessCaseID: DIAG-001
    """
    logger.info("🔍 [DB-DIAG] DB Diagnostics endpoint called")

    result = {
        "credential": None,
        "key_vault_url": None,
        "key_vault_secret": None,
        "key_vault_ok": False,
        "sql_server": None,
        "sql_database": None,
        "sql_dns": None,
        "sql_tcp": None,
        "sql_ok": False,
        "members_count": None,
        "member_devices_count": None,
        "stg_count": None,
    }
    errors = []

    # ── Step 1: Managed Identity credential ──────────────────────────────────
    try:
        credential = DefaultAzureCredential()
        result["credential"] = "DefaultAzureCredential acquired"
        logger.info("✅ [DB-DIAG] DefaultAzureCredential acquired")
    except Exception as e:
        msg = f"DefaultAzureCredential FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        errors.append(msg)
        return _build_response(result, errors, partial=True)

    # ── Step 2: Key Vault → fetch connection string ───────────────────────────
    key_vault_url = os.environ.get("KEY_VAULT_URL", "")
    db_secret_name = os.environ.get("DB_SECRET_NAME", "SqlConnectionString")
    result["key_vault_url"] = key_vault_url or "NOT SET"

    if not key_vault_url:
        msg = "KEY_VAULT_URL environment variable is not set"
        logger.error(f"❌ [DB-DIAG] {msg}")
        errors.append(msg)
        return _build_response(result, errors, partial=True)

    try:
        secret_client = SecretClient(vault_url=key_vault_url, credential=credential)
        sql_conn_str = secret_client.get_secret(db_secret_name).value
        result["key_vault_secret"] = f"{db_secret_name} ✅"
        result["key_vault_ok"] = True
        logger.info(f"✅ [DB-DIAG] Key Vault secret '{db_secret_name}' retrieved")
    except Exception as e:
        msg = f"Key Vault secret retrieval FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        errors.append(msg)
        result["key_vault_secret"] = f"{db_secret_name} ❌ — {e}"
        return _build_response(result, errors, partial=True)

    # ── Step 3: Parse server / database from connection string ────────────────
    params = {}
    for part in sql_conn_str.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key.strip()] = value.strip()

    server = params.get("Server", "").replace("tcp:", "").split(",")[0]
    database = params.get("Database", "")
    result["sql_server"] = server or "UNKNOWN"
    result["sql_database"] = database or "UNKNOWN"
    logger.info(f"🔍 [DB-DIAG] Parsed server='{server}' database='{database}'")

    # ── Step 4: Socket pre-checks (DNS + TCP) ─────────────────────────────────
    # DNS resolution
    try:
        ip = socket.gethostbyname(server)
        logger.info(f"✅ [DB-DIAG] DNS resolved: {server} -> {ip}")
        result["sql_dns"] = f"DNS OK ({server} -> {ip})"
    except Exception as e:
        logger.error(f"❌ [DB-DIAG] DNS resolution failed: {e}")
        result["sql_dns"] = f"DNS FAILED: {e}"
        errors.append(f"DNS resolution failed for '{server}': {e}")

    # TCP port 1433 reachability
    try:
        sock = socket.create_connection((server, 1433), timeout=5)
        sock.close()
        logger.info("✅ [DB-DIAG] TCP connection to port 1433 succeeded")
        result["sql_tcp"] = "TCP 1433 OK"
    except Exception as e:
        logger.error(f"❌ [DB-DIAG] TCP connection to port 1433 failed: {e}")
        result["sql_tcp"] = f"TCP 1433 FAILED: {e}"
        errors.append(f"TCP port 1433 unreachable on '{server}': {e}")

    # ── Step 5: pyodbc connection + queries ───────────────────────────────────
    db_schema = os.environ.get("DB_SCHEMA", "ioe")
    db_schema_stg = os.environ.get("DB_SCHEMA_STG", "ioe_stg")

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

    try:
        logger.info("🔄 [DB-DIAG] Opening pyodbc connection (ActiveDirectoryMsi) …")
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        logger.info("✅ [DB-DIAG] pyodbc connection established")

        # ioe.members
        cursor.execute(f"SELECT COUNT(*) FROM {db_schema}.members")
        result["members_count"] = cursor.fetchone()[0]
        logger.info(f"✅ [DB-DIAG] {db_schema}.members: {result['members_count']} records")

        # ioe.member_devices
        cursor.execute(f"SELECT COUNT(*) FROM {db_schema}.member_devices")
        result["member_devices_count"] = cursor.fetchone()[0]
        logger.info(f"✅ [DB-DIAG] {db_schema}.member_devices: {result['member_devices_count']} records")

        # ioe_stg.stg_device_activation_delta (may not exist in all environments)
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {db_schema_stg}.stg_device_activation_delta")
            result["stg_count"] = cursor.fetchone()[0]
            logger.info(
                f"✅ [DB-DIAG] {db_schema_stg}.stg_device_activation_delta: "
                f"{result['stg_count']} records"
            )
        except Exception as stg_err:
            result["stg_count"] = f"inaccessible — {stg_err}"
            logger.warning(f"⚠️ [DB-DIAG] stg_device_activation_delta: {stg_err}")

        cursor.close()
        conn.close()
        result["sql_ok"] = True

    except Exception as e:
        msg = f"pyodbc connection FAILED: {e}"
        logger.error(f"❌ [DB-DIAG] {msg}")
        errors.append(msg)

    return _build_response(result, errors, partial=False)


def _build_response(result: dict, errors: list, partial: bool) -> func.HttpResponse:
    """Format the diagnostic result as a human-readable plain-text response."""
    sep = "━" * 40

    kv_icon = "✅" if result["key_vault_ok"] else "❌"
    sql_icon = "✅" if result["sql_ok"] else "❌"

    checks_passed = sum([result["key_vault_ok"], result["sql_ok"]])
    total_checks = 2

    lines = [
        "🔍 IOE-SERVICES-DEV DB Diagnostics",
        sep,
        "",
        f"{kv_icon} Key Vault",
        f"   URL: {result['key_vault_url']}",
        f"   Secret: {result['key_vault_secret'] or '(not attempted)'}",
        "",
        f"{sql_icon} SQL Database",
        f"   Server:   {result['sql_server']}",
        f"   Database: {result['sql_database']}",
        f"   DNS:      {result['sql_dns'] or '(not attempted)'}",
        f"   TCP:      {result['sql_tcp'] or '(not attempted)'}",
    ]

    db_schema = os.environ.get("DB_SCHEMA", "ioe")
    db_schema_stg = os.environ.get("DB_SCHEMA_STG", "ioe_stg")

    if result["members_count"] is not None:
        lines.append(f"   {db_schema}.members: {result['members_count']} records")
    if result["member_devices_count"] is not None:
        lines.append(f"   {db_schema}.member_devices: {result['member_devices_count']} records")
    if result["stg_count"] is not None:
        lines.append(
            f"   {db_schema_stg}.stg_device_activation_delta: {result['stg_count']} records"
        )

    if errors:
        lines += ["", "❌ Errors:"]
        for err in errors:
            lines.append(f"   • {err}")

    lines += [
        "",
        sep,
        f"Overall Status: {checks_passed}/{total_checks} {'✅' if checks_passed == total_checks else '⚠️'}",
    ]

    body = "\n".join(lines) + "\n"
    status_code = 200 if checks_passed == total_checks else 206

    return func.HttpResponse(
        body=body,
        status_code=status_code,
        mimetype="text/plain",
    )
