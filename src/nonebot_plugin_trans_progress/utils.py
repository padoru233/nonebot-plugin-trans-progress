from datetime import datetime, timedelta

from nonebot import get_bot, logger
from nonebot.adapters.onebot.v11 import Message


def get_default_ddl() -> datetime:
    """获取默认死线：当前时间 + 14天"""
    return datetime.now() + timedelta(days=14)

async def send_group_message(group_id: int, message: Message):
    """
    通用发送函数：接收构建好的 Message 对象并发送
    """
    try:
        bot = get_bot()
        await bot.send_group_msg(group_id=group_id, message=message)
    except Exception as e:
        logger.warning(f"消息发送失败 [群 {group_id}]: {e}")
