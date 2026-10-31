"""Evaluation use-case: cache-aside lookup of a flag's rules, then the pure engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.cache import FlagConfigCache
from app.engine import EvaluationResult, FlagRuleSet, Reason, evaluate
from app.models import Flag, FlagConfig
from app.repositories.flags import FlagRepository

Source = Literal["cache", "database", "database_cache_unavailable"]


@dataclass(frozen=True, slots=True)
class Outcome:
    flag_key: str
    environment: str
    result: EvaluationResult
    source: Source
    rollout_percentage: int | None


def to_rules(flag: Flag, config: FlagConfig) -> FlagRuleSet:
    return FlagRuleSet(
        flag_key=flag.key,
        environment=config.environment,
        enabled=config.enabled,
        kill_switch=config.kill_switch,
        rollout_percentage=config.rollout_percentage,
        included_users=frozenset(config.included_users),
        excluded_users=frozenset(config.excluded_users),
        archived=flag.archived_at is not None,
        version=config.version,
    )


class EvaluationService:
    def __init__(self, db: Session, cache: FlagConfigCache) -> None:
        self.db = db
        self.cache = cache

    def load_rules(self, environment: str, flag_key: str) -> tuple[FlagRuleSet | None, Source]:
        lookup = self.cache.get(environment, flag_key)
        if lookup.status == "hit":
            return (lookup.rules if lookup.found else None), "cache"

        row = FlagRepository(self.db).get_config_for_evaluation(environment, flag_key)
        # Redis down -> we still answer correctly from PostgreSQL ("degraded" but not broken).
        source: Source = "database" if lookup.status == "miss" else "database_cache_unavailable"
        if row is None:
            self.cache.set_missing(environment, flag_key)
            return None, source
        rules = to_rules(*row)
        self.cache.set(rules)
        return rules, source

    def evaluate(self, environment: str, flag_key: str, user_id: str) -> Outcome:
        rules, source = self.load_rules(environment, flag_key)
        if rules is None:
            return Outcome(flag_key, environment, EvaluationResult(False, Reason.FLAG_NOT_FOUND), source, None)
        return Outcome(flag_key, environment, evaluate(rules, user_id), source, rules.rollout_percentage)
