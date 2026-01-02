from typing import Optional
from datetime import datetime, timedelta

from nonebot import get_bots, logger
from nonebot.adapters.onebot.v11 import Message, Bot

def get_default_ddl() -> datetime:
    """获取默认死线：当前时间 + 14天"""
    return datetime.now() + timedelta(days=14)

async def send_group_message(group_id: int, message: Message, bot: Optional[Bot] = None):
    """
    通用发送函数：
    :param group_id: 目标群号
    :param message: 消息内容
    :param bot: 指定发送的 Bot。如果为 None，则自动查找加入了该群的 Bot。
    """
    target_bot = bot

    # 1. 如果没有指定 Bot (Web端/定时任务)，需要自动寻找能发消息的 Bot
    if not target_bot:
        all_bots = get_bots()
        # 遍历所有在线的 Bot
        for b in all_bots.values():
            # 必须是 OneBot V11 的 Bot
            if isinstance(b, Bot):
                try:
                    # 获取该 Bot 的群列表
                    g_list = await b.get_group_list()
                    # 检查目标群是否在这个 Bot 的列表里
                    if any(str(g['group_id']) == str(group_id) for g in g_list):
                        target_bot = b
                        break
                except Exception:
                    continue

    # 2. 执行发送
    if target_bot:
        try:
            await target_bot.send_group_msg(group_id=group_id, message=message)
            logger.info(f"Bot [{target_bot.self_id}] 向群 [{group_id}] 发送消息成功")
        except Exception as e:
            logger.warning(f"Bot [{target_bot.self_id}] 发送失败: {e}")
    else:
        logger.error(f"发送失败：未找到任何一个加入了群 [{group_id}] 的 OneBot V11 机器人")
