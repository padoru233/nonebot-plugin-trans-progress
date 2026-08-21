from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import logger

from .models import Episode, GroupSetting
from .notifications import notify_deadline_broadcast

BROADCAST_TIMEZONE = ZoneInfo("Asia/Shanghai")


async def check_and_send_broadcast(
    group_id: str, is_manual: bool = False, now: datetime | None = None
):
    """
    播报逻辑：
    1. 无论是自动还是手动，只播报 [今天截止] 和 [已超期] 的任务。
    2. 不去重 At，每个任务行后面紧跟负责人的 At。
    """
    now = now or datetime.now(BROADCAST_TIMEZONE)
    today_date = now.date()

    # 1. 获取该群所有未完结任务
    active_eps = await Episode.filter(
        status__in=[1, 2, 3, 4],
        project__group_id=group_id
    ).prefetch_related('project', 'translator', 'proofreader', 'typesetter', 'supervisor')

    lines = []
    mentioned_qq_ids = set()

    for ep in active_eps:
        stage_name = ""
        target_user = None
        current_ddl = None

        if ep.status == 1:
            stage_name, target_user, current_ddl = "翻译", ep.translator, ep.ddl_trans
        elif ep.status == 2:
            stage_name, target_user, current_ddl = "校对", ep.proofreader, ep.ddl_proof
        elif ep.status == 3:
            stage_name, target_user, current_ddl = "嵌字", ep.typesetter, ep.ddl_type
        elif ep.status == 4:
            stage_name, target_user, current_ddl = "监修", ep.supervisor, ep.ddl_supervision

        if not current_ddl:
            continue

        ddl_date = current_ddl.date()

        # === 核心逻辑：严厉过滤 ===
        # 只要 DDL 在今天之后，就认为是安全的，绝对不播报
        if ddl_date > today_date:
            continue

        prefix = ""
        if ddl_date < today_date:
            days = (today_date - ddl_date).days
            prefix = f"💢 [拖了{days}天啦]"
        elif ddl_date == today_date:
            prefix = "🔥 [就在今天!]"

        if target_user:
            mentioned_qq_ids.add(target_user.qq_id)
        else:
            stage_name = f"{stage_name}, 未分配"
        lines.append(f"{prefix} {ep.project.name} {ep.title} ({stage_name})")

    # 发送逻辑
    if lines:
        title = "🔔 这种事情不可以忘记哦" if is_manual else f"📅 早安！来看看今天的死线战士 ({now.strftime('%m-%d')})"
        await notify_deadline_broadcast(group_id, title, lines, mentioned_qq_ids)

    elif is_manual:
        # 手动触发，但没有超期任务
        await notify_deadline_broadcast(
            group_id, "催更提醒", ["暂无到期或逾期任务"], set()
        )
