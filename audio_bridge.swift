// audio_bridge.swift — ScribeOS Audio Bridge
//
// Captures system audio via ScreenCaptureKit and the microphone via AVFoundation,
// mixes them into a single 16 kHz / mono / signed-16-bit PCM stream, and writes
// the raw bytes continuously to stdout so the Python backend can chunk them into
// WAV files for Gemini transcription.
//
// stdin commands (newline-terminated, case-insensitive):
//   MIC_OFF  – silence the microphone channel
//   MIC_ON   – restore the microphone channel
//   QUIT     – stop all capture and exit cleanly
//
// All diagnostic messages are written to stderr so they never pollute the PCM stdout
// stream, and can be captured separately by Python for logging.
//
// ── Compile ───────────────────────────────────────────────────────────────────
//   swiftc audio_bridge.swift -o audio_bridge -framework ScreenCaptureKit
//
// ── Permissions Required (grant once in System Settings) ────────────────────
//   Security & Privacy → Screen Recording  (for ScreenCaptureKit)
//   Security & Privacy → Microphone        (for AVFoundation inputNode)
// ─────────────────────────────────────────────────────────────────────────────

import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia

// MARK: ── Output Format Constants ─────────────────────────────────────────────

private let kSampleRate: Double          = 16_000
private let kChannels:   AVAudioChannelCount = 1

/// The canonical output format shared between the Swift mixer and the Python WAV wrapper.
/// 16 kHz · mono · signed-16-bit PCM · non-interleaved (single channel = trivially interleaved)
private let kOutputFormat: AVAudioFormat = {
    guard let fmt = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: kSampleRate,
        channels: kChannels,
        interleaved: true
    ) else {
        fatalError("[audio_bridge] FATAL: Could not create output AVAudioFormat")
    }
    return fmt
}()

// MARK: ── Thread-Safe Mic Mute State ──────────────────────────────────────────

private let micLock = NSLock()
private var _micMuted: Bool = CommandLine.arguments.contains("--mic-off")

private func micIsMuted() -> Bool {
    micLock.lock(); defer { micLock.unlock() }
    return _micMuted
}

private func setMicMuted(_ v: Bool) {
    micLock.lock()
    _micMuted = v
    micLock.unlock()
}

// MARK: ── I/O Helpers ─────────────────────────────────────────────────────────

/// Writes diagnostic text to stderr (never contaminates the PCM stdout stream).
private func log(_ message: String) {
    fputs("[audio_bridge] \(message)\n", stderr)
}

/// Writes raw bytes directly to stdout, bypassing Swift's buffered print.
private func writeStdout(_ data: Data) {
    data.withUnsafeBytes { ptr in
        _ = Darwin.write(STDOUT_FILENO, ptr.baseAddress!, ptr.count)
    }
}

// MARK: ── AVAudioConverter Cache ──────────────────────────────────────────────
// Creating a new AVAudioConverter is expensive. We cache one converter per
// source format so the same converter is reused across all callbacks.

private final class ConverterCache {
    static let shared = ConverterCache()
    private var cache: [String: AVAudioConverter] = [:]
    private let lock = NSLock()

    func converter(from source: AVAudioFormat) -> AVAudioConverter? {
        let key = "\(source.sampleRate)|\(source.channelCount)|\(source.commonFormat.rawValue)"
        lock.lock(); defer { lock.unlock() }
        if let cached = cache[key] { return cached }
        guard let c = AVAudioConverter(from: source, to: kOutputFormat) else { return nil }
        cache[key] = c
        return c
    }
}

// MARK: ── Audio Conversion ────────────────────────────────────────────────────
// Resamples & converts any AVAudioPCMBuffer to 16 kHz mono Int16 samples.

private func convertToInt16(buffer src: AVAudioPCMBuffer) -> [Int16]? {
    guard src.frameLength > 0 else { return [] }
    guard let converter = ConverterCache.shared.converter(from: src.format) else {
        log("Warning: No converter for format \(src.format)")
        return nil
    }

    // Calculate output capacity with a small headroom for rounding
    let ratio        = kSampleRate / src.format.sampleRate
    let outCapacity  = AVAudioFrameCount(ceil(Double(src.frameLength) * ratio) + 64)
    guard let dst = AVAudioPCMBuffer(pcmFormat: kOutputFormat, frameCapacity: outCapacity) else {
        return nil
    }

    var inputConsumed = false
    var convError: NSError?

    converter.convert(to: dst, error: &convError) { _, outStatus in
        if inputConsumed {
            outStatus.pointee = .noDataNow
            return nil
        }
        inputConsumed        = true
        outStatus.pointee    = .haveData
        return src
    }

    if let e = convError { log("Converter error: \(e.localizedDescription)"); return nil }
    guard let ptr = dst.int16ChannelData else { return nil }
    return Array(UnsafeBufferPointer(start: ptr[0], count: Int(dst.frameLength)))
}

// MARK: ── CMSampleBuffer → AVAudioPCMBuffer ────────────────────────────────────
// ScreenCaptureKit delivers audio as CMSampleBuffer. We bridge it to the
// AVFoundation type that AVAudioConverter understands.

private func avBuffer(from sb: CMSampleBuffer) -> AVAudioPCMBuffer? {
    guard let fmtDesc = CMSampleBufferGetFormatDescription(sb) else { return nil }
    var asbd = CMAudioFormatDescriptionGetStreamBasicDescription(fmtDesc)!.pointee
    guard let fmt = AVAudioFormat(streamDescription: &asbd) else { return nil }

    let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(sb))
    guard let buf  = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: frameCount) else { return nil }
    buf.frameLength = frameCount

    guard CMSampleBufferCopyPCMDataIntoAudioBufferList(
        sb, at: 0, frameCount: Int32(frameCount), into: buf.mutableAudioBufferList
    ) == noErr else { return nil }

    return buf
}

// MARK: ── Audio Mixer ──────────────────────────────────────────────────────────
// Receives Int16 samples from both the system-audio thread and the mic thread,
// then every 100 ms flushes both buffers, mixes them with clamped addition, and
// writes the result as little-endian raw PCM to stdout.

private final class AudioMixer {
    private let queue  = DispatchQueue(label: "scribeos.mixer", qos: .userInteractive)
    private var sysBuf : [Int16] = []
    private var micBuf : [Int16] = []
    private var timer  : DispatchSourceTimer?

    func start() {
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: .milliseconds(100))
        t.setEventHandler { [weak self] in self?.flush() }
        t.resume()
        timer = t
    }

    func stop() { timer?.cancel(); timer = nil }

    func addSystem(_ samples: [Int16]) { queue.async { self.sysBuf.append(contentsOf: samples) } }
    func addMic   (_ samples: [Int16]) { queue.async { self.micBuf.append(contentsOf: samples) } }

    private func flush() {
        let muted = micIsMuted()
        let n     = muted ? sysBuf.count : max(sysBuf.count, micBuf.count)
        guard n > 0 else { return }

        var out = [Int16]()
        out.reserveCapacity(n)
        for i in 0 ..< n {
            let s = i < sysBuf.count ? Int32(sysBuf[i]) : 0
            let m = (!muted && i < micBuf.count) ? Int32(micBuf[i]) : 0
            // Clamped addition prevents hard clipping when both sources are loud
            out.append(Int16(clamping: s + m))
        }

        sysBuf.removeAll(keepingCapacity: true)
        micBuf.removeAll(keepingCapacity: true) // always drain mic to prevent unbounded growth

        // Write as native little-endian Int16 bytes (Apple Silicon & Intel are both LE)
        let raw = out.withUnsafeBytes { Data($0) }
        writeStdout(raw)
    }
}

// MARK: ── System Audio Capture (ScreenCaptureKit) ─────────────────────────────

@available(macOS 13.0, *)
private final class SystemAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    private var scStream: SCStream?
    let mixer: AudioMixer

    init(mixer: AudioMixer) { self.mixer = mixer }

    func start() async throws {
        // SCShareableContent.excludingDesktopWindows triggers the Screen Recording
        // permission prompt on first run if permission has not been granted yet.
        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: false
        )
        guard let display = content.displays.first else {
            throw NSError(domain: "ScribeOS", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "No display found for ScreenCaptureKit"])
        }

        let cfg = SCStreamConfiguration()
        cfg.capturesAudio               = true
        cfg.excludesCurrentProcessAudio = true  // avoids capturing our own stderr echo
        cfg.sampleRate                  = Int(kSampleRate)  // request 16 kHz output
        cfg.channelCount                = 1                 // request mono output

        // SCStream requires a video configuration even for audio-only capture.
        // We set an minimal 2 × 2 px viewport at 1 fps to stay near-zero CPU.
        cfg.width                   = 2
        cfg.height                  = 2
        cfg.minimumFrameInterval    = CMTime(value: 1, timescale: 1) // 1 fps

        // Capture audio from the entire display (all application audio)
        let filter = SCContentFilter(
            display: display,
            excludingApplications: [],
            exceptingWindows: []
        )

        let stream = SCStream(filter: filter, configuration: cfg, delegate: self)
        try stream.addStreamOutput(
            self, type: .audio,
            sampleHandlerQueue: DispatchQueue(label: "scribeos.sysaudio", qos: .userInteractive)
        )
        try await stream.startCapture()
        scStream = stream
        log("System audio capture started via ScreenCaptureKit (16 kHz mono)")
    }

    func stop() {
        Task { try? await scStream?.stopCapture(); scStream = nil }
    }

    // SCStreamOutput — called on the sampleHandlerQueue for every audio buffer
    func stream(_ stream: SCStream,
                didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio                          else { return }
        guard let avBuf  = avBuffer(from: sampleBuffer) else { return }
        guard let pcm16  = convertToInt16(buffer: avBuf)  else { return }
        mixer.addSystem(pcm16)
    }

    // SCStreamDelegate — called when the stream ends unexpectedly
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("SCStream stopped unexpectedly: \(error.localizedDescription)")
    }
}

// MARK: ── Microphone Capture (AVFoundation) ───────────────────────────────────

private final class MicCapture {
    private let engine = AVAudioEngine()
    let mixer: AudioMixer

    init(mixer: AudioMixer) { self.mixer = mixer }

    func start() throws {
        let inputNode = engine.inputNode

        // Capture `mixer` directly (strong reference) so this closure keeps
        // delivering audio even if the enclosing MicCapture object is released.
        let capturedMixer = self.mixer

        // Pass nil as the format — AVAudioEngine uses the hardware's native format
        // directly. Querying outputFormat(forBus: 0) BEFORE engine.start() can
        // return a zero-Hz invalid format on some macOS versions, which causes
        // AVAudioConverter creation to fail and mic audio to be silently dropped.
        inputNode.installTap(onBus: 0, bufferSize: 4096, format: nil) { buf, _ in
            guard !micIsMuted()                            else { return }
            guard let pcm16 = convertToInt16(buffer: buf) else { return }
            capturedMixer.addMic(pcm16)
        }
        try engine.start()
        log("Microphone capture started via AVFoundation (\(inputNode.outputFormat(forBus: 0).sampleRate) Hz, \(inputNode.outputFormat(forBus: 0).channelCount) ch)")
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }
}

// MARK: ── Microphone Permission ───────────────────────────────────────────────

private func requestMicrophonePermission() async -> Bool {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized:
        return true
    case .notDetermined:
        return await AVCaptureDevice.requestAccess(for: .audio)
    default:
        log("Microphone access denied — grant it in System Settings › Privacy & Security › Microphone")
        return false
    }
}

// MARK: ── stdin Command Listener ──────────────────────────────────────────────
// Runs on a dedicated background thread so it never blocks the main run loop.
// Python writes MIC_OFF / MIC_ON / QUIT to the bridge's stdin for real-time control.

private func startStdinListener() {
    Thread {
        while let line = readLine(strippingNewline: true) {
            switch line.uppercased().trimmingCharacters(in: .whitespaces) {
            case "MIC_OFF":
                setMicMuted(true)
                log("Mic muted via stdin command")
            case "MIC_ON":
                setMicMuted(false)
                log("Mic unmuted via stdin command")
            case "QUIT":
                log("QUIT received — shutting down")
                exit(0)
            default:
                break
            }
        }
    }.start()
}

// MARK: ── Global Object Retention (ARC fix) ─────────────────────────────────
// Swift's ARC deallocates Task { } local variables when the Task body finishes.
// These globals keep the capture objects alive for the entire process lifetime.
private var _gMixer     : AudioMixer?
private var _gSysCapture: AnyObject?   // SystemAudioCapture (typed as AnyObject to allow @available guard)
private var _gMicCapture: MicCapture?

// MARK: ── Entry Point ─────────────────────────────────────────────────────────

if #available(macOS 13.0, *) {
    Task {
        let mixer = AudioMixer()
        _gMixer = mixer          // Pin to global — survives Task body completion
        mixer.start()
        startStdinListener()

        // ── System audio via ScreenCaptureKit ──
        let sysCapture = SystemAudioCapture(mixer: mixer)
        _gSysCapture = sysCapture  // Pin to global
        do {
            try await sysCapture.start()
        } catch {
            log("ScreenCaptureKit unavailable: \(error.localizedDescription)")
            log("→ Open System Settings › Privacy & Security › Screen Recording")
            log("→ Enable your Terminal (or this binary) and re-run. Continuing without system audio.")
        }

        // ── Microphone via AVFoundation ──
        let micOK = await requestMicrophonePermission()
        if micOK {
            let mic = MicCapture(mixer: mixer)
            _gMicCapture = mic   // Pin to global — prevents [weak self] from going nil in the tap
            do {
                try mic.start()
            } catch {
                log("Microphone capture failed: \(error.localizedDescription)")
            }
        }

        log("ScribeOS Audio Bridge is active.")
        log("Streaming 16 kHz · mono · Int16 PCM → stdout")
        log("Send MIC_OFF / MIC_ON / QUIT to stdin to control.")
    }

    // Hand control to the main run loop so DispatchSource timers and SCStream
    // callbacks continue to fire indefinitely.
    RunLoop.main.run()

} else {
    fputs("[audio_bridge] FATAL: macOS 13.0 (Ventura) or later is required.\n", stderr)
    exit(1)
}
