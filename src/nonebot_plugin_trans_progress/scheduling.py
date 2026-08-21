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
    """Use the preceding episode's actual stage completion as each stage anchor."""
    base_time = now or datetime.now()
    previous_episodes = await Episode.filter(
        project=episode.project, id__lt=episode.id
    ).order_by("-id")

    for stage, (started_field, completed_field, deadline_field) in (
        STAGE_TIMING_FIELDS.items()
    ):
        start_time = next(
            (
                completed_at
                for previous in previous_episodes
                if (completed_at := getattr(previous, completed_field)) is not None
            ),
            base_time + STAGE_DURATION * (stage - 1),
        )
        setattr(episode, started_field, start_time)
        setattr(episode, deadline_field, deadline_from_start(start_time))

    await episode.save()


async def record_stage_completion(
    episode: Episode, stage: int, completed_at: datetime | None = None
):
    """Carry a completed stage's time to the oldest eligible following episode."""
    started_field, completed_field, deadline_field = STAGE_TIMING_FIELDS[stage]
    completion_time = completed_at or datetime.now()
    setattr(episode, completed_field, completion_time)

    if episode.auto_schedule and stage < 4:
        next_started_field, _, next_deadline_field = STAGE_TIMING_FIELDS[stage + 1]
        setattr(episode, next_started_field, completion_time)
        setattr(episode, next_deadline_field, deadline_from_start(completion_time))
    await episode.save()

    following_episodes = await Episode.filter(
        project=episode.project,
        id__gt=episode.id,
        status__lt=5,
        auto_schedule=True,
    ).order_by("id")
    next_episode = next(
        (
            candidate
            for candidate in following_episodes
            if getattr(candidate, completed_field) is None
        ),
        None,
    )
    if not next_episode:
        return None

    setattr(next_episode, started_field, completion_time)
    setattr(next_episode, deadline_field, deadline_from_start(completion_time))
    await next_episode.save()
    return next_episode