"""
TeslaCam Viewer - Cloud Backend
Serves video metadata and streams to iOS app.
Uses Cloudflare R2 for video storage.
"""

import os
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Configuration ---
# Set these via environment variables in production
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")  # e.g., https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "teslacam-videos")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "")  # Public URL for video access

# API Key for simple auth
API_KEY = os.getenv("TESLACAM_API_KEY", "dev-key-change-me")

# --- App Setup ---
app = FastAPI(
    title="TeslaCam Viewer API",
    description="Cloud API for TeslaCam video browsing and playback",
    version="1.0.0"
)

# CORS for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
class Video(BaseModel):
    id: str
    date: str
    timestamp: str
    duration: int  # seconds
    file_size: int  # bytes
    thumbnail_url: Optional[str] = None
    video_url: str

class VideoDate(BaseModel):
    date: str
    video_count: int

class UploadRequest(BaseModel):
    filename: str
    file_size: int
    date: str

class UploadResponse(BaseModel):
    upload_url: str
    video_id: str

# --- In-Memory Video Index ---
# In production, use a database like SQLite or PostgreSQL
video_index: List[dict] = []
video_index_file = Path("video_index.json")

def load_video_index():
    global video_index
    if video_index_file.exists():
        with open(video_index_file, 'r') as f:
            video_index = json.load(f)

def save_video_index():
    with open(video_index_file, 'w') as f:
        json.dump(video_index, f, indent=2, ensure_ascii=False)

# --- API Key Verification ---
def verify_api_key(api_key: str = Query(..., alias="key")):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# --- API Endpoints ---

@app.on_event("startup")
async def startup():
    load_video_index()
    print(f"Loaded {len(video_index)} videos from index")

@app.get("/")
async def root():
    return {"message": "TeslaCam Viewer API", "version": "1.0.0"}

@app.get("/api/dates", response_model=List[VideoDate])
async def get_dates(key: str = Query(...)):
    """Get all dates that have videos."""
    verify_api_key(key)
    
    date_counts = {}
    for video in video_index:
        date = video.get("date", "unknown")
        date_counts[date] = date_counts.get(date, 0) + 1
    
    return [
        VideoDate(date=date, video_count=count)
        for date, count in sorted(date_counts.items(), reverse=True)
    ]

@app.get("/api/videos", response_model=List[Video])
async def get_videos(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    key: str = Query(...)
):
    """Get all videos for a specific date."""
    verify_api_key(key)
    
    videos = [
        Video(**v) for v in video_index
        if v.get("date") == date
    ]
    return sorted(videos, key=lambda x: x.timestamp)

@app.get("/api/video/{video_id}")
async def get_video(video_id: str, key: str = Query(...)):
    """Get video details and streaming URL."""
    verify_api_key(key)
    
    for video in video_index:
        if video.get("id") == video_id:
            return Video(**video)
    
    raise HTTPException(status_code=404, detail="Video not found")

@app.post("/api/upload", response_model=UploadResponse)
async def request_upload(request: UploadRequest, key: str = Query(...)):
    """
    Request a presigned URL for uploading a video.
    Called by the Mac app after merging.
    """
    verify_api_key(key)
    
    if not R2_ENDPOINT or not R2_ACCESS_KEY:
        raise HTTPException(
            status_code=503,
            detail="Cloud storage not configured. Set R2_* environment variables."
        )
    
    import boto3
    from botocore.config import Config
    
    # Generate video ID
    video_id = f"{request.date}_{request.filename.replace('.mp4', '')}_{int(datetime.now().timestamp())}"
    
    # Create S3 client for R2
    s3 = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )
    
    # Generate presigned upload URL
    object_key = f"videos/{video_id}.mp4"
    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': R2_BUCKET,
            'Key': object_key,
            'ContentType': 'video/mp4'
        },
        ExpiresIn=3600  # 1 hour
    )
    
    return UploadResponse(upload_url=upload_url, video_id=video_id)

@app.post("/api/upload/complete")
async def complete_upload(
    video_id: str = Query(...),
    date: str = Query(...),
    duration: int = Query(0),
    file_size: int = Query(0),
    key: str = Query(...)
):
    """Called after upload completes to register video in index."""
    verify_api_key(key)
    
    video_url = f"{R2_PUBLIC_URL}/videos/{video_id}.mp4" if R2_PUBLIC_URL else ""
    
    video_data = {
        "id": video_id,
        "date": date,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "duration": duration,
        "file_size": file_size,
        "video_url": video_url
    }
    
    video_index.append(video_data)
    save_video_index()
    
    return {"status": "ok", "video": video_data}

@app.delete("/api/video/{video_id}")
async def delete_video(video_id: str, key: str = Query(...)):
    """Delete a video from the index and storage."""
    verify_api_key(key)
    
    global video_index
    video_index = [v for v in video_index if v.get("id") != video_id]
    save_video_index()
    
    # Note: Actual R2 deletion would require boto3 call
    return {"status": "deleted", "video_id": video_id}

@app.get("/health")
async def health_check():
    """Health check endpoint for deployment platforms."""
    return {"status": "healthy", "videos_indexed": len(video_index)}


# --- Local Development ---
if __name__ == "__main__":
    import uvicorn
    print("Starting TeslaCam Cloud API in development mode...")
    print("API Key:", API_KEY)
    uvicorn.run(app, host="0.0.0.0", port=8080)
