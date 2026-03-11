# analyzer_settings.py
import os
import json
import logging

LOG = logging.getLogger("Settings")

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "analyzer_settings.json")

def load_settings() -> dict:
    """Carrega analyzer_settings.json (ou retorna dict vazio)."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        LOG.exception(f"Falha ao carregar settings: {e}")
        return {}

def save_settings(data: dict):
    """Persiste settings em analyzer_settings.json (cria/overwrite)."""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        LOG.exception(f"Falha ao salvar settings: {e}")
