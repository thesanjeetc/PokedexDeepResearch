import asyncio
from typing import Any, List, Dict
from httpx import AsyncClient
from pydantic_ai import ModelRetry
from tools.utils import pretty_print, _fetch_url, BASE_URL


def _clean_flavor_text(text: str) -> str:
    """Removes newlines and other special characters from flavor text."""
    return text.replace("\n", " ").replace("\x0c", " ").strip()


def _process_pokedex_entries(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extracts the English flavor text for each game version."""
    processed = {}
    entry = next(
        (ft for ft in entries if ft["language"]["name"] == "en"),
        None,
    )
    if entry:
        version_name = entry["version"]["name"].replace("-", " ").title()
        processed[version_name] = _clean_flavor_text(entry["flavor_text"])
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
        trigger = details["trigger"]["name"]

        conditions = []
        if trigger == "level-up":
            if details.get("min_level"):
                conditions.append(f"at level {details['min_level']}")
            if details.get("min_happiness"):
                conditions.append("with high friendship")
            if details.get("time_of_day"):
                conditions.append(f"during the {details['time_of_day']}")
            if not conditions:
                conditions.append("by leveling up")
        elif trigger == "use-item":
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


async def get_pokemon_profile(client: AsyncClient, name: str) -> dict[str, Any]:
    """The primary tool for all-in-one information about a single, known Pokémon.
    Args:
    name (str): The exact name or Pokédex ID of the Pokémon.
    """
    name = name.lower()

    species = await _fetch_url(client, f"{BASE_URL}/pokemon-species/{name}")
    if not species:
        raise ModelRetry(f"Pokémon '{name}' not found. Please check the spelling.")

    tasks = {
        "pokemon": _fetch_url(client, f"{BASE_URL}/pokemon/{name}"),
        "evolution_chain": _fetch_url(client, species["evolution_chain"]["url"]),
    }
    task_results = await asyncio.gather(*tasks.values())
    results = dict(zip(tasks.keys(), task_results))

    pokemon = results.get("pokemon")
    evolution_chain = results.get("evolution_chain")

    if not pokemon or not evolution_chain:
        raise ModelRetry("Could not fetch all required profile data.")

    profile = {
        "identity": {
            "id": pokemon.get("id"),
            "name": pokemon.get("name"),
            "genus": next(
                (
                    g["genus"]
                    for g in species["genera"]
                    if g["language"]["name"] == "en"
                ),
                "",
            ),
            "types": [t["type"]["name"] for t in pokemon["types"]],
            "is_legendary": species["is_legendary"],
            "is_mythical": species.get("is_mythical", False),
            "is_baby": species.get("is_baby", False),
        },
        "description": {
            "pokedex_entries": _process_pokedex_entries(species["flavor_text_entries"])
        },
        "physical_characteristics": {
            "height": f"{pokemon.get('id') / 10.0}m",
            "weight": f"{pokemon.get('id') / 10.0}kg",
            "color": species.get("color", {}).get("name"),
            "shape": species.get("shape", {}).get("name"),
            "habitat": species.get("habitat", {}).get("name", "Unknown"),
        },
        "battle_stats": {
            "base_stats": {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]},
            "abilities": [
                a["ability"]["name"] + (" (hidden)" if a["is_hidden"] else "")
                for a in pokemon["abilities"]
            ],
        },
        "training_and_breeding": {
            "base_experience": pokemon.get("base_experience"),
            "capture_rate": species.get("capture_rate"),
            "growth_rate": species.get("growth_rate", {}).get("name"),
            "egg_groups": [eg["name"] for eg in species.get("egg_groups", [])],
            "gender_rate_female": (
                f"{(species.get('gender_rate', -1) / 8.0):.1%}"
                if species.get("gender_rate", -1) != -1
                else "Genderless"
            ),
        },
        "evolution": {
            "evolves_from": (
                species.get("evolves_from_species", {}).get("name")
                if species.get("evolves_from_species")
                else None
            ),
            "paths": _process_evolution_chain(evolution_chain["chain"]),
        },
    }
    pretty_print(profile)
    return profile
