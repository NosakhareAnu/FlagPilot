from sqlalchemy.orm import Session

from app.models import ENVIRONMENT_KEYS
from app.repositories.flags import AuditRepository, FlagRepository
from app.schemas.flags import AuditEventOut, EnvironmentStats, StatsOut


def build_stats(db: Session) -> StatsOut:
    counts = FlagRepository(db).counts()
    envs = {env: EnvironmentStats(enabled=0, disabled=0) for env in ENVIRONMENT_KEYS}
    for environment, enabled, n in counts["env_rows"]:
        if enabled:
            envs[environment].enabled = n
        else:
            envs[environment].disabled = n
    events, _ = AuditRepository(db).list(limit=8, offset=0)
    return StatsOut(
        total_flags=counts["total"],
        active_flags=counts["total"] - counts["archived"],
        archived_flags=counts["archived"],
        environments=envs,
        recent_events=[AuditEventOut.model_validate(e) for e in events],
    )
