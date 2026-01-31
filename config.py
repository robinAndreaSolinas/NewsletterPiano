import json

def get_keys(file:str):
    try:
        with open(file) as f:
            keys = json.loads(f.read())
            return keys.get('items', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

keys = get_keys('keys.json')

__all__ = ['get_keys', keys]