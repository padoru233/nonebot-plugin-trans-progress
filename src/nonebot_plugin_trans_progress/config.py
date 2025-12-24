from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    # 数据库链接格式: postgres://用户名:密码@地址:端口/数据库名
    trans_db_url: str = "postgres://postgres:password@127.0.0.1:5432/trans_db"
    # Web访问密码
    trans_auth_password: str = "admin"


# 配置加载
plugin_config: Config = get_plugin_config(Config)
global_config = get_driver().config

# 全局名称
NICKNAME: str = next(iter(global_config.nickname), "")
