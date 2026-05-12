"""
私域机器人 RPA 版本 - watchdog 监听微信文件目录，发现新表格自动下载并删除

流程:
1. watchdog 监听微信本月文件夹，仅检测是否有新表格文件创建
2. 检测到后，打开聊天文件窗口获取今天的表格文件列表
3. 逐个另存为到 SAVE_DIR，保存后直接删除该文件项
4. 全部处理完后关闭聊天文件窗口
"""

import json
import os
import re
import time
import threading
import traceback
from datetime import datetime
from enum import Enum
from typing import Optional

import pymem
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker, Session as DBSession

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from wx import Weixin, MessageStatus, find_process


"""
私域服务端 API 客户端封装 (desktop_automation 模式)

基于《桌面自动化客户端对接文档 v2》实现，所有交互基于 nickname 进行。
服务端通过 NicknameResolver 在内部完成 nickname ↔ virtual_wxid 的双向映射。

用法:
    client = Siyu(
        base_url="https://dev-sy.jushuitan.com/WebApi/v1",
        token="your_jwt_token",
    )
    # 连接
    robot_id = client.connect(nickname="红升", device_id="xxx")
    # 心跳
    client.beat()
    # 获取收单群
    dist = client.get_distributor_from_list(order_catch="on")
    # 上报文本订单
    client.text_order_report(room_nickname="VIP群", text="苹果5斤", sender_nickname="张三")
"""

import logging
import time
import uuid
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SiyuError(Exception):
    """私域 API 错误基类"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class AuthError(SiyuError):
    """JWT 过期或未认证 (code=10001)"""
    pass


class PermissionError(SiyuError):
    """权限不足 (code=10003)"""
    pass


class MissingRobotIdError(SiyuError):
    """缺少 robot_id header (code=10008)"""
    pass


class BusinessError(SiyuError):
    """业务错误 (code=20001)"""
    pass


class Siyu:
    """
    私域服务端 API 客户端。

    封装 desktop_automation 模式下的所有 HTTP 接口，包括：
    - robot_connect: 机器人连接
    - robot_beat: 心跳
    - v2_distributor_from_list: 获取收单群列表
    - v2_provider_from_list: 获取发货群列表
    - v2_text_order_report: 文本订单上报
    - v2_file_upload_report: 文件订单上报（客户端解析后上报）
    - v2_file_upload_raw: 文件订单直传（原始文件上传，服务端解析）
    - v2_file_validate: 文件名校验
    - v2_message_precheck: 消息预校验
    - v2_nickname_mapping: 昵称映射表

    Args:
        base_url: API 基础地址，如 "https://dev-sy.jushuitan.com/WebApi/v1"
        token: JWT 认证 token
        timeout: 请求超时时间（秒），默认 10
    """

    def __init__(self, base_url: str, token: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.robot_id: Optional[str] = None
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Authorization": token,
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _handle_response(self, resp: requests.Response) -> dict:
        """统一处理响应，检查 HTTP 状态码和业务错误码"""
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code", -1)
        message = data.get("message", "")

        if code == 0:
            return data.get("result") or {}

        if code == 10001:
            raise AuthError(code, message or "未认证，请重新登录")
        elif code == 10003:
            raise PermissionError(code, message or "权限不足")
        elif code == 10008:
            raise MissingRobotIdError(code, message or "缺少 droplet-robot-id header")
        elif code == 20001:
            raise BusinessError(code, message)
        else:
            raise SiyuError(code, message or f"未知错误 code={code}")

    def _post(self, path: str, data: dict, need_robot_id: bool = True) -> dict:
        """发送 POST 请求"""
        headers = {}
        if need_robot_id and self.robot_id:
            headers["droplet-robot-id"] = self.robot_id

        resp = self._session.post(
            self._url(path),
            json={"data": data},
            headers=headers,
            timeout=self.timeout,
        )
        return self._handle_response(resp)

    # ========================= 接口方法 =========================

    def connect(
        self,
        nickname: str,
        device_id: str,
        account: str = "",
        avatar: str = "",
    ) -> str:
        """
        机器人连接（启动时调用）。

        用微信昵称查找机器人并绑定设备，返回 robot_id。
        每次启动都应调用，不缓存 robot_id。

        Args:
            nickname: 当前微信号的昵称（需 trim 空格）
            device_id: 设备唯一标识
            account: 微信号（仅展示用，可选）
            avatar: 头像 URL 或 base64（可选）

        Returns:
            robot_id 字符串

        Raises:
            BusinessError: 未找到匹配昵称的机器人
            AuthError: JWT 过期
        """
        result = self._post("/siyu/robot_connect", {
            "nickname": nickname.strip(),
            "device_id": device_id,
            "account": account,
            "avatar": avatar,
        }, need_robot_id=False)

        self.robot_id = result["robot_id"]
        self._session.headers["droplet-robot-id"] = self.robot_id
        logger.info(f"机器人已连接: robot_id={self.robot_id}")
        return self.robot_id

    def beat(self) -> None:
        """
        心跳（每 20-25 秒调用一次）。

        维持在线状态，超过 30 秒未心跳将被标记为离线。

        Raises:
            SiyuError: 心跳失败
        """
        if not self.robot_id:
            raise RuntimeError("未连接，请先调用 connect()")
        self._post("/siyu/robot_beat", {"robot_id": self.robot_id})

    def get_distributor_from_list(self, order_catch: str = "") -> dict:
        """
        获取收单群/好友列表。

        Args:
            order_catch: "on" = 只返回开启接单的；"off" = 只返回关闭的；空 = 全部

        Returns:
            dict，结构:
            {
                "rooms": [{"nickname": "...", "wx_id": "..."}],
                "friends": [{"nickname": "...", "wx_id": "..."}],
                "rooms_ignore_contact": {"群名": [{"nickname": "...", "wx_id": "..."}]}
            }
        """
        return self._post("/siyu/v2_distributor_from_list", {
            "order_catch": order_catch,
        })

    def get_provider_from_list(self, order_catch: str = "") -> dict:
        """
        获取发货群/好友列表。

        Args:
            order_catch: "on" / "off" / ""

        Returns:
            dict，结构同 get_distributor_from_list
        """
        return self._post("/siyu/v2_provider_from_list", {
            "order_catch": order_catch,
        })

    def text_order_report(
        self,
        room_nickname: str,
        text: str,
        sender_nickname: str = "",
    ) -> None:
        """
        文本订单上报。

        客户端在收单群中捕获到文本消息后，上报给服务端进行 AI 解析。

        Args:
            room_nickname: 消息来源群的昵称
            text: 原始消息文本
            sender_nickname: 发送者昵称（可选）

        Raises:
            BusinessError: 群昵称不存在
        """
        self._post("/siyu/v2_text_order_report", {
            "room_nickname": room_nickname,
            "sender_nickname": sender_nickname,
            "text": text,
        })

    def file_upload_report(
        self,
        room_nickname: str,
        file_name: str,
        headers: list[str],
        first_line: list[str],
        rows: list[list[str]],
        sender_nickname: str = "",
        file_id: str = "",
        file_type: str = "",
    ) -> None:
        """
        文件订单上报。

        客户端在收单群中捕获到 Excel 文件后，解析内容并上报。

        Args:
            room_nickname: 来源群昵称
            file_name: 原始文件名
            headers: Excel 表头（第一行）
            first_line: 第一行数据
            rows: 所有数据行（含 first_line）
            sender_nickname: 发送者昵称（可选）
            file_id: 文件唯一标识（客户端生成，用于去重）
            file_type: 文件类型（可选）
        """
        if not file_id:
            file_id = str(uuid.uuid4())

        self._post("/siyu/v2_file_upload_report", {
            "room_nickname": room_nickname,
            "sender_nickname": sender_nickname,
            "file_name": file_name,
            "file_id": file_id,
            "file_type": file_type or file_name.rsplit(".", 1)[-1] if "." in file_name else "",
            "headers": headers,
            "first_line": first_line,
            "rows": rows,
        })

    def file_validate(
        self,
        room_nickname: str,
        file_name: str,
        file_size: int = 0,
    ) -> dict:
        """
        文件名校验。

        客户端收到群文件后，先校验文件名是否有效，避免无效下载和解析。

        Args:
            room_nickname: 文件来源群的昵称
            file_name: 文件名（含扩展名）
            file_size: 文件大小（字节），用于大文件拦截

        Returns:
            dict: {"valid": bool, "type": str, "reason": str}
        """
        data = {
            "room_nickname": room_nickname,
            "file_name": file_name,
        }
        if file_size:
            data["file_size"] = file_size

        return self._post("/siyu/v2_file_validate", data)

    def message_precheck(
        self,
        room_nickname: str,
        sender_nickname: str = "",
    ) -> dict:
        """
        消息预校验。

        客户端收到群消息后，调用此接口判断是否需要处理。

        Args:
            room_nickname: 消息来源群的昵称
            sender_nickname: 发送者昵称（用于忽略列表判断）

        Returns:
            dict: {"should_process": bool, "type": str, "reason": str}
        """
        return self._post("/siyu/v2_message_precheck", {
            "room_nickname": room_nickname,
            "sender_nickname": sender_nickname,
        })

    def get_nickname_mapping(self) -> dict:
        """
        获取当前机器人的完整 wxid ↔ nickname 映射。

        通常不需要调用——v2 接口内部自动解析。
        仅在客户端需要本地缓存映射时使用。

        Returns:
            dict: {"rooms": {...}, "contacts": {...}, "room_members": {...}}
        """
        return self._post("/siyu/v2_nickname_mapping", {})

    def file_upload_raw(
        self,
        file_path: str,
        room_nickname: str,
        sender_nickname: str = "",
        file_type: str = "order",
    ) -> dict:
        """
        文件订单直传（v2_file_upload_raw）。

        将原始 Excel 文件直接上传给服务端，服务端完成所有解析工作
        （智能表头检测、手机号过滤、订单处理）。

        Args:
            file_path: 本地文件路径（.xlsx / .xls，最大 10MB）
            room_nickname: 消息来源群的昵称
            sender_nickname: 发送者昵称（可选）
            file_type: 文件类型，固定 "order"

        Returns:
            dict: {"file_id": str, "row_count": int, "valid_row_count": int}

        Raises:
            SiyuError: 上传失败（格式不支持、文件过大、群不存在、无有效订单等）
        """
        headers = {}
        if self.robot_id:
            headers["droplet-robot-id"] = self.robot_id

        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as fp:
            files = {"file": (file_name, fp)}
            data = {
                "room_nickname": room_nickname,
                "sender_nickname": sender_nickname,
                "file_type": file_type,
            }
            # multipart/form-data 请求不能带 Content-Type: application/json
            resp = self._session.post(
                self._url("/siyu/v2_file_upload_raw"),
                files=files,
                data=data,
                headers=headers,
                timeout=max(self.timeout, 30),  # 上传文件给更长超时
            )
        return self._handle_response(resp)

    # ========================= 心跳管理 =========================

    def start_heartbeat(self, interval: float = 22) -> "threading.Thread":
        """
        启动后台心跳线程。

        Args:
            interval: 心跳间隔（秒），推荐 20-25 秒，默认 22

        Returns:
            心跳线程对象
        """
        import threading

        def _heartbeat_loop():
            while True:
                try:
                    self.beat()
                except Exception as e:
                    logger.warning(f"心跳失败: {e}")
                time.sleep(interval)

        t = threading.Thread(target=_heartbeat_loop, daemon=True, name="siyu-heartbeat")
        t.start()
        logger.info(f"心跳线程已启动 (间隔 {interval}s)")
        return t

    # ========================= 内部工具 =========================

    def __repr__(self):
        status = "connected" if self.robot_id else "disconnected"
        return f"<Siyu({status}, robot_id={self.robot_id})>"


def get_data_dir_by_pid(pid: int) -> str:
    """通过进程 PID 扫描微信内存，提取数据目录路径。

    在微信进程内存中搜索 'Path:...\\db_storage\\contact\\contact.db' 模式，
    从匹配结果中解析出数据目录（db_storage 的父目录）。

    Args:
        pid: 微信进程的 PID

    Returns:
        数据目录路径字符串，如 'C:\\Users\\xxx\\Documents\\WeChat Files\\wxid_xxx'

    Raises:
        RuntimeError: 无法附加进程或未找到数据目录
    """
    try:
        pm = pymem.Pymem(pid)
    except Exception as e:
        raise RuntimeError(f"无法附加到进程 PID={pid}: {e}")

    pattern = re.escape(b'Path:') + b'.{10,200}' + re.escape(rb'\db_storage')

    try:
        results = pymem.pattern.pattern_scan_all(pm.process_handle, pattern, return_multiple=True)
    except Exception as e:
        raise RuntimeError(f"内存扫描失败: {e}")

    if not results:
        raise RuntimeError(f"在 PID={pid} 的内存中未找到数据目录")

    # 循环读取所有匹配地址，找到第一个可用的路径（读取可能出错）
    for addr in results:
        try:
            raw = pm.read_string(addr, byte=256)
            # raw 格式: "Path:C:\Users\xxx\...\db_storage\contact\contact.db"
            path_str = raw.split("Path:", 1)[-1].strip()

            # 截取到 \db_storage 之前，得到数据目录
            idx = path_str.find("\\db_storage")
            if idx == -1:
                continue
            return path_str[:idx]
        except Exception:
            continue

    raise RuntimeError(f"在 PID={pid} 的内存中找到 {len(results)} 个匹配，但均无法解析出有效路径")


# ==============================
# 当前登录微信号数据目录
bot_nickname = None
# _wx_processes = find_process("Weixin.exe")
# if not _wx_processes:
#     raise RuntimeError("未找到运行中的微信进程 (Weixin.exe)")
WECHAT_DATA_DIR = r"C:\Users\张明明\xwechat_files\wxid_g7leryvu7kqm22_a246" or get_data_dir_by_pid(_wx_processes[0]["pid"])
# 全局微信操作锁（下载文件和发送消息共用，避免 UI 操作冲突）
wx_lock = threading.Lock()
# 上次执行任务的时间戳（用于空闲自动扫描）
last_task_time: float = 0
# 空闲多少秒后自动扫描聊天文件
IDLE_FILE_SCAN_SECONDS = 120
# 是否启用定时检查文件功能
ENABLE_IDLE_FILE_SCAN = True
# 上次自动扫描聊天文件的时间戳
last_file_scan_time: float = 0
# 微信文件根目录
WECHAT_FILE_ROOT = rf"{WECHAT_DATA_DIR}\msg\file"
# 下载保存目录
SAVE_DIR = r"C:\Users\张明明\Desktop\待上传表格"
# 关注的扩展名
EXCEL_EXTS = {".xls", ".xlsx", ".csv"}
# 文件写入稳定检测间隔（秒）
STABLE_CHECK_INTERVAL = 1
# 连续 N 次大小不变视为写入完成
STABLE_CHECK_COUNT = 3
# ==============================


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"          # 待处理
    PROCESSING = "processing"    # 处理中
    SUCCESS = "success"          # 成功
    FAILED = "failed"            # 失败


Base = declarative_base()


class JxySiyuTask(Base):
    """私域任务表 ORM 模型"""
    __tablename__ = "jxy_siyu_task"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="任务ID")
    msg_id = Column(String(100), nullable=True, comment="消息ID")
    task_type = Column(String(50), nullable=False, comment="任务类型")
    task_name = Column(String(200), nullable=False, default="", comment="任务名称")
    task_metadata = Column(Text, nullable=True, comment="任务元数据(JSON)")
    to = Column(String(100), nullable=False, default="", comment="目标微信号/群ID")
    at_members = Column(Text, nullable=True, comment="@的成员列表(JSON)")
    content = Column(Text, nullable=True, comment="消息内容")
    files = Column(Text, nullable=True, comment="文件/图片路径列表(JSON)")
    status = Column(
        SAEnum(TaskStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=TaskStatus.PENDING, comment="任务状态",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    finished_at = Column(DateTime, nullable=True, comment="完成时间")
    fail_reason = Column(Text, nullable=True, comment="失败原因")
    extra = Column(Text, nullable=True, comment="扩展数据(JSON)")
    wxid = Column(String(100), nullable=True, comment="机器人微信号")

    def __repr__(self):
        return (f"<JxySiyuTask(id={self.id}, type={self.task_type!r}, "
                f"name={self.task_name!r}, status={self.status.value})>")


class SiYuTask:
    """
    私域任务表操作封装。

    用法:
        task_mgr = SiYuTask()  # 默认 siyu_task.db
        # 创建任务
        task = task_mgr.create("download_file", "下载表格", metadata={"file": "a.xlsx"}, wxid="wxid_xxx")
        # 更新状态
        task_mgr.update_status(task.id, TaskStatus.PROCESSING)
        task_mgr.update_status(task.id, TaskStatus.SUCCESS)
        # 查询
        t = task_mgr.get_by_id(task.id)
        pending = task_mgr.get_by_status(TaskStatus.PENDING)
    """

    def __init__(self, db_path: str = "siyu_task.db", echo: bool = False):
        db_url = f"sqlite:///{db_path}"
        self._engine = create_engine(db_url, echo=echo)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    def _get_session(self) -> DBSession:
        return self._Session()

    def create(
        self,
        task_type: str,
        task_name: str,
        to: str = "",
        content: str = "",
        files: Optional[list[str]] = None,
        at_members: Optional[list[str]] = None,
        msg_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        wxid: str = "",
    ) -> JxySiyuTask:
        """创建任务，返回任务对象"""
        with self._get_session() as session:
            task = JxySiyuTask(
                msg_id=msg_id,
                task_type=task_type,
                task_name=task_name,
                task_metadata=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                to=to,
                at_members=json.dumps(at_members, ensure_ascii=False) if at_members else None,
                content=content,
                files=json.dumps(files, ensure_ascii=False) if files else None,
                status=TaskStatus.PENDING,
                wxid=wxid,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    def get_by_id(self, task_id: int) -> Optional[JxySiyuTask]:
        """根据 ID 查询任务"""
        with self._get_session() as session:
            return session.query(JxySiyuTask).filter_by(id=task_id).first()

    def get_by_status(self, status: TaskStatus) -> list[JxySiyuTask]:
        """根据状态查询任务列表"""
        with self._get_session() as session:
            return session.query(JxySiyuTask).filter_by(status=status).all()

    def get_pending(self) -> list[JxySiyuTask]:
        """获取所有待处理任务"""
        return self.get_by_status(TaskStatus.PENDING)

    def update_status(self, task_id: int, status: TaskStatus, fail_reason: str = "") -> bool:
        """
        根据 ID 修改任务状态。
        如果状态为 SUCCESS 或 FAILED，自动设置完成时间。
        """
        with self._get_session() as session:
            task = session.query(JxySiyuTask).filter_by(id=task_id).first()
            if not task:
                return False
            task.status = status
            if status in (TaskStatus.SUCCESS, TaskStatus.FAILED):
                task.finished_at = datetime.now()
            if fail_reason:
                task.fail_reason = fail_reason
            session.commit()
            return True

    def update_metadata(self, task_id: int, metadata: dict) -> bool:
        """根据 ID 更新任务元数据"""
        with self._get_session() as session:
            task = session.query(JxySiyuTask).filter_by(id=task_id).first()
            if not task:
                return False
            task.task_metadata = json.dumps(metadata, ensure_ascii=False)
            session.commit()
            return True

    def get_by_wxid(self, wxid: str) -> list[JxySiyuTask]:
        """根据微信号查询任务列表"""
        with self._get_session() as session:
            return session.query(JxySiyuTask).filter_by(wxid=wxid).all()

    def get_by_type(self, task_type: str) -> list[JxySiyuTask]:
        """根据任务类型查询"""
        with self._get_session() as session:
            return session.query(JxySiyuTask).filter_by(task_type=task_type).all()

    def delete_by_id(self, task_id: int) -> bool:
        """根据 ID 删除任务"""
        with self._get_session() as session:
            task = session.query(JxySiyuTask).filter_by(id=task_id).first()
            if not task:
                return False
            session.delete(task)
            session.commit()
            return True


def parse_file_size(size_str: str) -> float:
    """将文件大小字符串（如 '1.5M', '500K', '2.3G'）转换为字节数，解析失败返回 0"""
    units = {'B': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
    m = re.match(r'([\d.]+)([BKMGT])', size_str.strip())
    if not m:
        return 0
    return float(m.group(1)) * units[m.group(2)]


def get_current_month_dir() -> str:
    """获取当月文件夹路径，格式: WATCH_ROOT/YYYY-MM"""
    now = datetime.now()
    month_folder = now.strftime("%Y-%m")
    return os.path.join(WECHAT_FILE_ROOT, month_folder)


def is_excel(path: str) -> bool:
    """判断是否为表格文件"""
    return os.path.splitext(path)[1].lower() in EXCEL_EXTS


def wait_file_stable(path: str) -> bool:
    """
    等待文件写入完成（文件大小连续稳定）。
    on_created 触发时文件可能还在写入中，需要等写完再操作。
    """
    stable_count = 0
    last_size = -1
    for _ in range(120):  # 最多等 120 秒
        if not os.path.exists(path):
            return False
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        if size > 0 and size == last_size:
            stable_count += 1
            if stable_count >= STABLE_CHECK_COUNT:
                return True
        else:
            stable_count = 0
        last_size = size
        time.sleep(STABLE_CHECK_INTERVAL)
    return False


class ExcelFileHandler(FileSystemEventHandler):
    """监听新表格文件创建，触发聊天文件下载和删除"""

    def __init__(self, wx: Weixin, siyu: Optional[Siyu] = None):
        super().__init__()
        self._wx = wx
        self._siyu = siyu

    def on_created(self, event):
        if event.is_directory or not is_excel(event.src_path):
            return

        file_name = os.path.basename(event.src_path)
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🆕 检测到新文件: {file_name}")

        # 在新线程中处理，避免阻塞 watchdog
        threading.Thread(
            target=self._handle_new_file,
            args=(event.src_path,),
            daemon=True,
        ).start()

    def _handle_new_file(self, src_path: str):
        """等待文件写入完成 → 打开聊天文件 → 获取今天表格 → 逐个下载删除"""
        print(f"  ⏳ 等待文件写入完成...")
        if not wait_file_stable(src_path):
            print(f"  ❌ 文件写入超时或已消失")
            return

        # 加锁，避免与发送消息等操作冲突
        with wx_lock:
            try:
                self._download_today_files()
            finally:
                _mark_task_done()

    def _download_today_files(self):
        """打开聊天文件窗口，获取今天的表格文件，逐个另存为并删除"""
        try:
            # 1. 打开聊天文件管理器，筛选表格
            print(f"  📂 打开聊天文件窗口...")
            self._wx.file_manager.open(filter_type="表格")
            time.sleep(1)

            # 2. 获取今天的文件列表
            today_files = self._wx.file_manager.get_today_files()
            if not today_files:
                print(f"  📭 今天没有表格文件")
                self._wx.file_manager.close()
                return

            print(f"  📋 今天共 {len(today_files)} 个表格文件，开始处理...")

            # 3. 逐个处理：群聊文件另存为+删除，联系人文件直接删除（倒序处理）
            for i, f in enumerate(reversed(today_files), 1):
                print(f)
                if not f._cell:
                    print(f"  ⚠️ [{i}] 跳过（无控件引用）: {f.file_name}")
                    continue

                # 机器人自己发的文件直接删除，不下载
                if f.sender_name == bot_nickname:
                    try:
                        self._wx.file_manager.delete_file(f)
                        print(f"  🗑️ [{i}/{len(today_files)}] 机器人自身文件直接删除: {f.file_name}")
                    except Exception as e:
                        print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                    continue

                # 联系人发的表格直接删除，不下载
                if f.source_type == "contact":
                    try:
                        self._wx.file_manager.delete_file(f)
                        print(f"  🗑️ [{i}/{len(today_files)}] 联系人文件直接删除: {f.file_name}")
                    except Exception as e:
                        print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                    continue

                # 超过 2MB 的文件直接删除，不下载
                if parse_file_size(f.file_size) > 2 * 1024 ** 2:
                    try:
                        self._wx.file_manager.delete_file(f)
                        print(f"  🗑️ [{i}/{len(today_files)}] 文件超过2M直接删除: {f.file_name} ({f.file_size})")
                    except Exception as e:
                        print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                    continue

                # 消息预校验：询问服务端该群/发送者的文件是否需要处理
                # if self._siyu:
                #     try:
                #         precheck = self._siyu.message_precheck(
                #             room_nickname=f.source_name,
                #             sender_nickname=f.sender_name,
                #         )
                #         if not precheck.get("should_process", True):
                #             reason = precheck.get("reason", "服务端拒绝")
                #             try:
                #                 self._wx.file_manager.delete_file(f)
                #                 print(f"  🚫 [{i}/{len(today_files)}] 预校验跳过并删除: {f.file_name} ({reason})")
                #             except Exception as e:
                #                 print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                #             continue
                #     except Exception as e:
                #         print(f"  ⚠️ 预校验异常（继续处理）: {f.file_name} - {e}")

                # 文件名校验：询问服务端该文件名是否有效，避免无效下载
                # if self._siyu:
                #     try:
                #         file_size_bytes = int(parse_file_size(f.file_size))
                #         validate = self._siyu.file_validate(
                #             room_nickname=f.source_name,
                #             file_name=f.file_name,
                #             file_size=file_size_bytes,
                #         )
                #         if not validate.get("valid", True):
                #             reason = validate.get("reason", "文件名无效")
                #             try:
                #                 self._wx.file_manager.delete_file(f)
                #                 print(f"  🚫 [{i}/{len(today_files)}] 文件校验不通过并删除: {f.file_name} ({reason})")
                #             except Exception as e:
                #                 print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                #             continue
                #     except Exception as e:
                #         print(f"  ⚠️ 文件校验异常（继续处理）: {f.file_name} - {e}")

                # 未下载的文件先触发下载，尝试右键复制验证下载完成（最长30秒）
                if f.file_status == "未下载":
                    print(f"  📥 [{i}/{len(today_files)}] 下载中: {f.file_name}")
                    try:
                        f.download()
                        time.sleep(3)
                        # 尝试右键复制验证下载是否完成，最多重试10次，每次等3秒
                        downloaded = False
                        for attempt in range(10):
                            try:
                                f.copy()
                                downloaded = True
                                break
                            except Exception:
                                time.sleep(3)
                        if not downloaded:
                            print(f"  ❌ 下载超时: {f.file_name}")
                            continue
                        print(f"  ✅ 下载完成: {f.file_name}")
                    except Exception as e:
                        print(f"  ❌ 下载异常: {f.file_name} - {e}")
                        continue

                # 群聊文件：另存为到本地 → 上传服务端 → 定位回复 → 删除
                # 构造本地保存路径
                save_path = os.path.join(SAVE_DIR, f.file_name)
                if os.path.exists(save_path):
                    name, ext = os.path.splitext(f.file_name)
                    timestamp = datetime.now().strftime("%H%M%S")
                    save_path = os.path.join(SAVE_DIR, f"{name}_{timestamp}{ext}")

                # 另存为到本地
                print(f"  📥 [{i}/{len(today_files)}] 另存为: {f.file_name}")
                try:
                    ok = self._wx.file_manager.save_file_as(f, save_path)
                    if not ok:
                        print(f"  ❌ 另存为失败: {f.file_name}")
                        continue
                    print(f"  ✅ 已保存到本地: {save_path}")
                except Exception as e:
                    print(f"  ❌ 另存为异常: {f.file_name} - {e}")
                    continue

                # 上传文件到服务端 v2_file_upload_raw
                upload_success = False
                if self._siyu:
                    print(f"  📤 [{i}/{len(today_files)}] 上传服务端: {f.file_name}")
                    try:
                        result = self._siyu.file_upload_raw(
                            file_path=save_path,
                            room_nickname=f.source_name,
                            sender_nickname=f.sender_name or "",
                        )
                        file_id = result.get("file_id", "")
                        row_count = result.get("row_count", 0)
                        valid_row_count = result.get("valid_row_count", 0)
                        print(f"  ✅ 上传成功: file_id={file_id}, 总行数={row_count}, 有效行数={valid_row_count}")
                        upload_success = True
                    except SiyuError as e:
                        print(f"  ❌ 上传失败: {f.file_name} - {e}")
                    except Exception as e:
                        print(f"  ❌ 上传异常: {f.file_name} - {e}")
                        traceback.print_exc()

                # 清理本地临时文件
                try:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                except Exception:
                    pass

                # 上传成功后，定位到聊天位置并引用回复确认消息
                if upload_success:
                    try:
                        f.switch_to_message()
                        time.sleep(1)

                        chat = self._wx.chat
                        if chat:
                            messages = chat.get_visible_messages()
                            target_msg = None
                            for msg in reversed(messages):
                                if hasattr(msg, 'file_name') and msg.file_name == f.file_name:
                                    target_msg = msg
                                    break
                            if target_msg:
                                chat.send_text("已收到文件，正在处理中，请耐心等待。", reply_to=target_msg)
                                print(f"  ✅ 已引用回复: {f.file_name}")
                            else:
                                chat.send_text("已收到文件，正在处理中，请耐心等待。")
                                print(f"  ✅ 已回复（未匹配到消息引用）: {f.file_name}")
                        else:
                            print(f"  ⚠️ 定位后未找到聊天窗口: {f.file_name}")
                    except Exception as e:
                        print(f"  ⚠️ 回复异常（不影响删除）: {f.file_name} - {e}")

                # 删除聊天文件管理器中的文件项
                try:
                    time.sleep(0.5)
                    self._wx.file_manager.delete_file(f)
                    print(f"  🗑️ 已删除: {f.file_name}")
                except Exception as e:
                    print(f"  ⚠️ 删除异常: {f.file_name} - {e}")

            # 4. 关闭聊天文件窗口
            self._wx.file_manager.close()
            print(f"  ✅ 全部处理完成")

        except Exception as e:
            print(f"  ❌ 处理异常: {e}")
            traceback.print_exc()
            try:
                self._wx.file_manager.close()
            except Exception:
                pass


def _handle_send_text(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """处理发送文本消息任务"""
    chat = wx.open_session_by_search(task.to)

    # 如果有 @成员，使用 send_at
    if task.at_members:
        members = json.loads(task.at_members)
        status = chat.send_at(task.content or "", members)
    else:
        status = chat.send_text(task.content or "")

    if status == MessageStatus.FAILED:
        raise RuntimeError("消息发送失败")


def _handle_send_file(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """处理发送文件任务"""
    if not task.files:
        raise RuntimeError("files 字段为空，没有要发送的文件")

    file_list = json.loads(task.files)
    chat = wx.open_session_by_search(task.to)

    # 先发文本内容（如果有）
    if task.content:
        chat.send_text(task.content)
        time.sleep(0.5)

    # 逐个发送文件
    for file_path in file_list:
        if not os.path.exists(file_path):
            raise RuntimeError(f"文件不存在: {file_path}")
        status = chat.send_file(file_path)
        if status == MessageStatus.FAILED:
            raise RuntimeError(f"文件发送失败: {file_path}")
        time.sleep(0.5)


def _handle_send_image(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """处理发送图片任务（图片也通过 send_file 发送）"""
    if not task.files:
        raise RuntimeError("files 字段为空，没有要发送的图片")

    file_list = json.loads(task.files)
    chat = wx.open_session_by_search(task.to)

    # 先发文本内容（如果有）
    if task.content:
        chat.send_text(task.content)
        time.sleep(0.5)

    # 逐个发送图片
    for file_path in file_list:
        if not os.path.exists(file_path):
            raise RuntimeError(f"图片不存在: {file_path}")
        status = chat.send_file(file_path)
        if status == MessageStatus.FAILED:
            raise RuntimeError(f"图片发送失败: {file_path}")
        time.sleep(0.5)


def _handle_send_room_at(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """
    处理 /msg/send_room_at — 发送群文本消息（带 @）

    metadata 中包含:
      - at_nickname_list: {wxid: nickname} 映射
    task.to: 目标群昵称 (to_nickname)
    task.content: 消息文本
    task.at_members: at_nickname_list 中的 nickname 列表
    """
    chat = wx.open_session_by_search(task.to)

    if task.at_members:
        members = json.loads(task.at_members)
        status = chat.send_at(task.content or "", members)
    else:
        status = chat.send_text(task.content or "")

    if status == MessageStatus.FAILED:
        raise RuntimeError("群消息发送失败")


def _generate_excel_file(excel_name: str, datas: list) -> str:
    """
    根据 excel_msg 数据生成 Excel 文件到临时目录，返回文件路径。

    Args:
        excel_name: 文件名（如 "回单_20260512.xlsx"）
        datas: 二维数组，第一行为表头

    Returns:
        生成的 Excel 文件路径
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in datas:
        ws.append(row)

    # 保存到临时目录
    temp_dir = os.path.join(SAVE_DIR, "_temp_excel")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, excel_name)
    # 避免重名
    if os.path.exists(file_path):
        name, ext = os.path.splitext(excel_name)
        timestamp = datetime.now().strftime("%H%M%S")
        file_path = os.path.join(temp_dir, f"{name}_{timestamp}{ext}")

    wb.save(file_path)
    return file_path


def _handle_send_excel(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """
    处理 /msg/send_file_msg, /msg/send_file_gys, /msg/send_file_gys_bill
    — 生成 Excel 文件并发送到群

    metadata 中包含:
      - excel_msg: {"excel_name": str, "datas": [[...]]}
      - at_nickname_list: {wxid: nickname}
    task.to: 目标群昵称
    task.content: 附带的文本消息
    task.at_members: @ 的成员昵称列表
    """
    metadata = json.loads(task.task_metadata) if task.task_metadata else {}
    excel_msg = metadata.get("excel_msg")
    if not excel_msg:
        raise RuntimeError("缺少 excel_msg 数据")

    excel_name = excel_msg.get("excel_name", "output.xlsx")
    datas = excel_msg.get("datas", [])
    if not datas:
        raise RuntimeError("excel_msg.datas 为空")

    # 生成 Excel 文件
    file_path = _generate_excel_file(excel_name, datas)

    try:
        chat = wx.open_session_by_search(task.to)

        # 先发文本内容（带 @ 或不带）
        if task.content:
            if task.at_members:
                members = json.loads(task.at_members)
                chat.send_at(task.content, members)
            else:
                chat.send_text(task.content)
            time.sleep(0.5)

        # 发送 Excel 文件
        status = chat.send_file(file_path)
        if status == MessageStatus.FAILED:
            raise RuntimeError(f"Excel 文件发送失败: {excel_name}")
    finally:
        # 清理临时文件
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


def _handle_send_binary_file(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """
    处理 /msg/send_file — 发送文件（支持 b64 / url / file_path）

    metadata 中包含:
      - b64: base64 编码的文件内容
      - url: 文件下载 URL
      - file_path: 本地文件路径
      - file_name: 文件名（用于 b64/url 场景）
    task.to: 目标群/好友昵称
    """
    import base64

    metadata = json.loads(task.task_metadata) if task.task_metadata else {}
    b64_data = metadata.get("b64", "")
    url = metadata.get("url", "")
    file_path = metadata.get("file_path", "")
    file_name = metadata.get("file_name", "file")

    local_path = None
    temp_file = False

    if file_path and os.path.exists(file_path):
        # 直接使用本地文件
        local_path = file_path
    elif b64_data:
        # base64 解码保存到临时文件
        temp_dir = os.path.join(SAVE_DIR, "_temp_files")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, file_name)
        with open(local_path, "wb") as fp:
            fp.write(base64.b64decode(b64_data))
        temp_file = True
    elif url:
        # 从 URL 下载
        temp_dir = os.path.join(SAVE_DIR, "_temp_files")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, file_name)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(local_path, "wb") as fp:
            fp.write(resp.content)
        temp_file = True
    else:
        raise RuntimeError("send_file: 缺少 b64/url/file_path，无法获取文件")

    try:
        chat = wx.open_session_by_search(task.to)
        status = chat.send_file(local_path)
        if status == MessageStatus.FAILED:
            raise RuntimeError(f"文件发送失败: {file_name}")
    finally:
        if temp_file and local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


def _handle_send_message_with_type(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """
    处理 /msg/send_message_with_type — 发送多类型消息

    metadata 中包含:
      - type: "text" / "image" / "file" / "video"
      - url: 文件/图片 URL
      - file_name: 文件名
      - at_nickname_list: @ 成员映射
    task.to: 目标群/好友昵称
    task.content: 文本内容
    task.at_members: @ 的成员昵称列表
    """
    import base64

    metadata = json.loads(task.task_metadata) if task.task_metadata else {}
    msg_type = metadata.get("type", "text")
    url = metadata.get("url", "")
    file_name = metadata.get("file_name", "file")

    chat = wx.open_session_by_search(task.to)

    if msg_type == "text":
        # 纯文本消息
        if task.at_members:
            members = json.loads(task.at_members)
            status = chat.send_at(task.content or "", members)
        else:
            status = chat.send_text(task.content or "")
        if status == MessageStatus.FAILED:
            raise RuntimeError("文本消息发送失败")

    elif msg_type in ("image", "file", "video"):
        # 先发文本（如果有）
        if task.content:
            if task.at_members:
                members = json.loads(task.at_members)
                chat.send_at(task.content, members)
            else:
                chat.send_text(task.content)
            time.sleep(0.5)

        # 下载文件并发送
        if not url:
            raise RuntimeError(f"send_message_with_type({msg_type}): 缺少 url")

        temp_dir = os.path.join(SAVE_DIR, "_temp_files")
        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, file_name)

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(local_path, "wb") as fp:
                fp.write(resp.content)

            status = chat.send_file(local_path)
            if status == MessageStatus.FAILED:
                raise RuntimeError(f"{msg_type} 发送失败: {file_name}")
        finally:
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception:
                pass
    else:
        raise RuntimeError(f"不支持的消息类型: {msg_type}")


def _handle_refresh_rooms(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
    """
    处理 /contact/update_rooms_contacts — 刷新群列表

    此任务不需要操作微信 UI，仅标记为成功。
    实际刷新逻辑由主循环中的 siyu 客户端完成。
    """
    # 标记需要刷新（通过 metadata 传递信号给主循环）
    print("  📋 收到刷新群列表通知")


# 任务类型 → 处理函数映射
TASK_HANDLERS = {
    "send_text": _handle_send_text,
    "send_file": _handle_send_file,
    "send_image": _handle_send_image,
    "send_room_at": _handle_send_room_at,
    "send_excel": _handle_send_excel,
    "send_binary_file": _handle_send_binary_file,
    "send_message_with_type": _handle_send_message_with_type,
    "refresh_rooms": _handle_refresh_rooms,
}


# ========================= FastAPI 回调服务 =========================

api = FastAPI(title="私域机器人回调服务", version="0.1.0")
# 模块级任务管理器，供 API 和 RPA 主循环共用
_api_task_mgr: Optional[SiYuTask] = None


class SendTextRequest(BaseModel):
    """发送文本消息的回调请求体"""
    to: str = Field(..., description="目标会话（联系人昵称或群名）")
    content: str = Field(..., description="消息内容")
    at_members: Optional[list[str]] = Field(default=None, description="需要@的成员列表")
    msg_id: Optional[str] = Field(default=None, description="外部消息ID，用于去重/追踪")
    wxid: Optional[str] = Field(default=None, description="机器人微信号")


@api.post("/siyu/wxrpa/msg/send_text")
def send_text_callback(req: SendTextRequest):
    """接收发送文本消息的推送通知，保存到任务表"""
    task = _api_task_mgr.create(
        task_type="send_text",
        task_name=f"发送文本到 {req.to}",
        to=req.to,
        content=req.content,
        at_members=req.at_members,
        msg_id=req.msg_id,
        wxid=req.wxid or "",
    )
    return {
        "code": 0,
        "msg": "任务已创建",
        "data": {
            "task_id": task.id,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
        },
    }


# ========================= WxService 统一回调接口 =========================

# api_path → task_type 映射
_API_PATH_TO_TASK_TYPE = {
    "/msg/send_room_at": "send_room_at",
    "/msg/send_file_msg": "send_excel",
    "/msg/send_file_gys": "send_excel",
    "/msg/send_file_gys_bill": "send_excel",
    "/msg/send_file": "send_binary_file",
    "/msg/send_message_with_type": "send_message_with_type",
    "/contact/update_rooms_contacts": "refresh_rooms",
}

# 桌面自动化模式下应忽略的命令
_IGNORED_API_PATHS = {
    "/contact/get_contacts",
    "/contacts/refresh_and_upload_full_contacts_and_rooms",
    "/room/get_rooms",
    "/room/refresh_room_contacts_by_room_id",
}


class SiyuCmdRequest(BaseModel):
    """WxService gRPC 推送的统一命令格式"""
    type: str = Field(default="siyu_cmd")
    data: dict = Field(..., description="命令数据")


@api.post("/siyu/wxrpa/cmd")
def siyu_cmd_callback(req: SiyuCmdRequest):
    """
    接收 WxService 服务端推送的统一命令，解析后生成对应任务。

    请求格式:
    {
      "type": "siyu_cmd",
      "data": {
        "api_path": "/msg/send_room_at",
        "param": { ... },
        "request_id": "uuid-xxx",
        "robot_type": "wx",
        "ts": "2026-05-12 10:30:00",
        "robot_id": "651249037923681e9c985192"
      }
    }
    """
    cmd_data = req.data
    api_path = cmd_data.get("api_path", "")
    param = cmd_data.get("param") or {}
    request_id = cmd_data.get("request_id", "")
    robot_id = cmd_data.get("robot_id", "")

    # 忽略桌面自动化模式不需要处理的命令
    if api_path in _IGNORED_API_PATHS:
        return {
            "code": 0,
            "msg": f"命令已忽略（桌面自动化模式不适用）: {api_path}",
            "data": {"ignored": True},
        }

    # 查找对应的任务类型
    task_type = _API_PATH_TO_TASK_TYPE.get(api_path)
    if not task_type:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 api_path: {api_path}",
        )

    # 提取通用字段
    to_nickname = param.get("to_nickname", "")
    content = param.get("content", "")
    at_nickname_list = param.get("at_nickname_list") or {}
    # 将 at_nickname_list 的 values 作为 at_members（昵称列表）
    at_members = list(at_nickname_list.values()) if at_nickname_list else None

    # 构建 metadata（保存原始 param 中的扩展信息）
    metadata = {}

    if task_type == "send_room_at":
        # 纯文本 + @
        metadata["at_nickname_list"] = at_nickname_list

    elif task_type == "send_excel":
        # Excel 生成 + 发送
        metadata["excel_msg"] = param.get("excel_msg") or {}
        metadata["at_nickname_list"] = at_nickname_list
        metadata["order_info"] = param.get("order_info") or {}
        metadata["enable_reply_new_shipment"] = param.get("enable_reply_new_shipment", False)
        metadata["new_shipment_order_indexs"] = param.get("new_shipment_order_indexs") or []

    elif task_type == "send_binary_file":
        # 文件发送（b64/url/file_path）
        metadata["b64"] = param.get("b64", "")
        metadata["url"] = param.get("url", "")
        metadata["file_path"] = param.get("file_path", "")
        metadata["file_name"] = param.get("file_name", "file")

    elif task_type == "send_message_with_type":
        # 多类型消息
        metadata["type"] = param.get("type", "text")
        metadata["url"] = param.get("url", "")
        metadata["file_name"] = param.get("file_name", "file")
        metadata["file_size"] = param.get("file_size", 0)
        metadata["at_nickname_list"] = at_nickname_list
        metadata["msg_id"] = param.get("msg_id", "")

    elif task_type == "refresh_rooms":
        # 刷新群列表（无需额外参数）
        pass

    # 生成任务名称
    task_name_map = {
        "send_room_at": f"群消息(@) → {to_nickname}",
        "send_excel": f"发送Excel → {to_nickname}",
        "send_binary_file": f"发送文件 → {to_nickname}",
        "send_message_with_type": f"发送{param.get('type', '?')}消息 → {to_nickname}",
        "refresh_rooms": "刷新群列表",
    }
    task_name = task_name_map.get(task_type, f"{api_path} → {to_nickname}")

    # 创建任务
    task = _api_task_mgr.create(
        task_type=task_type,
        task_name=task_name,
        to=to_nickname,
        content=content,
        at_members=at_members,
        msg_id=request_id,
        metadata=metadata,
        wxid=robot_id,
    )

    print(f"  📨 收到命令 [{api_path}] → 任务 [{task.id}] {task_name}")

    return {
        "code": 0,
        "msg": "任务已创建",
        "data": {
            "task_id": task.id,
            "task_type": task_type,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
        },
    }


@api.get("/siyu/wxrpa/task/{task_id}")
def get_task_status(task_id: int):
    """查询任务状态"""
    task = _api_task_mgr.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "code": 0,
        "data": {
            "task_id": task.id,
            "task_type": task.task_type,
            "task_name": task.task_name,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "fail_reason": task.fail_reason,
        },
    }


def _start_api_server(host: str = "0.0.0.0", port: int = 8000):
    """在后台线程中启动 FastAPI 服务"""
    uvicorn.run(api, host=host, port=port, log_level="info")


def _mark_task_done():
    """标记任务完成时间，用于空闲计时"""
    global last_task_time
    last_task_time = time.time()


def _try_idle_file_scan(wx: Weixin, siyu: Optional[Siyu] = None):
    """空闲超过 IDLE_FILE_SCAN_SECONDS 且距上次扫描也超过该时间，自动扫描聊天文件"""
    if not ENABLE_IDLE_FILE_SCAN:
        return

    global last_file_scan_time
    now = time.time()

    # 有任务刚执行完不久，不算空闲
    if last_task_time > 0 and now - last_task_time < IDLE_FILE_SCAN_SECONDS:
        return
    # 距上次扫描不足间隔
    if now - last_file_scan_time < IDLE_FILE_SCAN_SECONDS:
        return

    last_file_scan_time = now
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 空闲 {IDLE_FILE_SCAN_SECONDS}s，自动扫描聊天文件...")

    with wx_lock:
        try:
            handler = ExcelFileHandler(wx, siyu=siyu)
            handler._download_today_files()
        except Exception as e:
            print(f"  ❌ 自动扫描异常: {e}")
            traceback.print_exc()
        finally:
            _mark_task_done()


def do_task(wx: Weixin, task_mgr: SiYuTask):
    """
    取出待处理任务，按类型分发执行。
    入口即获取 wx_lock，整批任务执行完再释放，避免与文件下载交叉。
    """
    pending = task_mgr.get_pending()
    if not pending:
        return

    with wx_lock:
        for task in pending:
            handler = TASK_HANDLERS.get(task.task_type)
            if not handler:
                task_mgr.update_status(
                    task.id, TaskStatus.FAILED,
                    fail_reason=f"未知的任务类型: {task.task_type}",
                )
                print(f"  ❌ 未知任务类型: {task.task_type} (id={task.id})")
                continue

            # 标记为处理中
            task_mgr.update_status(task.id, TaskStatus.PROCESSING)
            print(f"  ▶️ 执行任务 [{task.id}] {task.task_type}: {task.task_name}")

            try:
                handler(wx, task, task_mgr)
                task_mgr.update_status(task.id, TaskStatus.SUCCESS)
                print(f"  ✅ 任务成功 [{task.id}]")
            except Exception as e:
                task_mgr.update_status(
                    task.id, TaskStatus.FAILED, fail_reason=str(e),
                )
                print(f"  ❌ 任务失败 [{task.id}]: {e}")
                traceback.print_exc()
        _mark_task_done()


def run():
    os.makedirs(SAVE_DIR, exist_ok=True)

    print("=" * 55)
    print("  聚协云私域机器人RPA版本")
    print("=" * 55)

    # 初始化微信
    wx = Weixin()
    print("✅ 微信已连接")
    # self_info = wx.get_self_info()
    # bot_nickname_local = self_info.get("nickname", "")
    # print(f"当前账号: {bot_nickname_local} (微信号: {self_info.get('account', '')})")

    # 更新全局 bot_nickname
    # global bot_nickname
    # bot_nickname = bot_nickname_local

    # 连接私域服务端
    siyu = Siyu(
        base_url="https://dev-sy.jushuitan.com/WebApi/v1",
        token="your_jwt_token",  # TODO: 替换为实际 token
    )
    # device_id = f"rpa_{os.environ.get('COMPUTERNAME', 'unknown')}_{wx.pid}"
    # siyu.connect(
    #     nickname=bot_nickname_local,
    #     device_id=device_id,
    #     account=self_info.get("account", ""),
    #     avatar=self_info.get("avatar", ""),
    # )
    # print(f"✅ 私域服务端已连接: robot_id={siyu.robot_id}")

    # 启动心跳线程
    # siyu.start_heartbeat(interval=22)
    print("💓 心跳线程已启动")

    # 在文件传输助手发送启动通知
    # startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # wx.send_text("文件传输助手", f"[{startup_time}] 机器人启动成功！")
    # print("📨 已发送启动通知到文件传输助手")

    # 初始化任务管理器
    task_mgr = SiYuTask()
    print("✅ 任务数据库已就绪")

    # 启动 FastAPI 回调服务（后台线程）
    global _api_task_mgr
    _api_task_mgr = task_mgr
    api_thread = threading.Thread(
        target=_start_api_server, kwargs={"host": "127.0.0.1", "port": 8000}, daemon=True,
    )
    api_thread.start()
    print("🌐 API 回调服务: http://127.0.0.1:8000")

    # 启动文件监听线程
    watch_dir = get_current_month_dir()
    os.makedirs(watch_dir, exist_ok=True)
    handler = ExcelFileHandler(wx, siyu=siyu)
    observer = Observer()
    observer.schedule(handler, path=watch_dir, recursive=True)
    observer.start()
    print(f"🔄 文件监听: {watch_dir}")

    print(f"📋 任务轮询已启动")
    print(f"按 Ctrl+C 停止")
    print("=" * 55 + "\n")

    try:
        while True:
            # 执行待处理任务
            try:
                do_task(wx, task_mgr)
            except Exception as e:
                print(f"⚠️ 任务轮询异常: {e}")
                traceback.print_exc()

            # 检查月份切换
            new_dir = get_current_month_dir()
            if new_dir != watch_dir:
                print(f"\n📅 月份切换，更新监听目录: {new_dir}")
                observer.unschedule_all()
                watch_dir = new_dir
                os.makedirs(watch_dir, exist_ok=True)
                observer.schedule(handler, path=watch_dir, recursive=True)

            # 空闲超过2分钟自动扫描聊天文件
            _try_idle_file_scan(wx, siyu=siyu)

            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
        print("\n\n🛑 已停止")
    observer.join()


if __name__ == "__main__":
    run()
