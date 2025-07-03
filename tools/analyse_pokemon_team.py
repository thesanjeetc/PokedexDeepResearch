import asyncio
import json
from typing import Dict, List, Optional
from collections import defaultdict
from dataset.type_chart import fetch_type_chart
from dataset.utils import load_pokemon_dataset
from resources.enums import VersionGroup


async def analyse_pokemon_team(
    pokemon_names: List[str], game_version: Optional[VersionGroup] = None
) -> str:
    """
    Analyzes a team of Pokémon and returns detailed offensive and defensive summaries,
    including weaknesses, resistances, and strategic role distributions.

    Args:
        pokemon_names (List[str]): List of Pokémon names to analyze.
        game_version (VersionGroup, optional): Game version to extract strategic role tags.

    Returns:
        str: JSON string containing the analysis summary.
    """
    df = load_pokemon_dataset()
    df = df[df.index.isin([name.lower() for name in pokemon_names])]

    pokemon_profiles = {}
    type_counts = defaultdict(int)
    role_counts = defaultdict(int)
    speed_counts = defaultdict(int)
    coverage_map = defaultdict(list)
    offense_total_types = set()
    resistances_total = defaultdict(int)
    resistances_set = set()
    top_threats = {}
    strategic_counts = defaultdict(int)
    weakness_counts = defaultdict(int)

    all_types = set(fetch_type_chart().keys())

    for name, profile in df.iterrows():
        for t in profile["resists_2x"]:
            resistances_total[t] += 1
            resistances_set.add(t)
        for t in profile["resists_4x"]:
            resistances_total[t] += 1
            resistances_set.add(t)
        for t in profile["immune_to"]:
            resistances_total[t] += 1
            resistances_set.add(t)

        for t in profile["weak_to_2x"]:
            weakness_counts[t] += 1
            top_threats[t] = max(top_threats.get(t, 0.0), 2.0)
        for t in profile["weak_to_4x"]:
            weakness_counts[t] += 1
            top_threats[t] = 4.0

        game_moves = profile["moves"].get(game_version, {})
        tags = game_moves.get("strategic_tags", [])
        for tag in tags:
            strategic_counts[tag] += 1

        offense = {
            "super_effective_against": profile["super_effective_against"],
            "not_very_effective_against": profile["not_very_effective_against"],
            "no_effect_against": profile["no_effect_against"],
        }

        defense = {
            "immune_to": profile["immune_to"],
            "resists_4x": profile["resists_4x"],
            "resists_2x": profile["resists_2x"],
            "weak_to_2x": profile["weak_to_2x"],
            "weak_to_4x": profile["weak_to_4x"],
        }

        roles = profile["roles"]
        speed = profile["speed_tier"]

        for t in profile["types"]:
            type_counts[t] += 1
        for r in roles:
            role_counts[r] += 1
        speed_counts[speed] += 1

        for t in offense["super_effective_against"]:
            coverage_map[t].append(name)
            offense_total_types.add(t)

        pokemon_profiles[name] = {
            "types": profile["types"],
            "roles": roles,
            "speed_tier": speed,
            "offense": offense,
            "defense": defense,
        }

    shared_weaknesses = {k: v for k, v in weakness_counts.items() if v > 1}
    coverage_gaps_off = sorted(list(all_types - offense_total_types))
    coverage_gaps_def = sorted(list(all_types - resistances_set))
    redundancy = {k: len(v) for k, v in coverage_map.items() if len(v) > 1}

    analysis = {
        "team_summary": {
            "size": len(pokemon_names),
            "types": dict(type_counts),
            "role_distribution": dict(role_counts),
            "speed_distribution": dict(speed_counts),
            "strategic_distribution": dict(strategic_counts),
        },
        "offense_analysis": {
            "coverage_map": dict(coverage_map),
            "coverage_gaps": coverage_gaps_off,
            "coverage_redundancy": redundancy,
        },
        "defense_analysis": {
            "top_threats": top_threats,
            "shared_weaknesses": shared_weaknesses,
            "coverage_gaps": coverage_gaps_def,
            "resistances_summary": dict(resistances_total),
        },
        "pokemon_profiles": pokemon_profiles,
    }

    return json.dumps(analysis, indent=2)
