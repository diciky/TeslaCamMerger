import Foundation

struct Video: Identifiable, Codable {
    let id: String
    let date: String
    let timestamp: String
    let duration: Int
    let fileSize: Int
    let thumbnailUrl: String?
    let videoUrl: String
    
    enum CodingKeys: String, CodingKey {
        case id
        case date
        case timestamp
        case duration
        case fileSize = "file_size"
        case thumbnailUrl = "thumbnail_url"
        case videoUrl = "video_url"
    }
    
    init(id: String, date: String, timestamp: String, duration: Int, fileSize: Int, thumbnailUrl: String? = nil, videoUrl: String) {
        self.id = id
        self.date = date
        self.timestamp = timestamp
        self.duration = duration
        self.fileSize = fileSize
        self.thumbnailUrl = thumbnailUrl
        self.videoUrl = videoUrl
    }
}

struct VideoDate: Identifiable, Codable {
    var id: String { date }
    let date: String
    let videoCount: Int
    
    enum CodingKeys: String, CodingKey {
        case date
        case videoCount = "video_count"
    }
}
