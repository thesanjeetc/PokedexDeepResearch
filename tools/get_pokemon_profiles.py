import asyncio
from typing import Any, List, Dict, Optional, Set
from httpx import AsyncClient
from pydantic_ai import ModelRetry
from tools.utils import pretty_print, _fetch_url, BASE_URL


def _clean_flavor_text(text: str) -> str:
    """Removes newlines and other special characters from flavor text."""
    return text.replace("\n", " ").replace("\x0c", " ").strip()


def _process_pokedex_entries(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extracts the English flavor text for each game version, prioritizing recent games."""
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
    """Recursively processes the raw evolution chain into a simple list of paths."""
    paths = []
    from_species = chain_link["species"]["name"]

    if not chain_link.get("evolves_to"):
        return []

    for evolution in chain_link["evolves_to"]:
        to_species = evolution["species"]["name"]
        details = evolution["evolution_details"][0]
        trigger = details["trigger"]["name"].replace("-", " ")

        conditions = []
        if trigger == "level up":
            if details.get("min_level"):
                conditions.append(f"at level {details['min_level']}")
            if details.get("min_happiness"):
                conditions.append("with high friendship")
            if details.get("time_of_day"):
                conditions.append(f"during the {details['time_of_day']}")
            if not conditions:
                conditions.append("by leveling up")
        elif trigger == "use item":
            conditions.append(f"using a '{details['item']['name']}'")
        elif trigger == "trade":
            condition = "by trading"
            if details.get("held_item"):
                condition += f" while holding a '{details['held_item']['name']}'"
            conditions.append(condition)
        else:
            conditions.append(f"by a special method: '{trigger}'")

        paths.append(
            {
                "from_pokemon": from_species.capitalize(),
                "to_pokemon": to_species.capitalize(),
                "condition": " and ".join(conditions),
            }
        )

        paths.extend(_process_evolution_chain(evolution))

    return paths


def _process_moves(
    moves_data: List[Dict[str, Any]], version_group_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Processes raw move data into a structured list, optionally filtered by version group."""
    processed_moves = []
    for move_entry in moves_data:
        filtered_vg_details = [
            vgd
            for vgd in move_entry["version_group_details"]
            if not version_group_filter
            or vgd["version_group"]["name"] == version_group_filter
        ]

        if not filtered_vg_details:
            continue

        grouped_methods: Dict[tuple, Set[str]] = {}
        for vgd in filtered_vg_details:
            method = vgd["move_learn_method"]["name"]
            level = vgd["level_learned_at"]
            key = (method, level)
            if key not in grouped_methods:
                grouped_methods[key] = set()
            grouped_methods[key].add(
                vgd["version_group"]["name"].replace("-", " ").title()
            )

        learn_methods_list = []
        for (method, level), versions in grouped_methods.items():
            learn_methods_list.append(
                {
                    "method": method.replace("-", " "),
                    "level": level if method == "level-up" else None,
                    "games": sorted(list(versions)),
                }
            )

        processed_moves.append(
            {
                "name": move_entry["move"]["name"].replace("-", " ").title(),
                "learn_methods": learn_methods_list,
            }
        )

    return sorted(processed_moves, key=lambda x: x["name"])


def _process_encounters(
    encounter_data: List[Dict[str, Any]], game_version_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Processes raw encounter data, optionally filtered by game version."""
    if not encounter_data:
        return []

    locations = {}
    for encounter in encounter_data:
        location_name = encounter["location_area"]["name"].replace("-", " ").title()

        relevant_versions = {
            vd["version"]["name"]
            for vd in encounter["version_details"]
            if not game_version_filter or vd["version"]["name"] == game_version_filter
        }

        if relevant_versions:
            if location_name not in locations:
                locations[location_name] = set()
            locations[location_name].update(relevant_versions)

    processed_encounters = [
        {"location": loc, "games": sorted([v.replace("-", " ").title() for v in vers])}
        for loc, vers in locations.items()
    ]
    return sorted(processed_encounters, key=lambda x: x["location"])


async def _get_pokemon_profile(
    client: AsyncClient,
    pokemon_name: str,
    data_groups: Optional[List[str]] = None,
    game_version: Optional[str] = None,
) -> dict[str, Any]:
    """Assembles and structures a Pokémon profile, then filters it by semantic groups."""
    pokemon_name = pokemon_name.lower()
    game_version = game_version.lower() if game_version else None

    version_group_filter = None
    if game_version:
        version_data = await _fetch_url(client, f"{BASE_URL}/version/{game_version}")
        if not version_data:
            raise ModelRetry(f"Game version '{game_version}' not found.")
        version_group_filter = version_data["version_group"]["name"]

    pokemon_task = _fetch_url(client, f"{BASE_URL}/pokemon/{pokemon_name}")
    species_task = _fetch_url(client, f"{BASE_URL}/pokemon-species/{pokemon_name}")
    pokemon, species = await asyncio.gather(pokemon_task, species_task)

    if not species:
        raise ModelRetry(f"Pokémon species '{pokemon_name}' not found.")
    if not pokemon:
        raise ModelRetry(f"Pokémon data for '{pokemon_name}' not found.")

    evolution_chain_task = _fetch_url(client, species["evolution_chain"]["url"])
    encounters_task = _fetch_url(client, pokemon["location_area_encounters"])
    evolution_chain, encounters = await asyncio.gather(
        evolution_chain_task, encounters_task
    )

    if not evolution_chain:
        raise ModelRetry("Could not fetch evolution chain data.")

    identity_data = {
        "id": pokemon.get("id"),
        "name": pokemon.get("name").capitalize(),
        "genus": next(
            (g["genus"] for g in species["genera"] if g["language"]["name"] == "en"), ""
        ),
        "types": [t["type"]["name"] for t in pokemon["types"]],
        "is_legendary": species["is_legendary"],
        "is_mythical": species.get("is_mythical", False),
        "is_baby": species.get("is_baby", False),
    }

    physical_data = {
        "height_m": pokemon.get("height", 0) / 10.0,
        "weight_kg": pokemon.get("weight", 0) / 10.0,
        "color": species.get("color", {}).get("name"),
        "shape": species.get("shape", {}).get("name"),
    }

    battle_stats_data = {
        "base_stats": {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]},
        "abilities": [
            a["ability"]["name"] + (" (hidden)" if a["is_hidden"] else "")
            for a in pokemon["abilities"]
        ],
    }

    training_data = {
        "base_experience": pokemon.get("base_experience"),
        "capture_rate": species.get("capture_rate"),
        "growth_rate": species.get("growth_rate", {}).get("name"),
        "egg_groups": [eg["name"] for eg in species.get("egg_groups", [])],
        "gender_rate_female": (
            f"{(species.get('gender_rate', -1) / 8.0):.1%}"
            if species.get("gender_rate", -1) != -1
            else "Genderless"
        ),
    }

    evolution_data = {
        "evolves_from": species.get("evolves_from_species", {}).get("name"),
        "paths": _process_evolution_chain(evolution_chain["chain"]),
    }

    final_structured_profile = {
        "summary": {
            "identity": identity_data,
            "physical_characteristics": physical_data,
        },
        "battle_profile": {
            "battle_stats": battle_stats_data,
            "training_and_breeding": training_data,
            "evolution": evolution_data,
        },
        "moves": _process_moves(pokemon["moves"], version_group_filter),
        "ecology": {
            "habitat": species.get("habitat", {}).get("name", "Unknown"),
            "encounter_locations": _process_encounters(encounters, game_version),
        },
        "lore": {
            "pokedex_entries": _process_pokedex_entries(species["flavor_text_entries"])
        },
    }

    if not data_groups:
        return final_structured_profile

    return {
        group: final_structured_profile[group]
        for group in data_groups
        if group in final_structured_profile
    }


async def _get_pokemon_profiles(
    client: AsyncClient,
    pokemon_names: List[str],
    data_groups: Optional[List[str]] = None,
    game_version: Optional[str] = None,
) -> dict[str, Any]:
    """Retrieves comprehensive profiles for one or more Pokémon, organized into logical data groups."""
    tasks = {
        name: _get_pokemon_profile(client, name, data_groups, game_version)
        for name in pokemon_names
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    profiles = {}
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            profiles[name] = {"error": str(result)}
        else:
            profiles[name] = result
    return profiles
