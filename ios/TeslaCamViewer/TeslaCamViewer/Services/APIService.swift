import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case networkError(Error)
    case decodingError(Error)
    case serverError(Int)
    case unauthorized
    
    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "无效的服务器地址"
        case .networkError(let error):
            return "网络错误: \(error.localizedDescription)"
        case .decodingError:
            return "数据解析错误"
        case .serverError(let code):
            return "服务器错误: \(code)"
        case .unauthorized:
            return "API密钥无效"
        }
    }
}

class APIService {
    static let shared = APIService()
    
    // MARK: - Configuration
    // TODO: Move these to UserDefaults or a config file
    private var baseURL: String {
        UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8080"
    }
    
    private var apiKey: String {
        UserDefaults.standard.string(forKey: "api_key") ?? "dev-key-change-me"
    }
    
    private let session: URLSession
    private let decoder: JSONDecoder
    
    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)
        
        self.decoder = JSONDecoder()
    }
    
    // MARK: - Public Methods
    
    func fetchDates() async throws -> [VideoDate] {
        let url = try buildURL(path: "/api/dates")
        return try await fetch(url: url)
    }
    
    func fetchVideos(forDate date: String) async throws -> [Video] {
        var components = URLComponents(string: "\(baseURL)/api/videos")!
        components.queryItems = [
            URLQueryItem(name: "date", value: date),
            URLQueryItem(name: "key", value: apiKey)
        ]
        
        guard let url = components.url else {
            throw APIError.invalidURL
        }
        
        return try await fetch(url: url)
    }
    
    func fetchVideo(id: String) async throws -> Video {
        let url = try buildURL(path: "/api/video/\(id)")
        return try await fetch(url: url)
    }
    
    // MARK: - Configuration Methods
    
    func configure(baseURL: String, apiKey: String) {
        UserDefaults.standard.set(baseURL, forKey: "api_base_url")
        UserDefaults.standard.set(apiKey, forKey: "api_key")
    }
    
    // MARK: - Private Methods
    
    private func buildURL(path: String) throws -> URL {
        var components = URLComponents(string: "\(baseURL)\(path)")!
        components.queryItems = [
            URLQueryItem(name: "key", value: apiKey)
        ]
        
        guard let url = components.url else {
            throw APIError.invalidURL
        }
        
        return url
    }
    
    private func fetch<T: Decodable>(url: URL) async throws -> T {
        do {
            let (data, response) = try await session.data(from: url)
            
            guard let httpResponse = response as? HTTPURLResponse else {
                throw APIError.networkError(URLError(.badServerResponse))
            }
            
            switch httpResponse.statusCode {
            case 200...299:
                do {
                    return try decoder.decode(T.self, from: data)
                } catch {
                    throw APIError.decodingError(error)
                }
            case 401:
                throw APIError.unauthorized
            default:
                throw APIError.serverError(httpResponse.statusCode)
            }
        } catch let error as APIError {
            throw error
        } catch {
            throw APIError.networkError(error)
        }
    }
}
