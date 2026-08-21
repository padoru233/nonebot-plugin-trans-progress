from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from .models import Episode, Project
from .utils import send_group_message
from .view_renderer import ColorPalette, MINT_PALETTE, RenderModule, render_modules


async def send_image_notification(
    group_id: str,
    title: str,
    modules: list[RenderModule],
    mentioned_qq_ids: set[str] | None = None,
    palette: ColorPalette = MINT_PALETTE,
    bot: Bot | None = None,
) -> None:
    """Render a notification image and mention each target at most once."""
    image = render_modules(title, modules, palette)[0]
    message = Message(MessageSegment.image(image))
    for qq_id in sorted(mentioned_qq_ids or set()):
        message += MessageSegment.at(qq_id)

    await send_group_message(int(group_id), message, bot=bot)


async def notify_episode_created(
    project: Project, episode: Episode, group_id: str
) -> None:
    """Send one consistent notification for every newly created episode."""
    assignments = (
        ("翻译", episode.translator),
        ("校对", episode.proofreader),
        ("嵌字", episode.typesetter),
        ("监修", episode.supervisor),
    )
    task_lines = [f"{project.name} {episode.title}"]
    task_lines.extend(
        f"{role}: {user.name if user else '未分配'}"
        for role, user in assignments
    )
    await send_image_notification(
        group_id,
        "新任务",
        [RenderModule("任务安排", task_lines)],
        {user.qq_id for _, user in assignments if user},
    )


async def notify_episode_updated(
    project: Project,
    episode: Episode,
    group_id: str,
    changes: list[str],
    mentioned_qq_ids: set[str],
) -> None:
    """Send a consistent image notification for episode changes."""
    await send_image_notification(
        group_id,
        "情报变更",
        [RenderModule(f"{project.name} {episode.title}", changes)],
        mentioned_qq_ids,
    )


async def notify_project_created(
    project: Project,
    group_id: str,
    aliases: list[str] | None = None,
    tags: list[str] | None = None,
) -> None:
    """Send a consistent notification when a project is created."""
    await project.fetch_related(
        "leader",
        "default_translator",
        "default_proofreader",
        "default_typesetter",
        "default_supervisor",
    )
    assignments = (
        ("负责人", project.leader),
        ("默认翻译", project.default_translator),
        ("默认校对", project.default_proofreader),
        ("默认嵌字", project.default_typesetter),
        ("默认监修", project.default_supervisor),
    )
    lines = [project.name]
    if aliases:
        lines.append(f"别名: {', '.join(aliases)}")
    if tags:
        lines.append(f"标签: {', '.join(tags)}")
    lines.extend(
        f"{role}: {user.name if user else '未分配'}"
        for role, user in assignments
    )
    await send_image_notification(
        group_id,
        "新坑开张",
        [RenderModule("项目安排", lines)],
        {user.qq_id for _, user in assignments if user},
    )


async def notify_episode_manually_completed(
    project: Project, episode: Episode, group_id: str
) -> None:
    """Send a consistent notification when an administrator finishes an episode."""
    await send_image_notification(
        group_id,
        "任务完结",
        [RenderModule("处理结果", [f"{project.name} {episode.title}", "已由管理员手动完结"])],
    )


async def notify_episode_member_removed(
    project: Project, episode: Episode, group_id: str, user_name: str, role: str
) -> None:
    """Send a consistent notification for an episode member removal."""
    await send_image_notification(
        group_id,
        "成员变动",
        [RenderModule(f"{project.name} {episode.title}", [f"{user_name} 已移出 {role}"])],
    )


async def notify_episode_completed(
    group_id: str,
    lines: list[str],
    mentioned_qq_ids: set[str] | None = None,
    bot: Bot | None = None,
) -> None:
    """Send a consistent notification for an episode completion."""
    await send_image_notification(
        group_id,
        "任务完成",
        [RenderModule("处理结果", lines)],
        mentioned_qq_ids,
        bot=bot,
    )


async def notify_deadline_broadcast(
    group_id: str, title: str, lines: list[str], mentioned_qq_ids: set[str]
) -> None:
    """Send a consistent image notification for a deadline broadcast."""
    await send_image_notification(
        group_id,
        title,
        [RenderModule("待处理任务", lines)],
        mentioned_qq_ids,
    )