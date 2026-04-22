import re


def camel_to_snake(string: str) -> str:
    return re.sub(r'(?<![_])(?<!^)(?=[A-Z])(?!_)', '_', string).lower()
