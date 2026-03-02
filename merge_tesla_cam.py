import os
import threading
import subprocess
import glob
import time
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

class TeslaCamMerger:
    def __init__(self, source_path, output_dir, progress_callback=None):
        self.source_path = source_path
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        self.stop_requested = False
        self.lock = threading.Lock()
        self.active_tasks = {} # timestamp -> status
        
        # 平台探测
        import platform
        self.is_windows = platform.system() == "Windows"
        self.default_hw_codec = "h264_videotoolbox" if not self.is_windows else "h264_nvenc"
        
    def log(self, message):
        if self.progress_callback:
            self.progress_callback(message)
        else:
            print(message, flush=True)

    def group_videos(self):
        """Finds and groups videos by date and timestamp within the source directory."""
        grouped = defaultdict(lambda: defaultdict(dict))
        
        found_files = 0
        # 递归遍历 source_path 及其所有子目录
        for root, _, filenames in os.walk(self.source_path):
            for filename in filenames:
                if filename.endswith(".mp4") and not filename.startswith("._"):
                    f = os.path.join(root, filename)
                    try:
                        # TeslaCam filename format: YYYY-MM-DD_HH-MM-SS-camera.mp4
                        parts = filename.replace(".mp4", "").split("-")
                        camera_name = parts[-1]
                        timestamp_str = "-".join(parts[:-1]) 
                        date_str = timestamp_str.split("_")[0] 
                        
                        grouped[date_str][timestamp_str][camera_name] = f
                        found_files += 1
                    except Exception as e:
                        # self.log(f"Skipping file {f} due to format: {e}")
                        pass
                        
        return grouped, found_files

    def get_ffmpeg_path(self, cmd="ffmpeg"):
        """Resolves path to ffmpeg/ffprobe binary, compatible with PyInstaller."""
        import sys
        if getattr(sys, 'frozen', False):
            # PyInstaller mode: binaries are in sys._MEIPASS
            base_path = sys._MEIPASS
            # Windows 下需要加 .exe 扩展名
            bin_name = f"{cmd}.exe" if self.is_windows else cmd
            return os.path.join(base_path, bin_name)
        else:
            # Normal mode: assume on PATH
            return f"{cmd}.exe" if self.is_windows else cmd

    def create_grid_command(self, cameras, output_path, codec="h264_videotoolbox"):
        """Creates a ffmpeg command to merge camera views into a grid layout (1080p)."""
        # Define layout map: (key, x, y, width, height)
        layout = [
            ("front", 480, 0, 960, 720),
            ("left_repeater", 0, 600, 640, 480),
            ("back", 640, 600, 640, 480),
            ("right_repeater", 1280, 600, 640, 480)
        ]
        
        valid_cams = [(k, cameras[k], x, y, w, h) for k, x, y, w, h in layout if cameras.get(k)]
        if not valid_cams:
            return None
        
        canvas_w, canvas_h = 1920, 1080
        inputs = []
        filter_complex = ""
        
        # Base: Pad the first valid camera to create the canvas
        first_k, first_path, first_x, first_y, first_w, first_h = valid_cams[0]
        inputs.append(f"-i \"{first_path}\"")
        filter_complex += f"[0:v] scale={first_w}:{first_h}, pad={canvas_w}:{canvas_h}:{first_x}:{first_y}:black [base]; "
        
        current_node = "[base]"
        for i, (k, path, x, y, w, h) in enumerate(valid_cams[1:], start=1):
            inputs.append(f"-i \"{path}\"")
            filter_complex += f"[{i}:v] scale={w}:{h} [v{k}]; "
            filter_complex += f"{current_node}[v{k}] overlay=x={x}:y={y}:eof_action=pass [tmp{i}]; "
            current_node = f"[tmp{i}]"
        
        final_node = current_node.strip("[]")

        # Bitrate and codec settings with compatibility flags for Apple QuickTime
        ffmpeg_bin = self.get_ffmpeg_path("ffmpeg")
        cmd = (f"\"{ffmpeg_bin}\" -y {' '.join(inputs)} -filter_complex \"{filter_complex}\" "
               f"-map \"[{final_node}]\" -c:v {codec} -b:v 3000k -r 25 -pix_fmt yuv420p "
               f"-color_range tv -colorspace bt709 -color_trc bt709 -color_primaries bt709 "
               f"-movflags +faststart \"{output_path}\"")
        return cmd

    def process_clip(self, timestamp, cameras):
        if self.stop_requested:
            return None
        
        temp_output = os.path.join(self.output_dir, f"temp_{timestamp}.mp4")
        ffprobe_bin = self.get_ffmpeg_path("ffprobe")
        
        # 优化：如果临时分片已生成且不为空，则跳过（支持断点续传）
        if os.path.exists(temp_output) and os.path.getsize(temp_output) > 1000:
            self.log(f"DEBUG: Found cached file for {timestamp}, checking validity...")
            check = subprocess.run([ffprobe_bin, "-v", "error", temp_output], capture_output=True)
            if check.returncode == 0:
                self.log(f"DEBUG: Cache for {timestamp} is VALID.")
                return temp_output
            else:
                self.log(f"DEBUG: Cache for {timestamp} is INVALID, deleting...")
                os.remove(temp_output)

        with self.lock:
            self.active_tasks[timestamp] = "正在转码"
        
        self.log(f"DEBUG: Processing {timestamp} - HW Start")
        # 自动尝试硬件加速（macOS 为 videotoolbox, Windows 默认为 nvenc）
        cmd_hw = self.create_grid_command(cameras, temp_output, codec=self.default_hw_codec)
        try:
            self.log(f"DEBUG: Executing HW CMD: {cmd_hw}")
            result = subprocess.run(cmd_hw, shell=True, capture_output=True, text=True, timeout=300)
            self.log(f"DEBUG: HW CMD Finished for {timestamp} with code {result.returncode}")
            if result.returncode == 0:
                with self.lock:
                    if timestamp in self.active_tasks: del self.active_tasks[timestamp]
                return temp_output
            else:
                self.log(f"Hardware transcoding failed for {timestamp} (Code {result.returncode}), stderr: {result.stderr[:100]}")
                # 如果是 Windows 且 nvenc 失败，尝试 qsv (Intel)
                if self.is_windows and self.default_hw_codec == "h264_nvenc":
                    self.log("Retrying with h264_qsv (Intel HW acceleration)...")
                    cmd_qsv = self.create_grid_command(cameras, temp_output, codec="h264_qsv")
                    result = subprocess.run(cmd_qsv, shell=True, capture_output=True, text=True, timeout=300)
                    if result.returncode == 0:
                        with self.lock:
                            if timestamp in self.active_tasks: del self.active_tasks[timestamp]
                        return temp_output

        except subprocess.TimeoutExpired:
            self.log(f"Hardware transcoding TIMEOUT for {timestamp}, switching to software fallback...")
        
        # 预案 2：软件解码 (Robust)
        self.log(f"DEBUG: Retrying {timestamp} with software encoder (libx264)...")
        if os.path.exists(temp_output): os.remove(temp_output)
        
        cmd_sw = self.create_grid_command(cameras, temp_output, codec="libx264 -preset veryfast")
        try:
            self.log(f"DEBUG: Executing SW CMD: {cmd_sw}")
            result = subprocess.run(cmd_sw, shell=True, capture_output=True, text=True, timeout=600)
            self.log(f"DEBUG: SW CMD Finished for {timestamp} with code {result.returncode}")
            if result.returncode == 0:
                with self.lock:
                    if timestamp in self.active_tasks: del self.active_tasks[timestamp]
                return temp_output
            else:
                self.log(f"CRITICAL: Software fallback failed for {timestamp}: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            self.log(f"CRITICAL: Software fallback TIMEOUT for {timestamp}.")
        
        with self.lock:
            if timestamp in self.active_tasks: del self.active_tasks[timestamp]
        return None

    def merge_all(self, sample_count=None, target_date=None):
        os.makedirs(self.output_dir, exist_ok=True)
        self.log("Scanning videos...")
        grouped_days, total_files = self.group_videos()
        
        if not grouped_days:
            self.log("No videos found to process.")
            return

        # 日期过滤逻辑
        if target_date:
            if target_date in grouped_days:
                self.log(f"FILTER ENABLED: Only processing date {target_date}")
                grouped_days = {target_date: grouped_days[target_date]}
            else:
                self.log(f"ERROR: Target date {target_date} not found in source.")
                return

        # 时间戳过滤逻辑 (NEW)
        if hasattr(self, 'target_timestamps') and self.target_timestamps:
            self.log(f"TIMESTAMP FILTER ENABLED: Processing {len(self.target_timestamps)} specific clips.")
            for d in grouped_days:
                # 只保留在 target_timestamps 中的时间戳
                filtered_ts = {ts: cams for ts, cams in grouped_days[d].items() if ts in self.target_timestamps}
                grouped_days[d] = filtered_ts
                if not filtered_ts:
                    self.log(f"Warning: No matching timestamps found for date {d}")

        if sample_count:
            self.log(f"SAMPLE TEST MODE ENABLED: Limiting to {sample_count} clips per day.")
            # 对每个日期只保留前 sample_count 个时间戳
            for d in grouped_days:
                sorted_ts = sorted(grouped_days[d].keys())
                limited_ts = {ts: grouped_days[d][ts] for ts in sorted_ts[:sample_count]}
                grouped_days[d] = limited_ts

        total_timestamps = sum(len(ts) for ts in grouped_days.values())
        processed_count = 0
        
        self.log(f"Starting processing {total_timestamps} clips across {len(grouped_days)} days...")

        last_successful_output = None
        for date_str, timestamps in sorted(grouped_days.items()):
            if self.stop_requested: break
            
            self.log(f"Processing date: {date_str} ({len(timestamps)} clips)")
            daily_temp_files = []
            
            # Parallel processing for 1-minute clips
            # 限制并发数：M 系列芯片上硬件加速建议设为 2，防止过载导致超时
            max_workers = 2
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ts = {executor.submit(self.process_clip, ts, cameras): ts 
                               for ts, cameras in timestamps.items()}
                
                for future in as_completed(future_to_ts):
                    if self.stop_requested: 
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    res = future.result()
                    ts = future_to_ts[future]
                    if res:
                        daily_temp_files.append(res)
                        status_text = f"完成 {ts}"
                    else:
                        status_text = f"失败 {ts}"
                    
                    processed_count += 1
                    # Progress update
                    progress = (processed_count / total_timestamps) * 100
                    
                    # 构造并行进度信息
                    with self.lock:
                        active_info = ";".join([f"🔥 正在处理: {k}" for k in self.active_tasks.keys()])
                    
                    self.log(f"PROGRESS:{progress:.1f}%:{status_text} ({processed_count}/{total_timestamps});{active_info}")

            if daily_temp_files and not self.stop_requested:
                # Chronological sort
                daily_temp_files.sort() 
                
                # 最终检查：核对分片是否真实存在且不是坏块
                valid_files = []
                ffprobe_bin = self.get_ffmpeg_path("ffprobe")
                for tf in daily_temp_files:
                    # 使用 ffprobe 检查文件头是否完整
                    check = subprocess.run([ffprobe_bin, "-v", "error", tf], capture_output=True)
                    if check.returncode == 0:
                        valid_files.append(tf)
                    else:
                        self.log(f"Removing invalid fragment: {os.path.basename(tf)}")
                        if os.path.exists(tf): os.remove(tf)

                if len(valid_files) < len(daily_temp_files):
                    self.log(f"Warning: {len(daily_temp_files) - len(valid_files)} fragments were corrupted and removed.")
                
                if not valid_files:
                    self.log(f"Error: No valid fragments for {date_str}, skipping merge.")
                    continue

                concat_list_path = os.path.join(self.output_dir, f"concat_{date_str}.txt")
                with open(concat_list_path, "w") as f:
                    for temp_file in valid_files:
                        f.write(f"file '{os.path.abspath(temp_file)}'\n")
                
                final_output = os.path.join(self.output_dir, f"TeslaCam_{date_str}.mp4")
                self.log(f"Merging daily video for {date_str} ({len(valid_files)} clips)...")
                
                ffmpeg_bin = self.get_ffmpeg_path("ffmpeg")
                concat_cmd = f"\"{ffmpeg_bin}\" -y -f concat -safe 0 -i \"{concat_list_path}\" -c copy \"{final_output}\""
                result = subprocess.run(concat_cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    for temp_file in daily_temp_files:
                        if os.path.exists(temp_file): os.remove(temp_file)
                    if os.path.exists(concat_list_path): os.remove(concat_list_path)
                    self.log(f"Successfully created {final_output}")
                    last_successful_output = final_output
                else:
                    self.log(f"Failed to merge {date_str}: {result.stderr}")

        self.log("COMPLETED:Processing finished.")
        return last_successful_output

    def stop(self):
        self.stop_requested = True

if __name__ == "__main__":
    # Test run
    merger = TeslaCamMerger("/Volumes/TESLADRIVE/TeslaCam", "/Users/diciky/cam")
    merger.merge_all()
