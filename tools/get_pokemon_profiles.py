from typing import List, Dict, Optional, Any
from dataset.utils import load_pokemon_dataset
from resources.enums import VersionGroup


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
    data_groups: Optional[List[str]] = None,
    game_version: Optional[VersionGroup] = None,
) -> Dict[str, Any]:
    df = load_pokemon_dataset()
    data_groups = data_groups or ["profile"]

    results: Dict[str, Any] = {}

    for name in names:
        name = name.lower().strip()
        if name not in df.index:
            results[name] = {"name": name, "error": "Pokémon not found"}
            continue

        row = df.loc[name]
        profile = row["full_profile"]
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

    return results
