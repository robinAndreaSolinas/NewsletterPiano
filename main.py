import logging
from config import keys
import piano_api
import db

session = db.get_session('sqlite:///db.sqlite3')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    for value in keys:
        site_id, name, key = value.values()
        esp = piano_api.PianoESP(key, site_id, name)
        print(esp)
        print(esp.get_all_campaign())

if __name__ == "__main__":
    main()