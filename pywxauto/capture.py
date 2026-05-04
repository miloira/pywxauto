

import io
import ctypes

import win32ui
import win32gui
import win32con
from windows_capture import WindowsCapture, Frame, InternalCaptureControl # pip install windows-capture
from PIL import Image # pip install pillow

try:
    # https://docs.microsoft.com/en-us/windows/win32/api/shellscalingapi/nf-shellscalingapi-setprocessdpiawareness
    # Once SetProcessDpiAwareness is set for an app, any future calls to SetProcessDpiAwareness will fail.
    # Windows 8.1+
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # 支持每个显示器不同 DPI
except Exception as ex:
    pass


def capture_by_bitblt(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """BitBlt方式截取窗口图像（窗口必须可见）"""
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    win_width = right - left
    win_height = bottom - top

    crop_width = win_width - offset_left - offset_right
    crop_height = win_height - offset_top - offset_bottom
    if crop_width <= 0 or crop_height <= 0:
        raise ValueError(f"裁剪后区域无效: {crop_width}x{crop_height}")

    hwndDC = win32gui.GetWindowDC(hwnd)
    try:
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitmap = win32ui.CreateBitmap()
        saveBitmap.CreateCompatibleBitmap(mfcDC, crop_width, crop_height)
        saveDC.SelectObject(saveBitmap)

        saveDC.BitBlt((0, 0), (crop_width, crop_height), mfcDC,
                      (offset_left, offset_top), win32con.SRCCOPY)

        bmp_info = saveBitmap.GetInfo()
        bmp_str = saveBitmap.GetBitmapBits(True)

        img = Image.frombuffer("RGB",
                               (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                               bmp_str, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(saveBitmap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def capture_by_print_window(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """PrintWindow方式截取窗口图像（支持后台截图）"""
    if hwnd == win32gui.GetDesktopWindow():
        raise ValueError("PrintWindow 不支持截取整个桌面，请使用 bitblt 或 window_capture 模式")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    win_width = right - left
    win_height = bottom - top

    hwndDC = win32gui.GetWindowDC(hwnd)
    try:
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitmap = win32ui.CreateBitmap()
        saveBitmap.CreateCompatibleBitmap(mfcDC, win_width, win_height)
        saveDC.SelectObject(saveBitmap)

        ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

        bmp_info = saveBitmap.GetInfo()
        bmp_str = saveBitmap.GetBitmapBits(True)

        img = Image.frombuffer("RGB",
                               (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                               bmp_str, "raw", "BGRX", 0, 1)
    finally:
        win32gui.DeleteObject(saveBitmap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

    if offset_left or offset_top or offset_right or offset_bottom:
        crop_box = (offset_left, offset_top,
                    win_width - offset_right, win_height - offset_bottom)
        img = img.crop(crop_box)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def capture_by_window_capture(
    hwnd: int, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0
) -> bytes:
    """Windows.Graphics.Capture方式截取窗口图像（支持后台截图）"""
    result = {}

    # 判断是否为桌面窗口，桌面用 monitor_index 截全屏
    desktop_hwnd = win32gui.GetDesktopWindow()
    if hwnd == desktop_hwnd:
        wc = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            monitor_index=1
        )
    else:
        wc = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=hwnd
        )

    @wc.event
    def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
        arr = frame.frame_buffer
        h, w = arr.shape[:2]
        end_h = h - offset_bottom if offset_bottom else h
        end_w = w - offset_right if offset_right else w
        result["buffer"] = arr[offset_top:end_h, offset_left:end_w, :].copy()
        capture_control.stop()

    @wc.event
    def on_closed():
        pass

    wc.start()

    arr = result["buffer"]
    img = Image.fromarray(arr[:, :, 2::-1])  # BGRA -> RGB
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def capture_window(
    hwnd: int = None, 
    offset_left: int = 0, 
    offset_top: int = 0, 
    offset_right: int = 0, 
    offset_bottom: int = 0, 
    mode: str = "bitblt"
) -> bytes:
    """统一截图接口

    Args:
        hwnd: 窗口句柄，传None截取整个屏幕
        offset_left: 左边裁剪偏移（正数向内裁剪）
        offset_top: 上边裁剪偏移（正数向内裁剪）
        offset_right: 右边裁剪偏移（正数向内裁剪）
        offset_bottom: 下边裁剪偏移（正数向内裁剪）
        mode: 截图模式
            - "bitblt": BitBlt方式（窗口必须可见）
            - "print_window": PrintWindow方式（支持后台截图）
            - "window_capture": Windows.Graphics.Capture方式（支持后台截图）

    Returns:
        PNG 格式的图像字节数据
    """
    if hwnd is None:
        hwnd = win32gui.GetDesktopWindow()

    if mode == "bitblt":
        return capture_by_bitblt(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    elif mode == "print_window":
        return capture_by_print_window(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    elif mode == "window_capture":
        return capture_by_window_capture(hwnd, offset_left, offset_top, offset_right, offset_bottom)
    else:
        raise ValueError(f"不支持的截图模式: {mode}")


def capture_control(
    hwnd: int, 
    uia_control,
    offset_left: int = 0, 
    offset_top: int = 0,
    offset_right: int = 0, 
    offset_bottom: int = 0, 
    mode: str = "bitblt"
) -> bytes:
    """
    通过截取窗口图像，然后裁剪出指定控件区域。

    Args:
        hwnd:          窗口句柄
        uia_control:   uiautomation 控件对象，需要有 BoundingRectangle 属性
        offset_left:   左边裁剪像素（正值向内收缩）
        offset_top:    上边裁剪像素（正值向内收缩）
        offset_right:  右边裁剪像素（正值向内收缩）
        offset_bottom: 下边裁剪像素（正值向内收缩）
        mode:          截图模式（bitblt / print_window / window_capture）

    Returns:
        PNG 格式的 bytes 数据（裁剪后的控件区域图像）
    """
    # 获取窗口位置
    win_left, win_top, _, _ = win32gui.GetWindowRect(hwnd)

    # 获取控件的屏幕坐标
    rect = uia_control.BoundingRectangle
    ctrl_left = rect.left - win_left + offset_left
    ctrl_top = rect.top - win_top + offset_top
    ctrl_right = rect.right - win_left - offset_right
    ctrl_bottom = rect.bottom - win_top - offset_bottom

    # 先截取完整窗口
    data = capture_window(hwnd, mode=mode)

    # 裁剪控件区域
    img = Image.open(io.BytesIO(data))
    img = img.crop((ctrl_left, ctrl_top, ctrl_right, ctrl_bottom))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
