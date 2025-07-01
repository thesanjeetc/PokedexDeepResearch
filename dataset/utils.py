import pandas as pd
from typing import Optional, Any, List, Dict
from httpx import AsyncClient
from async_lru import alru_cache
from collections import defaultdict
import numpy as np

BASE_URL = "https://pokeapi.co/api/v2"


@alru_cache(maxsize=512)
async def fetch_url(client: AsyncClient, url: str) -> Optional[dict]:
    """Safely fetches a single URL, returning JSON or None on error."""
    try:
        response = await client.get(url, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


_PARQUET_PATH = "resources/pokemon.parquet"
_cached_df = None


def load_pokemon_dataset() -> pd.DataFrame:
    global _cached_df
    if _cached_df is None:
        _cached_df = pd.read_parquet(_PARQUET_PATH)
        for col in _cached_df.columns:
            _cached_df[col] = _cached_df[col].apply(
                lambda x: x.tolist() if isinstance(x, np.ndarray) else x
            )
    return _cached_df


def clean_flavor_text(text: str) -> str:
    return text.replace("\n", " ").replace("\x0c", " ").strip()


def format_string(version: str) -> str:
    return version.replace(" ", "-").replace("_", "-").lower()


def process_pokedex_entries(entries: List[Dict[str, Any]]) -> Dict[str, str]:
    processed = {}
    seen_versions = set()
    for entry in reversed(entries):
        if entry["language"]["name"] == "en":
            version_name = format_string(entry["version"]["name"])
            if version_name not in seen_versions:
                processed[version_name] = clean_flavor_text(entry["flavor_text"])
                seen_versions.add(version_name)
    return processed


def process_evolution_chain(chain_link: Dict[str, Any]) -> List[Dict[str, Any]]:
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
                    "method": "unknown",
                    "requirements": [],
                }
            )
            continue

        details = details_list[0]
        trigger = details.get("trigger", {}).get("name", "unknown").replace("-", " ")
        conditions = []
        requirements = []
        method = "unknown"

        if trigger == "level up":
            method = "level"
            if details.get("min_level") is not None:
                level = details["min_level"]
                conditions.append(f"at level {level}")
                requirements.append(
                    {
                        "requirement_type": "min_level",
                        "name": str(level),
                        "description": f"must be at least level {level}",
                    }
                )
            if details.get("min_happiness"):
                conditions.append("with high friendship")
                requirements.append(
                    {
                        "requirement_type": "high_friendship",
                        "name": None,
                        "description": "requires high friendship",
                    }
                )
            if details.get("time_of_day"):
                time = details["time_of_day"]
                conditions.append(f"during the {time}")
                requirements.append(
                    {
                        "requirement_type": "time_of_day",
                        "name": time,
                        "description": f"must evolve during the {time}",
                    }
                )
            if not requirements:
                conditions.append("by leveling up")
                requirements.append(
                    {
                        "requirement_type": "level_up",
                        "name": None,
                        "description": "requires level up",
                    }
                )

        elif trigger == "use item":
            method = "item"
            item = details.get("item", {})
            if item and item.get("name"):
                item_name = item["name"]
                conditions.append(f"using a '{item_name}'")
                requirements.append(
                    {
                        "requirement_type": "item",
                        "name": item_name,
                        "description": f"requires item: {item_name}",
                    }
                )

        elif trigger == "trade":
            method = "trade"
            cond = "by trading"
            requirements.append(
                {
                    "requirement_type": "trade",
                    "name": None,
                    "description": "requires trading",
                }
            )
            held_item = details.get("held_item", {})
            if held_item and held_item.get("name"):
                item_name = held_item["name"]
                cond += f" while holding a '{item_name}'"
                requirements.append(
                    {
                        "requirement_type": "held_item",
                        "name": item_name,
                        "description": f"must hold item during trade: {item_name}",
                    }
                )
            conditions.append(cond)

        else:
            conditions.append(f"by a special method: '{trigger}'")
            requirements.append(
                {
                    "requirement_type": "special",
                    "name": trigger,
                    "description": f"evolution method: {trigger}",
                }
            )

        paths.append(
            {
                "from_pokemon": from_species.lower(),
                "to_pokemon": to_species.lower(),
                "condition": " and ".join(conditions),
                "method": method,
                "requirements": requirements,
            }
        )

        paths.extend(process_evolution_chain(evolution))

    return paths


from typing import Dict, Any, List, Set

STRATEGIC_MOVE_TAGS: Dict[str, Set[str]] = {
    "pivot": {"u-turn", "volt switch", "flip turn", "parting shot"},
    "hazard_setter": {"stealth rock", "spikes", "toxic spikes", "sticky web"},
    "hazard_remover": {"defog", "rapid spin", "court change", "tidy up"},
    "setup_sweeper": {
        "swords dance",
        "nasty plot",
        "calm mind",
        "dragon dance",
        "quiver dance",
        "bulk up",
        "shell smash",
    },
    "cleric": {"wish", "heal bell", "aromatherapy", "life dew", "moonlight"},
    "scout": {"protect", "detect", "substitute"},
    "status_spreader": {
        "spore",
        "sleep powder",
        "hypnosis",
        "yawn",
        "toxic",
        "thunder wave",
        "will-o-wisp",
        "glare",
    },
    "screen_support": {"reflect", "light screen", "aurora veil"},
    "phazer": {"roar", "whirlwind", "dragon tail", "circle throw"},
    "trick_room_support": {"trick room"},
    "redirection": {"follow me", "rage powder"},
    "trapper": {"mean look", "block", "spirit shackle"},
    "priority_user": {
        "extreme speed",
        "aqua jet",
        "bullet punch",
        "shadow sneak",
        "ice shard",
        "sucker punch",
    },
}


def tag_strategic_roles(moves: Dict[str, Any]) -> List[str]:
    all_moves = set()

    for method, value in moves.items():
        if method == "level_up" and isinstance(value, list):
            all_moves.update(m["name"].lower() for m in value if isinstance(m, dict))
        elif isinstance(value, list):
            all_moves.update(m.lower() for m in value)

    return sorted(
        [
            format_string(tag)
            for tag, keywords in STRATEGIC_MOVE_TAGS.items()
            if all_moves & keywords
        ]
    )


def process_moves(moves_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result = {
        "level_up": defaultdict(list),
        "machine": defaultdict(set),
        "tutor": defaultdict(set),
        "egg": defaultdict(set),
    }

    for move_entry in moves_data:
        move_name = move_entry["move"]["name"].replace("-", " ").title()

        for vgd in move_entry["version_group_details"]:
            version = format_string(vgd["version_group"]["name"])
            method = vgd["move_learn_method"]["name"].replace("-", "_")
            level = vgd["level_learned_at"]

            if method == "level_up" and level > 0:
                result["level_up"][version].append({"level": level, "name": move_name})
            elif method in ["machine", "tutor", "egg"]:
                result[method][version].add(move_name)

    versions = set()
    for method_dict in result.values():
        versions.update(method_dict.keys())

    final_result = {}
    for version in versions:
        version_data = {}

        if version in result["level_up"]:
            version_data["level_up"] = sorted(
                result["level_up"][version], key=lambda m: m["level"]
            )
        for method in ["machine", "tutor", "egg"]:
            if version in result[method]:
                version_data[method] = sorted(result[method][version])

        version_data["strategic_tags"] = tag_strategic_roles(version_data)
        final_result[version] = version_data

    return final_result


def process_encounters(encounter_data: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    game_to_locations = defaultdict(set)

    for encounter in encounter_data:
        location = encounter["location_area"]["name"].replace("-", " ").title()
        for version_detail in encounter["version_details"]:
            version = version_detail["version"]["name"]
            game_to_locations[version].add(location)

    return {
        version: sorted(locations) for version, locations in game_to_locations.items()
    }


def derive_speed_tier(speed: int) -> str:
    if speed >= 100:
        return "fast"
    elif speed >= 70:
        return "medium"
    return "slow"


def derive_attack_focus(attack: int, special_attack: int) -> str:
    diff = attack - special_attack
    if diff >= 20:
        return "physical"
    elif diff <= -20:
        return "special"
    return "balanced"


def derive_defense_category(defense: int, special_defense: int) -> str:
    avg = (defense + special_defense) / 2
    if avg >= 90:
        return "bulky"
    elif avg >= 60:
        return "average"
    return "fragile"


def derive_bst_tier(total: int) -> str:
    if total >= 600:
        return "very_high"
    elif total >= 500:
        return "high"
    elif total >= 400:
        return "medium"
    elif total >= 300:
        return "low"
    return "very_low"


def derive_overview(base_stats: Dict[str, Any]) -> Dict[str, str]:
    total = sum(
        base_stats.get(k, 0)
        for k in [
            "hp",
            "attack",
            "defense",
            "special-attack",
            "special-defense",
            "speed",
        ]
    )

    return {
        "speed_tier": derive_speed_tier(base_stats["speed"]),
        "attack_focus": derive_attack_focus(
            base_stats["attack"], base_stats["special-attack"]
        ),
        "defense_category": derive_defense_category(
            base_stats["defense"], base_stats["special-defense"]
        ),
        "bst_tier": derive_bst_tier(total),
    }


def derive_roles(bs: Dict[str, Any]) -> List[str]:
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
