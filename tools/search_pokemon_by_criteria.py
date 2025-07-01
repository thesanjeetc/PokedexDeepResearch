from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from dataset.utils import load_pokemon_dataset
from resources.enums import (
    VersionGroup,
    PokemonType,
    PokemonShape,
    PokemonColor,
    PokemonHabitat,
)

from enum import Enum


from enum import Enum


class PokemonRole(str, Enum):
    PHYSICAL_WALL = "physical-wall"
    SPECIAL_WALL = "special-wall"
    FAST_PHYSICAL_SWEEPER = "fast-physical-sweeper"
    FAST_SPECIAL_SWEEPER = "fast-special-sweeper"
    BULKY_PHYSICAL_ATTACKER = "bulky-physical-attacker"
    BULKY_SPECIAL_ATTACKER = "bulky-special-attacker"
    OFFENSIVE_PIVOT = "offensive-pivot"
    DEFENSIVE_PIVOT = "defensive-pivot"


class SpeedTier(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class StrategicRoleTag(str, Enum):
    PIVOT = "pivot"
    HAZARD_SETTER = "hazard-setter"
    HAZARD_REMOVER = "hazard-remover"
    SETUP_SWEEPER = "setup-sweeper"
    CLERIC = "cleric"
    SCOUT = "scout"
    STATUS_SPREADER = "status-spreader"
    SCREEN_SUPPORT = "screen-support"
    PHAZER = "phazer"
    TRICK_ROOM_SUPPORT = "trick-room-support"
    REDIRECTION = "redirection"
    TRAPPER = "trapper"
    PRIORITY_USER = "priority-user"


class AttackFocus(str, Enum):
    physical = "physical"
    special = "special"
    balanced = "balanced"


class DefenseCategory(str, Enum):
    fragile = "fragile"
    average = "average"
    bulky = "bulky"


class BaseStatTier(str, Enum):
    very_low = "very-low"
    low = "low"
    medium = "medium"
    high = "high"
    very_high = "very-high"


async def search_pokemon_by_criteria(
    include_types: Optional[List[PokemonType]] = None,
    exclude_types: Optional[List[PokemonType]] = None,
    include_roles: Optional[List[PokemonRole]] = None,
    speed_tiers: Optional[List[SpeedTier]] = None,
    attack_focus: Optional[List[AttackFocus]] = None,
    defense_categories: Optional[List[DefenseCategory]] = None,
    base_stat_tier: Optional[List[BaseStatTier]] = None,
    strategic_tags: Optional[List[StrategicRoleTag]] = None,
    required_resists: Optional[List[PokemonType]] = None,
    required_immunities: Optional[List[PokemonType]] = None,
    exclude_weaknesses: Optional[List[PokemonType]] = None,
    game_version: Optional[VersionGroup] = None,
    is_legendary: Optional[bool] = None,
    is_mythical: Optional[bool] = None,
    is_baby: Optional[bool] = None,
    shape: Optional[List[PokemonShape]] = None,
    color: Optional[List[PokemonColor]] = None,
    habitat: Optional[List[PokemonHabitat]] = None,
    limit: int = 25,
) -> List[dict]:
    df = load_pokemon_dataset()
    df = df.reset_index()

    if include_types:
        df = df[df["types"].apply(lambda x: any(t in x for t in include_types))]
        print(f"After include_types: {len(df)}")

    if not df.empty and exclude_types:
        df = df[~df["types"].apply(lambda x: any(t in x for t in exclude_types))]
        print(f"After exclude_types: {len(df)}")

    if not df.empty and include_roles:
        df = df[df["roles"].apply(lambda x: any(r in x for r in include_roles))]
        print(f"After include_roles: {len(df)}")

    if not df.empty and speed_tiers:
        df = df[df["speed_tier"].isin(speed_tiers)]
        print(f"After speed_tiers: {len(df)}")
    if not df.empty and attack_focus:
        df = df[df["attack_focus"].isin(attack_focus)]
        print(f"After attack_focus: {len(df)}")
    if not df.empty and defense_categories:
        df = df[df["defense_category"].isin(defense_categories)]
        print(f"After defense_categories: {len(df)}")
    if not df.empty and base_stat_tier:
        df = df[df["bst_tier"].isin(base_stat_tier)]
        print(f"After base_stat_tier: {len(df)}")
    if not df.empty and strategic_tags and game_version:
        df["game_moves"] = df["moves"].apply(lambda mv: mv.get(game_version, {}))
        df["strategic_tags"] = df["game_moves"].apply(
            lambda mv: mv.get("strategic_tags", []) if mv else []
        )
        df = df[
            df["strategic_tags"].apply(
                lambda tags: any(tag in tags for tag in strategic_tags)
            )
        ]
        print(f"After strategic_tags: {len(df)}")

    if not df.empty and required_resists:
        df = df[
            df["resists_2x"].apply(lambda x: all(t in x for t in required_resists))
            | df["resists_4x"].apply(lambda x: all(t in x for t in required_resists))
        ]
        print(f"After required_resists: {len(df)}")

    if not df.empty and required_immunities:
        df = df[
            df["immune_to"].apply(lambda x: all(t in x for t in required_immunities))
        ]
        print(f"After required_immunities: {len(df)}")

    if not df.empty and exclude_weaknesses:
        df = df[
            ~df["weak_to_2x"].apply(lambda x: any(t in x for t in exclude_weaknesses))
            & ~df["weak_to_4x"].apply(lambda x: any(t in x for t in exclude_weaknesses))
        ]
        print(f"After exclude_weaknesses: {len(df)}")

    if not df.empty and is_legendary is not None:
        df = df[df["is_legendary"] == is_legendary]
        print(f"After is_legendary: {len(df)}")

    if not df.empty and is_mythical is not None:
        df = df[df["is_mythical"] == is_mythical]
    print(f"After is_mythical: {len(df)}")

    if not df.empty and is_baby is not None:
        df = df[df["is_baby"] == is_baby]
    print(f"After is_baby: {len(df)}")

    if not df.empty and shape:
        df = df[df["shape"].isin(shape)]
        print(f"After shape: {len(df)}")

    if not df.empty and color:
        df = df[df["color"].isin(color)]
        print(f"After color: {len(df)}")

    if not df.empty and habitat:
        df = df[df["habitat"].isin(habitat)]
        print(f"After habitat: {len(df)}")

    selected_columns = [
        "name",
        "types",
        "speed_tier",
        "attack_focus",
        "defense_category",
        "bst_tier",
    ]

    return df.head(limit)[selected_columns].to_csv(index=False)
