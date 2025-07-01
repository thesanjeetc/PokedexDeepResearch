import asyncio
import json
from typing import Dict, List
from collections import defaultdict
from pydantic import BaseModel
from dataset.type_chart import fetch_type_chart
from dataset.utils import load_pokemon_dataset
from resources.enums import VersionGroup
from typing import Optional


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
    strategic_distribution: Dict[str, int]


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


async def analyse_pokemon_team(
    pokemon_names: List[str], game_version: Optional[VersionGroup] = None
) -> TeamAnalysisSummary:
    """
    Analyzes a team of Pokémon and returns detailed offensive and defensive summaries,
    including weaknesses, resistances, and strategic role distributions.

    This tool is ideal for evaluating team synergy, identifying coverage gaps,
    and understanding potential threats based on type matchups and battle roles.

    Args:
        pokemon_names (List[str]): List of Pokémon names to analyze. Must match dataset names.
        game_version (VersionGroup, optional): Game version to extract strategic role tags
                                               from movesets. Affects strategic role distribution.

    Returns:
        TeamAnalysisSummary: An object containing:
            - team_summary: Basic breakdown (types, roles, speed tiers, strategic tags).
            - offense_analysis:
                - coverage_map: Types this team can hit super-effectively, and who provides it.
                - coverage_gaps: Types the team lacks effective coverage against.
                - coverage_redundancy: How many Pokémon overlap in each type's coverage.
            - defense_analysis:
                - top_threats: Types that deal the most collective damage to the team.
                - shared_weaknesses: Types multiple teammates are weak to.
                - coverage_gaps: Types the team does not resist or block.
                - resistances_summary: Count of how many Pokémon resist each type.
            - pokemon_profiles: Simplified battle-focused profiles for each Pokémon, including
                                offensive/defensive typing, roles, and speed tier.
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

        offense = PokemonOffenseProfile(
            super_effective_against=profile["super_effective_against"],
            not_very_effective_against=profile["not_very_effective_against"],
            no_effect_against=profile["no_effect_against"],
        )
        defense = PokemonVulnerabilityProfile(
            immune_to=profile["immune_to"],
            resists_4x=profile["resists_4x"],
            resists_2x=profile["resists_2x"],
            weak_to_2x=profile["weak_to_2x"],
            weak_to_4x=profile["weak_to_4x"],
        )

        roles = profile["roles"]
        speed = profile["speed_tier"]

        for t in profile["types"]:
            type_counts[t] += 1
        for r in roles:
            role_counts[r] += 1
        speed_counts[speed] += 1

        for t in offense.super_effective_against:
            coverage_map[t].append(name)
            offense_total_types.add(t)

        pokemon_profiles[name] = PokemonTeamProfile(
            types=profile["types"],
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
            strategic_distribution=dict(strategic_counts),
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

    return analysis
