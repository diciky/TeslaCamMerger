import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = VideoViewModel()
    @State private var selectedDate: Date = Date()
    @State private var showingPlayer = false
    @State private var selectedVideo: Video?
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Header
                HStack {
                    Image(systemName: "car.fill")
                        .font(.title)
                        .foregroundColor(.red)
                    Text("TeslaCam Viewer")
                        .font(.title2)
                        .fontWeight(.bold)
                    Spacer()
                }
                .padding()
                .background(Color.black.opacity(0.9))
                
                // Date Picker
                DatePickerView(selectedDate: $selectedDate)
                    .onChange(of: selectedDate) { newDate in
                        viewModel.loadVideos(for: newDate)
                    }
                
                // Video List
                if viewModel.isLoading {
                    Spacer()
                    ProgressView("加载中...")
                        .progressViewStyle(CircularProgressViewStyle())
                    Spacer()
                } else if viewModel.videos.isEmpty {
                    Spacer()
                    VStack(spacing: 16) {
                        Image(systemName: "video.slash")
                            .font(.system(size: 60))
                            .foregroundColor(.gray)
                        Text("该日期没有视频")
                            .foregroundColor(.gray)
                    }
                    Spacer()
                } else {
                    VideoListView(
                        videos: viewModel.videos,
                        onVideoTap: { video in
                            selectedVideo = video
                            showingPlayer = true
                        }
                    )
                }
            }
            .background(Color.black)
            .navigationBarHidden(true)
        }
        .preferredColorScheme(.dark)
        .fullScreenCover(isPresented: $showingPlayer) {
            if let video = selectedVideo {
                VideoPlayerView(video: video)
            }
        }
        .onAppear {
            viewModel.loadDates()
            viewModel.loadVideos(for: selectedDate)
        }
    }
}

#Preview {
    ContentView()
}
