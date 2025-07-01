import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
from httpx import AsyncClient
from functools import lru_cache
from dataset.utils import fetch_url, BASE_URL


async def fetch_type_list(client: AsyncClient) -> List[str]:
    data = await fetch_url(client, f"{BASE_URL}/type/")
    return [
        entry["name"]
        for entry in data["results"]
        if int(entry["url"].rstrip("/").split("/")[-1]) <= 18
    ]


async def fetch_type_effectiveness(
    client: AsyncClient, type_id: int, all_types: List[str]
) -> Optional[Dict[str, Dict[str, float]]]:
    data = await fetch_url(client, f"{BASE_URL}/type/{type_id}")

    type_name = data["name"]
    default = {t: 1.0 for t in all_types}
    offense = default.copy()
    defense = default.copy()

    for rel in data["damage_relations"]["double_damage_to"]:
        offense[rel["name"]] = 2.0
    for rel in data["damage_relations"]["half_damage_to"]:
        offense[rel["name"]] = 0.5
    for rel in data["damage_relations"]["no_damage_to"]:
        offense[rel["name"]] = 0.0

    for rel in data["damage_relations"]["double_damage_from"]:
        defense[rel["name"]] = 2.0
    for rel in data["damage_relations"]["half_damage_from"]:
        defense[rel["name"]] = 0.5
    for rel in data["damage_relations"]["no_damage_from"]:
        defense[rel["name"]] = 0.0

    return {type_name: {"offense": offense, "defense": defense}}


async def build_type_chart() -> Dict[str, Dict[str, Dict[str, float]]]:
    async with AsyncClient() as client:
        type_names = await fetch_type_list(client)
        results = await asyncio.gather(
            *[fetch_type_effectiveness(client, i, type_names) for i in range(1, 19)]
        )

        chart = {}
        for entry in results:
            chart.update(entry)

        with open(TYPE_CHART_PATH, "w", encoding="utf-8") as f:
            json.dump(chart, f, indent=2, ensure_ascii=False)
        return chart


TYPE_CHART_PATH = Path("resources/type_chart.json")


@lru_cache(maxsize=1)
def fetch_type_chart():
    with TYPE_CHART_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def calculate_type_defenses(pokemon_types: list[str]) -> dict:
    type_chart = fetch_type_chart()
    attack_types = set(type_chart.keys())
    combined_multipliers = {t: 1.0 for t in attack_types}

    for p_type in pokemon_types:
        type_defenses = type_chart[p_type]["defense"]
        for attack_type, multiplier in type_defenses.items():
            combined_multipliers[attack_type] *= multiplier

    defenses = {
        "immune_to": [],
        "resists_4x": [],
        "resists_2x": [],
        "weak_to_2x": [],
        "weak_to_4x": [],
    }

    for attack_type, multiplier in combined_multipliers.items():
        if multiplier == 0:
            defenses["immune_to"].append(attack_type)
        elif multiplier == 0.25:
            defenses["resists_4x"].append(attack_type)
        elif multiplier == 0.5:
            defenses["resists_2x"].append(attack_type)
        elif multiplier == 2.0:
            defenses["weak_to_2x"].append(attack_type)
        elif multiplier == 4.0:
            defenses["weak_to_4x"].append(attack_type)

    return defenses


def calculate_type_offenses(pokemon_types: list[str]) -> dict:
    type_chart = fetch_type_chart()
    super_effective = set()
    not_very_effective = set()
    no_effect = set()

    for p_type in pokemon_types:
        offense_profile = type_chart[p_type]["offense"]

        for defending_type, multiplier in offense_profile.items():
            if multiplier == 2.0:
                super_effective.add(defending_type)
            elif multiplier == 0.5:
                not_very_effective.add(defending_type)
            elif multiplier == 0.0:
                no_effect.add(defending_type)

    return {
        "super_effective_against": sorted(list(super_effective)),
        "not_very_effective_against": sorted(list(not_very_effective)),
        "no_effect_against": sorted(list(no_effect)),
    }
