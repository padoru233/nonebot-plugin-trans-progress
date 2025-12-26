from nonebot import on_command, require, get_driver, logger, get_plugin_config
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from tortoise import Tortoise
from tortoise.queryset import Q

from .models import Project, Episode, User
# 引入 send_group_message
from .utils import get_default_ddl, send_group_message
from .web import app as web_app
from .config import Config
from . import scheduler

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

# === 辅助函数：智能查找项目 ===
async def find_project(keyword: str) -> Project | None:
    # 1. 尝试名字精确匹配
    p = await Project.get_or_none(name=keyword).prefetch_related('leader')
    if p: return p

    # 2. 尝试别名匹配 (混合逻辑)
    # 先尝试数据库层面的数组包含 (精确匹配别名中的某一个)
    try:
        p = await Project.filter(aliases__contains=[keyword]).prefetch_related('leader').first()
        if p: return p
    except:
        pass # 忽略 JSON 格式错误

    # 3. 兜底：内存遍历 (支持模糊匹配，比如别名"MyGo"，搜"Go"也能找到)
    # 因为项目通常不会成千上万，内存遍历非常快且不易报错
    all_projs = await Project.all().prefetch_related('leader')
    for proj in all_projs:
        # 确保 aliases 是列表
        aliases = proj.aliases if isinstance(proj.aliases, list) else []
        for alias in aliases:
            if keyword in alias: # 只要包含这个字就算
                return proj

    return None

# === 辅助函数：智能查找话数 ===
async def find_episode(project: Project, keyword: str) -> Episode | None:
    """
    查找话数：
    1. 精确匹配 title
    2. 模糊匹配 title (contains)
    """
    # 1. 精确
    ep = await Episode.get_or_none(project=project, title=keyword).prefetch_related('translator', 'proofreader', 'typesetter')
    if ep: return ep

    # 2. 模糊 (包含)
    # 例如 DB存的是 "第12话", 用户搜 "12" -> 匹配成功
    # 可能会匹配到多个 (如搜 "1"，匹配到 "第1话", "第11话")，这里简单起见取第一个，或者可以做更复杂的数字提取
    eps = await Episode.filter(project=project, title__contains=keyword).prefetch_related('translator', 'proofreader', 'typesetter').all()

    if len(eps) == 1:
        return eps[0]
    elif len(eps) > 1:
        # 如果搜 "1" 匹配到 "1话" 和 "12话"，尝试通过正则提取数字对比，这里先简单返回第一个，或者抛出歧义
        # 简单优化：优先返回最短的匹配 (通常 "1" 对应 "1" 而不是 "11")
        eps.sort(key=lambda x: len(x.title))
        return eps[0]

    return None

# ----------------- Bot 指令逻辑 -----------------

# 1. 帮助指令
cmd_help = on_command("帮助", aliases={"help", "菜单"}, priority=5, block=True)

@cmd_help.handle()
async def _():
    msg = (
        "✨ 汉化组小助手在这里捏！\n"
        "========================\n"
        "🧐 想看进度?\n"
        "   • 查看 / 列表 -> 看看手里有多少坑\n"
        "   • 查看 <项目> -> 盯着某个坑看\n"
        "   • 查看 <项目> <话数> -> 查查某话动没动\n\n"
        "📝 做完啦?\n"
        "   • 完成 <项目> <话数> -> 交稿！(会自动艾特下一个人哦)\n\n"
        "💻 后台管理\n"
        "   • 戳这里: http://<你的IP>:端口/trans/\n"
        "   (开新坑、分锅、定死线都在这里哒)\n"
        "========================\n"
        "大家辛苦啦，要注意休息哦"
    )
    # 帮助指令简单回复，直接 finish 即可，或者也改成 send_group_message
    await cmd_help.finish(msg)


# 2. 完成指令
cmd_finish = on_command("完成", aliases={"done", "交稿"}, priority=5, block=True)

@cmd_finish.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    msg = args.extract_plain_text().strip().split()
    if len(msg) < 2:
        await cmd_finish.finish("唔…指令格式不对哦？😵‍💫\n试试这样：完成 <项目名> <话数>")

    proj_input, ep_input = msg[0], msg[1]
    qq_id = str(event.user_id)

    # 1. 智能查找项目
    project = await find_project(proj_input)
    if not project:
        await cmd_finish.finish(f"找不到叫「{proj_input}」的项目捏… 是不是名字打错啦？👀")

    # 2. 智能查找话数
    episode = await find_episode(project, ep_input)
    if not episode:
        await cmd_finish.finish(f"找不到话数「{ep_input}」(项目: {project.name}) 捏… 是不是名字打错啦？👀")

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
        await cmd_finish.finish("✅ 这个任务已经是完结状态啦")
    else:
        await cmd_finish.finish("⚠️ 这个任务还没在后台分配人员呢，先去Web端把锅分好再说吧！")

    if not (is_assignee or is_leader or is_group_admin):
        await cmd_finish.finish(
            f"🙅‍♀️ 达咩！不可以操作！\n"
            f"当前是【{stage_name}】阶段，负责人是: {target_user_name}\n"
            f"只有本人、组长或者管理员才能交稿哦~"
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

    reply = Message(f"🎉 辛苦啦！[{project.name} {episode.title}] {status_text}搞定！✨")
    if not is_assignee:
        reply += Message(f" (由 {event.sender.card or event.sender.nickname} 代提交)")
    reply += Message("\n")

    if episode.status == 4:
        reply += Message("🎆 撒花！全工序完结！")
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
            reply += Message("\n请 ") + MessageSegment.at(target_qq) + Message(" 查收，准备发布啦~ 🚀")
        else:
            reply += Message("\n请管理员查收发布")
    else:
        reply += Message(f"➡️ 进入 [{next_role}] 阶段\n")
        next_ddl = episode.ddl_proof if episode.status == 2 else episode.ddl_type
        if next_ddl:
            reply += Message(f"📅 死线: {next_ddl.strftime('%m-%d')}\n")
        if next_user:
            reply += Message("接力棒交给你啦！") + MessageSegment.at(next_user.qq_id) + Message("拜托了捏~ 🙏")
        else:
            reply += Message("⚠️ 哎呀，下一棒还没人接手！组长快来分锅！🍲")

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
            await cmd_view.finish("📭 现在的坑都填完啦？或者是还没开坑？(空空如也)")

        reply = "📂 **汉化组当前项目一览**"
        for p in projects:
            reply += f"\n📌 {p.name}"
            if p.aliases: reply += f" (别名: {','.join(p.aliases)})"

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

    # 1. 智能查找项目
    project = await find_project(target_name)

    if not project:
        await cmd_view.finish(f"找不到叫「{target_name}」的项目捏… 是不是名字打错啦？👀")

    if target_ep:
        # 2. 智能查找话数
        episode = await find_episode(project, target_ep)
        if not episode:
            await cmd_view.finish(f"找不到话数「{target_ep}」(项目: {project.name}) 捏… 是不是名字打错啦？👀")

        def fmt_role(user, ddl):
            u_name = user.name if user else "❌未分配"
            d_str = ddl.strftime('%m-%d') if ddl else "♾️无死线"
            return f"{u_name} (📅{d_str})"

        status_map = {0:'💤躺平中', 1:'✍️翻译中', 2:'🔍校对中', 3:'🎨嵌字中', 4:'🏆已完结'}

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
            reply += "🎉 现在的坑都填完啦？或者是还没开坑？(空空如也)"
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
