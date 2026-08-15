<div align="center">
    <a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo"></a>

## ✨ nonebot-plugin-trans-progress 汉化进度记录✨
[![LICENSE](https://img.shields.io/github/license/padoru233/nonebot-plugin-trans-progress.svg)](./LICENSE)
[![pypi](https://img.shields.io/pypi/v/nonebot-plugin-trans-progress.svg)](https://pypi.python.org/pypi/nonebot-plugin-trans-progress)
[![python](https://img.shields.io/badge/python-3.10|3.11|3.12|3.13-blue.svg)](https://www.python.org)
[![uv](https://img.shields.io/badge/package%20manager-uv-black?style=flat-square&logo=uv)](https://github.com/astral-sh/uv)
<br/>
[![ruff](https://img.shields.io/badge/code%20style-ruff-black?style=flat-square&logo=ruff)](https://github.com/astral-sh/ruff)
[![pre-commit](https://results.pre-commit.ci/badge/github/padoru233/nonebot-plugin-trans-progress/master.svg)](https://results.pre-commit.ci/latest/github/padoru233/nonebot-plugin-trans-progress/master)

</div>

> [!IMPORTANT]
> **收藏项目**，你的每一个Star⭐都是作者更新的动力～️

## 📖 介绍

- ~~组长的催命机器人~~
- 记录和管理漫画汉化组的工作进度
- ~~AI含量极高~~

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-trans-progress --upgrade
使用 **pypi** 源安装

    nb plugin install nonebot-plugin-trans-progress --upgrade -i "https://pypi.org/simple"
使用**清华源**安装

    nb plugin install nonebot-plugin-trans-progress --upgrade -i "https://pypi.tuna.tsinghua.edu.cn/simple"


</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details open>
<summary>uv</summary>

    uv add nonebot-plugin-trans-progress
安装仓库 master 分支

    uv add git+https://github.com/padoru233/nonebot-plugin-trans-progress@master
</details>

<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-trans-progress
安装仓库 master 分支

    pdm add git+https://github.com/padoru233/nonebot-plugin-trans-progress@master
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-trans-progress
安装仓库 master 分支

    poetry add git+https://github.com/padoru233/nonebot-plugin-trans-progress@master
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_trans_progress"]

</details>

<details>
<summary>使用 nbr 安装(使用 uv 管理依赖可用)</summary>

[nbr](https://github.com/fllesser/nbr) 是一个基于 uv 的 nb-cli，可以方便地管理 nonebot2

    nbr plugin install nonebot-plugin-trans-progress
使用 **pypi** 源安装

    nbr plugin install nonebot-plugin-trans-progress -i "https://pypi.org/simple"
使用**清华源**安装

    nbr plugin install nonebot-plugin-trans-progress -i "https://pypi.tuna.tsinghua.edu.cn/simple"

</details>


## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的必填配置

| 配置项  | 必填  | 默认值 |   说明   |
| :-----: | :---: | :----: | :------: |
| TRANS_DB_URL |  是   |   无   | 见下 |
| TRANS_AUTH_PASSWORD |  是   |   admin   | Web访问密码 |
- 数据库链接格式: `postgres://用户名:密码@地址:端口/数据库名` 例如：`postgres://postgres:password@127.0.0.1:5432/trans_db`
- 使用驱动器 `DRIVER=~fastapi`或者`DRIVER=~quart`

## 🎉 使用
### 指令表
| 指令  | 权限  | 需要@ | 范围  |   说明   |
| :---: | :---: | :---: | :---: | :------: |
| 帮助 | 群员  |  否   | 群聊  | - |
| 完成 | 群员  |  是   | 群聊  | - |
| 查看 | 群员  |  是   | 群聊  | - |

### 🎨 效果图
如果有效果图的话

<div align="center">
  <img src="https://count.getloli.com/@nonebot-plugin-trans-progress?name=nonebot-plugin-trans-progress&theme=booru-qualityhentais&padding=7&offset=0&align=center&scale=1&pixelated=1&darkmode=auto" alt="nonebot-plugin-trans-progress" />
</div>

图片文字使用 [LXGW Neo XiHei](https://github.com/lxgw/LxgwNeoXiHei) 的 `LXGWNeoXiHeiPlus.ttf`；emoji 使用 [Noto Emoji](https://github.com/googlefonts/noto-emoji) 的 `NotoColorEmoji.ttf`（[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)）。两者均随插件本地打包，不依赖外部 CDN。
