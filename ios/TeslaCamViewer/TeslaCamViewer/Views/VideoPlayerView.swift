import SwiftUI
import AVKit

struct VideoPlayerView: View {
    let video: Video
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            
            if let player = player {
                VideoPlayer(player: player)
                    .ignoresSafeArea()
            } else {
                VStack(spacing: 16) {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                    Text("加载视频...")
                        .foregroundColor(.gray)
                }
            }
            
            // Close button
            VStack {
                HStack {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 32))
                            .foregroundColor(.white.opacity(0.8))
                    }
                    .padding()
                    
                    Spacer()
                }
                Spacer()
            }
        }
        .onAppear {
            setupPlayer()
        }
        .onDisappear {
            player?.pause()
            player = nil
        }
    }
    
    private func setupPlayer() {
        guard let url = URL(string: video.videoUrl) else {
            return
        }
        
        let player = AVPlayer(url: url)
        self.player = player
        player.play()
    }
}

#Preview {
    VideoPlayerView(
        video: Video(
            id: "1",
            date: "2024-01-01",
            timestamp: "08:30:00",
            duration: 180,
            fileSize: 52_428_800,
            videoUrl: "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        )
    )
}
