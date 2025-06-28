import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional
from httpx import AsyncClient
from collections import defaultdict
from tools.utils import _fetch_url, pretty_print, BASE_URL
from pydantic import BaseModel, Field
from tools.get_pokemon_profiles import _get_pokemon_profiles
from tools.type_chart import fetch_type_chart
from pydantic import BaseModel, Field
from typing import List, Dict


class PokemonVulnerabilityProfile(BaseModel):
    """The detailed defensive profile for a single Pokémon. This is the source of truth."""

    immune_to: List[str]
    resists_4x: List[str]
    resists_2x: List[str]
    weak_to_2x: List[str]
    weak_to_4x: List[str]


class TeamDefenseSummary(BaseModel):
    """
    A concise and actionable summary of a team's defensive profile.
    It provides top-level threats and allows for drilling down into specifics.
    """

    team_size: int = Field(description="The number of Pokémon on the team analyzed.")

    top_threats: Dict[str, float] = Field(
        description="A dictionary mapping the most dangerous attack types to the highest damage multiplier "
        "they inflict on any single team member. Example: {'fighting': 4.0, 'ground': 2.0}"
    )

    shared_weaknesses: Dict[str, int] = Field(
        description="Maps attack types to the number of team members weak to it, if more than one. "
        "Highlights common vulnerabilities. Example: {'ground': 3}"
    )

    coverage_gaps: List[str] = Field(
        description="A list of attack types for which the team has NO resistances or immunities."
    )

    pokemon_vulnerabilities: Dict[str, PokemonVulnerabilityProfile] = Field(
        description="The source-of-truth defensive breakdown for each individual Pokémon."
    )


async def analyze_team_defense(
    client: AsyncClient,
    pokemon_names: List[str],
) -> TeamDefenseSummary:
    team_profiles = await _get_pokemon_profiles(
        client, pokemon_names, ["battle_profile"]
    )

    pokemon_vulnerabilities = {}
    top_threats = {}
    weakness_counts = defaultdict(int)
    team_resistances_set = set()

    for name, profile in team_profiles.items():
        defenses = profile["battle_profile"]["battle_stats"]["type_defenses"]
        pokemon_vulnerabilities[name] = PokemonVulnerabilityProfile(**defenses)

        team_resistances_set.update(defenses["immune_to"])
        team_resistances_set.update(defenses["resists_2x"])
        team_resistances_set.update(defenses["resists_4x"])

        for attack_type in defenses["weak_to_2x"]:
            weakness_counts[attack_type] += 1
            top_threats[attack_type] = max(top_threats.get(attack_type, 0), 2.0)

        for attack_type in defenses["weak_to_4x"]:
            weakness_counts[attack_type] += 1
            top_threats[attack_type] = 4.0

    shared_weaknesses = {
        attack_type: count
        for attack_type, count in weakness_counts.items()
        if count > 1
    }

    all_attack_types = set(fetch_type_chart().keys())
    coverage_gaps = sorted(list(all_attack_types - team_resistances_set))

    return TeamDefenseSummary(
        team_size=len(team_profiles),
        top_threats=top_threats,
        shared_weaknesses=shared_weaknesses,
        coverage_gaps=coverage_gaps,
        pokemon_vulnerabilities=pokemon_vulnerabilities,
    )
