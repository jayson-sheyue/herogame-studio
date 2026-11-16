import AppKit
import WebKit
import UniformTypeIdentifiers

final class StudioApp: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var service: Process?
    var output = Data()
    var port: Int?
    var token = UUID().uuidString + UUID().uuidString
    var quitting = false
    var startupTimer: Timer?
    var status: NSTextField!
    var retry: NSButton!
    var ready = false
    var preparing: (id: String, filename: String)?
    var downloads: [ObjectIdentifier: (temp: URL, destination: URL, id: String?)] = [:]
    var downloadIDs: [ObjectIdentifier: String] = [:]
    let preferences = UserDefaults.standard
    var dataDirectory: URL {
        // A separate launch profile is useful for isolated tests; never copy a user's data.
        if let path = ProcessInfo.processInfo.environment["STUDIO_DATA_DIR"], path.hasPrefix("/") {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("HeroGameStudio", isDirectory: true)
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "作图工坊"
        window.minSize = NSSize(width: 860, height: 620)
        window.center(); window.delegate = self; window.isReleasedWhenClosed = false
        window.appearance = NSAppearance(named: .darkAqua)
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        config.preferences.javaScriptCanOpenWindowsAutomatically = true
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "studio")
        let prefs = preferences.dictionary(forKey: "workspacePreferences") ?? [:]
        let json = (try? JSONSerialization.data(withJSONObject: prefs)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        let bridge = (try? String(contentsOf: Bundle.main.url(forResource: "bridge", withExtension: "js")!, encoding: .utf8)) ?? ""
        config.userContentController.addUserScript(WKUserScript(source: "window.__studioPreferences = \(json);\n" + bridge, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web = WKWebView(frame: window.contentView!.bounds, configuration: config)
        web.autoresizingMask = [.width, .height]; web.navigationDelegate = self; web.uiDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        window.contentView!.addSubview(web)
        status = NSTextField(labelWithString: "正在启动作图工坊…")
        status.font = .systemFont(ofSize: 18); status.alignment = .center
        status.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(status)
        retry = NSButton(title: "重新启动", target: self, action: #selector(startBackend))
        retry.translatesAutoresizingMaskIntoConstraints = false; retry.isHidden = true
        window.contentView!.addSubview(retry)
        NSLayoutConstraint.activate([status.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor), status.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor), retry.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 24), retry.centerXAnchor.constraint(equalTo: status.centerXAnchor)])
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        startBackend()
    }
    func buildMenu() {
        let menu = NSMenu()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于作图工坊", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏作图工坊", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出作图工坊", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let appItem = NSMenuItem(); appItem.submenu = appMenu; menu.addItem(appItem)
        let edit = NSMenu(title: "编辑")
        for (title, selector, key) in [("撤销", "undo:", "z"), ("重做", "redo:", "Z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        let editItem = NSMenuItem(title: "编辑", action: nil, keyEquivalent: ""); editItem.submenu = edit; menu.addItem(editItem)
        let view = NSMenu(title: "窗口")
        view.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        view.addItem(withTitle: "关闭窗口", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        view.addItem(withTitle: "显示作图工坊", action: #selector(showWindow), keyEquivalent: "0")
        let viewItem = NSMenuItem(title: "窗口", action: nil, keyEquivalent: ""); viewItem.submenu = view; menu.addItem(viewItem)
        NSApp.mainMenu = menu
    }
    @objc func about() {
        NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "作图工坊", .applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "", .credits: NSAttributedString(string: "本地像素游戏资产与桌宠立绘工坊\nAPI Key 由你提供 · 工程保存在所选文件夹\n手动更新：退出后替换应用，工程与设置保留\n测试版 · 尚未通过 Apple 公证")])
    }
    @objc func showWindow() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func startBackend() {
        if service?.isRunning == true, let number = port {
            ready = true
            var url = URLComponents(string: "http://127.0.0.1:\(number)/_desktop/start")!
            url.queryItems = [URLQueryItem(name: "token", value: token)]
            web.load(URLRequest(url: url.url!)); return
        }
        guard service?.isRunning != true else { return }
        ready = false; port = nil; output = Data(); status.stringValue = "正在启动作图工坊…"; status.isHidden = false; retry.isHidden = true; web.isHidden = true
        do {
            try FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
            let child = Process()
            child.executableURL = Bundle.main.resourceURL!.appendingPathComponent("backend/studio-service")
            child.currentDirectoryURL = dataDirectory
            var env: [String: String] = ["PATH":"/usr/bin:/bin:/usr/sbin:/sbin", "HOME":NSHomeDirectory(), "TMPDIR":NSTemporaryDirectory(), "LANG":"zh_CN.UTF-8", "STUDIO_DATA_DIR":dataDirectory.path, "STUDIO_DESKTOP_TOKEN":token]
            // CLI users may explicitly provide their own key; Finder launches need none.
            for name in ["STUDIO_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"] {
                if let value = ProcessInfo.processInfo.environment[name] { env[name] = value }
            }
            child.environment = env
            let pipe = Pipe(); child.standardOutput = pipe; child.standardError = FileHandle.nullDevice
            pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let bytes = handle.availableData
                if bytes.isEmpty { handle.readabilityHandler = nil; return }
                DispatchQueue.main.async { self?.receive(bytes) }
            }
            child.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
                guard let self, !self.quitting else { return }
                self.fail("本地服务已停止。已保存的工程仍在原文件夹，请重新启动。")
            }}
            service = child; try child.run()
            startupTimer?.invalidate()
            startupTimer = Timer.scheduledTimer(withTimeInterval: 45, repeats: false) { [weak self] _ in
                guard let self, !self.ready else { return }
                self.stopBackend(); self.fail("启动超时。请确认应用已完整复制到本机，再重新启动。")
            }
        } catch { fail("无法启动内置服务。请确认应用完整、数据目录可写，再重新启动。") }
    }
    func receive(_ bytes: Data) {
        guard !ready else { return }
        output.append(bytes)
        guard output.count < 65536 else { stopBackend(); fail("内置服务启动异常，请重新安装应用。"); return }
        guard let end = output.firstIndex(of: 10), let object = try? JSONSerialization.jsonObject(with: output[..<end]) as? [String: Int], let number = object["port"], (1...65535).contains(number) else { return }
        port = number; ready = true; startupTimer?.invalidate()
        var url = URLComponents(string: "http://127.0.0.1:\(number)/_desktop/start")!
        url.queryItems = [URLQueryItem(name: "token", value: token)]
        web.load(URLRequest(url: url.url!))
    }
    func fail(_ message: String) { ready = false; startupTimer?.invalidate(); status.stringValue = message; status.isHidden = false; retry.isHidden = false; web.isHidden = true }
    func stopBackend() {
        guard let child = service, child.isRunning else { return }
        child.terminationHandler = nil; child.terminate()
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) { if child.isRunning { kill(child.processIdentifier, SIGKILL) } }
    }
    func isLocal(_ url: URL?) -> Bool { url?.scheme == "http" && url?.host == "127.0.0.1" && url?.port == port }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { status.isHidden = true; retry.isHidden = true; web.isHidden = false }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { if (error as NSError).code != NSURLErrorCancelled { fail("无法打开工作区。请重新启动应用。") } }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload { decisionHandler(.download); return }
        if isLocal(action.request.url) || action.request.url?.scheme == "blob" { decisionHandler(.allow); return }
        if let url = action.request.url, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }
    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) { decisionHandler(response.canShowMIMEType ? .allow : .download) }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if isLocal(action.request.url) { webView.load(action.request) }
        else if let url = action.request.url, ["https", "http"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        return nil
    }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard message.frameInfo.isMainFrame, isLocal(message.frameInfo.request.url), let body = message.body as? [String: Any], let action = body["action"] as? String else { replyHandler(nil, "无效的客户端请求"); return }
        if action == "pickFolder" {
            let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.canCreateDirectories = true
            panel.prompt = "选择文件夹"; panel.message = body["prompt"] as? String ?? "选择工程文件夹"
            if let path = body["directory"] as? String, !path.isEmpty { panel.directoryURL = URL(fileURLWithPath: path) }
            panel.beginSheetModal(for: window) { result in replyHandler(result == .OK ? panel.url?.path ?? "" : "", nil) }
        } else if action == "preference", let key = body["key"] as? String, key.hasPrefix("herogame.studio.session:") || key.hasPrefix("herogame.splitFrames.") {
            var prefs = preferences.dictionary(forKey: "workspacePreferences") ?? [:]
            if let value = body["value"] as? String, value.utf8.count < 200000 { prefs[key] = value } else { prefs.removeValue(forKey: key) }
            preferences.set(prefs, forKey: "workspacePreferences"); replyHandler(true, nil)
        } else if action == "prepareDownload", let id = body["id"] as? String, let filename = body["filename"] as? String {
            guard preparing == nil && downloads.isEmpty else { replyHandler(nil, "另一个文件正在保存，请稍候。"); return }
            preparing = (id, (filename as NSString).lastPathComponent); replyHandler(true, nil)
        } else { replyHandler(nil, "不支持的客户端请求") }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) { let alert = NSAlert(); alert.messageText = message; alert.beginSheetModal(for: window) { _ in completionHandler() } }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) { let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "确认"); alert.addButton(withTitle: "取消"); alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) } }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) { let panel = NSOpenPanel(); panel.allowsMultipleSelection = parameters.allowsMultipleSelection; panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) } }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let key = ObjectIdentifier(download), request = preparing; preparing = nil
        if let id = request?.id { downloadIDs[key] = id }
        let panel = NSSavePanel(); panel.nameFieldStringValue = request?.filename ?? (suggestedFilename as NSString).lastPathComponent
        panel.canCreateDirectories = true; panel.title = "保存导出文件"
        panel.beginSheetModal(for: window) { result in
            guard result == .OK, let destination = panel.url else {
                self.finish(download, saved: false)
                download.delegate = nil // A cancelled panel is not a failed transfer.
                completionHandler(nil); return
            }
            let temp = destination.deletingLastPathComponent().appendingPathComponent(".herostudio-\(UUID().uuidString).download")
            self.downloads[key] = (temp, destination, request?.id); completionHandler(temp)
        }
    }
    func downloadDidFinish(_ download: WKDownload) {
        let key = ObjectIdentifier(download)
        guard let item = downloads[key] else { return }
        do {
            if FileManager.default.fileExists(atPath: item.destination.path) { _ = try FileManager.default.replaceItemAt(item.destination, withItemAt: item.temp) }
            else { try FileManager.default.moveItem(at: item.temp, to: item.destination) }
            finish(download, saved: true)
        } catch { finish(download, saved: false, error: "文件保存失败。请检查目标文件夹的权限和剩余空间后重试。") }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) { finish(download, saved: false, error: "下载中断，原文件未更改。请重新导出。") }
    func finish(_ download: WKDownload, saved: Bool, error: String? = nil) {
        let key = ObjectIdentifier(download)
        if let item = downloads.removeValue(forKey: key) { try? FileManager.default.removeItem(at: item.temp) }
        if let id = downloadIDs.removeValue(forKey: key) {
            let args: [Any] = [id, saved, error as Any? ?? NSNull()]
            if let data = try? JSONSerialization.data(withJSONObject: args), let json = String(data: data, encoding: .utf8) { web.evaluateJavaScript("window.HeroStudioDesktop.finishDownload(...\(json))") }
        } else if let error { let alert = NSAlert(); alert.messageText = error; alert.beginSheetModal(for: window) }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        if !downloads.isEmpty || preparing != nil { let alert = NSAlert(); alert.messageText = "文件仍在保存，请完成或取消保存后再退出。"; alert.runModal(); return .terminateCancel }
        guard ready else { quitting = true; stopBackend(); return .terminateNow }
        web.evaluateJavaScript("window.studioDesktopCloseState ? window.studioDesktopCloseState() : ({busy:false,dirty:false})") { result, error in
            let state = result as? [String: Bool] ?? [:]
            if state["busy"] == true || state["dirty"] == true || error != nil {
                let alert = NSAlert(); alert.messageText = "仍有任务或尚未保存的修改"
                alert.informativeText = "退出会停止本地任务，未保存的修改可能丢失。已经提交的云端请求可能继续计费。"
                alert.addButton(withTitle: "返回工坊"); alert.addButton(withTitle: "退出")
                guard alert.runModal() == .alertSecondButtonReturn else { sender.reply(toApplicationShouldTerminate: false); return }
            }
            self.quitting = true; self.stopBackend(); sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) { quitting = true; stopBackend() }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
}

let app = NSApplication.shared
let delegate = StudioApp()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
