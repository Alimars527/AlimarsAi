from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / 'config'


def load_yaml(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_settings():
    return load_yaml(CONFIG_DIR / 'settings.yaml')


def load_holdings():
    return load_yaml(CONFIG_DIR / 'holdings.yaml')


def save_holdings(data):
    save_yaml(CONFIG_DIR / 'holdings.yaml', data)


def load_strategy():
    return load_yaml(CONFIG_DIR / 'strategy.yaml')


def load_preferences():
    return load_yaml(CONFIG_DIR / 'preferences.yaml')
