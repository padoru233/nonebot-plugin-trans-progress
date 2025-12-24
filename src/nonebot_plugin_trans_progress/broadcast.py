from datetime import datetime
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .models import Episode, GroupSetting
from .utils import send_group_message

async def check_and_send_broadcast(group_id: str, is_manual: bool = False):
    """
    检查指定群的死线并发送播报
    is_manual: 是否为手动触发（手动触发时，即使没到死线也可以播报进度，或者只播报超期的，这里按原有逻辑只播报超期/今日截止）
    """
    now = datetime.now()
    today_date = now.date()

    # 1. 获取该群所有未完结任务
    active_eps = await Episode.filter(
        status__in=[1, 2, 3],
        project__group_id=group_id
    ).prefetch_related('project', 'translator', 'proofreader', 'typesetter')

    if not active_eps:
        if is_manual:
            await send_group_message(int(group_id), Message("🔍 当前没有进行中的任务。"))
        return

    msg_list = []

    for ep in active_eps:
        # 确定当前工序
        stage_name = ""
        target_user = None
        current_ddl = None

        if ep.status == 1:
            stage_name, target_user, current_ddl = "翻译", ep.translator, ep.ddl_trans
        elif ep.status == 2:
            stage_name, target_user, current_ddl = "校对", ep.proofreader, ep.ddl_proof
        elif ep.status == 3:
            stage_name, target_user, current_ddl = "嵌字", ep.typesetter, ep.ddl_type

        if not current_ddl:
            continue

        ddl_date = current_ddl.date()

        # 判定逻辑：
        # 如果是自动播报，只播报 [超期] 或 [今天截止]
        # 如果是手动一键提醒 (is_manual=True)，我们可以放宽条件，或者保持一致。这里保持一致，只提醒紧迫任务。

        prefix = ""
        is_urgent = False

        if ddl_date < today_date:
            days = (today_date - ddl_date).days
            prefix = f"❌ [超期{days}天]"
            is_urgent = True
        elif ddl_date == today_date:
            prefix = "⚠️ [今天截止]"
            is_urgent = True

        # 如果手动触发，即使没超期也可以显示一下进度（可选），这里仅显示紧迫的
        if is_urgent or is_manual:
            # 如果是手动触发但未超期，给个普通前缀
            if not prefix: prefix = "⏳ [进行中]"

            line = Message(f"{prefix} {ep.project.name} {ep.title} ({stage_name}) ")
            if target_user:
                line += MessageSegment.at(target_user.qq_id)
            else:
                line += Message("未分配")
            line += Message("\n")
            msg_list.append(line)

    if msg_list:
        title = "🔔 催更提醒" if is_manual else f"📅 每日死线播报 ({now.strftime('%m-%d')})"
        final_message = Message(f"{title}：\n")
        for m in msg_list:
            final_message += m

        if is_manual:
            final_message += Message("\n(管理员手动触发)")
        else:
            final_message += Message("\n加油！")

        await send_group_message(int(group_id), final_message)
    elif is_manual:
        # 手动触发但没有需要催更的任务
        await send_group_message(int(group_id), Message("✅ 当前所有任务都在死线内，暂无需催更。"))
