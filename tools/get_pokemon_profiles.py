from typing import List, Dict, Optional, Any, Literal
from dataset.utils import load_pokemon_dataset
from resources.enums import VersionGroup
from enum import Enum
from tools.utils import pretty_print
import json


class DataGroup(str, Enum):
    PROFILE = "profile"
    BATTLE = "battle"
    LOCATIONS = "locations"
    MOVES = "moves"
    LORE = "lore"


def filter_moves(moves: Dict[str, Any], version: VersionGroup) -> Dict[str, Any]:
    return {
        k: v
        for k, v in moves.items()
        if isinstance(v, dict) and version in v and v[version]
    }


def filter_encounters(locations: Dict[str, Any], version: VersionGroup) -> List[str]:
    locs = locations.get(version)
    if isinstance(locs, list):
        return locs
    elif hasattr(locs, "tolist"):
        return locs.tolist()
    return []


async def get_pokemon_profiles(
    names: List[str],
    data_groups: List[DataGroup],
    game_version: Optional[VersionGroup] = None,
) -> Dict[str, Any]:
    """
    Retrieves structured Pokémon data for one or more Pokémon, optionally filtered by game version. This tool allows querying specific sections ("data groups") of Pokémon information in a consistent, LLM-friendly format. If no `data_groups` are specified, only the 'profile' group is returned by default.

    Args:
        pokemon_names (List[str]): A list of Pokémon names or Pokédex IDs to retrieve.

        data_groups (List[str], optional): Specific data sections to include. Valid options:
            - 'profile': Biological and identity traits including name, ID, types, genus,
                         height, weight, color, shape, evolution, and breeding data.
            - 'battle': Battle-related stats and derived analysis (roles, tiers, effectiveness).
            - 'locations': Game-specific encounter locations across all versions.
            - 'moves': Learnable moves organized by level, machine, and tutor, including strategic tags.
            - 'lore': All Pokédex entries, organized by game version.

        game_version (str, optional): A specific game version (e.g., 'red', 'black-2-white-2').
                                      This is required to filter 'moves' and 'locations' to version-specific data.

    Returns:
        Dict[str, Any]: A dictionary mapping Pokémon names to their corresponding data groups.
                        If a Pokémon is invalid or not found, an 'error' field is included in the result.
    """
    df = load_pokemon_dataset()
    data_groups = data_groups or ["profile"]

    results: Dict[str, Any] = {}

    for name in names:
        name = name.lower().strip()
        if name not in df.index:
            results[name] = {"name": name, "error": "Pokémon not found"}
            continue

        row = df.loc[name]
        print(row["full_profile"])
        profile = json.loads(row["full_profile"])
        result_profile: Dict[str, Any] = {}

        for group in data_groups:
            if group == "moves" and "moves" in profile and game_version:
                result_profile["moves"] = filter_moves(profile["moves"], game_version)

            elif group == "locations" and "locations" in profile and game_version:
                result_profile["locations"] = {
                    "encounter_locations": filter_encounters(
                        profile["locations"].get("encounter_locations", {}),
                        game_version,
                    )
                }

            elif group in profile:
                result_profile[group] = profile[group]

        results[name] = result_profile

    print(results)

    return results
