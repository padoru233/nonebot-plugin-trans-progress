from datetime import datetime, timedelta

from .models import Episode

STAGE_TIMING_FIELDS = {
    1: ("started_trans", "completed_trans", "ddl_trans"),
    2: ("started_proof", "completed_proof", "ddl_proof"),
    3: ("started_type", "completed_type", "ddl_type"),
    4: ("started_supervision", "completed_supervision", "ddl_supervision"),
}
STAGE_DURATION = timedelta(days=14)


def deadline_from_start(start_time: datetime) -> datetime:
    return start_time + STAGE_DURATION


async def initialize_episode_schedule(episode: Episode, now: datetime | None = None):
    """Schedule only the oldest unfinished episode's current stage."""
    await episode.fetch_related("project", "proofreader")
    if not episode.project.auto_schedule:
        return

    current_episode = await Episode.filter(
        project=episode.project, status__lt=5
    ).order_by("id").first()
    if current_episode is None or current_episode.id != episode.id:
        return

    stage = episode.status
    if stage not in STAGE_TIMING_FIELDS:
        return
    if stage == 2 and not episode.needs_proofreading:
        return
    if stage == 2 and not episode.proofreader:
        changed = False
        for field in ("started_proof", "ddl_proof"):
            if getattr(episode, field) is not None:
                setattr(episode, field, None)
                changed = True
        if changed:
            await episode.save()
        return

    base_time = now or datetime.now()
    started_field, _, deadline_field = STAGE_TIMING_FIELDS[stage]
    if getattr(episode, deadline_field) is not None:
        return

    setattr(episode, started_field, base_time)
    setattr(episode, deadline_field, deadline_from_start(base_time))

    await episode.save()


async def record_stage_completion(
    episode: Episode, stage: int, completed_at: datetime | None = None
):
    """Record completion without scheduling future stages or episodes."""
    await episode.fetch_related("project")
    _, completed_field, _ = STAGE_TIMING_FIELDS[stage]
    completion_time = completed_at or datetime.now()
    setattr(episode, completed_field, completion_time)
    await episode.save()
