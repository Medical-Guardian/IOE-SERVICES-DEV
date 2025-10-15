# Azure Functions CI/CD Workflow Documentation

## Overview

This document describes the enhanced GitHub Actions workflow for deploying Python Azure Function Apps with comprehensive logging, validation, and monitoring capabilities.

## Workflow File

**Location**: `.github/workflows/azure-function-deploy.yml`

## Features

### 🚀 Core Capabilities

1. **Comprehensive Logging**
   - Detailed logs at every step of the pipeline
   - Color-coded output with visual separators
   - Timing and performance metrics
   - Artifact information and file listings

2. **Dependency Caching**
   - Intelligent pip cache management
   - Separate caches for build and quality checks
   - Significant speed improvements on subsequent runs

3. **Multi-Stage Validation**
   - Python syntax validation across all modules
   - Critical import verification
   - Function module loading tests
   - Azure SDK component checks

4. **Quality Assurance**
   - Code formatting (Black)
   - Linting (Ruff)
   - Type checking (MyPy)
   - Security scanning (Bandit)
   - Dependency vulnerability checks (Safety)
   - Unit tests with coverage (PyTest)

5. **Optimized Packaging**
   - Smart exclusion of unnecessary files
   - Reduced artifact size
   - Proper .gitignore-style filtering

6. **Deployment Verification**
   - Automated health checks post-deployment
   - Retry logic for startup time
   - Clear success/failure reporting
   - Deployment summary with all key information

## Workflow Structure

### Job 1: Build & Package (🔨)

**Purpose**: Compile, validate, and package the application

**Steps**:
1. Repository checkout with full history
2. Python environment setup
3. Dependency caching
4. Package installation
5. Syntax validation
6. Import validation for all function modules
7. Project structure analysis
8. Optimized deployment package creation
9. Artifact upload

**Key Validations**:
- ✅ All Python files have valid syntax
- ✅ Azure Functions SDK loads correctly
- ✅ Database drivers (pymssql) are available
- ✅ Azure SDK components (identity, keyvault, storage) work
- ✅ All function modules can be imported
- ✅ All function blueprints are accessible

### Job 2: Quality & Security Checks (🔍)

**Purpose**: Ensure code quality and security standards

**Steps**:
1. Setup parallel environment
2. Install quality tools
3. Code formatting check (Black)
4. Linting analysis (Ruff)
5. Type checking (MyPy)
6. Security scanning (Bandit)
7. Dependency vulnerability check (Safety)
8. Unit test execution (PyTest)

**Non-Blocking**:
- Quality checks produce warnings but don't fail the build
- This allows deployment while alerting developers to issues
- Adjust behavior by changing `exit 0` to `exit 1` in the workflow

### Job 3: Deploy to Azure (🚀)

**Purpose**: Deploy the validated package to Azure Functions

**Steps**:
1. Download build artifact
2. Deploy to Azure Functions with Oryx build
3. Wait for deployment stabilization (30 seconds)
4. Perform health checks with retries
5. Display comprehensive deployment summary

**Deployment Configuration**:
- Uses Azure Functions Action v1
- Enables Oryx build for server-side dependency installation
- Deploys to Production slot
- Uses publish profile for authentication

## Triggers

### Automatic Triggers

1. **Push to main branch**
   ```yaml
   on:
     push:
       branches:
         - main
   ```

2. **Pull requests to main**
   ```yaml
   on:
     pull_request:
       branches:
         - main
   ```

### Manual Trigger

**Workflow Dispatch** with optional log level:
```yaml
workflow_dispatch:
  inputs:
    log_level:
      description: 'Log level for deployment'
      type: choice
      options:
        - info
        - debug
        - verbose
```

To manually trigger:
1. Go to Actions tab in GitHub
2. Select "Azure Function App - Build & Deploy"
3. Click "Run workflow"
4. Choose log level (optional)
5. Click "Run workflow"

## Environment Variables

```yaml
env:
  AZURE_FUNCTIONAPP_PACKAGE_PATH: '.'
  PYTHON_VERSION: '3.12'
  FUNCTIONAPP_NAME: 'IOE-function'
  ARTIFACT_NAME: 'azure-function-app'
```

### Customization

To customize for your environment:

1. **Function App Name**:
   ```yaml
   FUNCTIONAPP_NAME: 'your-function-app-name'
   ```

2. **Python Version**:
   ```yaml
   PYTHON_VERSION: '3.11'  # or 3.9, 3.10
   ```

3. **Package Path**:
   ```yaml
   AZURE_FUNCTIONAPP_PACKAGE_PATH: './src'  # if not root
   ```

## Secrets Required

### AZURE_PROD_FUNCTION_PUBLISH_PROFILE

**How to obtain**:

1. **Via Azure Portal**:
   ```bash
   az functionapp deployment list-publishing-profiles \
     --name IOE-function \
     --resource-group your-resource-group \
     --xml
   ```

2. **Via Portal UI**:
   - Navigate to your Function App
   - Click "Get publish profile"
   - Download the .PublishSettings file
   - Copy entire XML content

3. **Add to GitHub**:
   - Go to repository Settings
   - Navigate to Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `AZURE_PROD_FUNCTION_PUBLISH_PROFILE`
   - Value: Paste the publish profile XML
   - Click "Add secret"

## Logging Examples

### Build Job Logs

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Repository: your-org/IOE-functions
🌲 Branch: main
📝 Commit: abc123def456
👤 Author: developer
🏷️  Workflow: Azure Function App - Build & Deploy
🔢 Run Number: 42
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Import Validation Logs

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Validating Critical Dependencies & Function Imports
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Testing Azure Functions Core...
✅ azure-functions
   ✓ Azure Functions SDK loaded

🗄️  Testing Database Libraries...
✅ pymssql
   ✓ SQL Server driver loaded

☁️  Testing Azure SDK Components...
✅ azure-identity
✅ azure-keyvault-secrets
✅ azure-storage-blob

📊 Testing Data Processing Libraries...
✅ pandas
✅ pandera

⚡ Testing Function Modules...
✅ dtc_file_processor
   ✓ DTC File Processor module loaded
✅ partner_file_processor
   ✓ Partner File Processor module loaded
[... more modules ...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Import Validation Summary:
   Import errors: 0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ All critical imports validated successfully
```

### Deployment Summary

```
╔═══════════════════════════════════════════════════════════════╗
║                   DEPLOYMENT SUMMARY                          ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Function App: IOE-function                                   ║
║  Environment:  Production                                     ║
║  Python:       3.12                                           ║
║  Status:       success                                        ║
║                                                               ║
║  URLs:                                                        ║
║  🌐 App: https://ioe-function.azurewebsites.net              ║
║  🔧 SCM: https://ioe-function.scm.azurewebsites.net          ║
║                                                               ║
║  Deployment Info:                                             ║
║  📝 Commit: abc123def456789...                               ║
║  🌲 Branch: main                                              ║
║  👤 Author: developer                                         ║
║  🕐 Time:   2025-10-16 14:30:00 UTC                          ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

## Monitoring and Troubleshooting

### Viewing Workflow Runs

1. Navigate to the **Actions** tab in your GitHub repository
2. Select the workflow run you want to inspect
3. Click on individual jobs to see detailed logs
4. Expand each step to see granular output

### Common Issues and Solutions

#### Issue: Import Validation Fails

**Symptoms**:
```
❌ Failed to load DTC File Processor
   Import errors: 1
```

**Solutions**:
1. Check if the module exists in the `functions/` directory
2. Verify `requirements.txt` includes all dependencies
3. Look for syntax errors in the module
4. Check for circular imports

#### Issue: Cache Not Working

**Symptoms**:
- Always shows "Cache MISS"
- Dependencies download every time

**Solutions**:
1. Verify `requirements.txt` hasn't changed
2. Check cache key in workflow file
3. Review cache size limits (10GB max per repository)

#### Issue: Deployment Health Check Fails

**Symptoms**:
```
⚠️  Health check inconclusive
   The Function App may still be starting up.
```

**Solutions**:
1. Check Azure Portal for function app status
2. Review Application Insights logs
3. Verify environment variables are set in Azure
4. Check if function app is in "Running" state
5. Increase stabilization wait time in workflow

#### Issue: Quality Checks Producing Warnings

**Symptoms**:
- Build succeeds but many warnings appear
- "Code formatting issues detected"

**Solutions**:
1. Run tools locally before committing:
   ```bash
   black --line-length 100 .
   ruff check . --fix
   mypy af_code/ --ignore-missing-imports
   ```

2. To make quality checks blocking, change:
   ```yaml
   exit 0  # Don't fail build
   ```
   to:
   ```yaml
   exit 1  # Fail build on issues
   ```

### Performance Optimization

#### Build Time Breakdown

- **First Run** (no cache): ~3-5 minutes
- **Cached Run**: ~1-2 minutes
- **Quality Checks**: ~2-3 minutes
- **Deployment**: ~2-4 minutes

**Total**: 5-12 minutes depending on cache

#### Optimization Tips

1. **Parallel Jobs**: Build and quality-checks run in parallel
2. **Cache Strategy**: Separate caches for build and quality prevent conflicts
3. **Artifact Compression**: Pre-compressed artifacts avoid redundant compression
4. **Smart Exclusions**: Exclude unnecessary files to reduce package size

## Best Practices

### 1. Commit Message Standards

Use conventional commits for better tracking:
```
feat: add new function for data processing
fix: resolve database connection timeout
docs: update API documentation
chore: upgrade dependencies
```

### 2. Testing Before Deployment

Always test locally first:
```bash
# Validate syntax
python -m py_compile function_app.py

# Run tests
pytest af_code/ --verbose

# Check formatting
black --check --line-length 100 .

# Lint code
ruff check .
```

### 3. Environment Variables

Keep sensitive data in Azure:
- Use Azure Key Vault for secrets
- Reference via Application Settings
- Never commit secrets to repository

### 4. Monitoring Post-Deployment

1. Check Application Insights for errors
2. Review function execution logs
3. Monitor performance metrics
4. Set up alerts for failures

## Advanced Configuration

### Adding New Function Modules

When adding a new function module, update the validation step:

```yaml
- name: 🔍 Validate imports and function modules
  run: |
    # Add your new module here
    if python -c "from functions.your_new_module import bp; print('✅ your_new_module')"; then
      echo "   ✓ Your New Module loaded"
    else
      echo "   ✗ Failed to load Your New Module"
      IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    fi
```

### Adding New Quality Checks

Example: Adding pylint

```yaml
- name: 🔍 Run pylint
  run: |
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 Running Pylint"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    pylint af_code/ --exit-zero --output-format=colorized || {
      echo "⚠️  Pylint issues detected"
      echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
      exit 0  # Don't fail build
    }
```

### Staging Environment

To add a staging slot:

```yaml
deploy-staging:
  name: 🚀 Deploy to Staging
  runs-on: ubuntu-latest
  needs: [build, quality-checks]
  environment:
    name: Staging
    url: https://${{ env.FUNCTIONAPP_NAME }}-staging.azurewebsites.net

  steps:
    # ... similar to production deployment ...
    - name: 🚀 Deploy to Azure Functions
      uses: Azure/functions-action@v1
      with:
        app-name: ${{ env.FUNCTIONAPP_NAME }}
        slot-name: 'staging'  # Changed to staging
        package: release.zip
        publish-profile: ${{ secrets.AZURE_STAGING_FUNCTION_PUBLISH_PROFILE }}
        scm-do-build-during-deployment: true
        enable-oryx-build: true
```

## Rollback Procedure

If deployment fails or issues are detected:

### Via Azure Portal

1. Navigate to your Function App
2. Go to "Deployment Center"
3. Find previous successful deployment
4. Click "Redeploy"

### Via Azure CLI

```bash
# List deployments
az functionapp deployment list \
  --name IOE-function \
  --resource-group your-resource-group

# Redeploy specific version
az functionapp deployment source sync \
  --name IOE-function \
  --resource-group your-resource-group
```

### Via GitHub Actions

1. Go to Actions tab
2. Find the last successful deployment
3. Click "Re-run all jobs"

## Security Considerations

### Secrets Management

- ✅ Use GitHub Secrets for sensitive data
- ✅ Use Azure Key Vault in the function app
- ✅ Rotate publish profiles regularly
- ❌ Never commit secrets to repository
- ❌ Never log sensitive information

### Access Control

- Limit who can trigger manual deployments
- Use branch protection rules
- Require pull request reviews
- Enable signed commits

### Dependency Security

- Regular `safety check` runs
- Automated Dependabot alerts
- Review security advisories
- Update dependencies promptly

## Support and Maintenance

### Regular Maintenance Tasks

1. **Weekly**:
   - Review failed deployments
   - Check security scan results
   - Monitor deployment duration

2. **Monthly**:
   - Update dependencies
   - Review and update workflow
   - Clean up old artifacts

3. **Quarterly**:
   - Rotate publish profiles
   - Review and update documentation
   - Audit access controls

### Getting Help

1. **GitHub Actions Documentation**: https://docs.github.com/en/actions
2. **Azure Functions Documentation**: https://docs.microsoft.com/en-us/azure/azure-functions/
3. **Python Azure Functions Guide**: https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python

---

## Changelog

### Version 2.0 (Current)

- ✅ Comprehensive logging throughout pipeline
- ✅ Enhanced validation with detailed output
- ✅ Parallel quality checks
- ✅ Optimized artifact packaging
- ✅ Health check verification
- ✅ Detailed deployment summary
- ✅ Security scanning integration
- ✅ Improved caching strategy

### Version 1.0 (Original)

- Basic build and deploy
- Simple validation
- Basic quality checks
- Manual verification needed
