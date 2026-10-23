"""
ZUGZWANG - Sender Pool Service
Manages multiple SMTP sender accounts, daily sending quotas, and rotation policies.
"""

from __future__ import annotations
import uuid
import smtplib
import socket
import ssl
from datetime import date
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple

from ..core.config import config_manager
from ..core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SenderAccount:
    id: str
    email: str
    password: str
    name: str = ""
    is_enabled: bool = True
    daily_limit: int = 100
    sent_today: int = 0
    last_sent_date: str = ""

    def can_send(self) -> bool:
        if not self.is_enabled or self.daily_limit <= 0:
            return False
        today_str = date.today().isoformat()
        if self.last_sent_date != today_str:
            return True
        return self.sent_today < self.daily_limit

    def remaining_today(self) -> int:
        if not self.is_enabled or self.daily_limit <= 0:
            return 0
        today_str = date.today().isoformat()
        if self.last_sent_date != today_str:
            return self.daily_limit
        return max(0, self.daily_limit - self.sent_today)


def get_sender_accounts() -> list[SenderAccount]:
    """Retrieve all configured sender accounts from settings."""
    s = config_manager.settings
    raw_profiles = getattr(s, "email_sender_profiles", []) or []
    accounts: list[SenderAccount] = []

    for entry in raw_profiles:
        if not isinstance(entry, dict):
            continue
        email = str(entry.get("email", "")).strip()
        if not email or "@" not in email:
            continue

        acc_id = str(entry.get("id") or email.lower())
        password = str(entry.get("password", ""))
        name = str(entry.get("name") or getattr(s, "email_from_name", "") or "")
        is_enabled = bool(entry.get("is_enabled", True))
        daily_limit = int(entry.get("daily_limit", 100))
        sent_today = int(entry.get("sent_today", 0))
        last_sent_date = str(entry.get("last_sent_date", ""))

        # Reset daily counter if day changed
        today_str = date.today().isoformat()
        if last_sent_date != today_str:
            sent_today = 0
            last_sent_date = today_str

        accounts.append(
            SenderAccount(
                id=acc_id,
                email=email,
                password=password,
                name=name,
                is_enabled=is_enabled,
                daily_limit=daily_limit,
                sent_today=sent_today,
                last_sent_date=last_sent_date,
            )
        )

    # Seed default account from primary settings if pool is empty
    if not accounts and s.email_smtp_user:
        default_acc = SenderAccount(
            id="default",
            email=s.email_smtp_user.strip(),
            password=s.email_smtp_pass,
            name=s.email_from_name or "",
            is_enabled=True,
            daily_limit=100,
            sent_today=0,
            last_sent_date=date.today().isoformat(),
        )
        accounts.append(default_acc)
        save_sender_accounts(accounts)

    return accounts


def save_sender_accounts(accounts: list[SenderAccount]) -> None:
    """Save accounts back to settings."""
    raw = [asdict(a) for a in accounts]
    config_manager.settings.email_sender_profiles = raw
    # Keep primary settings in sync with first enabled account
    enabled = [a for a in accounts if a.is_enabled]
    if enabled:
        config_manager.settings.email_smtp_user = enabled[0].email
        config_manager.settings.email_smtp_pass = enabled[0].password
        if enabled[0].name:
            config_manager.settings.email_from_name = enabled[0].name
    else:
        config_manager.settings.email_smtp_user = ""
        config_manager.settings.email_smtp_pass = ""
    config_manager.save()


def add_sender_account(email: str, password: str, name: str = "", daily_limit: int = 100) -> SenderAccount:
    """Add a new sender account to the pool."""
    accounts = get_sender_accounts()
    clean_email = email.strip()
    # Check if already exists
    for existing in accounts:
        if existing.email.lower() == clean_email.lower():
            existing.password = password
            if name:
                existing.name = name
            existing.daily_limit = daily_limit
            existing.is_enabled = True
            save_sender_accounts(accounts)
            return existing

    acc = SenderAccount(
        id=str(uuid.uuid4())[:8],
        email=clean_email,
        password=password,
        name=name,
        is_enabled=True,
        daily_limit=daily_limit,
        sent_today=0,
        last_sent_date=date.today().isoformat(),
    )
    accounts.append(acc)
    save_sender_accounts(accounts)
    return acc


def update_sender_account(account: SenderAccount) -> None:
    """Update an existing account in the pool."""
    accounts = get_sender_accounts()
    for i, a in enumerate(accounts):
        if a.id == account.id or a.email.lower() == account.email.lower():
            accounts[i] = account
            save_sender_accounts(accounts)
            return


def delete_sender_account(account_id: str) -> None:
    """Remove a sender account from the pool."""
    accounts = [a for a in get_sender_accounts() if a.id != account_id]
    save_sender_accounts(accounts)


def record_account_send(account_email: str) -> None:
    """Increment sent counter for an account."""
    accounts = get_sender_accounts()
    today_str = date.today().isoformat()
    for a in accounts:
        if a.email.lower() == account_email.strip().lower():
            if a.last_sent_date != today_str:
                a.sent_today = 1
                a.last_sent_date = today_str
            else:
                a.sent_today += 1
            save_sender_accounts(accounts)
            return


def get_active_pool(rotation_mode: str = "pairs") -> list[SenderAccount]:
    """Return enabled accounts that have remaining daily quota."""
    all_accounts = get_sender_accounts()
    if rotation_mode == "none":
        enabled = [a for a in all_accounts if a.is_enabled]
        return enabled[:1] if enabled else []

    return [a for a in all_accounts if a.can_send()]


def test_smtp_account(
    account: SenderAccount,
    host: str = "smtp.gmail.com",
    port: int = 587,
    use_ssl: bool = False,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """Test connecting and authenticating with a specific account."""
    if not account.email or not account.password:
        return False, "Email and password cannot be empty."

    ctx = ssl.create_default_context()
    try:
        if use_ssl or port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=timeout)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()

        server.login(account.email.strip(), account.password)
        try:
            server.quit()
        except Exception:
            pass
        return True, "Authentication successful."

    except smtplib.SMTPAuthenticationError as e:
        return False, f"Authentication failed: {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

# 1.5.0
