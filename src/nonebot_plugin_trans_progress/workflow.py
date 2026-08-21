from typing import Optional

from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from .models import Episode
from .utils import get_default_ddl, send_group_message
from .scheduling import record_stage_completion


async def complete_episode(
    episode: Episode,
    actor_qq: str,
    actor_name: str,
    group_id: int,
    bot: Optional[Bot] = None,
):
    await episode.fetch_related(
        "project",
        "project__leader",
        "translator",
        "proofreader",
        "typesetter",
        "supervisor",
    )

    current_status = episode.status
    assignee = None
    stage_name = ""
    if current_status == 1:
        stage_name, assignee = "翻译", episode.translator
    elif current_status == 2:
        stage_name, assignee = "校对", episode.proofreader
    elif current_status == 3:
        stage_name, assignee = "嵌字", episode.typesetter
    elif current_status == 4:
        stage_name, assignee = "监修", episode.supervisor
    elif current_status == 5:
        raise ValueError("✅ 这个任务已经是完结状态啦")
    else:
        raise ValueError("⚠️ 这个任务还没在后台分配人员呢，先去Web端把锅分好再说吧！")

    if not assignee or assignee.qq_id != str(actor_qq):
        target_user_name = assignee.name if assignee else "未分配"
        raise PermissionError(
            f"🙅‍♀️ 达咩！不可以操作！\n"
            f"当前是【{stage_name}】阶段，负责人是: {target_user_name}\n"
            "只有当前负责人才能交稿哦~"
        )

    next_role = ""
    next_user = None
    await record_stage_completion(episode, current_status)
    if current_status == 1:
        episode.status = 2
        if not episode.ddl_proof:
            episode.ddl_proof = get_default_ddl()
        next_role, next_user = "校对", episode.proofreader
    elif current_status == 2:
        episode.status = 3
        if not episode.ddl_type:
            episode.ddl_type = get_default_ddl()
        next_role, next_user = "嵌字", episode.typesetter
    elif current_status == 3:
        episode.status = 4
        if not episode.ddl_supervision:
            episode.ddl_supervision = get_default_ddl()
        next_role, next_user = "监修", episode.supervisor
    else:
        episode.status = 5
        next_role = "发布"

    await episode.save()

    reply = Message(
        f"🎉 辛苦啦！[{episode.project.name} {episode.title}] {stage_name}搞定！✨\n"
    )
    if episode.status == 5:
        reply += Message("🎆 撒花！全工序完结！")
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
            reply += Message("\n请 ") + MessageSegment.at(target_qq) + Message(" 查收，准备发布啦~ 🚀")
        else:
            reply += Message("\n请管理员查收发布")
    else:
        reply += Message(f"➡️ 进入 [{next_role}] 阶段\n")
        next_ddl = None
        if episode.status == 2:
            next_ddl = episode.ddl_proof
        elif episode.status == 3:
            next_ddl = episode.ddl_type
        elif episode.status == 4:
            next_ddl = episode.ddl_supervision
        if next_ddl:
            reply += Message(f"📅 死线: {next_ddl.strftime('%m-%d')}\n")
        if next_user:
            reply += Message("接力棒交给你啦！") + MessageSegment.at(
                next_user.qq_id
            ) + Message(" 拜托了捏~ 🙏")
        else:
            reply += Message("⚠️ 哎呀，下一棒还没人接手！组长快来分锅！🍲")

    await send_group_message(group_id, reply, bot=bot)
    return episode