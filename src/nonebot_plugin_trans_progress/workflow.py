
from nonebot.adapters.onebot.v11 import Bot

from .utils import get_default_ddl
from .models import Episode
from .scheduling import (
    record_stage_completion,
    initialize_episode_schedule,
)
from .notifications import notify_episode_completed

STAGE_DETAILS = {
    1: ("翻译", "translator", "ddl_trans"),
    2: ("校对", "proofreader", "ddl_proof"),
    3: ("嵌字", "typesetter", "ddl_type"),
    4: ("监修", "supervisor", "ddl_supervision"),
}
SKIPPABLE_UNASSIGNED_STAGES = {2}


async def complete_episode(
    episode: Episode,
    actor_qq: str,
    actor_name: str,
    group_id: int,
    bot: Bot | None = None,
    allow_privileged: bool = False,
):
    await episode.fetch_related(
        "project",
        "translator",
        "proofreader",
        "typesetter",
        "supervisor",
    )
    await episode.project.fetch_related("leader")

    current_status = episode.status
    if current_status == 5:
        raise ValueError("✅ 这个任务已经是完结状态啦")
    if current_status not in STAGE_DETAILS:
        raise ValueError("⚠️ 这个任务还没在后台分配人员呢，先去Web端把锅分好再说吧！")

    stage_name, assignee_field, _ = STAGE_DETAILS[current_status]
    assignee = getattr(episode, assignee_field)
    future_assignees = [
        getattr(episode, field)
        for _, field, _ in (
            STAGE_DETAILS[stage] for stage in range(current_status, 5)
        )
    ]
    can_submit = any(
        user and user.qq_id == str(actor_qq) for user in future_assignees
    )
    if not (can_submit or allow_privileged):
        target_user_name = assignee.name if assignee else "未分配"
        raise PermissionError(
            f"🙅‍♀️ 达咩！不可以操作！\n"
            f"当前是【{stage_name}】阶段，负责人是: {target_user_name}\n"
            "仅当前或后续工序负责人、组长和管理员可以交稿哦~"
        )

    skipped_stages = []
    while episode.status < 5:
        stage = episode.status
        await record_stage_completion(episode, stage)
        episode.status = stage + 1
        if episode.status == 5:
            break

        next_role, next_field, next_ddl_field = STAGE_DETAILS[episode.status]
        next_user = getattr(episode, next_field)
        if next_user or episode.status not in SKIPPABLE_UNASSIGNED_STAGES:
            if (
                next_user
                and
                not episode.project.auto_schedule
                and getattr(episode, next_ddl_field) is None
            ):
                setattr(episode, next_ddl_field, get_default_ddl())
            break
        skipped_stages.append(next_role)

    await episode.save()
    if episode.status < 5:
        await initialize_episode_schedule(episode)

    result_lines = [f"{episode.project.name} {episode.title}", f"{stage_name}已完成"]
    if skipped_stages:
        result_lines.append(f"已自动跳过未分配工序：{'、'.join(skipped_stages)}")
    if not allow_privileged and (not assignee or assignee.qq_id != str(actor_qq)):
        result_lines.append(f"由 {actor_name} 代提交")
    mentioned_qq_ids = set()
    if episode.status == 5:
        result_lines.append("全部工序已完结，准备发布")
        target_qq = episode.project.leader.qq_id if episode.project.leader else None
        if not target_qq and bot:
            try:
                members = await bot.get_group_member_list(group_id=group_id)
                owner = next(
                    (member for member in members if member["role"] == "owner"),
                    None,
                )
                if owner:
                    target_qq = str(owner["user_id"])
            except Exception:
                pass
        if target_qq:
            mentioned_qq_ids.add(target_qq)
        else:
            result_lines.append("请管理员查收发布")
    else:
        next_role, next_field, next_ddl_field = STAGE_DETAILS[episode.status]
        next_user = getattr(episode, next_field)
        result_lines.append(f"下一阶段: {next_role}")
        next_ddl = getattr(episode, next_ddl_field)
        if next_ddl:
            result_lines.append(f"截止日期: {next_ddl.strftime('%m-%d')}")
        if next_user:
            mentioned_qq_ids.add(next_user.qq_id)
        else:
            result_lines.append("下一阶段尚未分配负责人")

    await notify_episode_completed(group_id, result_lines, mentioned_qq_ids, bot)
    return episode
