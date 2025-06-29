import asyncio
import json
import pandas as pd
from pathlib import Path
from tqdm.asyncio import tqdm_asyncio
from typing import Any, List, Dict, Optional
from httpx import AsyncClient
from dataset.utils import _fetch_url
from dataset.type_chart import calculate_type_defenses, calculate_type_offenses
from collections import defaultdict


def _clean_flavor_text(text: str) -> str:
    return text.replace("\n", " ").replace("\x0c", " ").strip()


def _process_pokedex_entries(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    processed = {}
    seen_versions = set()
    for entry in reversed(entries):
        if entry["language"]["name"] == "en":
            version_name = entry["version"]["name"]
            if version_name not in seen_versions:
                pretty_version_name = version_name.replace("-", " ").title()
                processed[pretty_version_name] = _clean_flavor_text(
                    entry["flavor_text"]
                )
                seen_versions.add(version_name)
    return processed


def _process_evolution_chain(chain_link: Dict[str, Any]) -> List[Dict[str, Any]]:
    paths = []
    from_species = chain_link["species"]["name"]

    for evolution in chain_link.get("evolves_to", []):
        to_species = evolution["species"]["name"]
        details_list = evolution.get("evolution_details", [])

        if not details_list:
            paths.append(
                {
                    "from_pokemon": from_species.lower(),
                    "to_pokemon": to_species.lower(),
                    "condition": "unknown",
                }
            )
            continue

        details = details_list[0]
        trigger = details.get("trigger", {}).get("name", "unknown").replace("-", " ")
        conditions = []

        if trigger == "level up":
            if "min_level" in details and details["min_level"] is not None:
                conditions.append(f"at level {details['min_level']}")
            if details.get("min_happiness"):
                conditions.append("with high friendship")
            if details.get("time_of_day"):
                conditions.append(f"during the {details['time_of_day']}")
            if not conditions:
                conditions.append("by leveling up")
        elif trigger == "use item":
            item = details.get("item", {})
            if item and item.get("name"):
                conditions.append(f"using a '{item['name']}'")
        elif trigger == "trade":
            cond = "by trading"
            held_item = details.get("held_item", {})
            if held_item and held_item.get("name"):
                cond += f" while holding a '{held_item['name']}'"
            conditions.append(cond)
        else:
            conditions.append(f"by a special method: '{trigger}'")

        paths.append(
            {
                "from_pokemon": from_species.lower(),
                "to_pokemon": to_species.lower(),
                "condition": " and ".join(conditions),
            }
        )

        paths.extend(_process_evolution_chain(evolution))

    return paths


def _process_moves(
    moves_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    version_group_moves = defaultdict(
        lambda: {
            "level_up": defaultdict(list),
            "machine": set(),
            "tutor": set(),
            "egg": set(),
        }
    )

    for move_entry in moves_data:
        move_name = move_entry["move"]["name"].replace("-", " ").title()

        for vgd in move_entry["version_group_details"]:
            vg_name = vgd["version_group"]["name"]
            method = vgd["move_learn_method"]["name"]
            level = vgd["level_learned_at"]

            if method == "level-up" and level > 0:
                version_group_moves[vg_name]["level_up"][str(level)].append(move_name)
            elif method in version_group_moves[vg_name]:
                version_group_moves[vg_name][method].add(move_name)

    final_result = {}
    for vg, methods in version_group_moves.items():
        final_moves = {}

        if methods["level_up"]:
            final_moves["level_up"] = {
                lvl: sorted(set(moves))
                for lvl, moves in sorted(
                    methods["level_up"].items(), key=lambda x: int(x[0])
                )
            }

        for method in ["machine", "tutor", "egg"]:
            if methods[method]:
                final_moves[method] = sorted(methods[method])

        final_result[vg] = final_moves

    return final_result


def _process_encounters(
    encounter_data: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    game_to_locations = defaultdict(set)

    for encounter in encounter_data:
        location_name = encounter["location_area"]["name"].replace("-", " ").title()
        for version_detail in encounter["version_details"]:
            game_version = version_detail["version"]["name"]
            game_to_locations[game_version].add(location_name)

    return {game: sorted(locations) for game, locations in game_to_locations.items()}


def derive_speed_tier(speed: int) -> str:
    return "fast" if speed >= 100 else "medium" if speed >= 70 else "slow"


def derive_roles(stats: Dict[str, Any]) -> List[str]:
    bs = stats["base_stats"]
    atk, defn, spatk, spdef, speed, hp = (
        bs["attack"],
        bs["defense"],
        bs["special-attack"],
        bs["special-defense"],
        bs["speed"],
        bs["hp"],
    )

    roles = []

    if defn >= 100 and hp >= 85:
        roles.append("Physical Wall")
    if spdef >= 100 and hp >= 85:
        roles.append("Special Wall")
    if speed >= 100 and atk >= 100:
        roles.append("Fast Physical Sweeper")
    if speed >= 100 and spatk >= 100:
        roles.append("Fast Special Sweeper")
    if atk >= 110 and hp >= 80 and defn >= 80:
        roles.append("Bulky Physical Attacker")
    if spatk >= 110 and hp >= 80 and spdef >= 80:
        roles.append("Bulky Special Attacker")
    if speed >= 90 and (atk >= 95 or spatk >= 95):
        roles.append("Offensive Pivot")
    if hp >= 80 and defn >= 80 and spdef >= 80 and speed >= 60:
        roles.append("Defensive Pivot")

    return sorted(set(roles))


async def _get_pokemon_profile(
    client: AsyncClient,
    name: str,
) -> dict[str, Any]:
    name = name.lower()

    pokemon = await _fetch_url(client, f"https://pokeapi.co/api/v2/pokemon/{name}")
    base_species_name = pokemon["species"]["name"]
    species = await _fetch_url(
        client, f"https://pokeapi.co/api/v2/pokemon-species/{base_species_name}"
    )
    evo_chain_url = species.get("evolution_chain", {}).get("url")
    evo_chain = (
        await _fetch_url(client, evo_chain_url) if evo_chain_url else {"chain": {}}
    )
    encounters = await _fetch_url(client, pokemon["location_area_encounters"])

    types = [
        t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])
    ]

    profile = {
        "summary": {
            "identity": {
                "id": pokemon["id"],
                "name": pokemon["name"].lower(),
                "genus": [
                    g["genus"]
                    for g in species["genera"]
                    if g["language"]["name"] == "en"
                ],
                "types": types,
                "is_legendary": species["is_legendary"],
                "is_mythical": species["is_mythical"],
                "is_baby": species["is_baby"],
            },
            "physical_characteristics": {
                "height_m": pokemon["height"] / 10.0,
                "weight_kg": pokemon["weight"] / 10.0,
                "color": species["color"]["name"],
                "shape": species["shape"]["name"],
            },
        },
        "battle_profile": {
            "battle_stats": {
                "base_stats": {
                    s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]
                },
                "type_defenses": calculate_type_defenses(types),
                "type_offenses": calculate_type_offenses(types),
                "abilities": [
                    a["ability"]["name"] + (" (hidden)" if a["is_hidden"] else "")
                    for a in pokemon["abilities"]
                ],
            },
            "training_and_breeding": {
                "base_experience": pokemon["base_experience"],
                "capture_rate": species["capture_rate"],
                "growth_rate": species["growth_rate"]["name"],
                "egg_groups": [g["name"] for g in species["egg_groups"]],
                "gender_rate_female": (
                    f"{(species['gender_rate'] / 8.0):.1%}"
                    if species["gender_rate"] != -1
                    else "Genderless"
                ),
            },
            "evolution": {
                "evolves_from": (
                    species["evolves_from_species"]["name"]
                    if species["evolves_from_species"]
                    else None
                ),
                "paths": _process_evolution_chain(evo_chain["chain"]),
            },
        },
        "moves": _process_moves(pokemon["moves"]),
        "ecology": {
            "habitat": species["habitat"]["name"] if species["habitat"] else "Unknown",
            "encounter_locations": _process_encounters(encounters),
        },
        "lore": {
            "pokedex_entries": _process_pokedex_entries(species["flavor_text_entries"]),
        },
    }

    profile["battle_profile"]["battle_stats"]["roles"] = derive_roles(
        profile["battle_profile"]["battle_stats"]
    )
    profile["battle_profile"]["battle_stats"]["speed_tier"] = derive_speed_tier(
        profile["battle_profile"]["battle_stats"]["base_stats"]["speed"]
    )

    return profile


async def get_all_pokemon(client: AsyncClient):
    url = "https://pokeapi.co/api/v2/pokemon?limit=2000"
    data = await _fetch_url(client, url)
    return [entry["name"] for entry in data["results"]]


async def fetch_pokemon_profiles(
    json_path="resources/pokemon.json", max_concurrency=20
):
    if Path(json_path).exists():
        return

    async with AsyncClient(timeout=30.0) as client:
        names = await get_all_pokemon(client)
        print(f"Fetching {len(names)} Pokémon profiles...")

        semaphore = asyncio.Semaphore(max_concurrency)
        profiles = {}

        async def fetch(name: str):
            async with semaphore:
                profile = await _get_pokemon_profile(client, name)
                return name, profile

        tasks = [fetch(name) for name in names]
        for name, profile in await tqdm_asyncio.gather(*tasks):
            if profile is not None:
                profiles[name] = profile

        with open(json_path, "w") as f:
            json.dump(profiles, f, indent=2)

        print(f"Saved {len(profiles)} profiles to {json_path}")


def build_parquet_dataset(
    json_path="resources/pokemon.json", output_path="resources/pokemon.parquet"
):
    with open(json_path, "r") as f:
        data = json.load(f)

    rows = []
    for name, profile in data.items():
        try:
            summary = profile.get("summary", {})
            battle_stats = profile.get("battle_profile", {}).get("battle_stats", {})
            identity = summary.get("identity", {})
            physical = summary.get("physical_characteristics", {})
            ecology = profile.get("ecology", {})

            rows.append(
                {
                    "name": identity.get("name"),
                    "types": identity.get("types", []),
                    "roles": battle_stats.get("roles", []),
                    "speed_tier": battle_stats.get("speed_tier"),
                    "is_legendary": identity.get("is_legendary"),
                    "is_mythical": identity.get("is_mythical"),
                    "is_baby": identity.get("is_baby"),
                    "color": physical.get("color"),
                    "habitat": ecology.get("habitat"),
                    "shape": physical.get("shape"),
                    "full_profile": profile,
                }
            )
        except Exception as e:
            print(f"Error processing {name}: {e}")

    df = pd.DataFrame(rows)
    df.set_index("name", inplace=True)
    df.to_parquet(output_path, engine="pyarrow", index=True)
    print(f"Saved dataset to {output_path}")
