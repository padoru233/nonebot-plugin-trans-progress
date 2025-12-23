from nonebot import logger, require, get_bot, on_message
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

require("nonebot_plugin_alconna")

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="汉化进度记录",
    description="记录和管理漫画汉化组的工作进度",
    usage="""========命令列表========
- 默认 <项目名> <职位> @成员  # 设置项目默认翻译
- 添加 <项目名> <话数>  # 添加新的一话
- 更换 <项目名+话数> <职位> @新成员  # 更换某话staff
- 添加 <项目名+话数> <职位> @成员  # 添加某话额外staff
- 完结 <项目名+话数>  # 标记某话完结
- 查看 <项目名+话数>  # 查看指定话的staff信息
- 查看 <项目名>  # 查看项目所有话数进度
- 查看所有项目  # 查看所有项目的默认staff""",
    type="application",
    homepage="https://github.com/padoru233/nonebot-plugin-trans-progress",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna"
    ),
)

from arclet.alconna import Args, Alconna
from nonebot_plugin_alconna import on_alconna, At, Match
from nonebot.matcher import Matcher
from nonebot.rule import to_me
from .utils import (
    create_project,
    set_default_staff,
    add_default_staff,
    add_project_episode,
    set_staff,
    add_staff,
    mark_completed,
    get_episode_info,
    get_default_info,
    get_project_episodes,
    get_all_projects
)


async def get_member_display(bot: Bot, group_id: int, user_id: str) -> str:
    """获取成员显示名称（昵称+ID）"""
    try:
        info = await bot.get_group_member_info(group_id=group_id, user_id=int(user_id))
        name = info.get("card") or info.get("nickname") or "未知"
        return f"{name}({user_id})"
    except Exception as e:
        logger.warning(f"获取成员信息失败: {e}")
        return f"未知({user_id})"


# 帮助命令（被at触发）
help_cmd = on_message(rule=to_me(), priority=10, block=False)

@help_cmd.handle()
async def _(matcher: Matcher):
    help_text = """📖 汉化进度记录 - 使用帮助

========命令列表========

📌 项目默认设置：
• 默认 <项目名> <职位> @成员
  示例：默认 魔法少年 翻译 @小明

➕ 添加新话：
• 添加 <项目名> <话数>
  示例：添加 魔法少年 18

🔄 更换Staff：
• 更换 <项目名+话数> <职位> @新成员
  示例：更换 魔法少年18 校对 @小红

➕ 添加额外Staff：
• 添加 <项目名+话数> <职位> @成员
  示例：添加 魔法少年18 校对 @小刚

✅ 标记完结：
• 完结 <项目名+话数>
  示例：完结 魔法少年18

🔍 查看进度：
• 查看 <项目名+话数>  # 查看指定话
• 查看 <项目名>  # 查看项目总览
• 查看所有项目  # 查看所有项目

💡 职位可选：翻译、校对、嵌字"""

    await matcher.finish(help_text)


# 默认设置命令：<项目名> <职位> @成员
cmd_default_set = on_alconna(
    Alconna(
        "默认",
        Args["project", str]["role", str]["member", At],
    ),
    priority=5,
    block=True,
)

@cmd_default_set.handle()
async def _(matcher: Matcher, project: str, role: str, member: At):
    valid_roles = ["翻译", "校对", "嵌字"]
    if role not in valid_roles:
        await matcher.finish(f"无效的职位，可选：{', '.join(valid_roles)}")

    member_id = str(member.target)
    set_default_staff(project, role, member_id)

    await matcher.finish(f"✅ 已设置 {project} 默认{role} 为 {member}")


# 添加新话数
cmd_add_episode = on_alconna(
    Alconna(
        "添加",
        Args["project", str]["episode", int],
    ),
    priority=5,
    block=True,
)

@cmd_add_episode.handle()
async def _(matcher: Matcher, project: str, episode: int):
    add_project_episode(project, episode)
    await matcher.finish(f"✅ 已添加 {project} 第{episode}话（已复制默认staff）")


# 更换某话staff
cmd_replace_staff = on_alconna(
    Alconna(
        "更换",
        Args["project_episode", str]["role", str]["member", At],
    ),
    priority=5,
    block=True,
)

@cmd_replace_staff.handle()
async def _(matcher: Matcher, project_episode: str, role: str, member: At):
    valid_roles = ["翻译", "校对", "嵌字"]
    if role not in valid_roles:
        await matcher.finish(f"无效的职位，可选：{', '.join(valid_roles)}")

    import re
    match = re.match(r"^(.+?)(\d+)$", project_episode)
    if not match:
        await matcher.finish("格式错误，示例：更换 魔法少年18 校对 @成员")

    project, episode_str = match.groups()
    episode = int(episode_str)

    member_id = str(member.target)
    set_staff(project, episode, role, member_id)

    await matcher.finish(f"✅ 已更换 {project} 第{episode}话 {role} 为 {member}")


# 添加某话额外staff
cmd_add_staff = on_alconna(
    Alconna(
        "添加",
        Args["project_episode", str]["role", str]["member", At],
    ),
    priority=5,
    block=True,
)

@cmd_add_staff.handle()
async def _(matcher: Matcher, project_episode: str, role: str, member: At):
    valid_roles = ["翻译", "校对", "嵌字"]
    if role not in valid_roles:
        await matcher.finish(f"无效的职位，可选：{', '.join(valid_roles)}")

    import re
    match = re.match(r"^(.+?)(\d+)$", project_episode)
    if not match:
        await matcher.finish("格式错误，示例：添加 魔法少年18 校对 @成员")

    project, episode_str = match.groups()
    episode = int(episode_str)

    member_id = str(member.target)
    add_staff(project, episode, role, member_id)

    await matcher.finish(f"✅ 已为 {project} 第{episode}话添加 {role}: {member}")


# 完结命令
cmd_complete = on_alconna(
    Alconna(
        "完结",
        Args["project_episode", str],
    ),
    priority=5,
    block=True,
)

@cmd_complete.handle()
async def _(matcher: Matcher, project_episode: str):
    import re
    match = re.match(r"^(.+?)(\d+)$", project_episode)
    if not match:
        await matcher.finish("格式错误，示例：完结 魔法少年18")

    project, episode_str = match.groups()
    episode = int(episode_str)

    success = mark_completed(project, episode, True)
    if success:
        await matcher.finish(f"✅ 已标记 {project} 第{episode}话 为完结")
    else:
        await matcher.finish(f"❌ {project} 第{episode}话 不存在")


# 查看指定话进度或总项目进度
cmd_view = on_alconna(
    Alconna(
        "查看",
        Args["project_info", str],
    ),
    priority=5,
    block=True,
)

@cmd_view.handle()
async def _(bot: Bot, event: GroupMessageEvent, matcher: Matcher, project_info: str):
    import re
    match = re.match(r"^(.+?)(\d+)$", project_info)

    # 如果匹配到数字，查看指定话
    if match:
        project, episode_str = match.groups()
        episode = int(episode_str)

        info = get_episode_info(project, episode)
        if not info:
            await matcher.finish(f"{project} 第{episode}话 暂无staff信息")

        completed = info.get("completed", False)
        status = "✅ 已完结" if completed else "🔄 进行中"

        msg = f"【{project} 第{episode}话】{status}\n"
        for role in ["翻译", "校对", "嵌字"]:
            members = info.get(role, [])
            if members:
                names = []
                for m in members:
                    name = await get_member_display(bot, event.group_id, m)
                    names.append(name)
                msg += f"{role}: {', '.join(names)}\n"

        await matcher.finish(msg.strip())

    # 否则查看总项目（包含默认staff和所有话数）
    else:
        project = project_info

        # 获取默认staff
        default_info = get_default_info(project)
        episodes = get_project_episodes(project)

        if episodes is None and not default_info:
            await matcher.finish(f"项目 {project} 不存在")

        msg = f"📊 【{project}】项目信息\n\n"

        # 显示默认staff
        msg += "🎯 默认Staff:\n"
        has_default = False
        for role in ["翻译", "校对", "嵌字"]:
            members = default_info.get(role, [])
            if members:
                has_default = True
                names = []
                for m in members:
                    name = await get_member_display(bot, event.group_id, m)
                    names.append(name)
                msg += f"  {role}: {', '.join(names)}\n"

        if not has_default:
            msg += "  暂未设置\n"

        # 显示所有话数进度
        if not episodes:
            msg += "\n暂无任何话数"
        else:
            sorted_eps = sorted(episodes.items(), key=lambda x: int(x[0]))
            msg += f"\n📝 进度列表 (共{len(sorted_eps)}话):\n"

            for ep_num, ep_data in sorted_eps:
                completed = ep_data.get("completed", False)
                status = "✅" if completed else "🔄"
                msg += f"{status} 第{ep_num}话"

                if completed:
                    msg += " (已完结)\n"
                else:
                    staff_info = []
                    for role in ["翻译", "校对", "嵌字"]:
                        members = ep_data.get(role, [])
                        if members:
                            names = []
                            for m in members:
                                name = await get_member_display(bot, event.group_id, m)
                                names.append(name)
                            staff_info.append(f"{role}:{','.join(names)}")

                    if staff_info:
                        msg += f" ({' | '.join(staff_info)})\n"
                    else:
                        msg += " (暂无staff)\n"

        await matcher.finish(msg.strip())


# 查看所有项目（只显示默认）
cmd_view_all = on_alconna(
    Alconna("查看所有项目"),
    priority=5,
    block=True,
)

@cmd_view_all.handle()
async def _(bot: Bot, event: GroupMessageEvent, matcher: Matcher):
    projects = get_all_projects()
    if not projects:
        await matcher.finish("暂无任何项目")

    msg = "📊 所有项目默认staff：\n"
    for proj in projects:
        info = get_default_info(proj)
        msg += f"\n【{proj}】\n"
        for role in ["翻译", "校对", "嵌字"]:
            members = info.get(role, [])
            if members:
                names = []
                for m in members:
                    name = await get_member_display(bot, event.group_id, m)
                    names.append(name)
                msg += f"  {role}: {', '.join(names)}\n"

    await matcher.finish(msg.strip())
