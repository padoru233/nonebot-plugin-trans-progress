from datetime import datetime
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from .models import Episode, GroupSetting
from .utils import send_group_message

async def check_and_send_broadcast(group_id: str, is_manual: bool = False):
    """
    播报逻辑：
    1. 无论是自动还是手动，只播报 [今天截止] 和 [已超期] 的任务。
    2. 不去重 At，每个任务行后面紧跟负责人的 At。
    """
    now = datetime.now()
    today_date = now.date()

    # 1. 获取该群所有未完结任务
    active_eps = await Episode.filter(
        status__in=[1, 2, 3],
        project__group_id=group_id
    ).prefetch_related('project', 'translator', 'proofreader', 'typesetter')

    msg_list = []

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

        # === 核心逻辑：不去重 At ===
        line = Message(f"{prefix} [{ep.project.name} {ep.title}] ({stage_name}) ")

        if target_user:
            line += MessageSegment.at(target_user.qq_id)
        else:
            line += Message("👻 (还没人认领)")

        line += Message("\n")
        msg_list.append(line)

    # 发送逻辑
    if msg_list:
        title = "🔔 这种事情不可以忘记哦" if is_manual else f"📅 早安！来看看今天的死线战士 ({now.strftime('%m-%d')})"
        final_message = Message(f"{title}：\n")
        for m in msg_list:
            final_message += m

        final_message += Message("\n大家的肝还好吗？做不完的话记得在群里喊一声哦~ 💪")
        await send_group_message(int(group_id), final_message)

    elif is_manual:
        # 手动触发，但没有超期任务
        await send_group_message(int(group_id), Message("☕ 居然没有要催的任务？大家休息一下吧~"))
