import logging
from pathlib import Path
import json
from lib.PianoESP import ClientESP

logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s %(levelname)s:%(name)s - %(message)s')

def get_api_key(path):
    with open(Path(__file__).parent / "data" / path, "r") as f:
        return json.loads(f.read())


PIANO_API_KEYS = get_api_key("publisher_keys.json").get("items")


def get_stats(client: ClientESP, date_start: str, date_end: str = None):
    fields = {}

    for campaign in client.get_all_campaigns():
        if campaign.schedule_type == "regular":
            stats = campaign.get_stats(date_start, date_end)
            fields.update(stats)

    return fields


if __name__ == '__main__':
    key = PIANO_API_KEYS[0]
    client = ClientESP(key.get("id"), key.get("api_key"))
    # print(list(get_stats(client, "2026-04-25")))
    client.call_api("pippo", "GET", params={"pippo": "pluto"})