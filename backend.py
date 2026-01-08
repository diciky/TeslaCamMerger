import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from merge_tesla_cam import TeslaCamMerger

app = FastAPI()

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
from typing import Dict, Any
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

@app.on_event("startup")
async def startup_event():
    status.loop = asyncio.get_running_loop()
    status.history_mgr = HistoryManager()

def progress_callback(message):
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

@app.get("/api/dates")
async def get_dates(path: str):
    if not os.path.exists(path):
        return {"dates": []}
    
    # 获取真正的 TeslaCamMerger 实例进行扫描
    from merge_tesla_cam import TeslaCamMerger
    merger = TeslaCamMerger(path, "", None)
    grouped, _ = merger.group_videos()
    
    # 返回排序后的日期列表
    return {"dates": sorted(grouped.keys(), reverse=True)}

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
        try:
            while True:
                if await request.is_disconnected():
                    break
                # 从本连接的队列中获取日志并推送
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield {"data": msg}
                except asyncio.TimeoutError:
                    # 保持连接
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
