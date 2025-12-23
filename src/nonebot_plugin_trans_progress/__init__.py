from nonebot import on_command, require, get_driver, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from tortoise import Tortoise
from tortoise.queryset import Q

require("nonebot_plugin_apscheduler")

from .models import Project, Episode, User
# 引入 send_group_message
from .utils import get_default_ddl, send_group_message
from .web import app as web_app
from .config import Config

driver = get_driver()
plugin_config = get_plugin_config(Config)

MODELS_PATH = [f"{__name__}.models"]

@driver.on_startup
async def init_db():
    db_url = plugin_config.trans_db_url
    logger.info(f"正在连接数据库 ...")
    try:
        await Tortoise.init(
            db_url=db_url,
            modules={"models": MODELS_PATH}
        )
        await Tortoise.generate_schemas(safe=True)
        logger.info("数据库连接成功！")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        raise e

@driver.on_shutdown
async def close_db():
    logger.info("正在关闭数据库连接...")
    await Tortoise.close_connections()

@driver.on_startup
async def init_web():
    app = driver.server_app
    app.include_router(web_app, prefix="/trans", tags=["汉化进度管理"])

# ----------------- Bot 指令逻辑 -----------------

# 1. 帮助指令
cmd_help = on_command("帮助", aliases={"help", "菜单"}, priority=5, block=True)

@cmd_help.handle()
async def _():
    msg = (
        "🤖 汉化进度管理 Bot 指令\n"
        "-----------------------------\n"
        "1. 查看进度:\n"
        "   查看 (列出所有项目)\n"
        "   查看 <项目名> (查看该项目详情)\n"
        "   查看 <项目名> <话数> (查看具体某话)\n\n"
        "2. 更新进度:\n"
        "   完成 <项目名> <话数> \n"
        "   (状态流转: 翻->校->嵌->完，自动At下一位)\n\n"
        "3. Web后台:\n"
        "   访问 http://<你的IP>:端口/trans/\n"
        "   (支持新建项目、分配人员、修改死线)"
    )
    # 帮助指令简单回复，直接 finish 即可，或者也改成 send_group_message
    await cmd_help.finish(msg)


# 2. 完成指令
cmd_finish = on_command("完成", aliases={"done", "交稿"}, priority=5, block=True)

@cmd_finish.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    msg = args.extract_plain_text().strip().split()
    if len(msg) < 2:
        await cmd_finish.finish("❌ 格式错误，请使用: 完成 <项目名> <话数>")

    proj_name_or_alias, ep_title = msg[0], msg[1]
    qq_id = str(event.user_id)

    # 1. 查询项目
    project = await Project.filter(
        Q(name=proj_name_or_alias) | Q(alias=proj_name_or_alias)
    ).prefetch_related('leader').first()

    if not project:
        await cmd_finish.finish(f"❌ 未找到项目: {proj_name_or_alias}")

    # 2. 查询话数
    episode = await Episode.get_or_none(project=project, title=ep_title).prefetch_related(
        'translator', 'proofreader', 'typesetter'
    )
    if not episode:
        await cmd_finish.finish(f"❌ 未找到话数: {ep_title}")

    # 3. 权限检查
    current_status = episode.status

    is_leader = (project.leader and project.leader.qq_id == qq_id)
    is_group_admin = event.sender.role in ["owner", "admin"]
    is_assignee = False

    stage_name = ""
    target_user_name = "未分配"

    if current_status == 1:
        stage_name = "翻译"
        if episode.translator:
            target_user_name = episode.translator.name
            if episode.translator.qq_id == qq_id: is_assignee = True
    elif current_status == 2:
        stage_name = "校对"
        if episode.proofreader:
            target_user_name = episode.proofreader.name
            if episode.proofreader.qq_id == qq_id: is_assignee = True
    elif current_status == 3:
        stage_name = "嵌字"
        if episode.typesetter:
            target_user_name = episode.typesetter.name
            if episode.typesetter.qq_id == qq_id: is_assignee = True
    elif current_status == 4:
        await cmd_finish.finish("✅ 该任务已是完结状态")
    else:
        await cmd_finish.finish("⚠️ 任务尚未开始，请先在Web端分配人员")

    if not (is_assignee or is_leader or is_group_admin):
        await cmd_finish.finish(
            f"⛔ 权限不足！\n"
            f"当前处于【{stage_name}】阶段，负责人是: {target_user_name}\n"
            f"仅限本人、项目组长或群管操作。"
        )

    # 4. 状态流转
    next_role = ""
    next_user = None

    if current_status == 1:
        episode.status = 2
        if not episode.ddl_proof: episode.ddl_proof = get_default_ddl()
        next_role = "校对"
        next_user = episode.proofreader
    elif current_status == 2:
        episode.status = 3
        if not episode.ddl_type: episode.ddl_type = get_default_ddl()
        next_role = "嵌字"
        next_user = episode.typesetter
    elif current_status == 3:
        episode.status = 4
        next_role = "发布"
        next_user = None

    await episode.save()

    # 5. 发送反馈
    status_text = ['','翻译','校对','嵌字'][current_status]

    reply = Message(f"✅ [{project.name} {ep_title}] {status_text}完成！")
    if not is_assignee:
        reply += Message(f" (由 {event.sender.card or event.sender.nickname} 代提交)")
    reply += Message("\n")

    if episode.status == 4:
        reply += Message("🎉 全工序完结！")
        target_qq = None
        if project.leader:
            target_qq = project.leader.qq_id
        else:
            try:
                mlist = await bot.get_group_member_list(group_id=int(event.group_id))
                owner = next((m for m in mlist if m['role'] == 'owner'), None)
                if owner: target_qq = str(owner['user_id'])
            except Exception as e:
                logger.warning(f"获取群主失败: {e}")

        if target_qq:
            reply += Message("\n请 ") + MessageSegment.at(target_qq) + Message(" 查收发布。")
        else:
            reply += Message("\n请管理员查收发布。")
    else:
        reply += Message(f"➡️ 进入 [{next_role}] 阶段\n")
        next_ddl = episode.ddl_proof if episode.status == 2 else episode.ddl_type
        if next_ddl:
            reply += Message(f"📅 死线: {next_ddl.strftime('%m-%d')}\n")
        if next_user:
            reply += Message("请 ") + MessageSegment.at(next_user.qq_id) + Message(" 接手")
        else:
            reply += Message("⚠️ 下一阶段未分配人员！")

    # 使用通用发送函数
    await send_group_message(int(event.group_id), reply)
    await cmd_finish.finish()


# 3. 查看指令
cmd_view = on_command("查看", aliases={"查看项目", "view", "进度", "项目列表"}, priority=5, block=True)

@cmd_view.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    msg = args.extract_plain_text().strip().split()

    if not msg or msg[0] in ["全部", "所有", "列表", "list", "all"]:
        projects = await Project.all().prefetch_related(
            'leader', 'default_translator', 'default_proofreader', 'default_typesetter'
        )
        if not projects:
            await cmd_view.finish("📭 当前没有任何项目，请去Web端新建。")

        reply = "📊 **所有项目一览**\n"
        for p in projects:
            reply += f"\n📌 {p.name}"
            if p.alias: reply += f" ({p.alias})"

            g_name = p.group_name or "未同步群名"
            reply += f"\n   群: {g_name} ({p.group_id})"

            if p.leader: reply += f" | 👑 {p.leader.name}"

            dt = p.default_translator.name if p.default_translator else "-"
            dp = p.default_proofreader.name if p.default_proofreader else "-"
            dty = p.default_typesetter.name if p.default_typesetter else "-"
            if dt != "-" or dp != "-" or dty != "-":
                reply += f"\n   🛡️ 默认: 翻[{dt}] 校[{dp}] 嵌[{dty}]"

        await cmd_view.finish(reply.strip())

    target_name = msg[0]
    target_ep = msg[1] if len(msg) > 1 else None

    project = await Project.filter(
        Q(name=target_name) | Q(alias=target_name)
    ).prefetch_related(
        'leader', 'default_translator', 'default_proofreader', 'default_typesetter'
    ).first()

    if not project:
        await cmd_view.finish(f"❌ 未找到项目: {target_name}\n请发送“查看”获取项目列表")

    if target_ep:
        episode = await Episode.get_or_none(project=project, title=target_ep).prefetch_related(
            'translator', 'proofreader', 'typesetter'
        )
        if not episode:
            await cmd_view.finish(f"❌ 未找到 {project.name} 的 {target_ep}")

        def fmt_role(user, ddl):
            u_name = user.name if user else "❌未分配"
            d_str = ddl.strftime('%m-%d') if ddl else "♾️无死线"
            return f"{u_name} (📅{d_str})"

        status_map = {0:'⚪未开始', 1:'🔵翻译中', 2:'🟠校对中', 3:'🟢嵌字中', 4:'✅已完结'}

        reply = f"📝 【{project.name} {episode.title}】\n"
        reply += f"状态: {status_map.get(episode.status)}\n"
        reply += f"----------------\n"
        reply += f"翻译: {fmt_role(episode.translator, episode.ddl_trans)}\n"
        reply += f"校对: {fmt_role(episode.proofreader, episode.ddl_proof)}\n"
        reply += f"嵌字: {fmt_role(episode.typesetter, episode.ddl_type)}"

        await cmd_view.finish(reply)

    else:
        active_eps = await Episode.filter(project=project, status__lt=4).order_by('id').all()

        reply = f"📊 【{project.name}】"
        if project.alias: reply += f" ({project.alias})"
        reply += "\n"
        if project.leader: reply += f"👑 组长: {project.leader.name}\n"

        dt = project.default_translator.name if project.default_translator else "无"
        dp = project.default_proofreader.name if project.default_proofreader else "无"
        dty = project.default_typesetter.name if project.default_typesetter else "无"
        reply += f"🛡️ 默认: 翻[{dt}] 校[{dp}] 嵌[{dty}]\n"
        reply += f"----------------\n"

        if not active_eps:
            reply += "🎉 当前无进行中任务 (全部完结或未添加)"
        else:
            reply += f"🔥 进行中 ({len(active_eps)}):\n"
            for ep in active_eps:
                s_map = {0:'未', 1:'翻', 2:'校', 3:'嵌'}
                curr_ddl = None
                if ep.status == 1: curr_ddl = ep.ddl_trans
                elif ep.status == 2: curr_ddl = ep.ddl_proof
                elif ep.status == 3: curr_ddl = ep.ddl_type

                ddl_str = f"|📅{curr_ddl.strftime('%m-%d')}" if curr_ddl else ""
                reply += f"[{s_map.get(ep.status)}]{ep.title}{ddl_str}\n"

        await cmd_view.finish(reply.strip())
