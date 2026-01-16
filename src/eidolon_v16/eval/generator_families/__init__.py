from __future__ import annotations

from eidolon_v16.eval.generator_families.base import GeneratorFamily
from eidolon_v16.eval.generator_families.family_absmax import AbsMaxFamily
from eidolon_v16.eval.generator_families.family_lists import ListsFamily
from eidolon_v16.eval.generator_families.family_ruleshift import RuleShiftFamily


def get_generator_families() -> list[GeneratorFamily]:
    return [AbsMaxFamily(), ListsFamily(), RuleShiftFamily()]
