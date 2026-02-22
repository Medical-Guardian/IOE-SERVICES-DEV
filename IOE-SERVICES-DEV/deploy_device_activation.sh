#!/bin/bash
# Device Activation Deployment Script with Cache Busting
# Ensures Device Activation functions are registered in Azure

set -e

echo "🚀 Starting Device Activation deployment with cache busting..."

# Step 1: Verify all Device Activation files exist locally
echo ""
echo "📋 Step 1: Verifying Device Activation files..."
FILES=(
    "functions/device_activation_scheduler.py"
    "functions/device_activation_file_processor.py"
    "functions/operations_device_activation_file_processor.py"
    "af_code/af_device_activation_logic.py"
    "af_code/device_activation_scheduler/main_logic.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ MISSING: $file"
        exit 1
    fi
done

# Step 2: Clean local build artifacts
echo ""
echo "🧹 Step 2: Cleaning local build artifacts..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo "  ✅ Cleaned Python cache files"

# Step 3: Deploy with remote build (forces clean deployment)
echo ""
echo "📦 Step 3: Deploying to Azure with remote build..."
func azure functionapp publish IOE-function --python --build remote

# Step 4: Restart function app to clear Azure cache
echo ""
echo "🔄 Step 4: Restarting function app to clear cache..."
az functionapp restart --name IOE-function --resource-group $(az functionapp list --query "[?name=='IOE-function'].resourceGroup" -o tsv)

echo ""
echo "⏳ Waiting 30 seconds for function app to restart..."
sleep 30

# Step 5: Verify deployment
echo ""
echo "✅ Step 5: Verifying Device Activation functions..."
echo ""
echo "Expected Device Activation triggers:"
echo "  - timer_device_activation (Timer)"
echo "  - http_device_activation (HTTP)"
echo "  - ProcessDeviceActivationBlob (Blob)"
echo "  - operations_device_activation_file_processor (Blob)"
echo ""
echo "Run this command to verify:"
echo "  az functionapp function list --name IOE-function --resource-group <your-rg> --query \"[].{name:name, trigger:properties.config.bindings[0].type}\" -o table"

