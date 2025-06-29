import asyncio
from typing import Any, List, Dict, Optional
from httpx import AsyncClient
from tools.utils import _fetch_url, pretty_print
from tools.type_chart import calculate_type_defenses, calculate_type_offenses


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

    if not chain_link["evolves_to"]:
        return []

    for evolution in chain_link["evolves_to"]:
        to_species = evolution["species"]["name"]
        details = evolution["evolution_details"][0]
        trigger = details["trigger"]["name"].replace("-", " ")

        conditions = []
        if trigger == "level up":
            if "min_level" in details:
                conditions.append(f"at level {details['min_level']}")
            if "min_happiness" in details:
                conditions.append("with high friendship")
            if "time_of_day" in details and details["time_of_day"]:
                conditions.append(f"during the {details['time_of_day']}")
            if not conditions:
                conditions.append("by leveling up")
        elif trigger == "use item":
            conditions.append(f"using a '{details['item']['name']}'")
        elif trigger == "trade":
            condition = "by trading"
            held_item = details.get("held_item")
            if held_item:
                condition += f" while holding a '{held_item['name']}'"
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
    moves_data: List[Dict[str, Any]], version_group_filter: str
) -> Dict[str, Any]:
    final_moves = {"level_up": {}, "machine": [], "tutor": [], "egg": []}

    for move_entry in moves_data:
        move_name = move_entry["move"]["name"].replace("-", " ").title()

        for vgd in move_entry["version_group_details"]:
            if vgd["version_group"]["name"] == version_group_filter:
                method = vgd["move_learn_method"]["name"]
                level = vgd["level_learned_at"]

                if method == "level-up" and level > 0:
                    final_moves["level_up"].setdefault(str(level), []).append(move_name)
                elif method in final_moves:
                    final_moves[method].append(move_name)

    final_moves["level_up"] = dict(
        sorted((lvl, sorted(set(mv))) for lvl, mv in final_moves["level_up"].items())
    )
    for key in ["machine", "tutor", "egg"]:
        final_moves[key] = sorted(set(final_moves[key]))

    return {k: v for k, v in final_moves.items() if v}


def _process_encounters(
    encounter_data: List[Dict[str, Any]], game_version_filter: str
) -> List[str]:
    locations = set()
    for encounter in encounter_data:
        for version_detail in encounter["version_details"]:
            if version_detail["version"]["name"] == game_version_filter:
                location_name = encounter["location_area"]["name"]
                locations.add(location_name.replace("-", " ").title())
                break
    return sorted(locations)


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
    offenses = stats["type_offenses"]
    roles = []
    if defn >= 100 and hp >= 80:
        roles.append("Physical Wall")
    if spdef >= 100 and hp >= 80:
        roles.append("Special Wall")
    if atk >= 120 and defn >= 90:
        roles.append("Bulky Attacker")
    if speed >= 100 and atk >= 100:
        roles.append("Fast Sweeper")
    if speed >= 100 and spatk >= 100:
        roles.append("Special Sweeper")
    if speed >= 90 and (atk >= 90 or spatk >= 90):
        roles.append("Offensive Pivot")
    if speed >= 70 and defn >= 80 and spdef >= 80:
        roles.append("Defensive Pivot")
    if "rock" in offenses["super_effective_against"] and defn >= 90:
        roles.append("Hazard Setter")
    if "flying" in offenses["super_effective_against"] and speed >= 80:
        roles.append("Hazard Remover")
    return sorted(set(roles))


async def _get_pokemon_profile(
    client: AsyncClient,
    name: str,
    data_groups: Optional[List[str]] = None,
    game_version: Optional[str] = None,
) -> dict[str, Any]:
    name = name.lower()
    vg_filter = None
    if game_version:
        vg_filter = (
            await _fetch_url(
                client, f"https://pokeapi.co/api/v2/version/{game_version}"
            )
        )["version_group"]["name"]

    pokemon = await _fetch_url(client, f"https://pokeapi.co/api/v2/pokemon/{name}")
    species = await _fetch_url(
        client, f"https://pokeapi.co/api/v2/pokemon-species/{name}"
    )
    evo_chain = await _fetch_url(client, species["evolution_chain"]["url"])
    encounters = await _fetch_url(client, pokemon["location_area_encounters"])

    types = [
        t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])
    ]

    profile = {
        "summary": {
            "identity": {
                "id": pokemon["id"],
                "name": pokemon["name"].capitalize(),
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
        "moves": _process_moves(pokemon["moves"], vg_filter) if vg_filter else {},
        "ecology": {
            "habitat": species["habitat"]["name"] if species["habitat"] else "Unknown",
            "encounter_locations": (
                _process_encounters(encounters, game_version) if game_version else []
            ),
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

    pretty_print(profile)

    if not data_groups:
        data_groups = ["summary"]
    return {k: profile[k] for k in data_groups if k in profile}


async def _get_pokemon_profiles(
    client: AsyncClient,
    names: List[str],
    data_groups: Optional[List[str]] = None,
    game_version: Optional[str] = None,
) -> dict[str, Any]:
    tasks = {
        name: _get_pokemon_profile(client, name, data_groups, game_version)
        for name in names
    }
    results = await asyncio.gather(*tasks.values())
    return dict(zip(tasks.keys(), results))
