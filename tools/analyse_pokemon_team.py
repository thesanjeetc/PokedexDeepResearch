import asyncio
import json
from typing import Dict, List
from collections import defaultdict
from httpx import AsyncClient
from pydantic import BaseModel, Field
from tools.utils import pretty_print
from tools.get_pokemon_profiles import _get_pokemon_profiles
from dataset.type_chart import fetch_type_chart


class PokemonVulnerabilityProfile(BaseModel):
    immune_to: List[str]
    resists_4x: List[str]
    resists_2x: List[str]
    weak_to_2x: List[str]
    weak_to_4x: List[str]


class PokemonOffenseProfile(BaseModel):
    super_effective_against: List[str]
    not_very_effective_against: List[str]
    no_effect_against: List[str]


class PokemonTeamProfile(BaseModel):
    types: List[str]
    roles: List[str]
    speed_tier: str
    offense: PokemonOffenseProfile
    defense: PokemonVulnerabilityProfile


class TeamSummary(BaseModel):
    size: int
    types: Dict[str, int]
    speed_distribution: Dict[str, int]
    role_distribution: Dict[str, int]


class TeamOffenseAnalysis(BaseModel):
    coverage_map: Dict[str, List[str]]
    coverage_gaps: List[str]
    coverage_redundancy: Dict[str, int]


class TeamDefenseAnalysis(BaseModel):
    top_threats: Dict[str, float]
    shared_weaknesses: Dict[str, int]
    coverage_gaps: List[str]
    resistances_summary: Dict[str, int]


class TeamAnalysisSummary(BaseModel):
    team_summary: TeamSummary
    offense_analysis: TeamOffenseAnalysis
    defense_analysis: TeamDefenseAnalysis
    pokemon_profiles: Dict[str, PokemonTeamProfile]


async def analyse_team(pokemon_names: List[str]) -> TeamAnalysisSummary:
    team_profiles = await _get_pokemon_profiles(
        pokemon_names, ["summary", "battle_profile"]
    )

    pokemon_profiles = {}
    type_counts = defaultdict(int)
    role_counts = defaultdict(int)
    speed_counts = defaultdict(int)
    coverage_map = defaultdict(list)
    offense_total_types = set()
    resistances_total = defaultdict(int)
    resistances_set = set()
    top_threats = {}
    weakness_counts = defaultdict(int)

    all_types = set(fetch_type_chart().keys())

    for name, profile in team_profiles.items():
        stats = profile["battle_profile"]["battle_stats"]
        types = profile["summary"]["identity"]["types"]

        for t in stats["type_defenses"]["resists_2x"]:
            resistances_total[t] += 1
            resistances_set.add(t)
        for t in stats["type_defenses"]["resists_4x"]:
            resistances_total[t] += 1
            resistances_set.add(t)
        for t in stats["type_defenses"]["immune_to"]:
            resistances_total[t] += 1
            resistances_set.add(t)

        for t in stats["type_defenses"]["weak_to_2x"]:
            weakness_counts[t] += 1
            top_threats[t] = max(top_threats.get(t, 0.0), 2.0)
        for t in stats["type_defenses"]["weak_to_4x"]:
            weakness_counts[t] += 1
            top_threats[t] = 4.0

        offense = PokemonOffenseProfile(**stats["type_offenses"])
        defense = PokemonVulnerabilityProfile(**stats["type_defenses"])
        roles = stats["roles"]
        speed = stats["speed_tier"]

        for t in types:
            type_counts[t] += 1
        for r in roles:
            role_counts[r] += 1
        speed_counts[speed] += 1

        for t in offense.super_effective_against:
            coverage_map[t].append(name)
            offense_total_types.add(t)

        pokemon_profiles[name] = PokemonTeamProfile(
            types=types,
            roles=roles,
            speed_tier=speed,
            offense=offense,
            defense=defense,
        )

    shared_weaknesses = {k: v for k, v in weakness_counts.items() if v > 1}
    coverage_gaps_off = sorted(list(all_types - offense_total_types))
    coverage_gaps_def = sorted(list(all_types - resistances_set))
    redundancy = {k: len(v) for k, v in coverage_map.items() if len(v) > 1}

    analysis = TeamAnalysisSummary(
        team_summary=TeamSummary(
            size=len(pokemon_names),
            types=dict(type_counts),
            role_distribution=dict(role_counts),
            speed_distribution=dict(speed_counts),
        ),
        offense_analysis=TeamOffenseAnalysis(
            coverage_map=dict(coverage_map),
            coverage_gaps=coverage_gaps_off,
            coverage_redundancy=redundancy,
        ),
        defense_analysis=TeamDefenseAnalysis(
            top_threats=top_threats,
            shared_weaknesses=shared_weaknesses,
            coverage_gaps=coverage_gaps_def,
            resistances_summary=dict(resistances_total),
        ),
        pokemon_profiles=pokemon_profiles,
    )

    pretty_print(analysis)
    return analysis
