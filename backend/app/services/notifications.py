import httpx
import structlog
from app.core.config import settings

log = structlog.get_logger()

async def send_slack_notification(title: str, description: str, severity: str):
    """
    Sends a formatted notification to Slack via Webhook.
    """
    if not settings.WEBHOOK_SLACK_URL:
        log.warning("slack_webhook_not_configured")
        return

    # Severity colors
    color = "#36a64f"  # Green
    if severity == "critical":
        color = "#ff0000"  # Red
    elif severity == "warning":
        color = "#ffcc00"  # Yellow

    payload = {
        "attachments": [
            {
                "fallback": f"{title}: {description}",
                "color": color,
                "title": title,
                "text": description,
                "footer": "Vita BI Insights Engine",
                "ts": None
            }
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(settings.WEBHOOK_SLACK_URL, json=payload)
            response.raise_for_status()
            log.info("slack_notification_sent", title=title)
    except Exception as e:
        log.error("slack_notification_failed", error=str(e))
