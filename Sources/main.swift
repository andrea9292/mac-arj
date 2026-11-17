import AppKit
import Foundation
import Darwin

struct AppError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
    init(_ message: String) { self.message = message }
}
let fm = FileManager.default
let maxBytes: UInt64 = 2 * 1024 * 1024 * 1024
let maxEntries = 10_000

func safePath(_ path: String) -> Bool {
    guard !path.isEmpty, !path.hasPrefix("/"), !path.hasPrefix("\\"),
          !path.contains(":"), !path.contains("\\"),
          !path.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { return false }
    return path.split(separator: "/", omittingEmptySubsequences: false).allSatisfy { !$0.isEmpty && $0 != "." && $0 != ".." }
}

func sevenZip() throws -> URL {
    for path in ["/opt/homebrew/bin/7zz", "/usr/local/bin/7zz"] where fm.isExecutableFile(atPath: path) {
        return URL(fileURLWithPath: path)
    }
    throw AppError("7zz를 찾을 수 없습니다. Homebrew로 7zip을 설치한 뒤 다시 시도하십시오.")
}

func run(_ executable: URL, _ arguments: [String], work: URL, timeout: TimeInterval) throws -> String {
    let log = work.appendingPathComponent(UUID().uuidString + ".log")
    guard fm.createFile(atPath: log.path, contents: nil) else { throw AppError("작업 로그를 만들 수 없습니다.") }
    let output = try FileHandle(forWritingTo: log)
    defer { try? output.close(); try? fm.removeItem(at: log) }
    let process = Process()
    process.executableURL = executable
    process.arguments = arguments
    process.standardInput = FileHandle.nullDevice
    process.standardOutput = output
    process.standardError = output
    process.currentDirectoryURL = work
    var environment = ProcessInfo.processInfo.environment
    environment["LC_ALL"] = "en_US.UTF-8"
    process.environment = environment
    try process.run()
    let deadline = Date().addingTimeInterval(timeout)
    var limitHit = false
    while process.isRunning {
        let size = (try? fm.attributesOfItem(atPath: log.path)[.size] as? NSNumber)?.uint64Value ?? 0
        if Date() >= deadline || size > 16 * 1024 * 1024 {
            limitHit = true
            process.terminate()
            Thread.sleep(forTimeInterval: 0.2)
            if process.isRunning { Darwin.kill(process.processIdentifier, SIGKILL) }
            break
        }
        Thread.sleep(forTimeInterval: 0.05)
    }
    process.waitUntilExit()
    if limitHit { throw AppError("처리 시간 또는 로그 크기 제한을 초과했습니다.") }
    let data = try Data(contentsOf: log)
    guard let text = String(data: data, encoding: .utf8) else { throw AppError("파일 이름 또는 목록의 문자 인코딩을 해석할 수 없습니다.") }
    guard process.terminationStatus == 0 else {
        throw AppError("ARJ 처리에 실패했습니다. 손상·암호화·분할 압축은 지원하지 않습니다.\n\n" + String(text.suffix(2000)))
    }
    return text
}

struct Entry { let path: String; let size: UInt64; let folder: Bool }
func entries(_ listing: String) throws -> [Entry] {
    var result: [Entry] = []
    var total: UInt64 = 0
    var seen = Set<String>()
    for block in listing.components(separatedBy: "\n\n") where !block.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        var fields: [String: String] = [:]
        for line in block.split(separator: "\n", omittingEmptySubsequences: true) {
            guard let range = line.range(of: " = ") else { throw AppError("안전하게 해석할 수 없는 압축 목록입니다.") }
            let key = String(line[..<range.lowerBound])
            guard fields[key] == nil else { throw AppError("중복된 압축 목록 항목입니다.") }
            fields[key] = String(line[range.upperBound...])
        }
        guard let path = fields["Path"], safePath(path),
              let rawSize = fields["Size"], let size = UInt64(rawSize),
              let folder = fields["Folder"], ["+", "-"].contains(folder),
              fields["Encrypted"] == "-", fields["Position"] == "",
              fields["Symbolic Link"] == nil, fields["Hard Link"] == nil,
              !(fields["Attributes"] ?? "").contains("l") else {
            throw AppError("안전하지 않은 경로, 링크, 암호화 또는 분할 압축 항목을 거부했습니다.")
        }
        // Conservative macOS collision check (case folding and Unicode normalization).
        let canonical = path.precomposedStringWithCanonicalMapping.lowercased()
        guard seen.insert(canonical).inserted else { throw AppError("이름이 충돌하는 압축 항목입니다.") }
        guard size <= maxBytes, total <= maxBytes - size, result.count < maxEntries else {
            throw AppError("압축 해제 한도(2 GiB 또는 10,000개 항목)를 초과했습니다.")
        }
        total += size
        result.append(Entry(path: path, size: size, folder: folder == "+"))
    }
    guard !result.isEmpty else { throw AppError("압축 파일에 해제할 항목이 없습니다.") }
    return result
}

func reserveDestination(_ archive: URL) throws -> URL {
    let parent = archive.deletingLastPathComponent()
    let stem = archive.deletingPathExtension().lastPathComponent
    guard !stem.isEmpty, stem != ".", stem != ".." else { throw AppError("대상 폴더 이름이 올바르지 않습니다.") }
    for index in 1...10_000 {
        let name = index == 1 ? stem : "\(stem) (\(index))"
        let destination = parent.appendingPathComponent(name, isDirectory: true)
        if Darwin.mkdir(destination.path, 0o700) == 0 { return destination }
        if errno != EEXIST { throw AppError("압축 파일 옆에 폴더를 만들 수 없습니다: \(String(cString: strerror(errno)))") }
    }
    throw AppError("사용할 수 있는 대상 폴더 이름을 찾지 못했습니다.")
}

func verify(_ destination: URL, expected: [Entry]) throws {
    // Foundation may enumerate /var aliases as /private/var. Compare against
    // the same resolved base rather than slicing a differently spelled path.
    let base = destination.resolvingSymlinksInPath().standardizedFileURL
    guard let enumerator = fm.enumerator(at: base, includingPropertiesForKeys: nil) else { throw AppError("결과를 확인할 수 없습니다.") }
    var actual: [String: UInt64] = [:]
    var count = 0
    for case let file as URL in enumerator {
        count += 1
        var statInfo = stat()
        guard count <= maxEntries * 2, lstat(file.path, &statInfo) == 0 else { throw AppError("결과 항목 제한 또는 확인 오류입니다.") }
        let kind = statInfo.st_mode & S_IFMT
        guard kind == S_IFREG || kind == S_IFDIR else { throw AppError("결과에서 링크 또는 특수 파일을 발견했습니다.") }
        guard file.path.hasPrefix(base.path + "/") else { throw AppError("결과가 대상 폴더 밖에 있습니다.") }
        let relative = String(file.path.dropFirst(base.path.count + 1))
        guard safePath(relative) else { throw AppError("안전하지 않은 결과 경로입니다.") }
        if kind == S_IFREG {
            guard statInfo.st_nlink == 1 else { throw AppError("하드 링크는 지원하지 않습니다.") }
            actual[relative] = UInt64(statInfo.st_size)
            _ = chmod(file.path, 0o600)
        } else { _ = chmod(file.path, 0o700) }
    }
    let wanted = Dictionary(uniqueKeysWithValues: expected.filter { !$0.folder }.map { ($0.path, $0.size) })
    guard actual == wanted else { throw AppError("해제 결과가 사전 확인한 목록과 일치하지 않습니다.") }
}

func extract(_ input: URL) throws -> URL {
    let source = input.standardizedFileURL
    guard source.pathExtension.lowercased() == "arj" else { throw AppError(".arj 파일만 지원합니다.") }
    var info = stat()
    guard lstat(source.path, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
          info.st_size > 0, UInt64(info.st_size) <= maxBytes else {
        throw AppError("읽을 수 있는 일반 ARJ 파일이 아니거나 파일 크기 제한(2 GiB)을 초과했습니다.")
    }
    let tool = try sevenZip()
    let work = fm.temporaryDirectory.appendingPathComponent("mac-arj-" + UUID().uuidString, isDirectory: true)
    try fm.createDirectory(at: work, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
    defer { try? fm.removeItem(at: work) }
    // Work from one private snapshot so preflight, CRC and extraction see identical bytes.
    let snapshot = work.appendingPathComponent("input.arj")
    try fm.copyItem(at: source, to: snapshot)
    let common = ["-tArj", "-p", "-bd", "-y"]
    let listing = try run(tool, ["l", "-slt", "-ba"] + common + ["--", snapshot.path], work: work, timeout: 30)
    let expected = try entries(listing)
    _ = try run(tool, ["t"] + common + ["--", snapshot.path], work: work, timeout: 120)
    let destination = try reserveDestination(source)
    do {
        _ = try run(tool, ["x", "-aos", "-o" + destination.path] + common + ["--", snapshot.path], work: work, timeout: 120)
        try verify(destination, expected: expected)
        return destination
    } catch {
        try? fm.removeItem(at: destination)
        throw error
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var queue: [URL] = []
    var busy = false
    var chooserShown = false
    var quitWork: DispatchWorkItem?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        if !busy && queue.isEmpty { choose() } else { processNext() }
    }
    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        quitWork?.cancel()
        queue.append(contentsOf: filenames.map { URL(fileURLWithPath: $0) })
        sender.reply(toOpenOrPrint: .success)
        processNext()
    }
    func choose() {
        guard !chooserShown else { return }
        chooserShown = true
        let panel = NSOpenPanel()
        panel.title = "ARJ 압축 파일 선택"
        panel.message = "원본은 보존하며 같은 위치의 새 폴더에 압축을 해제합니다."
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [UTType(filenameExtension: "arj") ?? .data]
        NSApp.activate(ignoringOtherApps: true)
        if panel.runModal() == .OK { queue.append(contentsOf: panel.urls) }
        processNext()
    }
    func processNext() {
        guard !busy else { return }
        quitWork?.cancel()
        guard !queue.isEmpty else {
            // Finder may deliver another open event after the current completion.
            let work = DispatchWorkItem { [weak self] in
                guard let self, !self.busy, self.queue.isEmpty else { return }
                NSApp.terminate(nil)
            }
            quitWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: work)
            return
        }
        busy = true
        let source = queue.removeFirst()
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result { try extract(source) }
            DispatchQueue.main.async {
                switch result {
                case .success(let destination): NSWorkspace.shared.open(destination)
                case .failure(let error):
                    NSApp.activate(ignoringOtherApps: true)
                    let alert = NSAlert()
                    alert.alertStyle = .warning
                    alert.messageText = "ARJ 압축을 해제하지 못했습니다"
                    alert.informativeText = source.lastPathComponent + "\n\n" + error.localizedDescription
                    alert.addButton(withTitle: "확인")
                    alert.runModal()
                }
                self.busy = false
                self.processNext()
            }
        }
    }
}

import UniformTypeIdentifiers
let arguments = CommandLine.arguments
if arguments.count > 1 {
    do {
        if arguments[1] == "--self-test" {
            let good = ["hello.txt", "한글 폴더/파일 이름.txt"]
            let bad = ["", "/etc/passwd", "../x", "a/../x", "C:/x", "C:\\x", "\\\\host\\x", "a//b", "a\nx", "./x"]
            guard good.allSatisfy(safePath), bad.allSatisfy({ !safePath($0) }) else { throw AppError("경로 검사 실패") }
            print("Path validation self-test passed")
        } else if arguments[1] == "--extract", arguments.count == 3 {
            print(try extract(URL(fileURLWithPath: arguments[2])).path)
        } else { throw AppError("Usage: Mac ARJ --extract FILE.arj | --self-test") }
    } catch {
        FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
        exit(1)
    }
} else {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
