import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "outer_template.pdf")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "outer_field_mapping.json")

def load_field_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return []
