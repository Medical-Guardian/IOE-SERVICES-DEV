import azure.functions as func
import logging

# Import all the necessary components for the webhook
from af_code.bland_ai_webhook.webhook_handler import WebhookHandler
from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.data_validator import DataValidator
from af_code.bland_ai_webhook.services.duplicate_detector import DuplicateDetector
from af_code.bland_ai_webhook.services.status_mapper import StatusMapper
from af_code.bland_ai_webhook.services.database_orchestrator import DatabaseOrchestrator
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.bland_ai_webhook.services.business_rules_engine import BusinessRulesEngine
from af_code.bland_ai_webhook.services.error_handler import ErrorHandler
from af_code.bland_ai_webhook.services.service_bus_handler import ServiceBusHandler
from af_code.bland_ai_webhook.utils.logging_config import setup_logging

# Create a "Blueprint" for the webhook function, following your project's pattern
bp = func.Blueprint()

# --- Initialize all services (Dependency Injection) ---
# This setup happens once when the Function App starts
setup_logging()
logging.info("⚙️ Initializing services for Bland AI Webhook...")

cfg = ConfigManager()
db_service = DatabaseService(cfg)
validator = DataValidator(cfg)
db_orchestrator = DatabaseOrchestrator(db_service)
dup_detector = DuplicateDetector(cfg, db_service)
status_mapper = StatusMapper()
rules = BusinessRulesEngine(cfg)
err_handler = ErrorHandler(cfg, db_service)
service_bus = ServiceBusHandler(cfg)

# Create a single, long-lived instance of the handler
webhook_handler_instance = WebhookHandler(
    config_manager=cfg,
    data_validator=validator,
    duplicate_detector=dup_detector,
    status_mapper=status_mapper,
    db_orchestrator=db_orchestrator,
    business_rules=rules,
    error_handler=err_handler,
    service_bus_handler=service_bus,
)
logging.info("✅ Bland AI Webhook services initialized successfully.")


@bp.function_name(name="BlandAIWebhook")
@bp.route(route="bland-ai-webhook", methods=[func.HttpMethod.POST])
async def handle_bland_ai_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP endpoint to receive and process webhooks from Bland AI.
    """
    logging.info("🚀 Bland AI Webhook received a request.")
    # Call the main handler method to process the request
    return await webhook_handler_instance.handle_webhook(req)
