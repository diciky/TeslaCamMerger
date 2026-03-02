import Foundation
import Combine

class VideoViewModel: ObservableObject {
    @Published var videos: [Video] = []
    @Published var availableDates: [VideoDate] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    
    private let apiService = APIService.shared
    private var cancellables = Set<AnyCancellable>()
    
    func loadDates() {
        isLoading = true
        
        Task {
            do {
                let dates = try await apiService.fetchDates()
                await MainActor.run {
                    self.availableDates = dates
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                    self.isLoading = false
                }
            }
        }
    }
    
    func loadVideos(for date: Date) {
        isLoading = true
        
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let dateString = formatter.string(from: date)
        
        Task {
            do {
                let videos = try await apiService.fetchVideos(forDate: dateString)
                await MainActor.run {
                    self.videos = videos
                    self.isLoading = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                    self.videos = []
                    self.isLoading = false
                }
            }
        }
    }
}
