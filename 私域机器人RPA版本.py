def run(droplet_token, device_id, send_offline_msg):
    """
    HEADER START

    :param !droplet_token: {string} 客户端TOKEN
    :param !device_id: {string} 客户端设备ID
    :param send_offline_msg: {dict} 是否发送离线消息
    HEADER END
    """
    
    """
    私域机器人 RPA 版本 - watchdog 监听微信文件目录，发现新表格自动下载并删除

    流程:
    1. watchdog 监听微信本月文件夹，仅检测是否有新表格文件创建
    2. 检测到后，打开聊天文件窗口获取今天的表格文件列表
    3. 逐个另存为到临时目录，保存后直接删除该文件项
    4. 全部处理完后关闭聊天文件窗口
    """
    # CODE START
    import base64
    import json
    import logging
    import os
    import re
    import threading
    import time
    import traceback
    import urllib.parse
    import uuid
    from datetime import datetime
    from enum import Enum
    from typing import Dict, List, Optional

    import openpyxl
    import pymem
    import requests
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
    from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Enum as SAEnum
    from sqlalchemy.orm import declarative_base, sessionmaker, Session as DBSession
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    from pywxauto.wx import Weixin, MessageStatus

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
            print("================>", resp.json())
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
            if not self.robot_id:
                raise RuntimeError("未连接，请先调用 connect()")
            self._post("/siyu/robot_beat", {"robot_id": self.robot_id})

        def get_distributor_from_list(self, order_catch: str = "") -> dict:
            return self._post("/siyu/v2_distributor_from_list", {
                "order_catch": order_catch,
            })

        def get_provider_from_list(self, order_catch: str = "") -> dict:
            return self._post("/siyu/v2_provider_from_list", {
                "order_catch": order_catch,
            })

        def text_order_report(
            self,
            room_nickname: str,
            text: str,
            sender_nickname: str = "",
        ) -> None:
            self._post("/siyu/v2_text_order_report", {
                "room_nickname": room_nickname,
                "sender_nickname": sender_nickname,
                "text": text,
            })

        def file_upload_report(
            self,
            room_nickname: str,
            file_name: str,
            headers: List[str],
            first_line: List[str],
            rows: List[List[str]],
            sender_nickname: str = "",
            file_id: str = "",
            file_type: str = "",
        ) -> None:
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
            return self._post("/siyu/v2_message_precheck", {
                "room_nickname": room_nickname,
                "sender_nickname": sender_nickname,
            })

        def get_nickname_mapping(self) -> dict:
            return self._post("/siyu/v2_nickname_mapping", {})

        def file_upload_raw(
            self,
            file_path: str,
            room_nickname: str,
            sender_nickname: str = "",
            file_type: str = "order",
        ) -> dict:
            headers = {}
            if self.robot_id:
                headers["droplet-robot-id"] = self.robot_id
            headers["Content-Type"] = None

            file_name = os.path.basename(file_path)
            with open(file_path, "rb") as fp:
                files = {"file": (file_name, fp)}
                data = {
                    "room_nickname": room_nickname,
                    "sender_nickname": sender_nickname,
                    "file_type": file_type,
                }
                resp = self._session.post(
                    self._url("/siyu/v2_file_upload_raw"),
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=max(self.timeout, 30),
                )
            return self._handle_response(resp)

        # ========================= 心跳管理 =========================

        def start_heartbeat(self, interval: float = 22) -> "threading.Thread":
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

        def __repr__(self):
            status = "connected" if self.robot_id else "disconnected"
            return f"<Siyu({status}, robot_id={self.robot_id})>"


    def get_data_dir_by_pid(pid: int) -> str:
        """通过进程 PID 扫描微信内存，提取数据目录路径。"""
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

        for addr in results:
            try:
                raw = pm.read_string(addr, byte=256)
                path_str = raw.split("Path:", 1)[-1].strip()
                idx = path_str.find("\\db_storage")
                if idx == -1:
                    continue
                return path_str[:idx]
            except Exception:
                continue

        raise RuntimeError(f"在 PID={pid} 的内存中找到 {len(results)} 个匹配，但均无法解析出有效路径")


    class TaskStatus(Enum):
        """任务状态"""
        PENDING = "pending"
        PROCESSING = "processing"
        SUCCESS = "success"
        FAILED = "failed"


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
        bot_id = Column(String(100), nullable=True, comment="机器人ID")

        def __repr__(self):
            return (f"<JxySiyuTask(id={self.id}, type={self.task_type!r}, "
                    f"name={self.task_name!r}, status={self.status.value})>")


    class SiYuTask:
        """私域任务表操作封装。"""

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
            files: Optional[List[str]] = None,
            at_members: Optional[List[str]] = None,
            msg_id: Optional[str] = None,
            metadata: Optional[dict] = None,
            bot_id: str = "",
        ) -> JxySiyuTask:
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
                    bot_id=bot_id,
                )
                session.add(task)
                session.commit()
                session.refresh(task)
                return task

        def get_by_id(self, task_id: int) -> Optional[JxySiyuTask]:
            with self._get_session() as session:
                return session.query(JxySiyuTask).filter_by(id=task_id).first()

        def get_by_status(self, status: TaskStatus) -> List[JxySiyuTask]:
            with self._get_session() as session:
                return session.query(JxySiyuTask).filter_by(status=status).all()

        def get_pending(self) -> List[JxySiyuTask]:
            return self.get_by_status(TaskStatus.PENDING)

        def update_status(self, task_id: int, status: TaskStatus, fail_reason: str = "") -> bool:
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
            with self._get_session() as session:
                task = session.query(JxySiyuTask).filter_by(id=task_id).first()
                if not task:
                    return False
                task.task_metadata = json.dumps(metadata, ensure_ascii=False)
                session.commit()
                return True

        def get_by_bot_id(self, bot_id: str) -> List[JxySiyuTask]:
            with self._get_session() as session:
                return session.query(JxySiyuTask).filter_by(bot_id=bot_id).all()

        def get_by_type(self, task_type: str) -> List[JxySiyuTask]:
            with self._get_session() as session:
                return session.query(JxySiyuTask).filter_by(task_type=task_type).all()

        def delete_by_id(self, task_id: int) -> bool:
            with self._get_session() as session:
                task = session.query(JxySiyuTask).filter_by(id=task_id).first()
                if not task:
                    return False
                session.delete(task)
                session.commit()
                return True



    # ==============================
    # 配置常量
    # ==============================

    appdata_path = os.getenv("APPDATA")
    if appdata_path is None:
        DROPLET_CLIENT_PATH = os.path.join(os.getenv("USERPROFILE"), "AppData", "Roaming", "droplet-client")
    else:
        DROPLET_CLIENT_PATH = os.path.join(appdata_path, "droplet-client")

    WECHAT_DATA_DIR = r"C:\Users\张明明\xwechat_files\wxid_g7leryvu7kqm22_a246"
    IDLE_FILE_SCAN_SECONDS = 600
    ENABLE_IDLE_FILE_SCAN = True
    WECHAT_FILE_ROOT = rf"{WECHAT_DATA_DIR}\msg\file"
    TEMP_DIR = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "jxysy")
    EXCEL_EXTS = {".xls", ".xlsx", ".csv"}
    STABLE_CHECK_INTERVAL = 1
    STABLE_CHECK_COUNT = 3
    EXCEL_FILE_MAX_SIZE = 2 * 1024 ** 2  # 2M
    API_HOST = "127.0.0.1"
    API_PORT = 8000
    HEARTBEAT_INTERVAL = 10
    OFFLINE_MSG_CHECK_INTERVAL = 300  # 离线消息检查间隔（秒）
    ENABLE_OFFLINE_MSG = False if send_offline_msg is None else bool(send_offline_msg.get("value", False) if isinstance(send_offline_msg, dict) else send_offline_msg)

    # ==============================
    # 运行时状态
    # ==============================
    wx_lock = threading.Lock()
    last_task_time: float = 0
    last_file_scan_time: float = 0
    last_offline_msg_check_time: float = 0
    bot_nickname = None

    # ==============================
    # 工具函数
    # ==============================

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
        """等待文件写入完成（文件大小连续稳定）。"""
        stable_count = 0
        last_size = -1
        for _ in range(120):
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

    def _mark_task_done():
        """标记任务完成时间，用于空闲计时"""
        nonlocal last_task_time
        last_task_time = time.time()

    # ==============================
    # 离线消息处理
    # ==============================

    def _get_offline_grpc_paths() -> List[str]:
        """获取离线消息文件路径列表"""
        grpc_file_path = os.path.join(DROPLET_CLIENT_PATH, "GrpcMsg", "siyu.msg")
        return [grpc_file_path]

    def _read_grpc(grpc_path: str) -> List[dict]:
        """读取离线消息文件，返回命令列表"""
        with open(grpc_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        msg_list = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                decoded = base64.b64decode(line)
                url_decoded = urllib.parse.unquote(decoded.decode())
                data = json.loads(url_decoded)
                msg_list.append(data)
            except Exception as e:
                print(f"  ⚠️ 解析离线消息行失败: {e}")
        return msg_list

    def _send_grpc_message(file_path: str):
        """读取离线消息文件并逐条发送到本地 API"""
        try:
            grpc_data = _read_grpc(file_path)
            for data in grpc_data:
                api_path = data.get("api_path", "")
                # 跳过不需要处理的命令
                if api_path in [
                    "/contacts/refresh_and_upload_full_contacts_and_rooms",
                    "/room/refresh_room_contacts_by_room_id",
                    "/contact/get_contacts",
                    "/room/get_rooms",
                ]:
                    continue
                print(f"  📨 重放离线消息: {api_path}")
                requests.post(
                    f"http://{API_HOST}:{API_PORT}/droplet/call",
                    json={"type": "siyu_cmd", "data": data},
                    timeout=10,
                )
            os.remove(file_path)
            print(f"  ✅ 离线消息文件已处理并删除: {file_path}")
        except Exception as e:
            print(f"  ❌ 处理离线消息失败: {file_path} - {e}")
            traceback.print_exc()

    def _process_offline_grpc_msg():
        """检查并处理所有离线消息文件"""
        for path in _get_offline_grpc_paths():
            if os.path.exists(path):
                print(f"  📬 发现离线消息文件: {path}")
                _send_grpc_message(path)

    def _delete_offline_grpc_msg():
        """删除所有离线消息文件（不处理）"""
        for path in _get_offline_grpc_paths():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"  🗑️ 已删除离线消息文件: {path}")
                except Exception as e:
                    print(f"  ⚠️ 删除离线消息文件失败: {path} - {e}")

    # ==============================
    # ExcelFileHandler
    # ==============================

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

            with wx_lock:
                try:
                    self._download_today_files()
                finally:
                    _mark_task_done()

        def _download_today_files(self):
            """打开聊天文件窗口，获取今天的表格文件，逐个另存为并删除"""
            try:
                print(f"  📂 打开聊天文件窗口...")
                self._wx.file_manager.open(filter_type="表格")
                time.sleep(1)

                today_files = self._wx.file_manager.get_today_files()
                if not today_files:
                    print(f"  📭 今天没有表格文件")
                    self._wx.file_manager.close()
                    return

                print(f"  📋 今天共 {len(today_files)} 个表格文件，开始处理...")

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
                    if parse_file_size(f.file_size) > EXCEL_FILE_MAX_SIZE:
                        try:
                            self._wx.file_manager.delete_file(f)
                            print(f"  🗑️ [{i}/{len(today_files)}] 文件超过2M直接删除: {f.file_name} ({f.file_size})")
                        except Exception as e:
                            print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                        continue

                    # 消息预校验
                    if self._siyu:
                        try:
                            precheck = self._siyu.message_precheck(
                                room_nickname=f.source_name,
                                sender_nickname=f.sender_name,
                            )
                            if not precheck.get("should_process", True):
                                reason = precheck.get("reason", "服务端拒绝")
                                try:
                                    self._wx.file_manager.delete_file(f)
                                    print(f"  🚫 [{i}/{len(today_files)}] 预校验跳过并删除: {f.file_name} ({reason})")
                                except Exception as e:
                                    print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                                continue
                        except Exception as e:
                            print(f"  ⚠️ 预校验异常（继续处理）: {f.file_name} - {e}")

                    # 文件名校验
                    if self._siyu:
                        try:
                            file_size_bytes = int(parse_file_size(f.file_size))
                            validate = self._siyu.file_validate(
                                room_nickname=f.source_name,
                                file_name=f.file_name,
                                file_size=file_size_bytes,
                            )
                            if not validate.get("valid", True):
                                reason = validate.get("reason", "文件名无效")
                                try:
                                    self._wx.file_manager.delete_file(f)
                                    print(f"  🚫 [{i}/{len(today_files)}] 文件校验不通过并删除: {f.file_name} ({reason})")
                                except Exception as e:
                                    print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                                continue
                        except Exception as e:
                            print(f"  ⚠️ 文件校验异常（继续处理）: {f.file_name} - {e}")

                    # 未下载的文件先触发下载
                    if f.file_status == "未下载":
                        print(f"  📥 [{i}/{len(today_files)}] 下载中: {f.file_name}")
                        try:
                            f.download()
                            time.sleep(3)
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

                    # 通过右键复制获取文件的本地路径
                    print(f"  📋 [{i}/{len(today_files)}] 获取文件路径: {f.file_name}")
                    try:
                        file_path = f.copy()
                        time.sleep(0.5)
                        if not file_path or not os.path.exists(file_path):
                            print(f"  ❌ 获取文件路径失败: {f.file_name} (path={file_path})")
                            continue
                        print(f"  ✅ 文件路径: {file_path}")
                    except Exception as e:
                        print(f"  ❌ 复制获取路径异常: {f.file_name} - {e}")
                        continue

                    # 上传文件到服务端
                    upload_success = False
                    if self._siyu:
                        print(f"  📤 [{i}/{len(today_files)}] 上传服务端: {f.file_name}")
                        try:
                            result = self._siyu.file_upload_raw(
                                file_path=file_path,
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

                    # 上传成功后，定位到聊天位置并引用回复确认消息，然后删除文件
                    if upload_success:
                        try:
                            f.switch_to_message()
                            self._wx.chat.send_at(f"【Excel下单】\n您的文件已收到：{f.file_name}，订单正在处理中，请耐心等待。", at_members=[f.sender_name])
                            print(f"  ✅ 已回复（未匹配到消息引用）: {f.file_name}")
                        except Exception as e:
                            print(f"  ⚠️ 回复异常（不影响删除）: {f.file_name} - {e}")

                        try:
                            time.sleep(0.5)
                            self._wx.file_manager.delete_file(f)
                            print(f"  🗑️ 已删除: {f.file_name}")
                        except Exception as e:
                            print(f"  ⚠️ 删除异常: {f.file_name} - {e}")
                    else:
                        print(f"  ⚠️ 上传未成功，保留文件不删除: {f.file_name}")

                self._wx.file_manager.close()
                print(f"  ✅ 全部处理完成")

            except Exception as e:
                print(f"  ❌ 处理异常: {e}")
                traceback.print_exc()
                try:
                    self._wx.file_manager.close()
                except Exception:
                    pass


    # ==============================
    # 任务处理函数
    # ==============================

    def _handle_send_text(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理发送文本消息任务"""
        chat = wx.open_session_by_search(task.to)
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
        if task.content:
            chat.send_text(task.content)
            time.sleep(0.5)
        for file_path in file_list:
            if not os.path.exists(file_path):
                raise RuntimeError(f"文件不存在: {file_path}")
            status = chat.send_file(file_path)
            if status == MessageStatus.FAILED:
                raise RuntimeError(f"文件发送失败: {file_path}")
            time.sleep(0.5)

    def _handle_send_image(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理发送图片任务"""
        if not task.files:
            raise RuntimeError("files 字段为空，没有要发送的图片")
        file_list = json.loads(task.files)
        chat = wx.open_session_by_search(task.to)
        if task.content:
            chat.send_text(task.content)
            time.sleep(0.5)
        for file_path in file_list:
            if not os.path.exists(file_path):
                raise RuntimeError(f"图片不存在: {file_path}")
            status = chat.send_file(file_path)
            if status == MessageStatus.FAILED:
                raise RuntimeError(f"图片发送失败: {file_path}")
            time.sleep(0.5)

    def _handle_send_room_at(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理 /msg/send_room_at — 发送群文本消息（带 @）"""
        chat = wx.open_session_by_search(task.to)
        if task.at_members:
            members = json.loads(task.at_members)
            status = chat.send_at(task.content or "", members)
        else:
            status = chat.send_text(task.content or "")
        if status == MessageStatus.FAILED:
            raise RuntimeError("群消息发送失败")

    def _generate_excel_file(excel_name: str, datas: list) -> str:
        """根据 excel_msg 数据生成 Excel 文件到临时目录，返回文件路径。"""
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in datas:
            ws.append(row)

        temp_dir = os.path.join(TEMP_DIR, "_temp_excel")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.join(temp_dir, excel_name)
        if os.path.exists(file_path):
            name, ext = os.path.splitext(excel_name)
            timestamp = datetime.now().strftime("%H%M%S")
            file_path = os.path.join(temp_dir, f"{name}_{timestamp}{ext}")

        wb.save(file_path)
        return file_path

    def _handle_send_excel(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理 Excel 生成 + 发送"""
        metadata = json.loads(task.task_metadata) if task.task_metadata else {}
        excel_msg = metadata.get("excel_msg")
        if not excel_msg:
            raise RuntimeError("缺少 excel_msg 数据")

        excel_name = excel_msg.get("excel_name", "output.xlsx")
        datas = excel_msg.get("datas", [])
        if not datas:
            raise RuntimeError("excel_msg.datas 为空")

        file_path = _generate_excel_file(excel_name, datas)

        try:
            chat = wx.open_session_by_search(task.to)
            if task.content:
                if task.at_members:
                    members = json.loads(task.at_members)
                    chat.send_at(task.content, members)
                else:
                    chat.send_text(task.content)
                time.sleep(0.5)
            status = chat.send_file(file_path)
            if status == MessageStatus.FAILED:
                raise RuntimeError(f"Excel 文件发送失败: {excel_name}")
        finally:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    def _handle_send_binary_file(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理 /msg/send_file — 发送文件（支持 b64 / url / file_path）"""

        metadata = json.loads(task.task_metadata) if task.task_metadata else {}
        b64_data = metadata.get("b64", "")
        url = metadata.get("url", "")
        file_path = metadata.get("file_path", "")
        file_name = metadata.get("file_name", "file")

        chat = wx.open_session_by_search(task.to)

        if file_path and os.path.exists(file_path):
            status = chat.send_file(file_path)
        elif url:
            status = chat.send_file(url)
        elif b64_data:
            # base64 需要先解码保存为临时文件
            temp_dir = os.path.join(TEMP_DIR, "_temp_files")
            os.makedirs(temp_dir, exist_ok=True)
            local_path = os.path.join(temp_dir, file_name)
            with open(local_path, "wb") as fp:
                fp.write(base64.b64decode(b64_data))
            try:
                status = chat.send_file(local_path)
            finally:
                try:
                    os.remove(local_path)
                except Exception:
                    pass
        else:
            raise RuntimeError("send_file: 缺少 b64/url/file_path，无法获取文件")

        if status == MessageStatus.FAILED:
            raise RuntimeError(f"文件发送失败: {file_name}")

    def _handle_send_message_with_type(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理 /msg/send_message_with_type — 发送多类型消息"""

        metadata = json.loads(task.task_metadata) if task.task_metadata else {}
        msg_type = metadata.get("type", "text")
        url = metadata.get("url", "")
        file_name = metadata.get("file_name", "file")

        chat = wx.open_session_by_search(task.to)

        if msg_type == "text":
            if task.at_members:
                members = json.loads(task.at_members)
                status = chat.send_at(task.content or "", members)
            else:
                status = chat.send_text(task.content or "")
            if status == MessageStatus.FAILED:
                raise RuntimeError("文本消息发送失败")

        elif msg_type in ("image", "file", "video"):
            if task.content:
                if task.at_members:
                    members = json.loads(task.at_members)
                    chat.send_at(task.content, members)
                else:
                    chat.send_text(task.content)
                time.sleep(0.5)

            if not url:
                raise RuntimeError(f"send_message_with_type({msg_type}): 缺少 url")

            status = chat.send_file(url)
            if status == MessageStatus.FAILED:
                raise RuntimeError(f"{msg_type} 发送失败: {file_name}")
        else:
            raise RuntimeError(f"不支持的消息类型: {msg_type}")

    def _handle_refresh_rooms(wx: Weixin, task: JxySiyuTask, task_mgr: SiYuTask):
        """处理 /contact/update_rooms_contacts — 刷新群列表"""
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


    # ==============================
    # FastAPI 回调服务
    # ==============================

    api = FastAPI(title="聚协云私域社群智能机器人RPA版本", version="0.0.1")

    class SendTextRequest(BaseModel):
        """发送文本消息的回调请求体"""
        to: str = Field(..., description="目标会话（联系人昵称或群名）")
        content: str = Field(..., description="消息内容")
        at_members: Optional[List[str]] = Field(default=None, description="需要@的成员列表")
        msg_id: Optional[str] = Field(default=None, description="外部消息ID，用于去重/追踪")
        bot_id: Optional[str] = Field(default=None, description="机器人ID")

    class SiyuCmdRequest(BaseModel):
        """WxService gRPC 推送的统一命令格式"""
        type: str = Field(default="siyu_cmd")
        data: dict = Field(..., description="命令数据")

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

    # 用列表包装 task_mgr 引用，供闭包内使用
    _api_task_mgr_ref = [None]

    @api.post("/siyu/wxrpa/msg/send_text")
    def send_text_callback(req: SendTextRequest):
        """接收发送文本消息的推送通知，保存到任务表"""
        task = _api_task_mgr_ref[0].create(
            task_type="send_text",
            task_name=f"发送文本到 {req.to}",
            to=req.to,
            content=req.content,
            at_members=req.at_members,
            msg_id=req.msg_id,
            bot_id=req.bot_id or "",
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

    @api.post("/droplet/call")
    def siyu_cmd_callback(req: SiyuCmdRequest):
        """接收 WxService 服务端推送的统一命令，解析后生成对应任务。"""
        cmd_data = req.data
        api_path = cmd_data.get("api_path", "")
        param = cmd_data.get("param") or {}
        request_id = cmd_data.get("request_id", "")
        robot_id = cmd_data.get("robot_id", "")

        if api_path in _IGNORED_API_PATHS:
            msg = f"命令已忽略（桌面自动化模式不适用）: {api_path}"
            print(msg)
            return {
                "code": 0,
                "msg": msg,
                "data": {"ignored": True},
            }

        task_type = _API_PATH_TO_TASK_TYPE.get(api_path)
        if not task_type:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 api_path: {api_path}",
            )

        to_nickname = param.get("to_nickname", "")
        content = param.get("content", "")
        at_nickname_list = param.get("at_nickname_list") or {}
        at_members = list(at_nickname_list.values()) if at_nickname_list else None

        metadata = {}

        if task_type == "send_room_at":
            metadata["at_nickname_list"] = at_nickname_list
        elif task_type == "send_excel":
            metadata["excel_msg"] = param.get("excel_msg") or {}
            metadata["at_nickname_list"] = at_nickname_list
            metadata["order_info"] = param.get("order_info") or {}
            metadata["enable_reply_new_shipment"] = param.get("enable_reply_new_shipment", False)
            metadata["new_shipment_order_indexs"] = param.get("new_shipment_order_indexs") or []
        elif task_type == "send_binary_file":
            metadata["b64"] = param.get("b64", "")
            metadata["url"] = param.get("url", "")
            metadata["file_path"] = param.get("file_path", "")
            metadata["file_name"] = param.get("file_name", "file")
        elif task_type == "send_message_with_type":
            metadata["type"] = param.get("type", "text")
            metadata["url"] = param.get("url", "")
            metadata["file_name"] = param.get("file_name", "file")
            metadata["file_size"] = param.get("file_size", 0)
            metadata["at_nickname_list"] = at_nickname_list
            metadata["msg_id"] = param.get("msg_id", "")
        elif task_type == "refresh_rooms":
            pass

        task_name_map = {
            "send_room_at": f"群消息(@) → {to_nickname}",
            "send_excel": f"发送Excel → {to_nickname}",
            "send_binary_file": f"发送文件 → {to_nickname}",
            "send_message_with_type": f"发送{param.get('type', '?')}消息 → {to_nickname}",
            "refresh_rooms": "刷新群列表",
        }
        task_name = task_name_map.get(task_type, f"{api_path} → {to_nickname}")

        task = _api_task_mgr_ref[0].create(
            task_type=task_type,
            task_name=task_name,
            to=to_nickname,
            content=content,
            at_members=at_members,
            msg_id=request_id,
            metadata=metadata,
            bot_id=robot_id,
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
        task = _api_task_mgr_ref[0].get_by_id(task_id)
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

    def _start_api_server():
        """在后台线程中启动 FastAPI 服务"""
        uvicorn.run(api, host=API_HOST, port=API_PORT, log_level="info")


    # ==============================
    # 空闲扫描 & 任务执行
    # ==============================

    def _try_idle_file_scan(wx: Weixin, siyu: Optional[Siyu] = None):
        """空闲超过 IDLE_FILE_SCAN_SECONDS 且距上次扫描也超过该时间，自动扫描聊天文件"""
        nonlocal last_file_scan_time
        if not ENABLE_IDLE_FILE_SCAN:
            return

        now = time.time()
        if last_task_time > 0 and now - last_task_time < IDLE_FILE_SCAN_SECONDS:
            return
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
        """取出待处理任务，按类型分发执行。"""
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

    # ==============================
    # 主流程开始
    # ==============================

    os.makedirs(TEMP_DIR, exist_ok=True)

    print("=" * 55)
    print("  聚协云私域社群智能机器人RPA版本")
    print("=" * 55)

    # 初始化微信
    wx = Weixin()
    print("✅ 微信已连接")
    self_info = wx.get_self_info()
    bot_nickname_local = self_info.get("nickname", "")
    print(f"当前账号: {bot_nickname_local} (微信号: {self_info.get('account', '')})")

    # 更新 bot_nickname
    bot_nickname = bot_nickname_local

    # 连接私域服务端
    siyu = Siyu(
        base_url="https://sy.jushuitan.com/WebApi/v1",
        token=droplet_token
    )
    siyu.connect(
        nickname=bot_nickname_local,
        device_id=device_id,
        account=self_info.get("account", ""),
        avatar=f"data:image/png;base64,{self_info.get('avatar', '')}" if self_info.get("avatar") else "",
    )
    print(f"✅ 私域服务端已连接: robot_id={siyu.robot_id}")

    # 启动心跳线程
    siyu.start_heartbeat(interval=HEARTBEAT_INTERVAL)
    print("💓 心跳线程已启动")

    # 在文件传输助手发送启动通知
    startup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    wx.send_text("文件传输助手", f"[{startup_time}] 机器人启动成功！")
    print("📨 已发送启动通知到文件传输助手")

    # 初始化任务管理器
    _db_dir = os.path.join(DROPLET_CLIENT_PATH, "GrpcMsg")
    os.makedirs(_db_dir, exist_ok=True)
    task_mgr = SiYuTask(db_path=os.path.join(_db_dir, "syrpa.db"))
    print("✅ 任务数据库已就绪")

    # 启动 FastAPI 回调服务（后台线程）
    _api_task_mgr_ref[0] = task_mgr
    api_thread = threading.Thread(
        target=_start_api_server, daemon=True,
    )
    api_thread.start()
    print(f"🌐 API 回调服务: http://{API_HOST}:{API_PORT}")

    # 处理离线消息
    time.sleep(1)  # 等待 API 服务就绪
    if ENABLE_OFFLINE_MSG:
        print("📬 处理离线消息...")
        _process_offline_grpc_msg()
    else:
        _delete_offline_grpc_msg()

    # 启动文件监听线程
    watch_dir = get_current_month_dir()
    os.makedirs(watch_dir, exist_ok=True)
    file_handler = ExcelFileHandler(wx, siyu=siyu)
    observer = Observer()
    observer.schedule(file_handler, path=watch_dir, recursive=True)
    observer.start()
    print(f"🔄 文件监听: {watch_dir}")

    print(f"📋 任务轮询已启动")
    print(f"按 Ctrl+C 停止")
    print("=" * 55 + "\n")

    try:
        while True:
            try:
                do_task(wx, task_mgr)
            except Exception as e:
                print(f"⚠️ 任务轮询异常: {e}")
                traceback.print_exc()

            new_dir = get_current_month_dir()
            if new_dir != watch_dir:
                print(f"\n📅 月份切换，更新监听目录: {new_dir}")
                observer.unschedule_all()
                watch_dir = new_dir
                os.makedirs(watch_dir, exist_ok=True)
                observer.schedule(file_handler, path=watch_dir, recursive=True)

            _try_idle_file_scan(wx, siyu=siyu)

            # 定期检查离线消息
            if ENABLE_OFFLINE_MSG:
                now = time.time()
                if now - last_offline_msg_check_time >= OFFLINE_MSG_CHECK_INTERVAL:
                    last_offline_msg_check_time = now
                    _process_offline_grpc_msg()

            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
        print("\n\n🛑 已停止")
    observer.join()
    # CODE END
