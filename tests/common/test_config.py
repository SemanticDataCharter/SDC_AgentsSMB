"""Tests for configuration loading and validation (SMB)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdc_agents.common.config import SDCAgentsConfig, load_config


def test_load_sample_config(sample_config_path: Path):
    """Sample config loads and validates successfully."""
    config = load_config(sample_config_path)
    assert isinstance(config, SDCAgentsConfig)
    assert config.sdcstudio.base_url == "https://sdcstudio.test.local"
    assert config.cache.root == ".test-cache"
    assert config.cache.ttl_hours == 1
    assert config.audit.log_level == "verbose"


def test_datasources_parsed(sample_config_path: Path):
    """Datasource entries are parsed correctly."""
    config = load_config(sample_config_path)
    assert "test_db" in config.datasources
    assert config.datasources["test_db"].type == "sql"
    assert "test_csv" in config.datasources
    assert config.datasources["test_csv"].type == "csv"


def test_env_var_substitution(tmp_path: Path):
    """${VAR} placeholders are substituted from environment."""
    config_file = tmp_path / "test.yaml"
    config_file.write_text('sdcstudio:\n  base_url: "https://${TEST_SDC_HOST}"\n')
    os.environ["TEST_SDC_HOST"] = "my-server.example.com"
    try:
        config = load_config(config_file)
        assert config.sdcstudio.base_url == "https://my-server.example.com"
    finally:
        del os.environ["TEST_SDC_HOST"]


def test_missing_env_var_raises(tmp_path: Path):
    """Missing environment variable causes KeyError (fail closed)."""
    config_file = tmp_path / "test.yaml"
    config_file.write_text('sdcstudio:\n  base_url: "${NONEXISTENT_SDC_VAR}"\n')
    # Ensure it's not set
    os.environ.pop("NONEXISTENT_SDC_VAR", None)
    with pytest.raises(KeyError, match="NONEXISTENT_SDC_VAR"):
        load_config(config_file)


def test_defaults_applied():
    """Default config values are set when YAML has empty sections."""
    config = SDCAgentsConfig()
    assert config.cache.ttl_hours == 24
    assert config.audit.log_level == "standard"
    assert config.output.directory == "./output"


def test_default_base_url_is_production():
    """SMB ships pointed at the production SDCStudio endpoint by default.

    Regression guard for the placeholder URL bug fixed in PR #1.
    """
    config = SDCAgentsConfig()
    assert config.sdcstudio.base_url == "https://sdcstudio.axius-sdc.com"
    assert "example.com" not in config.sdcstudio.base_url


def test_sdcstudio_api_key():
    """SDCStudio config supports optional api_key."""
    config = SDCAgentsConfig(sdcstudio={"base_url": "https://test.local", "api_key": "my-token"})
    assert config.sdcstudio.api_key == "my-token"


def test_sdcstudio_api_key_default_none():
    """api_key defaults to None."""
    config = SDCAgentsConfig()
    assert config.sdcstudio.api_key is None


def test_datasource_json_fields():
    """JSON datasource fields are parsed correctly."""
    config = SDCAgentsConfig(
        datasources={
            "records": {
                "type": "json",
                "path": "/data/records.json",
                "jsonpath": "$.results[*]",
            }
        }
    )
    ds = config.datasources["records"]
    assert ds.type == "json"
    assert ds.path == "/data/records.json"
    assert ds.jsonpath == "$.results[*]"


def test_datasource_mongodb_fields():
    """MongoDB datasource fields are parsed correctly."""
    config = SDCAgentsConfig(
        datasources={
            "clinical": {
                "type": "mongodb",
                "connection_string": "mongodb://localhost:27017",
                "database": "clinical",
                "collection": "lab_results",
            }
        }
    )
    ds = config.datasources["clinical"]
    assert ds.type == "mongodb"
    assert ds.database == "clinical"
    assert ds.collection == "lab_results"


# --- SMB-specific: local-inference ModelConfig ---


def test_model_config_defaults():
    """SMB defaults the model layer to local Ollama inference."""
    config = SDCAgentsConfig()
    assert config.model.default == "ollama_chat/gemma4:26b"
    assert config.model.ollama_base_url == "http://localhost:11434"


def test_model_config_override():
    """Model config accepts an override default + ollama base URL."""
    config = SDCAgentsConfig(
        model={"default": "ollama_chat/llama3:8b", "ollama_base_url": "http://gpu.local:11434"}
    )
    assert config.model.default == "ollama_chat/llama3:8b"
    assert config.model.ollama_base_url == "http://gpu.local:11434"


# --- SMB-specific: AssemblyConfig (HITL review) ---


def test_assembly_config_defaults():
    """Assembly defaults to human review before publish."""
    config = SDCAgentsConfig()
    assert config.assembly.review_before_publish is True
    assert config.assembly.poll_timeout_seconds == 60
    assert config.assembly.poll_interval_seconds == 5


# --- SMB-specific: connector datasource types ---


def test_datasource_notion_fields():
    """Notion datasource fields are parsed correctly."""
    config = SDCAgentsConfig(
        datasources={
            "crm": {
                "type": "notion",
                "notion_token": "secret_abc",
                "notion_database_id": "db123",
            }
        }
    )
    ds = config.datasources["crm"]
    assert ds.type == "notion"
    assert ds.notion_token == "secret_abc"
    assert ds.notion_database_id == "db123"


def test_datasource_sheets_fields():
    """Google Sheets datasource fields are parsed correctly."""
    config = SDCAgentsConfig(
        datasources={
            "intake": {
                "type": "sheets",
                "sheets_credentials": "/secrets/sa.json",
                "spreadsheet_id": "1AbC",
                "sheet_name": "Responses",
            }
        }
    )
    ds = config.datasources["intake"]
    assert ds.type == "sheets"
    assert ds.spreadsheet_id == "1AbC"
    assert ds.sheet_name == "Responses"


def test_datasource_airtable_fields():
    """Airtable datasource fields are parsed correctly."""
    config = SDCAgentsConfig(
        datasources={
            "catalog": {
                "type": "airtable",
                "airtable_token": "key123",
                "airtable_base_id": "appXYZ",
                "airtable_table": "Items",
            }
        }
    )
    ds = config.datasources["catalog"]
    assert ds.type == "airtable"
    assert ds.airtable_base_id == "appXYZ"
    assert ds.airtable_table == "Items"


# --- Destination config tests ---


def test_destinations_default_empty():
    """Destinations default to empty dict."""
    config = SDCAgentsConfig()
    assert config.destinations == {}


def test_destination_fuseki_config():
    """Fuseki destination config is parsed correctly."""
    config = SDCAgentsConfig(
        destinations={
            "triplestore": {
                "type": "fuseki",
                "endpoint": "http://localhost:3030/sdc4/data",
                "auth": "Basic dXNlcjpwYXNz",
                "upload_method": "named_graph",
            }
        }
    )
    dest = config.destinations["triplestore"]
    assert dest.type == "fuseki"
    assert dest.endpoint == "http://localhost:3030/sdc4/data"
    assert dest.upload_method == "named_graph"


def test_destination_filesystem_config():
    """Filesystem destination config is parsed correctly."""
    config = SDCAgentsConfig(
        destinations={
            "archive": {
                "type": "filesystem",
                "path": "./archive/{ct_id}/{instance_id}/",
                "create_directories": True,
            }
        }
    )
    dest = config.destinations["archive"]
    assert dest.type == "filesystem"
    assert dest.path == "./archive/{ct_id}/{instance_id}/"
    assert dest.create_directories is True
