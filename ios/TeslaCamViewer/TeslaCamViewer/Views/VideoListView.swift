import SwiftUI

struct VideoListView: View {
    let videos: [Video]
    let onVideoTap: (Video) -> Void
    
    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(videos) { video in
                    VideoCard(video: video)
                        .onTapGesture {
                            onVideoTap(video)
                        }
                }
            }
            .padding()
        }
    }
}

struct VideoCard: View {
    let video: Video
    
    var body: some View {
        HStack(spacing: 16) {
            // Thumbnail placeholder
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.gray.opacity(0.3))
                    .frame(width: 120, height: 68)
                
                Image(systemName: "play.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(.white.opacity(0.8))
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(video.timestamp)
                    .font(.headline)
                    .foregroundColor(.white)
                
                Text(formatDuration(video.duration))
                    .font(.subheadline)
                    .foregroundColor(.gray)
                
                Text(formatFileSize(video.fileSize))
                    .font(.caption)
                    .foregroundColor(.gray.opacity(0.7))
            }
            
            Spacer()
            
            Image(systemName: "chevron.right")
                .foregroundColor(.gray)
        }
        .padding()
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
    }
    
    private func formatDuration(_ seconds: Int) -> String {
        let minutes = seconds / 60
        let secs = seconds % 60
        return String(format: "%02d:%02d", minutes, secs)
    }
    
    private func formatFileSize(_ bytes: Int) -> String {
        let mb = Double(bytes) / 1024.0 / 1024.0
        if mb >= 1024 {
            return String(format: "%.1f GB", mb / 1024.0)
        }
        return String(format: "%.1f MB", mb)
    }
}

#Preview {
    VideoListView(
        videos: [
            Video(id: "1", date: "2024-01-01", timestamp: "08:30:00", duration: 180, fileSize: 52_428_800, videoUrl: ""),
            Video(id: "2", date: "2024-01-01", timestamp: "12:15:00", duration: 240, fileSize: 78_643_200, videoUrl: "")
        ],
        onVideoTap: { _ in }
    )
    .preferredColorScheme(.dark)
}
