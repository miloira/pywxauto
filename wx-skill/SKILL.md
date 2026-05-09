---
name: "微信自动化"
description: "通过 pywxauto 命令行工具控制微信客户端，支持发送文本、文件、图片、视频、表情、收藏、名片，以及创建笔记和群聊。"
inclusion: manual
---

# 微信自动化 Skill

通过 `wx-cli.py` 命令行工具操作微信 4.x 客户端（Windows），实现消息发送、联系人管理、群聊操作、朋友圈功能。

## 前置条件

- Windows 系统
- 微信 4.x 客户端已登录并运行
- Python 3.8+ 环境
- 工作目录为 `wx-skill/`

## 依赖安装

```bash
pip install uiautomation==2.0.29 pywin32==311 Pillow==12.1.1 requests==2.32.5 pyee==13.0.1 rapidocr==3.8.1 onnxruntime==1.25.1 psutil
```

可选依赖（仅后台截图模式需要）：
```bash
pip install windows-capture==2.0.0
```

## 可用命令

所有命令通过 `python wx-cli.py <command> --参数名 <参数值>` 执行。

---

## 一、消息发送

### send-text — 发送文本消息

```bash
python wx-cli.py send-text --to "联系人昵称" --content "消息内容"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称（联系人或群聊名称） |
| `--content` | 是 | 要发送的文本内容 |
| `--timeout` | 否 | 等待发送完成的超时时间（秒），默认 5 |

### send-file — 发送文件

```bash
python wx-cli.py send-file --to "联系人昵称" --file "C:\path\to\file.pdf"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称 |
| `--file` | 是 | 文件的绝对路径 |
| `--timeout` | 否 | 超时时间（秒），默认 30 |

### send-image — 发送图片

```bash
python wx-cli.py send-image --to "联系人昵称" --file "C:\path\to\image.jpg"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称 |
| `--file` | 是 | 图片的绝对路径 |
| `--timeout` | 否 | 超时时间（秒），默认 10 |

### send-video — 发送视频

```bash
python wx-cli.py send-video --to "联系人昵称" --file "C:\path\to\video.mp4"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称 |
| `--file` | 是 | 视频的绝对路径 |
| `--timeout` | 否 | 超时时间（秒），默认 60 |

### send-at — 在群聊中 @成员发送消息

```bash
python wx-cli.py send-at --to "群聊名称" --content "开会了" --members "张三" "李四"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 群聊名称 |
| `--content` | 是 | 消息内容 |
| `--members` | 是 | 要 @ 的成员昵称，空格分隔如 `"张三" "李四"`。传 `"所有人"` 可 @所有人 |
| `--timeout` | 否 | 超时时间（秒），默认 5 |

### send-emotion — 发送表情

```bash
# 搜索表情发送
python wx-cli.py send-emotion --to "联系人昵称" --keyword "哈喽"

# 发送自定义表情（第 1 个）
python wx-cli.py send-emotion --to "联系人昵称" --index 1
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称 |
| `--keyword` | 否 | 表情搜索关键词，不传则发送自定义表情 |
| `--index` | 否 | 选择第几个表情，从 1 开始，默认 1 |
| `--timeout` | 否 | 超时时间（秒），默认 5 |

### send-collection — 发送收藏内容

```bash
python wx-cli.py send-collection --to "联系人昵称" --keyword "搜索关键词"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收者昵称 |
| `--keyword` | 是 | 收藏搜索关键词 |
| `--timeout` | 否 | 超时时间（秒），默认 5 |

### send-card — 发送名片

```bash
python wx-cli.py send-card --to "接收者昵称" --share "要分享的联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--to` | 是 | 接收名片的联系人昵称 |
| `--share` | 是 | 要分享名片的联系人昵称（必须是私聊联系人） |

---

## 二、联系人操作

### get-contact-profile — 获取联系人资料

```bash
python wx-cli.py get-contact-profile --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### set-contact-remark — 设置联系人备注

```bash
python wx-cli.py set-contact-remark --nickname "联系人昵称" --remark "新备注"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |
| `--remark` | 是 | 新备注名 |

### add-contact-label — 添加联系人标签

```bash
python wx-cli.py add-contact-label --nickname "联系人昵称" --labels "同事" "朋友"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |
| `--labels` | 是 | 标签名称，空格分隔如 `"同事" "朋友"` |

### remove-contact-label — 移除联系人标签

```bash
python wx-cli.py remove-contact-label --nickname "联系人昵称" --labels "同事"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |
| `--labels` | 是 | 标签名称，空格分隔如 `"同事" "朋友"` |

### set-contact-star — 设为星标朋友

```bash
python wx-cli.py set-contact-star --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### cancel-contact-star — 取消星标朋友

```bash
python wx-cli.py cancel-contact-star --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### black-contact — 加入黑名单

```bash
python wx-cli.py black-contact --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### unblack-contact — 移出黑名单

```bash
python wx-cli.py unblack-contact --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### delete-contact — 删除联系人

```bash
python wx-cli.py delete-contact --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### add-friend — 添加朋友

```bash
python wx-cli.py add-friend --keyword "微信号或手机号" --message "你好，我是XXX"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--keyword` | 是 | 微信号或手机号 |
| `--message` | 否 | 申请消息 |
| `--remark` | 否 | 备注名 |
| `--permission` | 否 | 朋友权限: chatonly=仅聊天 |
| `--hide-my-posts` | 否 | 不让对方看我的朋友圈（开关） |
| `--hide-their-posts` | 否 | 不看对方的朋友圈（开关） |

### get-friend-permission — 获取联系人朋友权限

```bash
python wx-cli.py get-friend-permission --nickname "联系人昵称"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |

### set-friend-permission — 设置联系人朋友权限

```bash
python wx-cli.py set-friend-permission --nickname "联系人昵称" --permission chatonly --hide-my-posts
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人昵称 |
| `--permission` | 否 | 权限: all=全部, chatonly=仅聊天，默认 all |
| `--hide-my-posts` | 否 | 不让对方看我的朋友圈（开关） |
| `--hide-their-posts` | 否 | 不看对方的朋友圈（开关） |

---

## 三、群聊操作

### create-room — 发起群聊

```bash
python wx-cli.py create-room --members "张三" "李四" "王五"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--members` | 是 | 好友昵称列表，空格分隔如 `"张三" "李四" "王五"`（至少两个） |

### set-room-name — 设置群聊名称

```bash
python wx-cli.py set-room-name --nickname "当前群名" --name "新群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 群聊当前名称 |
| `--name` | 是 | 新群聊名称 |

### set-room-announcement — 设置群公告

```bash
python wx-cli.py set-room-announcement --nickname "群名" --content "公告内容"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 群聊名称 |
| `--content` | 是 | 群公告内容 |

### add-room-members — 添加群成员

```bash
python wx-cli.py add-room-members --nickname "群名" --members "张三" "李四"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 群聊名称 |
| `--members` | 是 | 要添加的成员昵称，空格分隔如 `"张三" "李四"` |

### remove-room-members — 移除群成员

```bash
python wx-cli.py remove-room-members --nickname "群名" --members "张三"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 群聊名称 |
| `--members` | 是 | 要移除的成员昵称，空格分隔如 `"张三" "李四"` |

### exit-room — 退出群聊

```bash
python wx-cli.py exit-room --nickname "群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 群聊名称 |

### pin-chat — 置顶会话

```bash
python wx-cli.py pin-chat --nickname "联系人或群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人或群聊名称 |

### unpin-chat — 取消置顶

```bash
python wx-cli.py unpin-chat --nickname "联系人或群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人或群聊名称 |

### mute-chat — 消息免打扰

```bash
python wx-cli.py mute-chat --nickname "联系人或群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人或群聊名称 |

### unmute-chat — 取消免打扰

```bash
python wx-cli.py unmute-chat --nickname "联系人或群名"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--nickname` | 是 | 联系人或群聊名称 |

---

## 四、朋友圈

### get-moments — 获取朋友圈动态

```bash
python wx-cli.py get-moments --count 5
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--count` | 否 | 获取条数，默认 10 |
| `--position` | 否 | 起始位置: top=从顶部（默认）, current=当前位置 |

### publish-moment — 发布朋友圈

```bash
# 纯文字
python wx-cli.py publish-moment --text "今天天气真好"

# 图文
python wx-cli.py publish-moment --text "美食分享" --images "C:\img1.jpg" "C:\img2.jpg"

# 视频
python wx-cli.py publish-moment --video "C:\video.mp4" --text "旅行记录"

# 带隐私设置
python wx-cli.py publish-moment --text "仅好友可见" --permission "谁可以看" --permission-contacts "张三" "李四"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--text` | 否* | 文本内容（纯文字模式必填） |
| `--images` | 否 | 图片路径列表，最多9张（与 --video 互斥） |
| `--video` | 否 | 视频路径（与 --images 互斥） |
| `--remind` | 否 | 提醒谁看的联系人昵称 |
| `--permission` | 否 | 隐私设置: 公开/私密/谁可以看/不给谁看 |
| `--permission-contacts` | 否 | 隐私联系人列表 |
| `--permission-labels` | 否 | 隐私标签列表 |

---

## 五、其他

### create-note — 创建笔记

```bash
python wx-cli.py create-note --content "笔记内容"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--content` | 是 | 笔记内容 |

### get-self-profile — 获取当前登录账号资料

```bash
python wx-cli.py get-self-profile
```

---

## 返回值

- 退出码 `0`: 操作成功
- 退出码 `1`: 操作失败
- 标准输出打印结果（如 `发送状态: sent`、JSON 格式资料）
- 错误信息输出到 stderr

## 使用注意

1. 联系人昵称必须与微信中显示的完全一致（备注名或原始昵称）
2. 所有昵称、成员名称参数都用引号包裹，如 `--to "张三"`、`--members "张三" "李四"`
3. 文件路径建议使用绝对路径
4. 发送文件/图片/视频时，文件必须存在且可读
5. 命令执行期间不要手动操作微信窗口
6. 工作目录必须是 `wx-skill/`，因为 `wx.cp38-win_amd64.pyd` 在该目录下
