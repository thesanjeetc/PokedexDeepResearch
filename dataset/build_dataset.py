import asyncio
import json
import pandas as pd
from pathlib import Path
from tqdm.asyncio import tqdm_asyncio
from typing import Any, List, Dict, Optional
from httpx import AsyncClient
from dataset.utils import fetch_url
from dataset.type_chart import calculate_type_defenses, calculate_type_offenses
from collections import defaultdict
from dataset.utils import (
    derive_overview,
    derive_roles,
    process_evolution_chain,
    process_encounters,
    process_moves,
    process_pokedex_entries,
)


async def get_pokemon_profile(client: AsyncClient, name: str) -> dict[str, Any]:
    name = name.lower()

    pokemon = await fetch_url(client, f"https://pokeapi.co/api/v2/pokemon/{name}")
    base_species_name = pokemon["species"]["name"]
    species = await fetch_url(
        client, f"https://pokeapi.co/api/v2/pokemon-species/{base_species_name}"
    )
    evo_chain_url = species.get("evolution_chain", {}).get("url")
    evo_chain = (
        await fetch_url(client, evo_chain_url) if evo_chain_url else {"chain": {}}
    )
    encounters = await fetch_url(client, pokemon["location_area_encounters"])

    types = [
        t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])
    ]

    base_stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]}
    type_defenses = calculate_type_defenses(types)
    type_offenses = calculate_type_offenses(types)
    battle_overview = derive_overview(base_stats)

    abilities = [
        {"name": a["ability"]["name"], "is_hidden": a["is_hidden"]}
        for a in pokemon["abilities"]
    ]

    roles = derive_roles(base_stats)
    evolves_from = (
        species["evolves_from_species"]["name"]
        if species["evolves_from_species"]
        else None
    )
    genus = [g["genus"] for g in species["genera"] if g["language"]["name"] == "en"]
    genus = genus[0] if genus else "Unknown"
    egg_groups = [g["name"] for g in species["egg_groups"]]
    gender_rate_female = (
        f"{(species['gender_rate'] / 8.0):.1%}"
        if species["gender_rate"] != -1
        else "Genderless"
    )

    return {
        # Identity
        "id": pokemon["id"],
        "name": pokemon["name"].lower(),
        "genus": genus,
        "types": types,
        "is_legendary": species["is_legendary"],
        "is_mythical": species["is_mythical"],
        "is_baby": species["is_baby"],
        # Physical
        "height_m": pokemon["height"] / 10.0,
        "weight_kg": pokemon["weight"] / 10.0,
        "color": species["color"]["name"],
        "shape": species["shape"]["name"],
        # Base Stats
        "base_hp": base_stats.get("hp", 0),
        "base_attack": base_stats.get("attack", 0),
        "base_defense": base_stats.get("defense", 0),
        "base_special_attack": base_stats.get("special-attack", 0),
        "base_special_defense": base_stats.get("special-defense", 0),
        "base_speed": base_stats.get("speed", 0),
        # Roles & Derived Tiers
        "roles": roles,
        "speed_tier": battle_overview["speed_tier"],
        "attack_focus": battle_overview["attack_focus"],
        "defense_category": battle_overview["defense_category"],
        "bst_tier": battle_overview["bst_tier"],
        # Matchups
        "immune_to": type_defenses["immune_to"],
        "resists_2x": type_defenses["resists_2x"],
        "resists_4x": type_defenses["resists_4x"],
        "weak_to_2x": type_defenses["weak_to_2x"],
        "weak_to_4x": type_defenses["weak_to_4x"],
        "super_effective_against": type_offenses["super_effective_against"],
        "not_very_effective_against": type_offenses["not_very_effective_against"],
        "no_effect_against": type_offenses["no_effect_against"],
        # Abilities
        "abilities": abilities,
        # Training & Breeding
        "base_experience": pokemon["base_experience"],
        "capture_rate": species["capture_rate"],
        "growth_rate": species["growth_rate"]["name"],
        "egg_groups": egg_groups,
        "gender_rate_female": gender_rate_female,
        # Evolution
        "evolves_from": evolves_from,
        "evolution_paths": process_evolution_chain(evo_chain["chain"]),
        # Ecology
        "habitat": species["habitat"]["name"] if species["habitat"] else "Unknown",
        "encounter_locations": process_encounters(encounters),
        # Moves (still nested)
        "moves": process_moves(pokemon["moves"]),
        # Lore (optional, keep nested or drop)
        "pokedex_entries": process_pokedex_entries(species["flavor_text_entries"]),
    }


import json
from collections import defaultdict

# --- HELPER FUNCTIONS FOR THE MAIN FORMATTER ---


def _format_name(s):
    """Helper to format names like 'lightning-rod' into 'Lightning Rod'."""
    return " ".join(word.capitalize() for word in s.replace("-", " ").split())


def _transform_abilities(raw_abilities):
    """Converts [{'name': '...', 'is_hidden': bool}] to ["Name", "Name (Hidden)"]."""
    if not raw_abilities:
        return []
    return [
        (
            f"{_format_name(a['name'])} (Hidden)"
            if a["is_hidden"]
            else _format_name(a["name"])
        )
        for a in raw_abilities
    ]


def _transform_evolutions(raw_paths):
    """Converts the complex evolution path list into simple, readable strings."""
    if not raw_paths:
        return []
    return [
        f"{path['from_pokemon'].capitalize()} evolves into {path['to_pokemon'].capitalize()} {path['condition']}."
        for path in raw_paths
    ]


def _transform_locations_by_game(raw_locations):
    """
    Keeps the {game: [locations]} structure but cleans up the location names.
    """
    if not raw_locations:
        return {}

    cleaned_data = {}
    # Iterate through games and their location lists
    for game, loc_list in raw_locations.items():
        # Clean each location name, remove duplicates with set(), and re-sort
        cleaned_list = sorted(
            list(set(loc.replace(" Area", "").strip() for loc in loc_list))
        )
        cleaned_data[game] = cleaned_list

    return cleaned_data


def _transform_pokedex_by_game(raw_entries):
    """
    Keeps the {game: text} structure but cleans the text for each entry.
    """
    if not raw_entries:
        return {}

    cleaned_data = {}
    for game, text in raw_entries.items():
        # Normalize text to fix common inconsistencies
        clean_text = (
            text.replace("POKéMON", "Pokémon")
            .replace("BERRIES", "berries")
            .replace("­ ", "")
            .strip()
        )
        cleaned_data[game] = clean_text

    return cleaned_data


def _transform_moves(raw_moves_by_game):
    """Aggregates moves from all games into one de-duplicated, readable moveset."""
    if not raw_moves_by_game:
        return {}

    level_up_moves = {}
    machine_moves, tutor_moves, all_tags = set(), set(), set()

    for game, moveset in raw_moves_by_game.items():
        for move in moveset.get("level_up", []):
            name = move["name"]
            level = move["level"]
            if name not in level_up_moves or level < level_up_moves[name]:
                level_up_moves[name] = level

        machine_moves.update(moveset.get("machine", []))
        tutor_moves.update(moveset.get("tutor", []))
        all_tags.update(moveset.get("strategic_tags", []))

    sorted_level_up = sorted(
        level_up_moves.items(), key=lambda item: (item[1], item[0])
    )

    return {
        "by_level_up": [f"Lvl {lvl}: {name}" for name, lvl in sorted_level_up],
        "by_machine": sorted(list(machine_moves)),
        "by_tutor": sorted(list(tutor_moves)),
        "strategic_tags": sorted(list(all_tags)),
    }


# --- THE MAIN FORMATTING FUNCTION ---


def format_pokemon_profile(data):
    """
    Takes the flat, processed data and formats it into a final, nested,
    LLM-friendly profile by cleaning up specific fields while preserving
    the desired structure for locations and pokedex entries.
    """

    # --- 1. Perform targeted transformations on the messy fields ---
    abilities_formatted = _transform_abilities(data.get("abilities", []))
    evolutions_formatted = _transform_evolutions(data.get("evolution_paths", []))
    locations_formatted = _transform_locations_by_game(
        data.get("encounter_locations", {})
    )
    moves_formatted = _transform_moves(data.get("moves", {}))
    pokedex_formatted = _transform_pokedex_by_game(data.get("pokedex_entries", {}))

    # --- 2. Build the final nested profile using the cleaned-up data ---
    full_profile = {
        "profile": {
            "identity": {
                "id": data["id"],
                "name": data["name"],
                "genus": data["genus"],
                "types": data["types"],
                "is_legendary": data["is_legendary"],
                "is_mythical": data["is_mythical"],
                "is_baby": data["is_baby"],
            },
            "physical": {
                "height_m": data["height_m"],
                "weight_kg": data["weight_kg"],
                "color": data["color"],
                "shape": data["shape"],
            },
            "biology": {
                "habitat": data["habitat"],
                "egg_groups": data["egg_groups"],
                "gender_rate": data["gender_rate_female"],
                "capture_rate": data["capture_rate"],
                "growth_rate": data["growth_rate"],
                "evolution": {
                    "evolves_from": data["evolves_from"],
                    "evolution_paths": evolutions_formatted,
                },
            },
        },
        "battle": {
            "base_stats": {
                "hp": data["base_hp"],
                "attack": data["base_attack"],
                "defense": data["base_defense"],
                "special_attack": data["base_special_attack"],
                "special_defense": data["base_special_defense"],
                "speed": data["base_speed"],
            },
            "combat_analysis": {
                "abilities": abilities_formatted,
                "roles": data["roles"],
                "bst_tier": data["bst_tier"],
                "speed_tier": data["speed_tier"],
                "attack_focus": data["attack_focus"],
                "defense_category": data["defense_category"],
                "base_experience": data["base_experience"],
            },
            "type_effectiveness": {
                "defensive": {
                    "immune_to": data["immune_to"],
                    "resists_4x": data["resists_4x"],
                    "resists_2x": data["resists_2x"],
                    "weak_to_2x": data["weak_to_2x"],
                    "weak_to_4x": data["weak_to_4x"],
                },
                "offensive": {
                    "super_effective_against": data["super_effective_against"],
                    "not_very_effective_against": data["not_very_effective_against"],
                    "no_effect_against": data["no_effect_against"],
                },
            },
        },
        "locations": {"encounter_locations": locations_formatted},
        "moves": moves_formatted,
        "lore": {"pokedex_entries": pokedex_formatted},
    }

    return full_profile


async def get_all_pokemon(client: AsyncClient):
    url = "https://pokeapi.co/api/v2/pokemon?limit=2000"
    data = await fetch_url(client, url)
    return [entry["name"] for entry in data["results"]]


async def fetch_pokemon_profiles(
    json_path="resources/pokemon.json", max_concurrency=20
):
    async with AsyncClient(timeout=30.0) as client:
        names = await get_all_pokemon(client)
        print(f"Fetching {len(names)} Pokémon profiles...")

        semaphore = asyncio.Semaphore(max_concurrency)
        profiles = {}

        async def fetch(name: str):
            async with semaphore:
                profile = await get_pokemon_profile(client, name)
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

    for _, profile in data.items():
        profile["full_profile"] = format_pokemon_profile(profile)

    df = pd.DataFrame(data.values())
    df.set_index("name", inplace=True)
    df.to_parquet(output_path, engine="pyarrow", index=True)
    print(f"Saved enriched dataset to {output_path}")
