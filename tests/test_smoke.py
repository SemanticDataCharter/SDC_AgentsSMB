"""Smoke tests for sdc_agents package importability and key invariants."""

from __future__ import annotations

import sdc_agents
from sdc_agents.common.config import (
    AuditConfig,
    CacheConfig,
    SDCAgentsConfig,
    SDCStudioConfig,
)


def test_package_importable():
    """The sdc_agents package imports without error."""
    assert sdc_agents is not None


def test_default_config_constructs():
    """SDCAgentsConfig with all defaults validates."""
    config = SDCAgentsConfig()
    assert config.sdcstudio is not None
    assert config.cache is not None
    assert config.audit is not None


def test_default_sdcstudio_base_url_is_production():
    """Default base_url must point at the production endpoint.

    Regression guard for the placeholder URL bug fixed in PR #1.
    """
    config = SDCStudioConfig()
    assert config.base_url == "https://sdcstudio.axius-sdc.com"
    assert "example.com" not in config.base_url


def test_default_cache_root():
    """CacheConfig defaults to a relative .sdc-cache directory."""
    config = CacheConfig()
    assert config.root == ".sdc-cache"


def test_default_audit_path():
    """AuditConfig defaults to .sdc-cache/audit.jsonl."""
    config = AuditConfig()
    assert config.path == ".sdc-cache/audit.jsonl"
