from typing import List, Dict, Optional, Any
from dataset.utils import load_pokemon_dataset


def _filter_moves(moves_data: Dict[str, Any], game_version: str) -> Dict[str, Any]:
    vg = game_version.lower().replace(" ", "-")
    return moves_data.get(vg, {})


def _filter_encounters(
    encounters: Dict[str, List[str]], game_version: str
) -> List[str]:
    gv = game_version.lower()
    return encounters.get(gv, [])


async def _get_pokemon_profiles(
    names: List[str],
    data_groups: Optional[List[str]] = None,
    game_version: Optional[str] = None,
) -> Dict[str, Any]:
    df = load_pokemon_dataset()
    data_groups = data_groups or ["summary"]

    result: Dict[str, Any] = {}

    for name in names:
        name = name.lower().strip()
        if name not in df.index:
            result[name] = {"name": name, "error": "Pokemon not found"}
            continue

        profile = df.loc[name]["full_profile"]
        filtered: Dict[str, Any] = {}

        for group in data_groups:
            if group not in profile:
                continue
            if group == "moves" and game_version:
                filtered["moves"] = _filter_moves(profile["moves"], game_version)
            elif group == "ecology" and game_version:
                filtered["ecology"] = {
                    "habitat": profile["ecology"].get("habitat", "Unknown"),
                    "encounter_locations": _filter_encounters(
                        profile["ecology"].get("encounter_locations", {}),
                        game_version,
                    ),
                }
            else:
                filtered[group] = profile[group]

        result[name] = filtered

    return result
