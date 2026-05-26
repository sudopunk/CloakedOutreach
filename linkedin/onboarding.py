# linkedin/onboarding.py
"""Onboarding: create Campaign + LinkedInProfile + LLM config in DB.

Two ways to supply config:
- OnboardConfig.from_json(path) — from a JSON file (non-interactive / cloud).
- collect_from_wizard()         — interactive questionary wizard (needs TTY).

Both return an OnboardConfig; ``apply()`` is the single write path.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from linkedin.conf import (
    DEFAULT_CONNECT_DAILY_LIMIT,
    DEFAULT_CONNECT_WEEKLY_LIMIT,
    DEFAULT_FOLLOW_UP_DAILY_LIMIT,
    ROOT_DIR,
)

DEFAULT_PRODUCT_DOCS = ROOT_DIR / "README.md"
DEFAULT_CAMPAIGN_OBJECTIVE = ROOT_DIR / "docs" / "default_campaign.md"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config dataclass (pure data — no I/O)
# ---------------------------------------------------------------------------

@dataclass
class OnboardConfig:
    """All values needed to onboard — filled interactively or from JSON."""

    linkedin_email: str = ""
    linkedin_password: str = ""
    campaign_name: str = ""
    product_description: str = ""
    campaign_objective: str = ""
    booking_link: str = ""
    seed_urls: str = ""
    llm_provider: str = "openai"
    llm_api_key: str = ""
    ai_model: str = ""
    llm_api_base: str = ""
    connect_daily_limit: int = DEFAULT_CONNECT_DAILY_LIMIT
    connect_weekly_limit: int = DEFAULT_CONNECT_WEEKLY_LIMIT
    follow_up_daily_limit: int = DEFAULT_FOLLOW_UP_DAILY_LIMIT
    legal_acceptance: bool = False

    @classmethod
    def from_json(cls, path: str) -> OnboardConfig:
        import json
        import dataclasses
        with open(path, "r") as f:
            data = json.load(f)
        fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# State inspection
# ---------------------------------------------------------------------------

_CAMPAIGN_KEYS = {
    "campaign_name", "product_description", "campaign_objective",
    "booking_link", "seed_urls",
}
_ACCOUNT_KEYS = {
    "linkedin_email", "linkedin_password",
    "connect_daily_limit", "connect_weekly_limit", "follow_up_daily_limit",
    "legal_acceptance",
}
_LLM_KEYS = {"llm_provider", "llm_api_key", "ai_model", "llm_api_base"}
_ALL_KEYS = _CAMPAIGN_KEYS | _ACCOUNT_KEYS | _LLM_KEYS


def missing_keys() -> set[str]:
    """Return onboarding field keys that still need values."""
    from linkedin.models import Campaign, LinkedInProfile, SiteConfig

    keys: set[str] = set()

    if not Campaign.objects.exists():
        keys |= _CAMPAIGN_KEYS

    if not LinkedInProfile.objects.filter(active=True).exists():
        keys |= _ACCOUNT_KEYS

    cfg = SiteConfig.load()
    if not cfg.llm_provider:
        keys.add("llm_provider")
    if not cfg.llm_api_key:
        keys.add("llm_api_key")
    if not cfg.ai_model:
        keys.add("ai_model")
    # llm_api_base is only required for the openai_compatible provider.
    if cfg.llm_provider == SiteConfig.LLMProvider.OPENAI_COMPATIBLE and not cfg.llm_api_base:
        keys.add("llm_api_base")

    return keys


# ---------------------------------------------------------------------------
# Interactive collection (needs TTY)
# ---------------------------------------------------------------------------

def _prompt_input(prompt_text: str, default: str = "", required: bool = True) -> str:
    default_str = f" [{default}]" if default else ""
    while True:
        try:
            val = input(f"? {prompt_text}{default_str}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding cancelled.")
            sys.exit(1)
        if not val and default:
            return default
        if not val and not required:
            return ""
        if not val and required:
            print("  This field is required.")
            continue
        return val


def _prompt_password(prompt_text: str, required: bool = True) -> str:
    import getpass
    while True:
        try:
            val = getpass.getpass(f"? {prompt_text}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding cancelled.")
            sys.exit(1)
        if not val and required:
            print("  This field is required.")
            continue
        return val


def _prompt_multiline(prompt_text: str, required: bool = True) -> str:
    print(f"? {prompt_text} (Enter empty line to finish):")
    lines = []
    while True:
        try:
            line = input()
            if not line:
                break
            lines.append(line)
        except (KeyboardInterrupt, EOFError):
            break
    val = "\n".join(lines).strip()
    if not val and required:
        print("  This field is required.")
        return _prompt_multiline(prompt_text, required)
    return val


def _prompt_confirm(prompt_text: str, default: bool = True) -> bool:
    default_str = " [Y/n]" if default else " [y/N]"
    while True:
        try:
            val = input(f"? {prompt_text}{default_str}: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding cancelled.")
            sys.exit(1)
        if not val:
            return default
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False
        print("  Please answer yes or no.")


def _prompt_integer(prompt_text: str, default: int = 0) -> int:
    while True:
        val_str = _prompt_input(prompt_text, default=str(default), required=False)
        if not val_str:
            return default
        try:
            return int(val_str)
        except ValueError:
            print("  Please enter a valid integer.")


def collect_from_wizard() -> OnboardConfig:
    """Run interactive cli wizard for missing fields; return an OnboardConfig.

    Raises SystemExit if the user cancels.
    """
    cfg = OnboardConfig()
    missing = missing_keys()
    if not missing:
        return cfg

    print("\n--- CloakedOutreach Onboarding Wizard ---\n")

    if "campaign_name" in missing:
        cfg.campaign_name = _prompt_input("Campaign name", default="LinkedIn Outreach")
    if "product_description" in missing:
        cfg.product_description = _prompt_multiline("Product/service description")
    if "campaign_objective" in missing:
        cfg.campaign_objective = _prompt_multiline("Campaign objective (e.g. 'sell analytics platform to CTOs')")
    if "booking_link" in missing:
        cfg.booking_link = _prompt_input("Booking link (e.g. https://cal.com/you)", required=False)
    if "seed_urls" in missing:
        cfg.seed_urls = _prompt_multiline("LinkedIn seed profile URLs (one per line, optional)", required=False)

    if "linkedin_email" in missing:
        cfg.linkedin_email = _prompt_input("LinkedIn email")
    if "linkedin_password" in missing:
        cfg.linkedin_password = _prompt_password("LinkedIn password")

    if "llm_provider" in missing:
        while True:
            prov = _prompt_input("LLM provider (choices: openai, anthropic, google, groq, mistral, cohere, openai_compatible)", default="openai")
            if prov in ("openai", "anthropic", "google", "groq", "mistral", "cohere", "openai_compatible"):
                cfg.llm_provider = prov
                break
            print("  Invalid provider.")
    if "llm_api_key" in missing:
        cfg.llm_api_key = _prompt_password("LLM API key (e.g. sk-...)")
    if "ai_model" in missing:
        cfg.ai_model = _prompt_input("AI model (e.g. gpt-4o, claude-3-5-sonnet-20241022)")
    if "llm_api_base" in missing:
        cfg.llm_api_base = _prompt_input("LLM API base URL (only for openai_compatible, optional)", required=False)

    if "connect_daily_limit" in missing:
        cfg.connect_daily_limit = _prompt_integer("Connection requests daily limit", default=DEFAULT_CONNECT_DAILY_LIMIT)
    if "connect_weekly_limit" in missing:
        cfg.connect_weekly_limit = _prompt_integer("Connection requests weekly limit", default=DEFAULT_CONNECT_WEEKLY_LIMIT)
    if "follow_up_daily_limit" in missing:
        cfg.follow_up_daily_limit = _prompt_integer("Follow-up messages daily limit", default=DEFAULT_FOLLOW_UP_DAILY_LIMIT)

    if "legal_acceptance" in missing:
        cfg.legal_acceptance = _prompt_confirm("Do you accept the Legal Notice? (https://github.com/sudopunk/CloakedOutreach/blob/main/LEGAL_NOTICE.md)", default=False)
        if not cfg.legal_acceptance:
            print("  You must accept the Legal Notice to proceed.")
            sys.exit(1)

    return cfg



# ---------------------------------------------------------------------------
# Record creation (pure DB, no I/O)
# ---------------------------------------------------------------------------

def _read_default_file(path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _create_campaign(name: str, product_docs: str, objective: str, booking_link: str = ""):
    """Create a Campaign record and return it."""
    from linkedin.models import Campaign

    campaign = Campaign.objects.create(
        name=name,
        product_docs=product_docs,
        campaign_objective=objective,
        booking_link=booking_link,
    )
    logger.info("Campaign '%s' created!", name)
    return campaign


def _create_account(
    campaign,
    email: str,
    password: str,
    *,
    connect_daily: int = DEFAULT_CONNECT_DAILY_LIMIT,
    connect_weekly: int = DEFAULT_CONNECT_WEEKLY_LIMIT,
    follow_up_daily: int = DEFAULT_FOLLOW_UP_DAILY_LIMIT,
):
    """Create a User + LinkedInProfile record and return the profile."""
    from django.contrib.auth.models import User
    from linkedin.models import LinkedInProfile

    handle = email.split("@")[0].lower().replace(".", "_").replace("+", "_")

    user, created = User.objects.get_or_create(
        username=handle,
        defaults={"is_staff": True, "is_active": True},
    )
    if created:
        user.set_unusable_password()
        user.save()

    campaign.users.add(user)

    profile = LinkedInProfile.objects.create(
        user=user,
        linkedin_username=email,
        linkedin_password=password,
        connect_daily_limit=connect_daily,
        connect_weekly_limit=connect_weekly,
        follow_up_daily_limit=follow_up_daily,
    )

    logger.info("Account '%s' created! (email=%s)", handle, email)
    return profile


def _create_seed_leads(campaign, seed_urls: str) -> None:
    """Parse seed URL text and create QUALIFIED leads."""
    if not seed_urls or not seed_urls.strip():
        return
    from linkedin.setup.seeds import parse_seed_urls, create_seed_leads

    public_ids = parse_seed_urls(seed_urls)
    if public_ids:
        created = create_seed_leads(campaign, public_ids)
        logger.info("%d seed profile(s) added as QUALIFIED.", created)


# ---------------------------------------------------------------------------
# Single write path
# ---------------------------------------------------------------------------

def apply(config: OnboardConfig) -> None:
    """Idempotent: create missing Campaign, Account, env vars, and legal acceptance."""
    from linkedin.management.setup_crm import DEFAULT_CAMPAIGN_NAME
    from linkedin.models import Campaign, LinkedInProfile

    # Campaign
    campaign = Campaign.objects.first()
    if campaign is None and config.campaign_name:
        campaign = _create_campaign(
            name=config.campaign_name or DEFAULT_CAMPAIGN_NAME,
            product_docs=config.product_description or _read_default_file(DEFAULT_PRODUCT_DOCS),
            objective=config.campaign_objective or _read_default_file(DEFAULT_CAMPAIGN_OBJECTIVE),
            booking_link=config.booking_link,
        )
        _create_seed_leads(campaign, config.seed_urls)

    # Account
    if (
        not LinkedInProfile.objects.filter(active=True).exists()
        and config.linkedin_email
    ):
        _create_account(
            campaign,
            config.linkedin_email,
            config.linkedin_password,
            connect_daily=config.connect_daily_limit,
            connect_weekly=config.connect_weekly_limit,
            follow_up_daily=config.follow_up_daily_limit,
        )

    # LLM config → DB
    from linkedin.models import SiteConfig
    cfg = SiteConfig.load()
    updated = False
    for field, val in [
        ("llm_provider", config.llm_provider),
        ("llm_api_key", config.llm_api_key),
        ("ai_model", config.ai_model),
        ("llm_api_base", config.llm_api_base),
    ]:
        if val:
            setattr(cfg, field, val)
            updated = True
    if updated:
        cfg.save()
        logger.info("LLM config saved to database.")

    # Legal
    if config.legal_acceptance:
        from linkedin.models import LinkedInProfile as LP
        LP.objects.filter(legal_accepted=False, active=True).update(legal_accepted=True)
