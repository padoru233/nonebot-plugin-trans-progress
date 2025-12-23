import json
from pathlib import Path
from typing import Dict, List, Optional

from nonebot import logger, require, get_plugin_config

require("nonebot_plugin_localstore")
from nonebot_plugin_localstore import get_plugin_data_file

from .config import Config

# 数据文件路径
DATA_FILE: Path = Path(get_plugin_data_file("data.json"))

plugin_config = get_plugin_config(Config)


def _ensure_data_file():
    """确保数据文件存在"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("{}", encoding="utf-8")


# 启动时确保文件存在
_ensure_data_file()


def load_data() -> Dict:
    """加载数据"""
    try:
        raw = DATA_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"[trans-progress] 读取数据文件失败，返回空字典: {e}")
        return {}


def save_data(data: Dict):
    """保存数据"""
    try:
        DATA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"[trans-progress] 保存数据失败: {e}")


def create_project(project: str):
    """创建新项目（总项目）"""
    data = load_data()

    if project not in data:
        data[project] = {
            "default": {
                "翻译": [],
                "校对": [],
                "嵌字": []
            },
            "episodes": {}
        }
        save_data(data)


def set_default_staff(project: str, role: str, member_id: str):
    """设置项目默认staff（替换模式）"""
    data = load_data()

    if project not in data:
        create_project(project)
        data = load_data()

    data[project]["default"][role] = [member_id]
    save_data(data)


def add_default_staff(project: str, role: str, member_id: str):
    """添加项目默认staff"""
    data = load_data()

    if project not in data:
        create_project(project)
        data = load_data()

    if member_id not in data[project]["default"][role]:
        data[project]["default"][role].append(member_id)

    save_data(data)


def add_project_episode(project: str, episode: int):
    """添加新话数（复制总项目默认staff）"""
    data = load_data()

    if project not in data:
        create_project(project)
        data = load_data()

    ep_key = str(episode)
    if ep_key not in data[project]["episodes"]:
        # 复制总项目的默认staff
        data[project]["episodes"][ep_key] = {
            "翻译": data[project]["default"]["翻译"][:],
            "校对": data[project]["default"]["校对"][:],
            "嵌字": data[project]["default"]["嵌字"][:],
            "completed": False  # 新增完结标记
        }

    save_data(data)


def set_staff(project: str, episode: int, role: str, member_id: str):
    """设置指定话staff（替换模式）"""
    data = load_data()

    if project not in data:
        create_project(project)
        data = load_data()

    ep_key = str(episode)
    if ep_key not in data[project]["episodes"]:
        add_project_episode(project, episode)
        data = load_data()

    data[project]["episodes"][ep_key][role] = [member_id]
    save_data(data)


def add_staff(project: str, episode: int, role: str, member_id: str):
    """添加指定话额外staff"""
    data = load_data()

    if project not in data:
        create_project(project)
        data = load_data()

    ep_key = str(episode)
    if ep_key not in data[project]["episodes"]:
        add_project_episode(project, episode)
        data = load_data()

    if member_id not in data[project]["episodes"][ep_key][role]:
        data[project]["episodes"][ep_key][role].append(member_id)

    save_data(data)


def mark_completed(project: str, episode: int, completed: bool = True):
    """标记某话完结状态"""
    data = load_data()

    if project not in data:
        return False

    ep_key = str(episode)
    if ep_key not in data[project]["episodes"]:
        return False

    data[project]["episodes"][ep_key]["completed"] = completed
    save_data(data)
    return True


def get_episode_info(project: str, episode: int) -> Optional[Dict]:
    """获取指定话的staff信息"""
    data = load_data()

    if project not in data:
        return None

    ep_key = str(episode)
    return data[project]["episodes"].get(ep_key)


def get_default_info(project: str) -> Optional[Dict[str, List[str]]]:
    """获取项目默认staff信息"""
    data = load_data()

    if project not in data:
        return None

    return data[project].get("default")


def get_project_episodes(project: str) -> Optional[Dict]:
    """获取项目所有话数信息"""
    data = load_data()

    if project not in data:
        return None

    return data[project].get("episodes", {})


def get_all_projects() -> List[str]:
    """获取所有项目名"""
    data = load_data()
    return list(data.keys())
