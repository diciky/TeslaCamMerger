import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from merge_tesla_cam import TeslaCamMerger

app = FastAPI()
VERSION = "v0.1.3"

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任务状态
class TaskStatus:
    def __init__(self):
        self.is_running = False
        self.progress = 0
        self.logs = []
        self.merger = None
        self.queues = []
        self.loop = None
        self.history_mgr = None

status = TaskStatus()

# --- History Manager ---
import json
import uuid
from typing import Dict, Any, List
from datetime import datetime

class HistoryManager:
    def __init__(self):
        self.data_dir = os.path.expanduser("~/.teslacam_merger")
        self.history_file = os.path.join(self.data_dir, "history.json")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.history = self.load_history()

    def load_history(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save history: {e}")

    def add_record(self, source_path, output_path, target_date=None, file_size=0):
        record = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_path": source_path,
            "output_path": output_path,
            "target_date": target_date or "All Dates",
            "file_size": file_size,
            "status": "success"
        }
        self.history.insert(0, record) # Add to top
        self.history = self.history[:100] # Limit to 100 records
        self.save_history()

    def clear_history(self):
        self.history = []
        self.save_history()

@app.get("/api/version")
async def get_version():
    return {"version": VERSION}

@app.on_event("startup")
async def startup_event():
    status.loop = asyncio.get_running_loop()
    status.history_mgr = HistoryManager()

def progress_callback(message):
    print(f"[CALLBACK] {message}", flush=True) # 增加终端打印，方便调试
    if status.loop:
        for q in status.queues:
            status.loop.call_soon_threadsafe(q.put_nowait, message)
            
    if message.startswith("PROGRESS:"):
        try:
            status.progress = float(message.split(":")[1].replace("%", ""))
        except:
            pass
    status.logs.append(message)
    if len(status.logs) > 500:
        status.logs.pop(0)

from pydantic import BaseModel
from typing import Optional, List
import threading

class StartRequest(BaseModel):
    source_path: str
    output_path: str
    sample_limit: Optional[int] = None
    target_date: Optional[str] = None
    target_timestamps: Optional[List[str]] = None

@app.post("/api/start")
async def start_task(req: StartRequest, background_tasks: BackgroundTasks):
    if status.is_running:
        return {"status": "error", "message": "任务已在运行中"}
    
    status.is_running = True
    status.progress = 0
    status.logs = ["开始扫描文件..."]
    
    def run_merger(source, output, limit, target_date, target_timestamps):
        try:
            # 发送初始进度，确保 SSE 建立后立刻有反馈
            progress_callback("PROGRESS:1%:正在初始化合并引擎...")
            status.merger = TeslaCamMerger(source, output, progress_callback)
            if target_timestamps:
                status.merger.target_timestamps = target_timestamps
                
            final_output_file = status.merger.merge_all(sample_count=limit, target_date=target_date)
            
            # Record Success to History
            if final_output_file and os.path.exists(final_output_file):
                f_size = os.path.getsize(final_output_file)
                size_str = f"{f_size / (1024*1024):.1f} MB"
                if status.history_mgr:
                    status.history_mgr.add_record(source, final_output_file, target_date, size_str)
            
            progress_callback(f"COMPLETED:Successfully processed clips. Saved to {output}")
        except Exception as e:
            progress_callback(f"Error: {str(e)}")
        finally:
            status.is_running = False

    thread = threading.Thread(target=run_merger, args=(req.source_path, req.output_path, req.sample_limit, req.target_date, req.target_timestamps))
    thread.start()
    
    return {"status": "success", "message": "任务已启动"}

@app.post("/api/stop")
async def stop_task():
    if status.merger:
        status.merger.stop()
        return {"status": "success", "message": "停止指令已发送"}
    return {"status": "error", "message": "没有正在运行的任务"}

@app.get("/api/status")
async def get_status():
    return {
        "is_running": status.is_running,
        "progress": status.progress,
        "logs": status.logs[-20:]
    }

# --- History APIs ---
@app.get("/api/history")
async def get_history():
    if status.history_mgr:
        return {"status": "success", "history": status.history_mgr.history}
    return {"status": "error", "history": []}

@app.delete("/api/history")
async def clear_history():
    if status.history_mgr:
        status.history_mgr.clear_history()
        return {"status": "success", "message": "History cleared"}
    return {"status": "error"}

@app.get("/api/videos")
async def get_videos(date: str, path: str):
    if not os.path.exists(path):
        return {"status": "error", "message": "路径不存在"}
    
    from merge_tesla_cam import TeslaCamMerger
    # 临时实例化以复用分组逻辑, 但这里我们只关心特定日期
    merger = TeslaCamMerger(path, "", None)
    grouped, _ = merger.group_videos()
    
    if date not in grouped:
        return {"status": "success", "date": date, "videos": []}

    videos = []
    # grouped[date] 是 timestamp -> {camera: file_path}
    for ts, cameras in grouped[date].items():
        # 取任意一个存在的摄像头文件作为预览源
        preview_file = next(iter(cameras.values()), "")
        videos.append({
            "timestamp": ts,
            "cameras": list(cameras.keys()),
            "preview_path": preview_file
        })
    
    # 按时间戳排序
    videos.sort(key=lambda x: x["timestamp"])
    return {"status": "success", "date": date, "videos": videos}

from fastapi.responses import FileResponse, StreamingResponse

@app.get("/api/stream")
async def stream_video(path: str, range: str =  None):
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"message": "File not found"})
    
    file_size = os.path.getsize(path)
    
    # 简单的 Range 支持
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4"
    }

    # 大多数浏览器（Safari/Chrome）需要 Range 支持才能 seek
    # 这里为了简便，如果检测到 range header，我们用 FileResponse (Starlette/FastAPI 自动处理)
    # 或者手动处理。其实 FileResponse 已经支持 Range 了。
    return FileResponse(path, media_type="video/mp4", filename=os.path.basename(path))

@app.post("/api/open_folder")
async def open_folder(path: str):
    import platform
    import subprocess
    if not os.path.exists(path):
        return {"status": "error", "message": "路径不存在"}
    
    # 如果路径是文件，打开其所在的文件夹
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    
    try:
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.run(["open", folder])
        else:
            subprocess.run(["xdg-open", folder])
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/api/delete_date")
async def delete_date(path: str, date: str):
    import shutil
    if not os.path.exists(path):
        return {"status": "error", "message": "源路径不存在"}
    
    # 查找属于该日期的所有子文件夹（通常在 TeslaCam/SavedClips, SentryClips 等）
    # 但由于合并逻辑是按文件夹扫描的，我们这里简单处理：
    # 如果该日期下有对应的文件夹，则删除。
    deleted_count = 0
    try:
        for root, dirs, files in os.walk(path):
            for d in dirs:
                if d.startswith(date):
                    full_p = os.path.join(root, d)
                    shutil.rmtree(full_p)
                    deleted_count += 1
        return {"status": "success", "message": f"解析并删除了 {deleted_count} 个日期文件夹"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/dates")
async def get_dates(path: str):
    if not os.path.exists(path):
        return {"dates": [], "merged_dates": []}
    
    from merge_tesla_cam import TeslaCamMerger
    merger = TeslaCamMerger(path, "", None)
    grouped, _ = merger.group_videos()
    
    # 获取历史记录中已经合并成功的日期
    merged_dates = []
    if status.history_mgr:
        merged_dates = [record["target_date"] for record in status.history_mgr.history if record["status"] == "success"]
    
    return {
        "dates": sorted(grouped.keys(), reverse=True),
        "merged_dates": list(set(merged_dates)) # 去重
    }

@app.get("/api/sys_stats")
async def get_sys_stats():
    import psutil
    try:
        cpu = psutil.cpu_percent(interval=None) # Non-blocking
        ram = psutil.virtual_memory()
        return {
            "status": "success",
            "cpu": cpu,
            "ram": {
                "percent": ram.percent,
                "free_gb": round(ram.available / (1024**3), 1),
                "total_gb": round(ram.total / (1024**3), 1)
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/disks")
async def get_disk_usage():
    import shutil
    import platform

    disks = []
    
    # 始终包含根目录
    paths_to_check = ["/"]
    
    # macOS/Linux 检查 /Volumes
    if platform.system() != "Windows":
        volumes_dir = "/Volumes"
        if os.path.exists(volumes_dir):
            try:
                for d in os.listdir(volumes_dir):
                    p = os.path.join(volumes_dir, d)
                    # 只有实际挂载的目录才加入，排除隐藏文件和系统链接
                    if os.path.isdir(p) and not d.startswith("."):
                        # 确保是一个挂载点或者普通的目录（U盘通常直接在 /Volumes 下）
                        paths_to_check.append(p)
            except: pass
    else:
        # Windows 简单处理常见盘符
        for letter in "CDEFG":
            p = f"{letter}:\\"
            if os.path.exists(p):
                paths_to_check.append(p)

    for p in paths_to_check:
        try:
            usage = shutil.disk_usage(p)
            disks.append({
                "path": p,
                "name": os.path.basename(p) or p,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": round((usage.used / usage.total) * 100, 1)
            })
        except: pass
        
    return {"status": "success", "disks": disks}

@app.get("/api/ls")
async def list_dirs(path: str = Query("/", description="要遍历的路径")):
    try:
        if not os.path.exists(path):
            return {"status": "error", "message": "路径不存在"}
        if not os.path.isdir(path):
            return {"status": "error", "message": "不是有效的目录"}

        entries = []
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and not entry.name.startswith("."):
                    entries.append({"name": entry.name, "path": entry.path})
        except PermissionError:
            return {"status": "error", "message": "无权访问此目录"}

        entries.sort(key=lambda x: x["name"].lower())
        parent = os.path.dirname(path)
        return {
            "status": "success",
            "current": path,
            "parent": parent if parent != path else None,
            "items": entries
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/preview")
async def get_preview(path: str = Query(..., description="要预览的路径")):
    try:
        if not os.path.exists(path):
            return {"status": "error", "message": "路径不存在"}
        
        files = []
        # 简单预览：只看当前层级或深入一级
        target_dirs = [path, os.path.join(path, "SavedClips"), os.path.join(path, "RecentClips")]
        
        for d in target_dirs:
            if os.path.exists(d) and os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".mp4") and not f.startswith("._") and not f.startswith("temp_"):
                        files.append({
                            "name": f,
                            "path": os.path.join(d, f),
                            "size": f"{os.path.getsize(os.path.join(d, f)) / (1024*1024):.1f} MB"
                        })
        
        # 按名称排序并限制数量
        files.sort(key=lambda x: x["name"], reverse=True)
        return {"status": "success", "files": files[:20]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/events")
async def sse_events(request: Request):
    async def event_generator():
        queue = asyncio.Queue()
        status.queues.append(queue)
        
        # 先把最近的 50 条日志补发给新连接，防止还没连上 SSE 之前的日志丢掉
        # 过滤掉之前的 PROGRESS 消息，以免进度条跳动，只补发普通文本日志
        for old_log in status.logs[-50:]:
            if not old_log.startswith("PROGRESS:"):
                yield {"data": old_log}
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield {"data": msg}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
        finally:
            if queue in status.queues:
                status.queues.remove(queue)

    return EventSourceResponse(event_generator())

import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# 挂载当前目录下的静态文件
# 这样系统会自动处理 index.css 等文件
app.mount("/static", StaticFiles(directory=resource_path(".")), name="static")

@app.get("/")
async def read_index():
    from fastapi.responses import FileResponse
    return FileResponse(resource_path("index.html"))

# 为了方便，如果直接请求 index.css 也返回它
@app.get("/index.css")
async def read_css():
    from fastapi.responses import FileResponse
    return FileResponse(resource_path("index.css"))

@app.get("/wechat_qr.jpg")
async def read_qr():
    from fastapi.responses import FileResponse
    qr_path = resource_path("wechat_qr.jpg")
    if os.path.exists(qr_path):
        return FileResponse(qr_path)
    return JSONResponse({"status": "error", "message": "QR code not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    import webview
    import threading
    import time

    def run_fastapi():
        uvicorn.run(app, host="127.0.0.1", port=8877, log_level="info")

    # 在后台线程启动 FastAPI
    server_thread = threading.Thread(target=run_fastapi, daemon=True)
    server_thread.start()

    # 等待一秒确保服务器启动
    time.sleep(1)

    # 创建并启动本地窗口
    # width/height 设为典型桌面尺寸
    webview.create_window(
        'TeslaCam Merger', 
        'http://127.0.0.1:8877', 
        width=1400, 
        height=900,
        background_color='#0a0a0a'
    )
    webview.start()
