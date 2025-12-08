# 09 - Error Handling & Recovery

> API failures, retry strategies, partial data handling, and alerting

## Error Handling Philosophy

1. **Fail Gracefully**: Partial failures should not stop the entire pipeline
2. **Retry Intelligently**: Use exponential backoff with jitter
3. **Log Everything**: Comprehensive logging for debugging
4. **Alert Appropriately**: Critical errors trigger alerts, warnings are logged
5. **Recover Automatically**: Self-healing where possible

---

## 1. Error Categories

### Transient Errors (Retriable)

| Error Type | HTTP Code | Retry Strategy |
|------------|-----------|----------------|
| Rate Limited | 429 | Exponential backoff, respect `Retry-After` |
| Server Error | 500-503 | Exponential backoff, max 3 retries |
| Timeout | - | Immediate retry, max 3 attempts |
| Connection Error | - | Exponential backoff, max 5 retries |

### Permanent Errors (Non-Retriable)

| Error Type | HTTP Code | Action |
|------------|-----------|--------|
| Bad Request | 400 | Log error, skip item |
| Unauthorized | 401 | Alert, stop pipeline |
| Forbidden | 403 | Alert, check API permissions |
| Not Found | 404 | Log warning, skip item |
| Invalid Symbol | - | Log warning, remove from list |

### Data Errors

| Error Type | Action |
|------------|--------|
| Validation Failed | Log, skip invalid rows |
| Schema Mismatch | Log error, alert |
| Duplicate Data | Deduplicate silently |
| Missing Data | Log warning, continue |

---

## 2. Retry Implementation

### Tenacity Retry Decorator

```python
# crypto_pipeline/utils/retry.py
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)
import httpx
import logging

logger = logging.getLogger(__name__)


# Standard retry for API calls
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.HTTPStatusError,
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    after=after_log(logger, logging.DEBUG),
    reraise=True,
)


# Aggressive retry for critical operations
critical_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=1, max=120),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.HTTPStatusError,
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# Rate limit specific retry
def rate_limit_retry(retry_after_header: str = "Retry-After"):
    """Retry decorator that respects Retry-After header."""
    
    def wait_for_retry_after(retry_state):
        exc = retry_state.outcome.exception()
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get(retry_after_header)
                if retry_after:
                    return float(retry_after)
        # Default exponential backoff
        return min(2 ** retry_state.attempt_number, 60)
    
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_for_retry_after,
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )
```

### Usage in API Client

```python
# crypto_pipeline/resources/cex_clients.py
from crypto_pipeline.utils.retry import api_retry, rate_limit_retry


class BinanceClient(ConfigurableResource):
    
    @api_retry
    async def _request(self, url: str, params: dict = None) -> dict:
        """Make rate-limited request with retries."""
        await self._rate_limiter.acquire()
        
        response = await self._client.get(url, params=params)
        
        # Handle rate limiting explicitly
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            logger.warning(f"Rate limited, waiting {retry_after}s")
            raise httpx.HTTPStatusError(
                f"Rate limited",
                request=response.request,
                response=response,
            )
        
        response.raise_for_status()
        return response.json()
```

---

## 3. Asset-Level Error Handling

### Bronze Asset with Error Isolation

```python
# crypto_pipeline/assets/bronze/ohlcv.py
from dagster import asset, AssetExecutionContext, Output, MetadataValue
import pandas as pd
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


@asset(
    partitions_def=daily_partitions,
    group_name="bronze",
)
def bronze_binance_ohlcv(
    context: AssetExecutionContext,
    binance_client: BinanceClient,
) -> Output[pd.DataFrame]:
    """Fetch OHLCV with per-symbol error isolation."""
    
    partition_date = context.partition_key
    start, end = get_partition_range(partition_date)
    
    results: List[pd.DataFrame] = []
    errors: List[Tuple[str, str]] = []
    
    for symbol in SYMBOLS:
        try:
            df = binance_client.fetch_ohlcv_sync(
                symbol=symbol,
                interval="1d",
                start=start,
                end=end,
            )
            df['symbol'] = symbol
            df['exchange'] = 'binance'
            results.append(df)
            
            context.log.info(f"Fetched {len(df)} rows for {symbol}")
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Symbol not found - log and continue
                context.log.warning(f"Symbol {symbol} not found, skipping")
                errors.append((symbol, "not_found"))
            elif e.response.status_code in (401, 403):
                # Auth error - this is critical
                context.log.error(f"Authentication error for {symbol}")
                raise  # Re-raise to fail the asset
            else:
                # Other HTTP error - log and continue
                context.log.error(f"HTTP error for {symbol}: {e}")
                errors.append((symbol, f"http_{e.response.status_code}"))
                
        except httpx.TimeoutException:
            context.log.error(f"Timeout fetching {symbol}")
            errors.append((symbol, "timeout"))
            
        except Exception as e:
            context.log.error(f"Unexpected error for {symbol}: {e}")
            errors.append((symbol, str(type(e).__name__)))
    
    # Combine results
    if results:
        combined = pd.concat(results, ignore_index=True)
    else:
        combined = pd.DataFrame()
    
    # Log summary
    success_count = len(SYMBOLS) - len(errors)
    context.log.info(
        f"Completed: {success_count}/{len(SYMBOLS)} symbols successful"
    )
    
    # Determine if we should fail
    failure_rate = len(errors) / len(SYMBOLS)
    if failure_rate > 0.5:
        # More than 50% failed - this is abnormal
        raise RuntimeError(
            f"High failure rate: {len(errors)}/{len(SYMBOLS)} symbols failed"
        )
    
    return Output(
        combined,
        metadata={
            "row_count": len(combined),
            "symbols_success": success_count,
            "symbols_failed": len(errors),
            "errors": MetadataValue.json(dict(errors)),
            "partition_date": partition_date,
        },
    )
```

### Silver Asset with Validation Errors

```python
# crypto_pipeline/assets/silver/ohlcv_normalized.py

@asset(group_name="silver")
def silver_ohlcv_normalized(
    context: AssetExecutionContext,
    binance: pd.DataFrame,
    coinbase: pd.DataFrame,
    okx: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Normalize with validation error handling."""
    
    # Combine sources
    dfs = [df for df in [binance, coinbase, okx] if not df.empty]
    
    if not dfs:
        context.log.warning("No input data from any exchange")
        return Output(
            pd.DataFrame(),
            metadata={"status": "no_input_data"},
        )
    
    combined = pd.concat(dfs, ignore_index=True)
    initial_count = len(combined)
    
    # Validate
    validation_result = validate_ohlcv(combined)
    
    if validation_result.errors:
        for error in validation_result.errors:
            context.log.error(f"Validation error: {error}")
    
    if validation_result.warnings:
        for warning in validation_result.warnings:
            context.log.warning(f"Validation warning: {warning}")
    
    # Remove invalid rows
    valid_mask = create_validity_mask(combined)
    cleaned = combined[valid_mask].copy()
    removed_count = initial_count - len(cleaned)
    
    if removed_count > 0:
        context.log.warning(f"Removed {removed_count} invalid rows")
    
    # Check if too much data was removed
    removal_rate = removed_count / initial_count if initial_count > 0 else 0
    if removal_rate > 0.1:  # More than 10% removed
        context.log.error(
            f"High removal rate: {removal_rate:.1%} of data was invalid"
        )
        # Could raise here or just alert
    
    return Output(
        cleaned,
        metadata={
            "input_rows": initial_count,
            "output_rows": len(cleaned),
            "removed_rows": removed_count,
            "removal_rate": f"{removal_rate:.2%}",
            "validation_errors": len(validation_result.errors),
            "validation_warnings": len(validation_result.warnings),
        },
    )
```

---

## 4. Custom Exception Classes

```python
# crypto_pipeline/exceptions.py
from typing import Optional, Dict, Any


class PipelineError(Exception):
    """Base exception for pipeline errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class ExchangeAPIError(PipelineError):
    """Error from exchange API."""
    
    def __init__(
        self, 
        message: str, 
        exchange: str,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, kwargs)
        self.exchange = exchange
        self.status_code = status_code


class RateLimitError(ExchangeAPIError):
    """Rate limit exceeded."""
    
    def __init__(self, exchange: str, retry_after: Optional[int] = None):
        super().__init__(
            f"Rate limit exceeded for {exchange}",
            exchange=exchange,
            status_code=429,
        )
        self.retry_after = retry_after


class ValidationError(PipelineError):
    """Data validation failed."""
    
    def __init__(self, message: str, invalid_rows: int = 0, **kwargs):
        super().__init__(message, kwargs)
        self.invalid_rows = invalid_rows


class PublishError(PipelineError):
    """Error publishing to HuggingFace."""
    pass


class ConfigurationError(PipelineError):
    """Configuration error."""
    pass
```

---

## 5. Alerting Integration

### Alert Levels

| Level | When to Use | Action |
|-------|-------------|--------|
| **Critical** | Pipeline completely failed | Page on-call |
| **Error** | Significant data loss (>10%) | Email + Slack |
| **Warning** | Minor issues, partial failures | Slack only |
| **Info** | Normal operations | Log only |

### Alerting Implementation

```python
# crypto_pipeline/utils/alerting.py
import os
import httpx
from enum import Enum
from typing import Optional
from datetime import datetime


class AlertLevel(Enum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AlertManager:
    """Send alerts via various channels."""
    
    def __init__(self):
        self.slack_webhook = os.environ.get("SLACK_WEBHOOK_URL")
        self.pagerduty_key = os.environ.get("PAGERDUTY_ROUTING_KEY")
    
    def alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        details: Optional[dict] = None,
    ):
        """Send alert based on level."""
        
        if level == AlertLevel.CRITICAL:
            self._send_pagerduty(title, message, details)
            self._send_slack(level, title, message, details)
        elif level == AlertLevel.ERROR:
            self._send_slack(level, title, message, details)
        elif level == AlertLevel.WARNING:
            self._send_slack(level, title, message, details)
        # INFO level - just log
    
    def _send_slack(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        details: Optional[dict] = None,
    ):
        """Send Slack notification."""
        if not self.slack_webhook:
            return
        
        color_map = {
            AlertLevel.CRITICAL: "#FF0000",
            AlertLevel.ERROR: "#FFA500",
            AlertLevel.WARNING: "#FFFF00",
            AlertLevel.INFO: "#00FF00",
        }
        
        payload = {
            "attachments": [{
                "color": color_map[level],
                "title": f"[{level.value.upper()}] {title}",
                "text": message,
                "fields": [
                    {"title": k, "value": str(v), "short": True}
                    for k, v in (details or {}).items()
                ],
                "ts": datetime.utcnow().timestamp(),
            }]
        }
        
        try:
            httpx.post(self.slack_webhook, json=payload, timeout=10)
        except Exception as e:
            # Don't fail on alert failure
            print(f"Failed to send Slack alert: {e}")
    
    def _send_pagerduty(
        self,
        title: str,
        message: str,
        details: Optional[dict] = None,
    ):
        """Send PagerDuty alert for critical issues."""
        if not self.pagerduty_key:
            return
        
        payload = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": title,
                "severity": "critical",
                "source": "crypto-pipeline",
                "custom_details": {
                    "message": message,
                    **(details or {}),
                },
            },
        }
        
        try:
            httpx.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=10,
            )
        except Exception as e:
            print(f"Failed to send PagerDuty alert: {e}")


# Singleton
_alert_manager: Optional[AlertManager] = None

def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def alert_critical(title: str, message: str, **details):
    get_alert_manager().alert(AlertLevel.CRITICAL, title, message, details)


def alert_error(title: str, message: str, **details):
    get_alert_manager().alert(AlertLevel.ERROR, title, message, details)


def alert_warning(title: str, message: str, **details):
    get_alert_manager().alert(AlertLevel.WARNING, title, message, details)
```

### Dagster Failure Hooks

```python
# crypto_pipeline/hooks.py
from dagster import failure_hook, HookContext

from crypto_pipeline.utils.alerting import alert_critical, alert_error


@failure_hook
def alert_on_failure(context: HookContext):
    """Send alert when asset/job fails."""
    
    # Get failure info
    asset_key = context.op.name if context.op else "unknown"
    run_id = context.run_id
    
    # Check if it's a critical asset
    critical_assets = ["gold_huggingface_ohlcv"]
    
    if asset_key in critical_assets:
        alert_critical(
            title=f"Critical Asset Failed: {asset_key}",
            message=f"Run {run_id} failed for critical asset",
            asset=asset_key,
            run_id=run_id,
        )
    else:
        alert_error(
            title=f"Asset Failed: {asset_key}",
            message=f"Run {run_id} failed",
            asset=asset_key,
            run_id=run_id,
        )
```

---

## 6. Recovery Strategies

### Automatic Backfill on Failure

```python
# crypto_pipeline/sensors/failure_sensor.py
from dagster import (
    sensor,
    RunRequest,
    SensorEvaluationContext,
    DagsterRunStatus,
)


@sensor(job=backfill_job)
def failure_recovery_sensor(context: SensorEvaluationContext):
    """Automatically retry failed partitions."""
    
    # Get recent failed runs
    failed_runs = context.instance.get_runs(
        filters=RunsFilter(
            statuses=[DagsterRunStatus.FAILURE],
            created_after=datetime.utcnow() - timedelta(hours=24),
        ),
        limit=10,
    )
    
    for run in failed_runs:
        # Check if already retried
        retry_tag = f"retry_of_{run.run_id}"
        existing_retries = context.instance.get_runs(
            filters=RunsFilter(tags={retry_tag: "true"}),
            limit=1,
        )
        
        if existing_retries:
            continue  # Already retried
        
        # Check retry count
        current_retries = int(run.tags.get("retry_count", "0"))
        if current_retries >= 3:
            continue  # Max retries exceeded
        
        # Schedule retry
        partition_key = run.tags.get("dagster/partition")
        if partition_key:
            yield RunRequest(
                run_key=f"retry_{run.run_id}",
                partition_key=partition_key,
                tags={
                    retry_tag: "true",
                    "retry_count": str(current_retries + 1),
                },
            )
```

### Manual Recovery Commands

```python
# crypto_pipeline/cli.py
import click
from datetime import datetime, timedelta


@click.group()
def cli():
    """Pipeline management CLI."""
    pass


@cli.command()
@click.option("--start", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD)")
@click.option("--asset", default="bronze_binance_ohlcv", help="Asset to backfill")
def backfill(start: str, end: str, asset: str):
    """Backfill failed partitions."""
    from dagster import execute_job
    
    start_date = datetime.strptime(start, "%Y-%m-%d")
    end_date = datetime.strptime(end, "%Y-%m-%d")
    
    current = start_date
    while current <= end_date:
        partition_key = current.strftime("%Y-%m-%d")
        click.echo(f"Backfilling {asset} for {partition_key}")
        
        # Execute backfill
        result = execute_job(
            job=backfill_job,
            partition_key=partition_key,
        )
        
        if result.success:
            click.echo(f"  Success")
        else:
            click.echo(f"  Failed: {result.failure_data}")
        
        current += timedelta(days=1)


@cli.command()
@click.option("--hours", default=24, help="Hours to look back")
def check_gaps(hours: int):
    """Check for missing data in recent partitions."""
    # Implementation to detect gaps
    pass
```

---

## 7. Error Monitoring Dashboard

### Key Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `pipeline.runs.failed` | Failed runs count | > 3 in 1 hour |
| `pipeline.symbols.failed` | Symbols with errors | > 10% |
| `pipeline.validation.removed` | Invalid rows removed | > 5% |
| `pipeline.latency.p95` | 95th percentile latency | > 5 minutes |
| `pipeline.data.freshness` | Time since last update | > 2 hours |

### Dagster Job Tags for Monitoring

```python
@job(
    tags={
        "team": "data-engineering",
        "criticality": "high",
        "alert_channel": "#crypto-pipeline-alerts",
    }
)
def daily_ingestion_job():
    pass
```

---

## Error Handling Checklist

### Per-Asset

- [ ] Wrap API calls in try/except
- [ ] Use appropriate retry decorators
- [ ] Log errors with context
- [ ] Return partial results when possible
- [ ] Add error counts to metadata

### Per-Pipeline

- [ ] Define critical vs non-critical assets
- [ ] Configure failure hooks
- [ ] Set up alerting channels
- [ ] Create recovery procedures
- [ ] Document known failure modes

### Monitoring

- [ ] Set up Slack/PagerDuty integration
- [ ] Define alert thresholds
- [ ] Create runbook for common failures
- [ ] Test alert delivery
