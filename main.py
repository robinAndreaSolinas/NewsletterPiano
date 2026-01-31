from config import keys
import piano_api


if __name__ == "__main__":
    for value in keys:
        id, name, key = value.values()
        esp = piano_api.PianoESP(key, id, name)
        print(esp)
        print(esp.get_all_campaign())