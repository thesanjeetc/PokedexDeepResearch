import asyncio
import json
from typing import Dict, List, Optional
from httpx import AsyncClient
from tools.utils import _fetch_url, BASE_URL


async def fetch_type_list(client: AsyncClient) -> List[str]:
    data = await _fetch_url(client, f"{BASE_URL}/type/")
    return [
        entry["name"]
        for entry in data["results"]
        if int(entry["url"].rstrip("/").split("/")[-1]) <= 18
    ]


async def fetch_type_effectiveness(
    client: AsyncClient, type_id: int, all_types: List[str]
) -> Optional[Dict[str, Dict[str, float]]]:
    data = await _fetch_url(client, f"{BASE_URL}/type/{type_id}")

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

        with open("data/type_chart.json", "w", encoding="utf-8") as f:
            json.dump(chart, f, indent=2, ensure_ascii=False)
        return chart
