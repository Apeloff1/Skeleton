// Minimal on-device Metal shared-buffer CPU↔GPU synchronization qualification.
// Run only on a consenting Apple Silicon Mac with a local Swift/Metal toolchain.
// Independent of llama.cpp; it proves only this probe's two command buffers.
import Foundation
import Metal
import CryptoKit

func issue(_ reason: String) -> Never {
    // No device paths, source content, or kernel diagnostics in JSON output.
    let safe = reason.replacingOccurrences(of: "\n", with: " ")
    let record: [String: Any] = [
        "schema": "skeleton.apple.metal-shared-fence.v1",
        "passed": false, "reason": safe,
        "model_tensor_fence_verified": false,
        "llama_kv_cache_fence_verified": false,
    ]
    if let bytes = try? JSONSerialization.data(withJSONObject: record,
                                                 options: [.sortedKeys]),
       let line = String(data: bytes, encoding: .utf8) {
        print(line)
    }
    exit(1)
}

guard #available(macOS 11.0, *) else {
    issue("macos_version_unqualified")
}
guard let device = MTLCreateSystemDefaultDevice(), device.hasUnifiedMemory else {
    issue("unified_metal_device_unavailable")
}
guard let queue = device.makeCommandQueue() else {
    issue("native_metal_command_queue_unavailable")
}

let kernel = """
#include <metal_stdlib>
using namespace metal;
kernel void skeleton_probe(device const uint *source [[buffer(0)]],
                           device uint *destination [[buffer(1)]],
                           uint index [[thread_position_in_grid]]) {
    if (index < 64) {
        destination[index] = (source[index] ^ uint(0x5a17b3e2)) + index;
    }
}
"""
let library: MTLLibrary
do {
    library = try device.makeLibrary(source: kernel, options: nil)
} catch {
    issue("metal_kernel_compile_unavailable")
}
guard let function = library.makeFunction(name: "skeleton_probe") else {
    issue("metal_kernel_missing")
}
let pipeline: MTLComputePipelineState
do {
    pipeline = try device.makeComputePipelineState(function: function)
} catch {
    issue("metal_compute_pipeline_unavailable")
}

let elementCount = 64
let byteCount = elementCount * MemoryLayout<UInt32>.stride
guard let input = device.makeBuffer(length: byteCount, options: .storageModeShared),
      let output = device.makeBuffer(length: byteCount, options: .storageModeShared)
else {
    issue("shared_buffers_not_allocated")
}
guard input.storageMode == .shared && output.storageMode == .shared else {
    issue("unexpected_metal_storage_mode")
}
let inputPtr = input.contents().bindMemory(to: UInt32.self, capacity: elementCount)
let outputPtr = output.contents().bindMemory(to: UInt32.self, capacity: elementCount)
var completed = 0
var hasher = SHA256()
for pass in 0..<2 {
    // CPU changes are written before GPU command-buffer submission.
    for index in 0..<elementCount {
        inputPtr[index] = UInt32(pass * 100_003 + index * 97)
        outputPtr[index] = 0
    }
    guard let command = queue.makeCommandBuffer(),
          let encoder = command.makeComputeCommandEncoder()
    else {
        issue("metal_command_buffer_creation_failed")
    }
    encoder.setComputePipelineState(pipeline)
    encoder.setBuffer(input, offset: 0, index: 0)
    encoder.setBuffer(output, offset: 0, index: 1)
    encoder.dispatchThreads(
        MTLSize(width: elementCount, height: 1, depth: 1),
        threadsPerThreadgroup: MTLSize(width: min(elementCount, pipeline.maxTotalThreadsPerThreadgroup),
                                      height: 1, depth: 1)
    )
    encoder.endEncoding()
    command.commit()
    command.waitUntilCompleted()
    guard command.status == .completed else {
        issue("metal_command_buffer_did_not_complete")
    }
    for index in 0..<elementCount {
        let expected = (inputPtr[index] ^ UInt32(0x5a17b3e2)) &+ UInt32(index)
        guard outputPtr[index] == expected else {
            issue("metal_shared_buffer_coherence_mismatch")
        }
        var value = outputPtr[index].littleEndian
        withUnsafeBytes(of: &value) { hasher.update(bufferPointer: $0) }
    }
    completed += 1
}
let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
let record: [String: Any] = [
    "schema": "skeleton.apple.metal-shared-fence.v1",
    "passed": true,
    "shared_metal_buffers": 2,
    "synchronized_command_buffers": completed,
    "verified_values": elementCount * completed,
    "output_sha256": digest,
    "model_tensor_fence_verified": false,
    "llama_kv_cache_fence_verified": false,
]
guard let bytes = try? JSONSerialization.data(withJSONObject: record,
                                               options: [.sortedKeys]),
      let line = String(data: bytes, encoding: .utf8)
else {
    issue("qualification_receipt_encoding_failed")
}
print(line)
