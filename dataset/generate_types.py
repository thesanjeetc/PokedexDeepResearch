import requests
from pathlib import Path

BASE_URL = "https://pokeapi.co/api/v2"
OUTPUT_FILE = Path("resources/enums.py")

ENDPOINTS = {
    "type": "PokemonType",
    "pokemon-habitat": "PokemonHabitat",
    "pokemon-shape": "PokemonShape",
    "pokemon-color": "PokemonColor",
    "version-group": "VersionGroup",
}


def fetch_enum_items(endpoint: str):
    response = requests.get(f"{BASE_URL}/{endpoint}/?limit=1000")
    response.raise_for_status()
    return [item["name"] for item in response.json()["results"]]


def format_enum_name(name: str) -> str:
    return name.upper().replace("-", "_")


def generate_enum_code(enum_name: str, values: list[str]) -> str:
    lines = [f"class {enum_name}(str, Enum):"]
    for val in values:
        label = format_enum_name(val)
        lines.append(f'    {label} = "{val}"')
    return "\n".join(lines)


def generate_enums():
    content = "from enum import Enum\n"
    for endpoint, enum_name in ENDPOINTS.items():
        values = fetch_enum_items(endpoint)
        content += "\n\n" + generate_enum_code(enum_name, values)
    OUTPUT_FILE.write_text(content)
