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
Style: DashData,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,2,7,40,40,40,1
Style: DashWheel,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,2,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        lines = []
        frame_duration = 1.0 / self.fps
        
        # Downsample to ~5 times a second for readability? 
        # Actually every 6 frames = ~166ms = 6 fps.
        step = max(1, int(self.fps / 6)) 
        
        for i in range(0, len(messages), step):
            meta = messages[i]
            
            start_time = i * frame_duration
            next_i = min(i + step, len(messages))
            end_time = next_i * frame_duration
            
            speed = format_speed(meta.vehicle_speed_mps)
            gear = format_gear(meta.gear_state)
            ap = format_autopilot(meta.autopilot_state)
            accel = f"{meta.accelerator_pedal_position:.0f}%"
            brake = "已踩下" if meta.brake_applied else "未踩下"
            l_icon, r_icon = format_blinker(meta.blinker_on_left, meta.blinker_on_right)
            steer = f"{meta.steering_wheel_angle:.0f}°"
            
            text_lines = []
            if base_dt:
                current_dt = base_dt + datetime.timedelta(seconds=start_time)
                text_lines.append(f"日　期:  {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")

            text_lines.extend([
                f"车　速:  {speed}",
                f"挡　位:  {gear}",
                f"自动驾驶:  {ap}",
                f"加速踏板:  {accel}",
                f"刹　车:  {brake}",
                f"转向灯:  {l_icon}   {r_icon}",
                f"方向盘:  {steer}"
            ])
            text = r"\N".join(text_lines)
            
            start_str = format_time_ass(start_time)
            end_str = format_time_ass(end_time)
            
            # Text block at Top-Left
            ass_line = f"Dialogue: 0,{start_str},{end_str},DashData,,0,0,0,,{{\\pos(40,40)}}{text}\n"
            lines.append(ass_line)
            
            # Steering Wheel Animation
            # Vector: A perfectly centered Tesla-style steering wheel (R=50). Origin (0,0) is exactly the pivot center.
            angle = -meta.steering_wheel_angle 
            wheel_vector = r"m 0 -50 b 28 -50 50 -28 50 0 b 50 28 28 50 0 50 b -28 50 -50 28 -50 0 b -50 -28 -28 -50 0 -50 m 0 -42 b -23 -42 -42 -23 -42 0 b -42 23 -23 42 0 42 b 23 42 42 23 42 0 b 42 -23 23 -42 0 -42 m -42 -8 l 42 -8 l 42 8 l -42 8 m -18 8 l 18 8 l 12 42 l -12 42"
            wheel_line = f"Dialogue: 0,{start_str},{end_str},DashWheel,,0,0,0,,{{\\an5\\pos(380,430)\\org(380,430)\\frz{-angle}}}{{\\p1}}{wheel_vector}{{\\p0}}\n"
            lines.append(wheel_line)
            
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
