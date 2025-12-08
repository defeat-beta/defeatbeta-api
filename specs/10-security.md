# 10 - Security

> API key management, secrets rotation, access controls, and security best practices

## Security Principles

1. **Least Privilege**: Only request permissions you need
2. **Defense in Depth**: Multiple layers of security
3. **Secrets Never in Code**: All secrets from environment or vaults
4. **Audit Everything**: Log all sensitive operations
5. **Fail Secure**: Default to denying access

---

## 1. API Key Management

### Exchange API Keys

| Exchange | Required Permissions | Notes |
|----------|---------------------|-------|
| **Binance** | Read-only (no permissions needed for public data) | Use IP whitelist if using keys |
| **Coinbase** | `view` only | No trade/transfer permissions |
| **OKX** | Read-only | Use passphrase |
| **Bybit** | Read-only | IP restrictions recommended |

### Key Creation Best Practices

```markdown
## Binance API Key Setup

1. Go to API Management in Binance
2. Create new API key with label "crypto-pipeline-readonly"
3. Permissions:
   - [ ] Enable Reading (required for authenticated endpoints)
   - [ ] Enable Spot & Margin Trading (DO NOT enable)
   - [ ] Enable Futures (DO NOT enable)
   - [ ] Enable Withdrawals (DO NOT enable)
4. IP Access Restrictions:
   - Restrict to specific IPs if running from static IP
   - Or use "Unrestricted" for dynamic environments
5. Save API Key and Secret securely
```

### Key Storage Hierarchy

```
Production:
├── AWS Secrets Manager / HashiCorp Vault (preferred)
├── Environment variables (acceptable)
└── .env files (NOT recommended)

Development:
├── .env.local file (gitignored)
└── Environment variables
```

---

## 2. Secrets Management

### Never Do This

```python
# BAD: Hardcoded secrets
BINANCE_API_KEY = "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy"  # NEVER!

# BAD: Secrets in config files committed to git
# config.yaml
# api_key: "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy"
```

### Do This Instead

```python
# GOOD: From environment
import os
api_key = os.environ.get("BINANCE_API_KEY")

# GOOD: From Pydantic SecretStr
from pydantic import SecretStr

class Config(BaseSettings):
    binance_api_key: SecretStr
    
    # SecretStr won't be printed in logs
    # config.binance_api_key.get_secret_value() to access
```

### AWS Secrets Manager Integration

```python
# crypto_pipeline/utils/secrets.py
import boto3
import json
from functools import lru_cache
from typing import Dict, Any
import os


class SecretsManager:
    """AWS Secrets Manager client."""
    
    def __init__(self, region: str = None):
        self.client = boto3.client(
            'secretsmanager',
            region_name=region or os.environ.get('AWS_REGION', 'us-east-1')
        )
        self._cache: Dict[str, Any] = {}
    
    @lru_cache(maxsize=10)
    def get_secret(self, secret_name: str) -> Dict[str, Any]:
        """Fetch and cache secret from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret = json.loads(response['SecretString'])
            return secret
        except Exception as e:
            raise RuntimeError(f"Failed to fetch secret {secret_name}: {e}")
    
    def get_exchange_credentials(self, exchange: str) -> Dict[str, str]:
        """Get credentials for a specific exchange."""
        secrets = self.get_secret("crypto-pipeline/exchange-keys")
        
        prefix = f"{exchange}_"
        return {
            k.replace(prefix, ""): v 
            for k, v in secrets.items() 
            if k.startswith(prefix)
        }


def load_secrets_to_env():
    """Load secrets from AWS to environment variables."""
    if os.environ.get("USE_AWS_SECRETS", "false").lower() != "true":
        return
    
    sm = SecretsManager()
    secrets = sm.get_secret("crypto-pipeline/exchange-keys")
    
    for key, value in secrets.items():
        env_key = key.upper()
        if env_key not in os.environ:  # Don't override existing
            os.environ[env_key] = value
```

### HashiCorp Vault Integration

```python
# crypto_pipeline/utils/vault.py
import hvac
import os


class VaultClient:
    """HashiCorp Vault client."""
    
    def __init__(self):
        self.client = hvac.Client(
            url=os.environ.get("VAULT_ADDR", "http://localhost:8200"),
            token=os.environ.get("VAULT_TOKEN"),
        )
    
    def get_secret(self, path: str) -> dict:
        """Read secret from Vault."""
        secret = self.client.secrets.kv.v2.read_secret_version(path=path)
        return secret['data']['data']
    
    def get_exchange_credentials(self, exchange: str) -> dict:
        """Get exchange API credentials."""
        return self.get_secret(f"crypto-pipeline/{exchange}")
```

---

## 3. Secrets Rotation

### Rotation Schedule

| Secret Type | Rotation Frequency | Automated |
|-------------|-------------------|-----------|
| Exchange API Keys | 90 days | Manual |
| HuggingFace Token | 180 days | Manual |
| Service Account Keys | 90 days | Automated |
| Database Passwords | 30 days | Automated |

### Rotation Procedure

```markdown
## Exchange API Key Rotation

1. **Preparation**
   - Generate new API key on exchange (keep old key active)
   - Test new key in staging environment

2. **Rotation**
   - Update secret in AWS Secrets Manager / Vault
   - Deploy new configuration
   - Verify pipeline works with new key

3. **Cleanup**
   - Wait 24 hours to ensure stability
   - Delete old API key from exchange
   - Update rotation log

4. **Documentation**
   - Record rotation date
   - Update next rotation reminder
```

### Automated Rotation Check

```python
# crypto_pipeline/utils/rotation_check.py
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


SECRET_MAX_AGE_DAYS = {
    "exchange_keys": 90,
    "hf_token": 180,
}


def check_secret_age(
    secret_name: str,
    created_at: datetime,
    secret_type: str = "exchange_keys",
) -> Optional[str]:
    """Check if secret needs rotation."""
    max_age = SECRET_MAX_AGE_DAYS.get(secret_type, 90)
    age_days = (datetime.utcnow() - created_at).days
    
    if age_days > max_age:
        return f"Secret '{secret_name}' is {age_days} days old (max: {max_age})"
    elif age_days > max_age - 14:
        return f"Secret '{secret_name}' will expire in {max_age - age_days} days"
    
    return None


def rotation_health_check():
    """Check all secrets for rotation needs."""
    warnings = []
    
    # This would integrate with your secrets manager
    # to check creation dates
    
    for warning in warnings:
        logger.warning(warning)
    
    return len(warnings) == 0
```

---

## 4. Access Controls

### Repository Access

| Role | Repository Access | Secrets Access |
|------|-------------------|----------------|
| Developer | Read/Write code | Dev secrets only |
| Reviewer | Read code | No secrets |
| DevOps | Read/Write code | All secrets |
| CI/CD | Read code | Production secrets |

### GitHub Repository Settings

```yaml
# .github/CODEOWNERS
# Require review for sensitive files

# Security-sensitive files
/.env* @security-team
/crypto_pipeline/utils/secrets.py @security-team
/crypto_pipeline/utils/vault.py @security-team

# Configuration files
/dagster.yaml @devops-team
/docker-compose.yml @devops-team
```

### Branch Protection

```markdown
## Required Branch Protections

- [x] Require pull request reviews (2 reviewers)
- [x] Require status checks to pass
- [x] Require signed commits
- [x] Do not allow force pushes
- [x] Do not allow deletions
```

---

## 5. Network Security

### IP Whitelisting

```python
# For exchanges that support IP restrictions
ALLOWED_IPS = [
    "203.0.113.10",  # Production server
    "203.0.113.11",  # Backup server
]

# Configure in exchange API settings
```

### Firewall Rules (Production)

```bash
# Only allow outbound to exchange APIs
# Binance
iptables -A OUTPUT -d api.binance.com -p tcp --dport 443 -j ACCEPT
iptables -A OUTPUT -d fapi.binance.com -p tcp --dport 443 -j ACCEPT

# Coinbase
iptables -A OUTPUT -d api.exchange.coinbase.com -p tcp --dport 443 -j ACCEPT

# HuggingFace
iptables -A OUTPUT -d huggingface.co -p tcp --dport 443 -j ACCEPT

# Block other outbound (careful with this!)
# iptables -A OUTPUT -j DROP
```

### TLS/SSL Requirements

```python
# Always verify SSL certificates
import httpx

# GOOD: SSL verification enabled (default)
client = httpx.AsyncClient(verify=True)

# BAD: Never disable SSL verification
# client = httpx.AsyncClient(verify=False)  # NEVER IN PRODUCTION
```

---

## 6. Data Security

### Sensitive Data Handling

```python
# crypto_pipeline/utils/sanitize.py
import re
from typing import Any, Dict


SENSITIVE_PATTERNS = [
    r'api[_-]?key',
    r'api[_-]?secret',
    r'password',
    r'token',
    r'passphrase',
]


def sanitize_for_logging(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive data before logging."""
    sanitized = {}
    
    for key, value in data.items():
        key_lower = key.lower()
        
        # Check if key matches sensitive patterns
        is_sensitive = any(
            re.search(pattern, key_lower) 
            for pattern in SENSITIVE_PATTERNS
        )
        
        if is_sensitive:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_for_logging(value)
        else:
            sanitized[key] = value
    
    return sanitized
```

### Logging Best Practices

```python
import logging
from crypto_pipeline.utils.sanitize import sanitize_for_logging

logger = logging.getLogger(__name__)


def fetch_data(config: dict):
    # GOOD: Sanitize before logging
    logger.info(f"Fetching with config: {sanitize_for_logging(config)}")
    
    # BAD: Logging raw config with secrets
    # logger.info(f"Fetching with config: {config}")
```

### Data at Rest

```python
# Parquet files don't contain secrets, but ensure:
# 1. No API keys in data
# 2. No PII (not applicable for market data)
# 3. Proper file permissions

import os

def secure_file_permissions(path: str):
    """Set restrictive file permissions."""
    os.chmod(path, 0o600)  # Owner read/write only
```

---

## 7. Audit Logging

### What to Log

| Event | Log Level | Details |
|-------|-----------|---------|
| API key used | INFO | Exchange, endpoint (not the key!) |
| Secret accessed | INFO | Secret name, accessor |
| Failed auth | WARNING | Exchange, error type |
| Rate limit hit | WARNING | Exchange, endpoint |
| Configuration change | INFO | What changed, who changed |

### Audit Log Implementation

```python
# crypto_pipeline/utils/audit.py
import logging
import json
from datetime import datetime
from typing import Optional

audit_logger = logging.getLogger("audit")


def log_secret_access(
    secret_name: str,
    accessor: str,
    action: str = "read",
):
    """Log secret access for audit."""
    audit_logger.info(json.dumps({
        "event": "secret_access",
        "timestamp": datetime.utcnow().isoformat(),
        "secret_name": secret_name,
        "accessor": accessor,
        "action": action,
    }))


def log_api_call(
    exchange: str,
    endpoint: str,
    success: bool,
    error: Optional[str] = None,
):
    """Log API calls for audit."""
    audit_logger.info(json.dumps({
        "event": "api_call",
        "timestamp": datetime.utcnow().isoformat(),
        "exchange": exchange,
        "endpoint": endpoint,
        "success": success,
        "error": error,
    }))
```

---

## 8. Dependency Security

### Dependency Scanning

```yaml
# .github/workflows/security.yml
name: Security Scan

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 0 * * *'  # Daily

jobs:
  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install safety bandit
      
      - name: Check for vulnerable dependencies
        run: safety check --full-report
      
      - name: Static security analysis
        run: bandit -r crypto_pipeline/ -ll
```

### Pinning Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    # Pin major.minor, allow patch updates
    "httpx >= 0.27.0, < 0.28",
    "pydantic >= 2.5.0, < 3.0",
    "dagster >= 1.7.0, < 2.0",
]
```

### Dependabot Configuration

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    reviewers:
      - "security-team"
```

---

## 9. Container Security

### Dockerfile Best Practices

```dockerfile
# Dockerfile
# Use specific version, not :latest
FROM python:3.11.7-slim-bookworm

# Run as non-root user
RUN useradd -m -u 1000 appuser

# Don't store secrets in image
# Use runtime environment variables instead

WORKDIR /app

# Copy only necessary files
COPY pyproject.toml .
COPY crypto_pipeline/ crypto_pipeline/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Switch to non-root user
USER appuser

# Don't expose unnecessary ports
EXPOSE 3000

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000"]
```

### Docker Compose Security

```yaml
# docker-compose.yml
version: "3.8"

services:
  dagster:
    build: .
    # Don't run as root
    user: "1000:1000"
    # Read-only filesystem where possible
    read_only: true
    tmpfs:
      - /tmp
    # Limit capabilities
    cap_drop:
      - ALL
    # Security options
    security_opt:
      - no-new-privileges:true
    # Resource limits
    deploy:
      resources:
        limits:
          memory: 4G
```

---

## 10. Security Checklist

### Before First Deploy

- [ ] All secrets in environment variables or secret manager
- [ ] No secrets in code or config files
- [ ] API keys have minimal required permissions
- [ ] IP whitelisting enabled (if supported)
- [ ] SSL certificate verification enabled
- [ ] Audit logging configured
- [ ] Dependency scanning enabled

### Regular Security Tasks

- [ ] Rotate API keys (every 90 days)
- [ ] Review access permissions (quarterly)
- [ ] Update dependencies (weekly)
- [ ] Review audit logs (weekly)
- [ ] Test secret rotation procedure (quarterly)

### Incident Response

- [ ] Revoke compromised credentials immediately
- [ ] Rotate all related secrets
- [ ] Review audit logs for unauthorized access
- [ ] Update security procedures
- [ ] Document incident and response
