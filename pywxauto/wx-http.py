"""
pywxauto HTTP 服务。

基于 FastAPI 将 Weixin 类的接口封装为 HTTP API，支持设置消息回调地址。

用法:
    # 从项目根目录运行
    python pywxauto/wx-http.py
"""

import os
import sys

import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from wx import (
    Event,
    Message,
    MessageStatus,
    Weixin,
    WeixinClient,
    WxAutoError,
)

# ---- 日志 ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---- 全局状态 ----
wx: Optional[Weixin] = None
_callback_url: Optional[str] = None
_listen_thread: Optional[threading.Thread] = None
_http_client: Optional[httpx.AsyncClient] = None


# ---- Pydantic 模型 ----

class SendTextRequest(BaseModel):
    pid: Optional[int] = Field(None, description="微信进程 PID，单客户端时可省略")
    to: str = Field(..., description="接收者昵称")
    content: str = Field(..., description="消息内容")
    timeout: float = Field(5, description="超时时间（秒）")


class SendFileRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收者昵称")
    file: str | list[str] = Field(..., description="文件路径或路径列表")
    timeout: float = Field(30, description="超时时间（秒）")


class SendImageRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收者昵称")
    file: str | list[str] = Field(..., description="图片路径或路径列表")
    timeout: float = Field(10, description="超时时间（秒）")


class SendVideoRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收者昵称")
    file: str | list[str] = Field(..., description="视频路径或路径列表")
    timeout: float = Field(60, description="超时时间（秒）")


class SendAtRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="群聊名称")
    content: str = Field(..., description="消息内容")
    members: list[str] = Field(..., description="要 @ 的成员昵称列表")
    timeout: float = Field(5, description="超时时间（秒）")


class SendEmotionRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收者昵称")
    keyword: Optional[str] = Field(None, description="表情搜索关键词，None 发送自定义表情")
    index: int = Field(1, description="选择第几个表情，从 1 开始")
    timeout: float = Field(5, description="超时时间（秒）")


class SendCollectionRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收者昵称")
    keyword: str = Field(..., description="收藏搜索关键词")
    timeout: float = Field(5, description="超时时间（秒）")


class SendCardRequest(BaseModel):
    pid: Optional[int] = None
    to: str = Field(..., description="接收名片的联系人昵称")
    share: str = Field(..., description="要分享名片的联系人昵称")


class CreateNoteRequest(BaseModel):
    pid: Optional[int] = None
    content: str = Field(..., description="笔记内容")


class CreateRoomRequest(BaseModel):
    pid: Optional[int] = None
    members: list[str] = Field(..., description="好友昵称列表（至少两个）")


class OpenClientRequest(BaseModel):
    install_path: Optional[str] = Field(None, description="微信安装路径，None 时自动从注册表检测")
    timeout: float = Field(30, description="等待微信进程启动的超时时间（秒）")


class CallbackRequest(BaseModel):
    url: str = Field(..., description="消息回调地址（POST），设为空字符串取消回调")


class ListenRequest(BaseModel):
    pid: Optional[int] = None
    names: Optional[list[str]] = Field(None, description="要监听的联系人/群聊名称列表，None 自动发现")


class ContactProfileRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="联系人昵称")


class SetRemarkRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="联系人昵称")
    remark: str = Field(..., description="备注名")


class ContactLabelRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="联系人昵称")
    labels: list[str] = Field(..., description="标签列表")


class ContactStarRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="联系人昵称")


class RoomNameRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="群聊名称")
    name: str = Field(..., description="新群名")


class RoomAnnouncementRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="群聊名称")
    content: str = Field(..., description="公告内容")


class RoomMembersRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="群聊名称")
    members: list[str] = Field(..., description="成员昵称列表")


class ChatNicknameRequest(BaseModel):
    pid: Optional[int] = None
    nickname: str = Field(..., description="会话名称")


# ---- 工具函数 ----

def _resolve_pid(pid: Optional[int]) -> int:
    """解析 PID：如果未指定且只有一个客户端，自动使用该客户端的 PID"""
    if pid is not None:
        return pid
    pids = wx.pids
    if len(pids) == 0:
        raise HTTPException(status_code=400, detail="没有已连接的微信客户端")
    if len(pids) == 1:
        return pids[0]
    raise HTTPException(
        status_code=400,
        detail=f"有多个微信客户端已连接 (PIDs: {pids})，请指定 pid 参数",
    )


def _status_response(status: MessageStatus) -> dict:
    return {"status": status.value, "success": status == MessageStatus.SENT}


# ---- 消息回调 ----

async def _dispatch_callback(message_data: dict):
    """将消息通过 HTTP POST 推送到回调地址"""
    global _callback_url, _http_client
    if not _callback_url or not _http_client:
        return
    try:
        resp = await _http_client.post(_callback_url, json=message_data, timeout=10)
        if resp.status_code >= 400:
            logger.warning(f"回调推送失败: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"回调推送异常: {e}")


def _on_message(client: WeixinClient, chat, message: Message):
    """统一消息处理器，将消息推送到回调地址"""
    if not _callback_url:
        return
    try:
        data = message.to_dict()
        data["pid"] = message.pid
        data["chat_name"] = chat.current_name if hasattr(chat, "current_name") else str(chat)
        # 在事件循环中异步推送
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_dispatch_callback(data))
        else:
            asyncio.run(_dispatch_callback(data))
    except Exception as e:
        logger.warning(f"消息回调处理异常: {e}")


# ---- FastAPI 生命周期 ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    global wx, _http_client
    _http_client = httpx.AsyncClient()
    wx = Weixin(resize=False)
    logger.info(f"微信管理器已初始化: {wx}")

    # 注册全局消息处理器
    @wx.on()
    def _handler(client, chat, message):
        _on_message(client, chat, message)

    yield

    # 清理
    if wx:
        wx.stop()
        wx.disconnect_all()
    if _http_client:
        await _http_client.aclose()


# ---- FastAPI 应用 ----

app = FastAPI(
    title="pywxauto HTTP API",
    description="微信自动化 HTTP 接口，基于 pywxauto",
    version="1.0.0",
    lifespan=lifespan,
)


# ---- 状态接口 ----

@app.get("/status", summary="获取服务状态")
async def get_status():
    """获取当前连接的微信客户端信息"""
    return {
        "clients": len(wx),
        "pids": wx.pids,
        "callback_url": _callback_url,
        "listening": _listen_thread is not None and _listen_thread.is_alive(),
    }


@app.get("/clients", summary="获取所有已连接客户端")
async def get_clients():
    """获取所有已连接的微信客户端 PID 列表"""
    return {"pids": wx.pids}


@app.post("/connect", summary="连接微信客户端")
async def connect_client(pid: Optional[int] = None):
    """连接指定 PID 的微信客户端，不传 PID 则连接所有"""
    try:
        if pid:
            result = wx.connect(pid)
            return {"pid": result}
        else:
            pids = wx.connect_all()
            return {"pids": pids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/disconnect", summary="断开微信客户端")
async def disconnect_client(pid: Optional[int] = None):
    """断开指定 PID 的微信客户端，不传 PID 则断开所有"""
    if pid:
        wx.disconnect(pid)
        return {"message": f"已断开 PID={pid}"}
    else:
        wx.disconnect_all()
        return {"message": "已断开所有客户端"}


@app.post("/open", summary="打开微信客户端")
async def open_client(req: OpenClientRequest = OpenClientRequest()):
    """
    启动一个新的微信客户端并连接，返回新进程的 PID。

    每次调用都会启动一个新进程（支持多开）。
    """
    try:
        pid = wx.open(install_path=req.install_path, timeout=req.timeout)
        return {"pid": pid, "message": f"微信客户端已启动，PID={pid}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 消息发送接口 ----

@app.post("/send/text", summary="发送文本消息")
async def send_text(req: SendTextRequest):
    """发送文本消息到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_text(pid, req.to, req.content, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/file", summary="发送文件")
async def send_file(req: SendFileRequest):
    """发送文件到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_file(pid, req.to, req.file, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/image", summary="发送图片")
async def send_image(req: SendImageRequest):
    """发送图片到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_image(pid, req.to, req.file, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/video", summary="发送视频")
async def send_video(req: SendVideoRequest):
    """发送视频到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_video(pid, req.to, req.file, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/at", summary="发送 @消息")
async def send_at(req: SendAtRequest):
    """在群聊中 @指定成员发送消息"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_at(pid, req.to, req.content, req.members, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/emotion", summary="发送表情")
async def send_emotion(req: SendEmotionRequest):
    """发送表情到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_emotion(pid, req.to, req.keyword, req.index, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/collection", summary="发送收藏内容")
async def send_collection(req: SendCollectionRequest):
    """发送收藏内容到指定联系人/群聊"""
    try:
        pid = _resolve_pid(req.pid)
        status = wx.send_collection(pid, req.to, req.keyword, req.timeout)
        return _status_response(status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send/card", summary="发送名片")
async def send_card(req: SendCardRequest):
    """发送名片到指定联系人"""
    try:
        pid = _resolve_pid(req.pid)
        success = wx.send_card(pid, req.to, req.share)
        return {"success": success}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 会话管理接口 ----

@app.post("/session/create-note", summary="创建笔记")
async def create_note(req: CreateNoteRequest):
    """创建笔记"""
    try:
        pid = _resolve_pid(req.pid)
        wx.create_note(pid, req.content)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/create-room", summary="发起群聊")
async def create_room(req: CreateRoomRequest):
    """发起群聊（至少两个好友）"""
    try:
        if len(req.members) < 2:
            raise HTTPException(status_code=400, detail="至少需要两个好友昵称才能创建群聊")
        pid = _resolve_pid(req.pid)
        wx.create_room(pid, req.members)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 联系人操作接口 ----

@app.post("/contact/profile", summary="获取联系人资料")
async def get_contact_profile(req: ContactProfileRequest):
    """获取联系人的资料信息"""
    try:
        pid = _resolve_pid(req.pid)
        profile = wx.get_contact_profile(pid, req.nickname)
        return {"profile": profile}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/set-remark", summary="设置联系人备注")
async def set_contact_remark(req: SetRemarkRequest):
    """设置联系人备注名"""
    try:
        pid = _resolve_pid(req.pid)
        wx.set_contact_remark(pid, req.nickname, req.remark)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/add-label", summary="添加联系人标签")
async def add_contact_label(req: ContactLabelRequest):
    """添加联系人标签"""
    try:
        pid = _resolve_pid(req.pid)
        wx.add_contact_label(pid, req.nickname, req.labels)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/remove-label", summary="移除联系人标签")
async def remove_contact_label(req: ContactLabelRequest):
    """移除联系人标签"""
    try:
        pid = _resolve_pid(req.pid)
        wx.remove_contact_label(pid, req.nickname, req.labels)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/star", summary="设为星标朋友")
async def set_contact_star(req: ContactStarRequest):
    """设为星标朋友"""
    try:
        pid = _resolve_pid(req.pid)
        wx.set_contact_star(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/unstar", summary="取消星标朋友")
async def cancel_contact_star(req: ContactStarRequest):
    """取消星标朋友"""
    try:
        pid = _resolve_pid(req.pid)
        wx.cancel_contact_star(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/black", summary="加入黑名单")
async def black_contact(req: ContactStarRequest):
    """加入黑名单"""
    try:
        pid = _resolve_pid(req.pid)
        wx.black_contact(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/unblack", summary="移出黑名单")
async def unblack_contact(req: ContactStarRequest):
    """移出黑名单"""
    try:
        pid = _resolve_pid(req.pid)
        wx.unblack_contact(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/contact/delete", summary="删除联系人")
async def delete_contact(req: ContactStarRequest):
    """删除联系人"""
    try:
        pid = _resolve_pid(req.pid)
        wx.delete_contact(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 群聊操作接口 ----

@app.post("/room/set-name", summary="设置群聊名称")
async def set_room_name(req: RoomNameRequest):
    """设置群聊名称"""
    try:
        pid = _resolve_pid(req.pid)
        wx.set_room_name(pid, req.nickname, req.name)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/room/set-announcement", summary="设置群公告")
async def set_room_announcement(req: RoomAnnouncementRequest):
    """设置群公告"""
    try:
        pid = _resolve_pid(req.pid)
        wx.set_room_announcement(pid, req.nickname, req.content)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/room/add-members", summary="添加群成员")
async def add_room_members(req: RoomMembersRequest):
    """添加群成员"""
    try:
        pid = _resolve_pid(req.pid)
        wx.add_room_members(pid, req.nickname, req.members)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/room/remove-members", summary="移除群成员")
async def remove_room_members(req: RoomMembersRequest):
    """移除群成员"""
    try:
        pid = _resolve_pid(req.pid)
        wx.remove_room_members(pid, req.nickname, req.members)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/room/exit", summary="退出群聊")
async def exit_room(req: ChatNicknameRequest):
    """退出群聊"""
    try:
        pid = _resolve_pid(req.pid)
        wx.exit_room(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 会话置顶/免打扰 ----

@app.post("/chat/pin", summary="置顶会话")
async def pin_chat(req: ChatNicknameRequest):
    """置顶会话"""
    try:
        pid = _resolve_pid(req.pid)
        wx.pin_chat(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/unpin", summary="取消置顶")
async def unpin_chat(req: ChatNicknameRequest):
    """取消置顶"""
    try:
        pid = _resolve_pid(req.pid)
        wx.unpin_chat(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/mute", summary="消息免打扰")
async def mute_chat(req: ChatNicknameRequest):
    """消息免打扰"""
    try:
        pid = _resolve_pid(req.pid)
        wx.mute_chat(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/unmute", summary="取消免打扰")
async def unmute_chat(req: ChatNicknameRequest):
    """取消免打扰"""
    try:
        pid = _resolve_pid(req.pid)
        wx.unmute_chat(pid, req.nickname)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 消息监听与回调 ----

@app.post("/callback", summary="设置消息回调地址")
async def set_callback(req: CallbackRequest):
    """
    设置消息回调地址。

    收到新消息时，服务会将消息以 JSON POST 到该地址。
    设为空字符串取消回调。

    回调 POST body 示例:
    {
        "type": "TextMessage",
        "type_label": "文本",
        "sender": "张三",
        "sender_type": "friend",
        "content": "你好",
        "status": "received",
        "pid": 12345,
        "chat_name": "张三"
    }
    """
    global _callback_url
    if req.url:
        _callback_url = req.url
        logger.info(f"消息回调地址已设置: {_callback_url}")
        return {"message": f"回调地址已设置: {_callback_url}"}
    else:
        _callback_url = None
        logger.info("消息回调已取消")
        return {"message": "回调已取消"}


@app.get("/callback", summary="获取当前回调地址")
async def get_callback():
    """获取当前设置的消息回调地址"""
    return {"callback_url": _callback_url}


@app.post("/listen/add", summary="添加聊天监听")
async def add_listen(req: ListenRequest):
    """
    为指定客户端添加聊天监听。

    添加监听后，该联系人/群聊的新消息会通过回调地址推送。
    """
    try:
        pid = _resolve_pid(req.pid)
        chats = wx.add_chat_listen(pid, req.names)
        return {
            "success": True,
            "listening": [c.current_name for c in chats if hasattr(c, "current_name")],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/listen/remove", summary="移除聊天监听")
async def remove_listen(req: ListenRequest):
    """移除指定客户端的聊天监听"""
    try:
        pid = _resolve_pid(req.pid)
        wx.remove_chat_listen(pid, req.names)
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/listen/start", summary="启动消息监听")
async def start_listen():
    """
    启动后台消息监听线程。

    需要先通过 /listen/add 添加监听对象，并通过 /callback 设置回调地址。
    监听启动后，新消息会自动推送到回调地址。
    """
    global _listen_thread

    if _listen_thread and _listen_thread.is_alive():
        return {"message": "监听已在运行中"}

    if not _callback_url:
        raise HTTPException(status_code=400, detail="请先设置回调地址 (POST /callback)")

    def _run_listen():
        try:
            wx.run(interval=0.1, idle_interval=0.1)
        except Exception as e:
            logger.error(f"监听线程异常退出: {e}")

    _listen_thread = threading.Thread(target=_run_listen, daemon=True, name="wx-listen")
    _listen_thread.start()
    return {"message": "消息监听已启动"}


@app.post("/listen/stop", summary="停止消息监听")
async def stop_listen():
    """停止后台消息监听"""
    wx.stop()
    return {"message": "消息监听已停止"}


# ---- 朋友圈 ----

@app.post("/moments/get", summary="获取朋友圈动态")
async def get_moments(pid: Optional[int] = None, count: int = 10):
    """获取朋友圈动态"""
    try:
        pid = _resolve_pid(pid)
        moments = wx.get_moments(pid, count)
        return {"moments": moments}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- 启动入口 ----

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9100)
