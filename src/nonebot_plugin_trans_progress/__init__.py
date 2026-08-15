import asyncio
import os
import random

from nonebot import on_command, require, get_driver, logger, get_plugin_config, get_asgi
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from tortoise import Tortoise
from tortoise.queryset import Q

# Ensure these imports exist in your project structure
from .models import Project, Episode, User
from .utils import get_default_ddl, send_group_message
from .web import api_router
from .config import Config
from . import scheduler
from .view_renderer import RenderModule, render_modules, render_text_pages

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except ImportError:
    FastAPI = None

driver = get_driver()
plugin_config = get_plugin_config(Config)

MODELS_PATH = [f"{__name__}.models"]

usage = """@Bot+帮助"""
IMAGE_SEND_MAX_INTERVAL_SECONDS = 2

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="汉化进度记录",
    description="记录和管理漫画汉化组的工作进度",
    usage=usage,
    type="application",
    homepage="https://github.com/padoru233/nonebot-plugin-trans-progress",
    config=Config,
    supported_adapters={"~onebot.v11"},
)


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
    if not FastAPI:
        logger.warning("未检测到 FastAPI 库，Web 后台无法启动。")
        return

    root_app = get_asgi()
    sub_app = FastAPI(
        title="汉化进度管理",
        description="NoneBot Plugin Trans Progress API",
        version="0.3.13",
        docs_url="/docs",
        openapi_url="/openapi.json"
    )

    # 手动添加首页路由 (无锁)
    @sub_app.get("/", response_class=HTMLResponse)
    async def index_page():
        template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        return "<h1>Template not found</h1>"

    # 挂载 web.py 的 API 路由 (自带锁)
    sub_app.include_router(api_router)

    logger.opt(colors=True).info(f"正在挂载 Web 后台到 <y>/trans</y> ...")

    try:
        root_app.mount("/trans", sub_app)
    except AttributeError:
        logger.warning("当前驱动器不支持 mount 操作，Web 后台可能无法访问 (请确保使用的是 ASGI 驱动器)")

# === 辅助函数：按当前群查找项目 ===
async def find_project(keyword: str, group_id: str) -> Project | None:
    needed_fields = [
        'leader',
        'default_translator',
        'default_proofreader',
        'default_typesetter',
        'default_supervisor'
    ]
    projects = Project.filter(group_id=str(group_id))
    all_projs = await projects.prefetch_related(*needed_fields).order_by('-id').all()

    # 1. 项目列表中的显示序号，例如【1】
    if keyword.isdecimal():
        position = int(keyword)
        if 1 <= position <= len(all_projs):
            return all_projs[position - 1]

    # 2. 项目名称精确匹配
    for project in all_projs:
        if project.name == keyword:
            return project

    # 3. 别称和标签精确匹配
    for project in all_projs:
        aliases = project.aliases if isinstance(project.aliases, list) else []
        tags = project.tags if isinstance(project.tags, list) else []
        if keyword in aliases or keyword in tags:
            return project

    # 4. 名称、别称和标签模糊匹配
    for proj in all_projs:
        aliases = proj.aliases if isinstance(proj.aliases, list) else []
        tags = proj.tags if isinstance(proj.tags, list) else []
        search_terms = [proj.name, *aliases, *tags]
        if any(isinstance(term, str) and keyword in term for term in search_terms):
            return proj

    return None

# === 辅助函数：智能查找话数 (FIXED) ===
async def find_episode(project: Project, keyword: str) -> Episode | None:
    """
    查找话数：
    1. 精确匹配 title
    2. 模糊匹配 title (contains)
    """
    # Added 'supervisor' to prefetch list
    needed_fields = ['translator', 'proofreader', 'typesetter', 'supervisor']

    # 1. 精确
    ep = await Episode.get_or_none(project=project, title=keyword).prefetch_related(*needed_fields)
    if ep: return ep

    # 2. 模糊 (包含)
    # 例如 DB存的是 "第12话", 用户搜 "12" -> 匹配成功
    eps = await Episode.filter(project=project, title__contains=keyword).prefetch_related(*needed_fields).all()

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


async def finish_image(
    matcher: Matcher, title: str, modules: list[RenderModule]
):
    images = render_modules(title, modules)
    for index, image in enumerate(images):
        if index:
            await asyncio.sleep(random.uniform(0, IMAGE_SEND_MAX_INTERVAL_SECONDS))
        await matcher.send(MessageSegment.image(image))
    await matcher.finish()


@cmd_help.handle()
async def _(matcher: Matcher):
    await finish_image(
        matcher,
        "汉化进度助手",
        [
            RenderModule("查看进度", ["查看 / 列表：显示本群全部项目", "查看 <项目>：显示项目任务", "查看 <项目> <话数>：显示单个任务"]),
            RenderModule("项目搜索", ["仅搜索当前群绑定的项目", "依次匹配：列表序号、名称、别称/标签、模糊关键词"]),
            RenderModule("完成任务", ["完成 <项目> <话数>", "完成后会自动提醒下一位负责人"]),
            RenderModule("后台管理", ["http://<你的IP>:端口/trans/", "开新坑、分配成员和设置死线"]),
        ],
    )


# 2. 完成指令
cmd_finish = on_command("完成", aliases={"done", "交稿"}, priority=5, block=True)

@cmd_finish.handle()
async def _(matcher: Matcher, bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    msg = args.extract_plain_text().strip().split()
    if len(msg) < 2:
        await finish_image(matcher, "指令格式不正确", [RenderModule("请这样输入", ["完成 <项目名> <话数>"])])

    proj_input, ep_input = msg[0], msg[1]
    qq_id = str(event.user_id)

    # 1. 智能查找项目
    project = await find_project(proj_input, str(event.group_id))
    if not project:
        await finish_image(matcher, "未找到项目", [RenderModule("查询内容", [proj_input])])

    # 2. 智能查找话数
    episode = await find_episode(project, ep_input)
    if not episode:
        await finish_image(matcher, "未找到任务", [RenderModule(project.name, [ep_input])])

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
        stage_name = "监修"
        if episode.supervisor:
            target_user_name = episode.supervisor.name
            if episode.supervisor.qq_id == qq_id: is_assignee = True
    elif current_status == 5:
        await finish_image(matcher, "任务已完结", [RenderModule("无需重复提交", [f"{project.name} {episode.title}"])])
    else:
        await finish_image(matcher, "任务尚未分配", [RenderModule("请前往后台", ["先为当前阶段分配负责人"] )])

    if not (is_assignee or is_leader or is_group_admin):
        await finish_image(
            matcher,
            "没有提交权限",
            [RenderModule("当前负责人", [f"阶段：{stage_name}", f"负责人：{target_user_name}", "仅本人、组长或管理员可提交"])],
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
        if not episode.ddl_supervision: episode.ddl_supervision = get_default_ddl()
        next_role = "监修"
        next_user = episode.supervisor
    elif current_status == 4:
        episode.status = 5
        next_role = "发布"
        next_user = None

    await episode.save()

    status_text = ['','翻译','校对','嵌字','监修'][current_status]
    result_lines = [f"{project.name} {episode.title}", f"{status_text}已完成"]
    if not is_assignee:
        result_lines.append(f"由 {event.sender.card or event.sender.nickname} 代提交")

    target_qq = None
    if episode.status == 5:
        result_lines.append("全部工序已完结，准备发布")
        if project.leader:
            target_qq = project.leader.qq_id
        else:
            try:
                mlist = await bot.get_group_member_list(group_id=int(event.group_id))
                owner = next((m for m in mlist if m['role'] == 'owner'), None)
                if owner: target_qq = str(owner['user_id'])
            except Exception as e:
                logger.warning(f"获取群主失败: {e}")

        if not target_qq:
            result_lines.append("请管理员查收发布")
    else:
        result_lines.append(f"下一阶段：{next_role}")

        next_ddl = None
        if episode.status == 2: next_ddl = episode.ddl_proof
        elif episode.status == 3: next_ddl = episode.ddl_type
        elif episode.status == 4: next_ddl = episode.ddl_supervision

        if next_ddl:
            result_lines.append(f"截止日期：{next_ddl.strftime('%m-%d')}")
        if next_user:
            target_qq = next_user.qq_id
            result_lines.append("已通知下一位负责人")
        else:
            result_lines.append("下一阶段尚未分配负责人")

    image = render_modules("任务完成", [RenderModule("处理结果", result_lines)])[0]
    reply = Message(MessageSegment.image(image))
    if target_qq:
        reply += MessageSegment.at(target_qq)
    await send_group_message(int(event.group_id), reply, bot=bot)
    await cmd_finish.finish()


# 3. 查看指令
cmd_view = on_command("查看", aliases={"查看项目", "view", "进度", "项目列表"}, priority=5, block=True)


async def send_view_images(matcher: Matcher, title: str, lines: list[str]):
    try:
        images = render_text_pages(title, lines)
        for index, image in enumerate(images):
            if index:
                await asyncio.sleep(random.uniform(0, IMAGE_SEND_MAX_INTERVAL_SECONDS))
            await matcher.send(MessageSegment.image(image))
    except Exception as exc:
        logger.exception(f"查看图片渲染失败: {exc}")
        raise


@cmd_view.handle()
async def _(
    matcher: Matcher, bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()
):
    msg = args.extract_plain_text().strip().split()

    if not msg or msg[0] in ["全部", "所有", "列表", "list", "all"]:
        current_gid = str(event.group_id)

        projects = await Project.filter(group_id=current_gid).order_by('-id').prefetch_related(
            'leader', 'default_translator', 'default_proofreader',
            'default_typesetter', 'default_supervisor'
        )

        if not projects:
            await finish_image(
                matcher,
                "项目一览",
                [RenderModule("暂无项目", ["本群目前没有进行中的汉化项目"])],
            )

        lines = [f"本群项目一览 | 共 {len(projects)} 个", ""]

        for i, p in enumerate(projects):
            lines.append(f"【{i + 1}】{p.name}")

            info_parts = []
            if p.leader:
                info_parts.append(f"负责人：{p.leader.name}")
            if p.aliases:
                shown_aliases = p.aliases[:2]
                alias_str = ",".join(shown_aliases)
                if len(p.aliases) > 2: alias_str += "..."
                info_parts.append(f"别名：{alias_str}")

            if info_parts:
                lines.append(f"  {'  '.join(info_parts)}")

            dt = p.default_translator.name if p.default_translator else "-"
            dp = p.default_proofreader.name if p.default_proofreader else "-"
            dty = p.default_typesetter.name if p.default_typesetter else "-"
            ds = p.default_supervisor.name if p.default_supervisor else "-"

            # 只有当设置了至少一个默认人员时才显示此行
            if any(x != "-" for x in [dt, dp, dty, ds]):
                lines.append(f"  默认编制：翻[{dt}] 校[{dp}] 嵌[{dty}] 监[{ds}]")

            lines.append("────────────────────")

        await send_view_images(matcher, "项目一览", lines)
        await cmd_view.finish()

    target_name = msg[0]
    target_ep = msg[1] if len(msg) > 1 else None

    # 1. 智能查找项目
    project = await find_project(target_name, str(event.group_id))

    if not project:
        await finish_image(matcher, "未找到项目", [RenderModule("查询内容", [target_name])])

    if target_ep:
        # 2. 智能查找话数
        episode = await find_episode(project, target_ep)
        if not episode:
            await finish_image(matcher, "未找到任务", [RenderModule(project.name, [target_ep])])

        def fmt_role(user, ddl):
            u_name = user.name if user else "未分配"
            d_str = ddl.strftime('%m-%d') if ddl else "无"
            return f"{u_name} (📅{d_str})"

        status_map = {0:'未开始', 1:'翻译中', 2:'校对中', 3:'嵌字中', 4:'监修中', 5:'已完结'}
        lines = [
            f"项目：{project.name}",
            f"话数：{episode.title}",
            f"状态：{status_map.get(episode.status, '未知')}",
            "────────────────────",
            f"翻译：{fmt_role(episode.translator, episode.ddl_trans)}",
            f"校对：{fmt_role(episode.proofreader, episode.ddl_proof)}",
            f"嵌字：{fmt_role(episode.typesetter, episode.ddl_type)}",
            f"监修：{fmt_role(episode.supervisor, episode.ddl_supervision)}",
        ]
        await send_view_images(matcher, "任务详情", lines)
        await cmd_view.finish()

    else:
        active_eps = await Episode.filter(project=project, status__lt=5).order_by('id').all()

        lines = []
        if project.aliases: lines.append(f"别名：{','.join(project.aliases)}")
        if project.leader: lines.append(f"组长：{project.leader.name}")
        if lines: lines.append("────────────────────")

        dt = project.default_translator.name if project.default_translator else "-"
        dp = project.default_proofreader.name if project.default_proofreader else "-"
        dty = project.default_typesetter.name if project.default_typesetter else "-"
        ds = project.default_supervisor.name if project.default_supervisor else "-"
        lines.append(f"默认编制：翻[{dt}] 校[{dp}] 嵌[{dty}] 监[{ds}]")
        lines.append("────────────────────")

        if not active_eps:
            lines.append("现在没有进行中的任务")
        else:
            lines.append(f"进行中任务（{len(active_eps)}）")
            for ep in active_eps:
                s_map = {0:'未', 1:'翻', 2:'校', 3:'嵌', 4:'监'}
                curr_ddl = None
                if ep.status == 1: curr_ddl = ep.ddl_trans
                elif ep.status == 2: curr_ddl = ep.ddl_proof
                elif ep.status == 3: curr_ddl = ep.ddl_type
                elif ep.status == 4: curr_ddl = ep.ddl_supervision

                ddl_str = f" | 截止 {curr_ddl.strftime('%m-%d')}" if curr_ddl else ""
                lines.append(f"[{s_map.get(ep.status)}] {ep.title}{ddl_str}")

        await send_view_images(matcher, project.name, lines)
        await cmd_view.finish()
