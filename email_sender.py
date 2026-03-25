"""
Email sender — sends the drafted email with the original invoice attached.
Uses SMTP (works with Gmail, Outlook, etc.)
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import config


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: list[dict] | None = None, # List of {"bytes": ..., "name": ...}
) -> str:
    """
    Send an email via SMTP with optional attachments.
    Returns "ok" on success or an error message on failure.
    """
    if not config.SMTP_EMAIL or not config.SMTP_PASSWORD:
        return "Credentials not configured. Add them in the Settings first"

    msg = MIMEMultipart()
    msg["From"] = config.SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    # Attach the files if provided
    if attachments:
        for attachment in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment["bytes"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment['name']}",
            )
            msg.attach(part)

    try:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_EMAIL, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return "ok"
    except Exception as e:
        return f"Failed to send email: {e}"
