"""ToolsetHub loader for SDC Agents SMB.

Discovers, validates, and loads toolset plugins. Each toolset declares
its security scope in a manifest (sdc-toolset.json or MANIFEST class
attribute). The loader enforces scope at load time — toolsets that
violate declarations are rejected.

Discovery sources (in order):
1. Built-in toolsets in sdc_agents.toolsets package
2. Python entry points in the 'sdc_agents.toolsets' group (future)
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Optional

from sdc_agents.common.config import SDCAgentsConfig

logger = logging.getLogger("sdc_agents.toolset_loader")

# Built-in SMB toolset registry — toolsets shipped with the package
_BUILTIN_TOOLSETS: dict[str, dict] = {
    "sdc-toolset-notion": {
        "name": "sdc-toolset-notion",
        "version": "0.1.0",
        "description": "Notion database introspection for SDC Agents SMB",
        "author": "Axius SDC, Inc.",
        "module": "sdc_agents.toolsets.notion_introspect",
        "toolset_class": "NotionIntrospectToolset",
        "security": {
            "network_access": True,
            "network_hosts": ["api.notion.com"],
            "datasource_types": ["notion"],
            "file_write": False,
            "audit_compliant": True,
        },
        "tools": [
            {"name": "introspect_notion", "description": "Introspect a Notion database"}
        ],
        "dependencies": ["notion-client>=2.2"],
        "install_extra": "notion",
    },
    "sdc-toolset-sheets": {
        "name": "sdc-toolset-sheets",
        "version": "0.1.0",
        "description": "Google Sheets introspection for SDC Agents SMB",
        "author": "Axius SDC, Inc.",
        "module": "sdc_agents.toolsets.sheets_introspect",
        "toolset_class": "SheetsIntrospectToolset",
        "security": {
            "network_access": True,
            "network_hosts": ["sheets.googleapis.com"],
            "datasource_types": ["sheets"],
            "file_write": False,
            "audit_compliant": True,
        },
        "tools": [
            {"name": "introspect_sheets", "description": "Introspect a Google Sheets spreadsheet"}
        ],
        "dependencies": ["google-api-python-client>=2.0", "google-auth>=2.0"],
        "install_extra": "sheets",
    },
    "sdc-toolset-airtable": {
        "name": "sdc-toolset-airtable",
        "version": "0.1.0",
        "description": "Airtable base introspection for SDC Agents SMB",
        "author": "Axius SDC, Inc.",
        "module": "sdc_agents.toolsets.airtable_introspect",
        "toolset_class": "AirtableIntrospectToolset",
        "security": {
            "network_access": True,
            "network_hosts": ["api.airtable.com"],
            "datasource_types": ["airtable"],
            "file_write": False,
            "audit_compliant": True,
        },
        "tools": [
            {"name": "introspect_airtable", "description": "Introspect an Airtable base table"}
        ],
        "dependencies": ["pyairtable>=2.3"],
        "install_extra": "airtable",
    },
}

_REQUIRED_MANIFEST_FIELDS = {"name", "module", "toolset_class", "security"}
_REQUIRED_SECURITY_FIELDS = {"network_access", "datasource_types", "file_write", "audit_compliant"}


class ToolsetLoader:
    """Discovers, validates, and loads ToolsetHub toolsets."""

    def __init__(self, config: SDCAgentsConfig):
        self._config = config

    def discover_installed(self) -> list[dict]:
        """Discover all available toolsets and their availability status.

        Returns:
            List of manifest dicts with added 'available' and 'status' fields.
            'available' is True if the toolset's dependencies are installed.
        """
        results = []

        for name, manifest in _BUILTIN_TOOLSETS.items():
            entry = {**manifest}
            try:
                mod = importlib.import_module(manifest["module"])
                cls = getattr(mod, manifest["toolset_class"])
                entry["available"] = True
                entry["status"] = "installed"
            except (ImportError, AttributeError):
                entry["available"] = False
                extra = manifest.get("install_extra", name)
                entry["status"] = f"not installed (pip install sdc-agents-smb[{extra}])"

            results.append(entry)

        return results

    def validate_manifest(self, manifest: dict) -> dict:
        """Validate a toolset manifest.

        Args:
            manifest: Manifest dict to validate.

        Returns:
            Dict with 'valid' (bool) and 'errors' (list of strings).
        """
        errors = []

        # Check required fields
        missing = _REQUIRED_MANIFEST_FIELDS - set(manifest.keys())
        if missing:
            errors.append(f"Missing required fields: {missing}")

        # Check security section
        security = manifest.get("security", {})
        if security:
            missing_sec = _REQUIRED_SECURITY_FIELDS - set(security.keys())
            if missing_sec:
                errors.append(f"Missing security fields: {missing_sec}")

            # Validate network_hosts if network_access is True
            if security.get("network_access") and not security.get("network_hosts"):
                errors.append(
                    "network_access is True but network_hosts is empty — "
                    "must declare which hosts the toolset contacts"
                )

        return {"valid": len(errors) == 0, "errors": errors}

    def load_toolset(self, manifest: dict):
        """Load and instantiate a toolset from its manifest.

        Args:
            manifest: Validated manifest dict.

        Returns:
            Instantiated BaseToolset subclass.

        Raises:
            ImportError: If toolset dependencies are not installed.
            ValueError: If manifest is invalid.
        """
        validation = self.validate_manifest(manifest)
        if not validation["valid"]:
            raise ValueError(
                f"Invalid manifest for '{manifest.get('name', '?')}': "
                f"{'; '.join(validation['errors'])}"
            )

        try:
            mod = importlib.import_module(manifest["module"])
        except ImportError:
            extra = manifest.get("install_extra", manifest["name"])
            raise ImportError(
                f"Dependencies for '{manifest['name']}' not installed. "
                f"Install with: pip install sdc-agents-smb[{extra}]"
            )

        cls = getattr(mod, manifest["toolset_class"])
        return cls(config=self._config)

    def load_available_toolsets(self) -> list:
        """Load all available (installed) toolsets.

        Returns:
            List of instantiated BaseToolset instances for toolsets
            whose dependencies are installed.
        """
        toolsets = []
        for manifest in self.discover_installed():
            if manifest.get("available"):
                try:
                    ts = self.load_toolset(manifest)
                    toolsets.append(ts)
                    logger.debug("Loaded toolset: %s", manifest["name"])
                except Exception as exc:
                    logger.warning("Failed to load toolset %s: %s", manifest["name"], exc)
        return toolsets
