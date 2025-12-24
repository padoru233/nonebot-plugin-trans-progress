from datetime import datetime
from nonebot import require, logger
from .models import GroupSetting
from .broadcast import check_and_send_broadcast # 引入刚才写的新文件

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 改为每分钟执行一次
@scheduler.scheduled_job("cron", minute="*")
async def check_broadcast_time():
    now = datetime.now()
    current_time_str = now.strftime("%H:%M") # 例如 "10:00"

    # 查找所有 开启播报 且 时间匹配 的群配置
    # 注意：TimeField在Tortoise里有时会有时区问题，存字符串最稳妥
    target_settings = await GroupSetting.filter(
        enable_broadcast=True,
        broadcast_time=current_time_str
    ).all()

    if target_settings:
        logger.info(f"⏰ 触发定时播报: {current_time_str}, 共 {len(target_settings)} 个群")
        for setting in target_settings:
            await check_and_send_broadcast(setting.group_id, is_manual=False)
