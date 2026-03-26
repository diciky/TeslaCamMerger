import struct
import tempfile
import codecs
import datetime
from typing import Generator, Optional, Tuple, List, Dict
from google.protobuf.message import DecodeError

# This requires dashcam_pb2 to be generated in the same directory.
import dashcam_pb2

def format_speed(mps: float) -> str:
    kmh = mps * 3.6
    return f"{kmh:.0f} km/h"

def format_gear(gear_enum: int) -> str:
    mapping = {
        0: "P",
        1: "D",
        2: "R",
        3: "N"
    }
    return mapping.get(gear_enum, "未知")

def format_autopilot(ap_enum: int) -> str:
    mapping = {
        0: "未启用",
        1: "FSD",
        2: "自动转向",
        3: "自适应巡航"
    }
    return mapping.get(ap_enum, "未知")

def format_blinker(left: bool, right: bool) -> tuple:
    l_str = r"{\c&H00FF00&}⬅{\c&HFFFFFF&}" if left else r"{\c&H666666&}⬅{\c&HFFFFFF&}"
    r_str = r"{\c&H00FF00&}➡{\c&HFFFFFF&}" if right else r"{\c&H666666&}➡{\c&HFFFFFF&}"
    return l_str, r_str

def format_time_ass(seconds: float) -> str:
    """Format seconds (float) into ASS time string: h:mm:ss.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

class DashcamParser:
    def __init__(self, fps=36.0):
        self.fps = fps # Typically 36 FPS for Tesla cameras

    def extract_sei_to_ass(self, video_path: str, output_ass_path: str, base_timestamp_str: str = None):
        """Extract SEI from video_path and write an .ass file to output_ass_path.
        Returns True if successful and SEI was found, False otherwise."""
        
        sei_messages = []
        base_dt = None
        if base_timestamp_str:
            try:
                base_dt = datetime.datetime.strptime(base_timestamp_str, "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                pass

        try:
            with open(video_path, "rb") as fp:
                offset, size = self._find_mdat(fp)
                for meta in self._iter_sei_messages(fp, offset, size):
                    sei_messages.append(meta)
        except Exception as e:
            return False

        if not sei_messages:
            return False

        self._write_ass_file(sei_messages, output_ass_path, base_dt)
        return True

    def _write_ass_file(self, messages: List[dashcam_pb2.SeiMetadata], out_path: str, base_dt: Optional[datetime.datetime] = None):
        # We group nearby messages if needed, or just write them frame by frame.
        # But writing 2160 lines for a 1 minute file is totally fine for ASS.
        
        # We will update the subtitle roughly every 3 frames (12fps) to reduce file size and jitter.
        # 1 frame at 36fps = 0.0277s
        
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HudG,Arial,48,&H80FFFFFF,&H000000FF,&H80FFFF00,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1
Style: HudF,Arial,48,&H00FFFFFF,&H000000FF,&HFFFF00&,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
Style: HudT,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
Style: HudSpeed,Arial,110,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,5,5,0,0,0,1
Style: HudGear,Arial,60,&HFFFF00&,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1
Style: HudWheel,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = []
        frame_duration = 1.0 / self.fps
        # 降采样率：每秒写入约 6fps 的动态数据，防止字幕文件过大并降低 ASS 渲染器的高频压力
        step = max(1, int(self.fps / 6)) 
        
        # --------------------------
        # 【HUD 全局调参配置区】
        # --------------------------
        # 这是一个坐标乘法函数：它自动解析矢量绘画指令中的每一个数字，进行倍率乘算
        def scale_vec(v_str, scale):
            parts = v_str.split()
            out = []
            for p in parts:
                try: out.append(str(int(int(p) * scale)))
                except ValueError: out.append(p)
            return " ".join(out)

        # 1. 【全局尺寸】所有矢量图形和字体等比缩放的倍率 (0.55 = 55% 原大)
        # 如果你觉得整个 HUD 还是太大或太小，只改数字 SCALE 即可！无需重新算别的。
        SCALE = 0.55
        
        # 2. 【主题颜色】(ASS 颜色格式为 &H[Alpha][Blue][Green][Red]&)
        CYAN = "&HFFFF00&"   # 赛博青色（主色光效）
        GREEN = "&H96FF00&"  # 荧光绿（加速、转向亮起等动态槽）
        RED = "&H3232FF&"    # 霓虹红（刹车触发色）
        GREY = "&H444444&"   # 暗影灰（背景线槽与未触发的组件）
        
        # 3. 【绝对定位】整个大框架在画面内的核心十字锚点 X 和 Y (基于 1920x1080)
        # 你可以改变 300(X轴)和 250(Y轴)来把 HUD 上下左右整体拖移定位。
        CX, CY = int(300 * SCALE), int(250 * SCALE)
        # 虚拟锚点边界控制：对抗ASS重心漂移使用的隐形占位框，无需修改。
        BBOX = scale_vec("m -320 -250 m 320 250", SCALE)

        # --------------------------
        # 下方为纯底层图形学构建（手写多边形/弧线矢量路径 m_X_Y_l(line)...）
        # 预先进行缩放装载，循环写入时可极大减轻处理开销
        # --------------------------
        hud_base = scale_vec("m -120 -5 l -280 15 l -280 150 l -180 210 l -120 210 l -120 -5 m 120 -5 l 280 15 l 280 150 l 180 210 l 120 210 l 120 -5 m -90 120 l 90 120 l 130 210 l -130 210 l -90 120", SCALE)
        accents = scale_vec("m -250 25 l -250 140 m -220 25 l -220 170 m 250 25 l 250 140 m 220 25 l 220 170", SCALE)
        arcs = scale_vec("m 0 -115 b 60 -115 110 -65 110 -5 b 110 55 60 105 0 105 b -60 105 -110 55 -110 -5 b -110 -65 -60 -115 0 -115", SCALE)
        arcs_in = scale_vec("m 0 -105 b 55 -105 100 -60 100 -5 b 100 50 55 95 0 95 b -55 95 -100 50 -100 -5 b -100 -60 -55 -105 0 -105", SCALE)
        shield = scale_vec("m -230 45 l -170 45 l -170 85 b -170 120 -200 135 -200 135 b -200 135 -230 120 -230 85 l -230 45", SCALE)
        bar_frames = scale_vec("m 180 50 l 200 50 l 200 160 l 180 160 l 180 50 m 230 50 l 250 50 l 250 160 l 230 160 l 230 50", SCALE)

        for i in range(0, len(messages), step):
            meta = messages[i]
            
            start_time = i * frame_duration
            next_i = min(i + step, len(messages))
            end_time = next_i * frame_duration
            
            # --- 解析并转换 Tesla 元数据为可视化 UI 数值 ---
            speed_val = f"{meta.vehicle_speed_mps * 3.6:.0f}"
            gear = format_gear(meta.gear_state)
            ap = format_autopilot(meta.autopilot_state)
            # 缩紧加速比的区间在 0.0 - 1.0 (等效0%-100%)
            accel_pct = max(0.0, min(1.0, meta.accelerator_pedal_position / 100.0))
            brake_applied = meta.brake_applied
            
            start_str = format_time_ass(start_time)
            end_str = format_time_ass(end_time)
            
            # 一个快速组装单条字幕轨迹层的工具方法
            def evt(layer, style, x, y, text):
                return f"Dialogue: {layer},{start_str},{end_str},{style},,0,0,0,,{{\\pos({x},{y})}}{text}\n"

            # ===============================
            # Layer 0 & 1 - 静态骨架背景层
            # 渲染左右羽翼及速度刻度环（携带半透明填充以实现赛博玻璃感）
            # ===============================
            # \an5 保证形状精确锚定。 \1c 是填充色，\1a是填充透明度。 \bord2 及 \3c 是发光边框。
            lines.append(evt(0, "HudG", CX, CY, f"{{\\an5\\1c&H111111&\\1a&HE0&\\3c{CYAN}\\3a&H40&\\p1}}{hud_base} {BBOX}{{\\p0}}"))
            lines.append(evt(0, "HudG", CX, CY, f"{{\\an5\\1a&HFF&\\bord2\\3c{CYAN}\\3a&H80&\\p1}}{accents} {BBOX}{{\\p0}}"))
            lines.append(evt(1, "HudG", CX, CY, f"{{\\an5\\1a&HFF&\\bord4\\3c{CYAN}\\3a&HDD&\\p1}}{arcs} {BBOX}{{\\p0}}"))
            lines.append(evt(1, "HudF", CX, CY, f"{{\\an5\\1a&HFF&\\bord1\\3c{CYAN}\\3a&H40&\\p1}}{arcs_in} {BBOX}{{\\p0}}"))
            
            # 当启用各类自动驾驶 (AP/FSD) 时，将护盾染成绿色实体
            shield_fill_alpha = "&HAA&" if meta.autopilot_state else "&HEE&"
            shield_fill_color = "&H96FF00&" if meta.autopilot_state else "&H333333&"
            lines.append(evt(1, "HudF", CX, CY, f"{{\\an5\\1a{shield_fill_alpha}\\1c{shield_fill_color}\\bord2\\3c{CYAN}\\p1}}{shield} {BBOX}{{\\p0}}"))
            
            # 右侧刻度槽（常驻白色半边框）
            lines.append(evt(1, "HudF", CX, CY, f"{{\\an5\\1a&HFF&\\bord2\\3c{CYAN}\\3a&H66&\\p1}}{bar_frames} {BBOX}{{\\p0}}"))

            # ===============================
            # Layer 2 - 动态进度条渲染层
            # ===============================
            # 加速槽逻辑：通过改变Y坐标顶缝值来缩近矩形高度，实现从底部向上溢满。
            accel_fill_y = 160 - int(110 * accel_pct)
            accel_fill = scale_vec(f"m 232 {accel_fill_y} l 248 {accel_fill_y} l 248 158 l 232 158 l 232 {accel_fill_y}", SCALE)
            lines.append(evt(2, "HudF", CX, CY, f"{{\\an5\\1c{GREEN}\\bord0\\3a&HFF&\\p1}}{accel_fill} {BBOX}{{\\p0}}"))
            
            # 刹车触发时瞬间填充满整个深红色指示框
            if brake_applied:
                brake_fill = scale_vec("m 182 52 l 198 52 l 198 158 l 182 158 l 182 52", SCALE)
                lines.append(evt(2, "HudF", CX, CY, f"{{\\an5\\1c{RED}\\bord0\\3a&HFF&\\p1}}{brake_fill} {BBOX}{{\\p0}}"))

            # ===============================
            # Layer 3 - 动态文本文字流与方向盘动画交互
            # ===============================
            # 帮助运算文字位置的一个辅助对齐器，将给定的相对横纵距加上主轴点完成相对偏移
            def off(ox, oy): return CX + int(ox * SCALE), CY + int(oy * SCALE)
            
            # 正中间速度 (拉大间距)
            lines.append(evt(3, "HudSpeed", *off(0, -50), f"{{\\fs{int(120*SCALE)}}}{speed_val}"))
            lines.append(evt(3, "HudT", *off(0, 60), f"{{\\fs{int(26*SCALE)}}}KM/H"))
            lines.append(evt(3, "HudGear", *off(0, 130), f"{{\\fs{int(60*SCALE)}}}{gear}"))

            # 右侧边翼踏板监视字符 (扩充 ox 间距)
            lines.append(evt(3, "HudF", *off(-220, 100), f"{{\\fs{int(50*SCALE)}}}A"))
            lines.append(evt(3, "HudT", *off(-220, 170), f"{{\\fs{int(20*SCALE)}}}{ap}"))

            lines.append(evt(3, "HudT", *off(210, 35), f"{{\\c{RED}\\fs{int(18*SCALE)}}}BRAKE"))
            lines.append(evt(3, "HudT", *off(260, 35), f"{{\\c{GREEN}\\fs{int(18*SCALE)}}}ACCEL"))
            lines.append(evt(3, "HudT", *off(235, 185), f"{{\\fs{int(18*SCALE)}}}加速: {int(accel_pct*100)}%"))
            lines.append(evt(3, "HudT", *off(235, 215), f"{{\\fs{int(18*SCALE)}}}刹车: {'已踩下' if brake_applied else '未踩下'}"))

            # -------------------------------
            # ※ 动态特斯拉连动式方向盘演算 ※
            # 按照用户给出的最优方案：直接用 \an5 + \org 相同坐标锁定自转重心
            # -------------------------------
            angle = -meta.steering_wheel_angle
            wheel_vector = scale_vec(r"m 0 -40 b 22 -40 40 -22 40 0 b 40 22 22 40 0 40 b -22 40 -40 22 -40 0 b -40 -22 -22 -40 0 -40 m 0 -33 b -18 -33 -33 -18 -33 0 b -33 18 -18 33 0 33 b 18 33 33 18 33 0 b 33 -18 18 -33 0 -33 m -33 -6 l 33 -6 l 33 6 l -33 6 m -14 6 l 14 6 l 9 33 l -9 33", SCALE)
            WX, WY = off(0, 205) # 将方向盘位置进一步调低，避免与挡位重叠
            # 1. \an5 确保绘图中心就在 (WX, WY)
            # 2. \org(WX, WY) 强制旋转轴心锁定在 (WX, WY)
            lines.append(evt(3, "HudWheel", WX, WY, f"{{\\an5\\org({WX},{WY})\\frz{-angle}\\1a&H33&\\3c{GREY}\\bord2\\p1}}{wheel_vector}{{\\p0}}"))
            # 3. 角度文字也对齐到中心
            lines.append(evt(4, "HudT", WX, WY, f"{{\\an5\\fs{int(18*SCALE)}\\c{CYAN}}}{-angle:.0f}°"))

            # 闪烁转向灯控制
            l_color = GREEN if meta.blinker_on_left else GREY
            r_color = GREEN if meta.blinker_on_right else GREY
            lines.append(evt(3, "HudT", *off(-60, 165), f"{{\\c{l_color}\\fs{int(30*SCALE)}}}⬅"))
            lines.append(evt(3, "HudT", *off(60, 165), f"{{\\c{r_color}\\fs{int(30*SCALE)}}}➡"))

            if base_dt:
                current_dt = base_dt + datetime.timedelta(seconds=start_time)
                lines.append(evt(3, "HudT", CX, CY + int(245 * SCALE), f"{{\\fs{int(24*SCALE)}}}{current_dt.strftime('%Y-%m-%d %H:%M:%S')}"))
            
        # ASS needs UTF-8 with BOM usually if it has CJK, but standard utf-8 works fine with ffmpeg.
        with codecs.open(out_path, "w", "utf-8") as f:
            f.write(header)
            f.writelines(lines)

    # Everything below is verbatim logic from sei_extractor.py
    def _iter_sei_messages(self, fp, offset: int, size: int):
        for nal in self._iter_nals(fp, offset, size):
            payload = self._extract_proto_payload(nal)
            if not payload:
                continue
            meta = dashcam_pb2.SeiMetadata()
            try:
                meta.ParseFromString(payload)
            except DecodeError:
                continue
            yield meta

    def _extract_proto_payload(self, nal: bytes) -> Optional[bytes]:
        if not isinstance(nal, bytes) or len(nal) < 2:
            return None
        for i in range(3, len(nal) - 1):
            byte = nal[i]
            if byte == 0x42:
                continue
            if byte == 0x69:
                if i > 2:
                    return self._strip_emulation_prevention_bytes(nal[i + 1:-1])
                break
            break
        return None

    def _strip_emulation_prevention_bytes(self, data: bytes) -> bytes:
        stripped = bytearray()
        zero_count = 0
        for byte in data:
            if zero_count >= 2 and byte == 0x03:
                zero_count = 0
                continue
            stripped.append(byte)
            zero_count = 0 if byte != 0 else zero_count + 1
        return bytes(stripped)

    def _iter_nals(self, fp, offset: int, size: int) -> Generator[bytes, None, None]:
        NAL_ID_SEI = 6
        NAL_SEI_ID_USER_DATA_UNREGISTERED = 5

        fp.seek(offset)
        consumed = 0
        while size == 0 or consumed < size:
            header = fp.read(4)
            if len(header) < 4:
                break
            nal_size = struct.unpack(">I", header)[0]
            if nal_size < 2:
                fp.seek(nal_size, 1)
                consumed += 4 + nal_size
                continue

            first_two = fp.read(2)
            if len(first_two) != 2:
                break

            if (first_two[0] & 0x1F) != NAL_ID_SEI or first_two[1] != NAL_SEI_ID_USER_DATA_UNREGISTERED:
                fp.seek(nal_size - 2, 1)
                consumed += 4 + nal_size
                continue

            rest = fp.read(nal_size - 2)
            if len(rest) != nal_size - 2:
                break
            payload = first_two + rest
            consumed += 4 + nal_size
            yield payload

    def _find_mdat(self, fp) -> Tuple[int, int]:
        fp.seek(0)
        while True:
            header = fp.read(8)
            if len(header) < 8:
                raise RuntimeError("mdat atom not found")
            size32, atom_type = struct.unpack(">I4s", header)
            if size32 == 1:
                large = fp.read(8)
                if len(large) != 8:
                    raise RuntimeError("truncated extended atom size")
                atom_size = struct.unpack(">Q", large)[0]
                header_size = 16
            else:
                atom_size = size32 if size32 else 0
                header_size = 8
            if atom_type == b"mdat":
                payload_size = atom_size - header_size if atom_size else 0
                return fp.tell(), payload_size
            if atom_size < header_size:
                raise RuntimeError("invalid MP4 atom size")
            fp.seek(atom_size - header_size, 1)
