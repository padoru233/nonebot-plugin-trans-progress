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
| TRANS_PUBLIC_CATALOG_ENABLED | 否 | `false` | 是否开放无鉴权的漫画进度目录 JSON |
| TRANS_PUBLIC_CATALOG_ALLOW_ORIGIN | 否 | `https://keli.love` | 可跨域读取目录的前端来源 |
| TRANS_PUBLIC_CATALOG_CACHE_SECONDS | 否 | `60` | 浏览器缓存目录的秒数 |
| TRANS_PUBLIC_CATALOG_CDN_CACHE_SECONDS | 否 | `300` | CDN 缓存目录的秒数 |
| TRANS_PUBLIC_CATALOG_SYNC_URL | 否 | 无 | Makers 私有目录同步接口 URL |
| TRANS_PUBLIC_CATALOG_SYNC_TOKEN | 否 | 无 | Makers 私有目录同步接口的 Bearer Token |
- 数据库链接格式: `postgres://用户名:密码@地址:端口/数据库名` 例如：`postgres://postgres:password@127.0.0.1:5432/trans_db`
- 使用驱动器 `DRIVER=~fastapi`或者`DRIVER=~quart`

## 🎉 使用

### 帮助与指令

在群内发送 `帮助`、`help` 或 `菜单` 可查看机器人帮助。项目名可使用项目列表序号、名称、别名或标签匹配。

| 功能 | 用法 | 说明 |
| :--- | :--- | :--- |
| 查看进度 | `查看` / `列表` | 显示本群全部项目 |
| 查看项目 | `查看 <项目>` | 显示项目下的任务 |
| 查看话数 | `查看 <项目> <话数>` | 显示单个任务的详细状态 |
| 我的项目 | `我的项目` | 显示本群中你参与的未完成话数、当前工序和截止日期 |
| 完成任务 | `完成 <项目> <话数>` / `完成<项目><话数>` | 按当前工序推进任务，并提醒下一位负责人；无空格写法需唯一匹配项目和话数 |
| 快捷完成 | `<项目> <话数> 好了` / `<项目><话数>好了` | 与完成任务相同，支持结尾 `！`、`!` 或 `。`；无空格写法需唯一匹配项目和话数 |

完成操作仅允许当前负责人、项目组长或群管理员提交。

### 后台管理

插件在 NoneBot 的 ASGI 服务下挂载管理后台。默认服务端口为 `8080` 时，访问地址为 `http://<服务器IP>:8080/trans/`；如 NoneBot 配置了其他端口，请替换地址中的端口号。

对接 Moeflow 时，请在 Moeflow 中填写上述 Bot 后台地址；Bot 侧无需配置 Moeflow URL。

在 Moeflow 中删除项目集不会通知 Bot，Bot 里的同名作品集和话数会保留；之后在 Moeflow 重建同名项目集时会复用它们。
需要清理时，请在 Bot 后台用作品集上的删除按钮手动删除（会连同下面的全部话数一起删除）。

使用 `TRANS_AUTH_PASSWORD` 登录后，可新建项目和话数、分配成员、设置截止日期，以及管理每日播报。
每一话、每个作品集都有删除按钮，删除前会弹出确认框，写明将删除的内容；删除作品集会同时删除其下全部话数。

### 公开进度目录

将 `TRANS_PUBLIC_CATALOG_ENABLED=true` 写入 `.env` 后，插件会开放无鉴权接口
`/trans/catalog.json`。例如站点通过 CDN 暴露该路径时，前端可读取
`https://bot.keli.love/trans/catalog.json`。

接口返回每个项目的漫画名、别称、标签、最早的未完结话数、全部未完结话数、
工序进度、话数统计和最后更新时间。可在项目设置中填写再漫画详情地址，例如
`https://manhua.zaimanhua.com/details/84456`；插件会从再漫画公开详情 API 获取封面，
并在目录 JSON 中以 `coverUrl` 与 `detailUrl` 输出，便于网页渲染卡片和跳转。名为 `default` 的作品集
（萌翻为未归类话数创建的占位作品集，不区分大小写）不会出现在目录中。

短篇集、单行本等不适合合并成一部作品的作品集，可在后台编辑作品集时打开“每话作为独立作品展示”。
开启后目录里不再输出该作品集本身，而是每一话各输出一项：`name` 为话名，`aliases` 为 `[作品集名]`，
`tags` 沿用作品集标签，并带有 `"standalone": true`。这类话数可在后台填写各自的再漫画地址，
封面和跳转取自这一话；未填写时显示“暂无封面”，不会借用作品集的封面。其余作品集保持原样。
不包含群号、成员信息或管理凭据。默认只允许
`https://keli.love` 与 `https://www.keli.love` 跨域读取。若部署域名不同，请通过
`TRANS_PUBLIC_CATALOG_ALLOW_ORIGIN` 显式修改允许来源。

目录会在 Bot 启动时生成至插件本地数据目录的 `catalog.json`，项目或话数发生变更后会
合并为一次静态文件重建。访问 `/trans/catalog.json` 时仅读取该文件，不再查询数据库；
响应会同时设置浏览器缓存 `max-age`、CDN 缓存 `s-maxage` 和
`stale-while-revalidate`。默认情况下，浏览器缓存 60 秒，CDN 缓存 300 秒。

若配置 `TRANS_PUBLIC_CATALOG_SYNC_URL` 与
`TRANS_PUBLIC_CATALOG_SYNC_TOKEN`，每次静态目录成功重建后，插件会以 HTTPS POST
将该 JSON 同步到 Makers 私有接口。Bot 只在目录变更时发起一次同步，访客读取可改由
Makers Blob 提供，不再访问 Bot。同步地址必须以 `https://` 开头；插件不会将 Token
发送到明文 HTTP 地址。使用 Makers 后建议设置
`TRANS_PUBLIC_CATALOG_ENABLED=false`，以关闭 Bot 的 `/trans/catalog.json` 公开接口；
已配置同步地址时，静态目录仍会在启动和项目/话数变更后生成并同步到 Makers。

### 🎨 效果图
如果有效果图的话

<div align="center">
  <img src="https://count.getloli.com/@nonebot-plugin-trans-progress?name=nonebot-plugin-trans-progress&theme=booru-qualityhentais&padding=7&offset=0&align=center&scale=1&pixelated=1&darkmode=auto" alt="nonebot-plugin-trans-progress" />
</div>

图片文字使用 [LXGW Neo XiHei](https://github.com/lxgw/LxgwNeoXiHei) 的 `LXGWNeoXiHeiPlus.ttf`；emoji 使用 [Noto Emoji](https://github.com/googlefonts/noto-emoji) 的 `NotoColorEmoji.ttf`（[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)）。两者均随插件本地打包，不依赖外部 CDN。
