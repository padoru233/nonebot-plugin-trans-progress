from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    # 数据库链接格式: postgres://用户名:密码@地址:端口/数据库名
    trans_db_url: str = "postgres://postgres:password@127.0.0.1:5432/trans_db"
    # Web访问密码
    trans_auth_password: str = "admin"
    # Moeflow Backend 后端 API 地址，不带尾部斜杠
    moeflow_api_url: str = "http://127.0.0.1:8000"
    # 是否公开漫画进度目录 JSON
    trans_public_catalog_enabled: bool = False
    # 允许读取公开目录的前端来源
    trans_public_catalog_allow_origin: str = "https://keli.love"
    # CDN 可缓存公开目录的秒数
    trans_public_catalog_cache_seconds: int = 60
    # CDN 可缓存公开目录的秒数，需大于等于浏览器缓存时间
    trans_public_catalog_cdn_cache_seconds: int = 300
    # Makers 私有目录同步接口；不配置时仅生成本地静态目录
    trans_public_catalog_sync_url: str | None = None
    # Makers 私有目录同步接口的 Bearer Token
    trans_public_catalog_sync_token: str | None = None


# 配置加载
plugin_config: Config = get_plugin_config(Config)
global_config = get_driver().config

# 全局名称
NICKNAME: str = next(iter(global_config.nickname), "")
