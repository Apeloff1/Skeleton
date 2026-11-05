// Four independent, bounded Metal memory synchronization qualifications.
// Actual Apple GPU work only, never evidence for llama.cpp's own allocations.
import Foundation
import Metal
import CryptoKit

func issue(_ reason: String) -> Never {
    let record: [String: Any] = [
        "schema": "skeleton.apple.metal-multisync.v2",
        "passed": false, "reason": reason,
        "model_tensor_fence_verified": false,
        "llama_kv_cache_fence_verified": false,
    ]
    if let bytes = try? JSONSerialization.data(withJSONObject: record,
                                                options: [.sortedKeys]),
       let output = String(data: bytes, encoding: .utf8) {
        print(output)
    }
    exit(1)
}

guard #available(macOS 11.0, *) else { issue("unsupported_macos") }
guard let device = MTLCreateSystemDefaultDevice(), device.hasUnifiedMemory else {
    issue("unified_metal_device_unavailable")
}
guard let queueA = device.makeCommandQueue(),
      let queueB = device.makeCommandQueue() else {
    issue("metal_command_queues_unavailable")
}

let source = """
#include <metal_stdlib>
using namespace metal;
kernel void skeleton_probe(device const uint *input [[buffer(0)]],
                           device uint *output [[buffer(1)]],
                           uint index [[thread_position_in_grid]]) {
    if (index < 64) {
        output[index] = (input[index] ^ uint(0x5a17b3e2)) + index;
    }
}
"""
let library: MTLLibrary
do { library = try device.makeLibrary(source: source, options: nil) }
catch { issue("metal_library_compilation_failed") }
guard let function = library.makeFunction(name: "skeleton_probe") else {
    issue("metal_kernel_missing")
}
let pipeline: MTLComputePipelineState
do { pipeline = try device.makeComputePipelineState(function: function) }
catch { issue("metal_pipeline_unavailable") }

let count = 64
let bytes = count * MemoryLayout<UInt32>.stride
let threads = MTLSize(
    width: min(count, pipeline.maxTotalThreadsPerThreadgroup),
    height: 1, depth: 1
)
let grid = MTLSize(width: count, height: 1, depth: 1)
func sharedBuffer() -> MTLBuffer {
    guard let buffer = device.makeBuffer(length: bytes, options: .storageModeShared),
          buffer.storageMode == .shared else {
        issue("native_shared_buffer_unavailable")
    }
    return buffer
}
func submit(_ command: MTLCommandBuffer, _ input: MTLBuffer, _ output: MTLBuffer) {
    guard let encoder = command.makeComputeCommandEncoder() else {
        issue("metal_compute_encoder_unavailable")
    }
    encoder.setComputePipelineState(pipeline)
    encoder.setBuffer(input, offset: 0, index: 0)
    encoder.setBuffer(output, offset: 0, index: 1)
    encoder.dispatchThreads(grid, threadsPerThreadgroup: threads)
    encoder.endEncoding()
}
func fill(_ input: MTLBuffer, seed: Int) {
    let values = input.contents().bindMemory(to: UInt32.self, capacity: count)
    for i in 0..<count {
        values[i] = UInt32(seed * 100_003 + i * 97)
    }
}
func transform(_ source: UInt32, _ i: Int) -> UInt32 {
    return (source ^ UInt32(0x5a17b3e2)) &+ UInt32(i)
}
var hasher = SHA256()
var verified = 0
func check(_ output: MTLBuffer, seed: Int, depth: Int) {
    let values = output.contents().bindMemory(to: UInt32.self, capacity: count)
    for i in 0..<count {
        var expected = UInt32(seed * 100_003 + i * 97)
        for _ in 0..<depth { expected = transform(expected, i) }
        if values[i] != expected {
            issue("metal_multisync_output_mismatch")
        }
        var little = values[i].littleEndian
        withUnsafeBytes(of: &little) { hasher.update(bufferPointer: $0) }
        verified += 1
    }
}
func ensureCompleted(_ command: MTLCommandBuffer) {
    command.waitUntilCompleted()
    guard command.status == .completed else {
        issue("metal_command_buffer_incomplete")
    }
}
var completed = 0

// Mode 1: repeated CPU-write -> GPU-execute -> CPU-readback with one queue.
// Inputs are rewritten ONLY after the previous GPU command has completed.
let serialIn = sharedBuffer()
let serialOut = sharedBuffer()
for pass in 0..<4 {
    fill(serialIn, seed: pass)
    guard let command = queueA.makeCommandBuffer() else {
        issue("serial_command_allocation_failed")
    }
    submit(command, serialIn, serialOut)
    command.commit()
    ensureCompleted(command)
    completed += 1
    check(serialOut, seed: pass, depth: 1)
}

// Mode 2: two independent GPU queues and an explicit device-local MTLEvent.
// Producer writes a staging allocation. Consumer waits for the signal before
// using it. Merely committing commands in order is not a completion fence.
guard let event = device.makeEvent() else {
    issue("device_metal_event_unavailable")
}
let relayIn = sharedBuffer()
let relayStage = sharedBuffer()
let relayOut = sharedBuffer()
var eventHandoffs = 0
for pass in 0..<4 {
    fill(relayIn, seed: 100 + pass)
    guard let producer = queueA.makeCommandBuffer(),
          let consumer = queueB.makeCommandBuffer() else {
        issue("cross_queue_command_allocation_failed")
    }
    submit(producer, relayIn, relayStage)
    producer.encodeSignalEvent(event, value: UInt64(pass + 1))
    consumer.encodeWaitForEvent(event, value: UInt64(pass + 1))
    submit(consumer, relayStage, relayOut)
    producer.commit()
    consumer.commit()
    ensureCompleted(consumer)
    ensureCompleted(producer)
    completed += 2
    eventHandoffs += 1
    check(relayOut, seed: 100 + pass, depth: 2)
}

// Mode 3: independent triple-buffered lanes submitted concurrently.
// No CPU writes/reads race with GPU work; results are checked only after
// all three separate command buffers have reached completed status.
var lanes: [(MTLBuffer, MTLBuffer, MTLCommandBuffer)] = []
for lane in 0..<3 {
    let input = sharedBuffer()
    let output = sharedBuffer()
    fill(input, seed: 200 + lane)
    guard let command = (lane % 2 == 0 ? queueA : queueB).makeCommandBuffer() else {
        issue("parallel_lane_command_allocation_failed")
    }
    submit(command, input, output)
    lanes.append((input, output, command))
}
for lane in lanes { lane.2.commit() }
for lane in lanes { ensureCompleted(lane.2) }
completed += lanes.count
for lane in 0..<lanes.count {
    check(lanes[lane].1, seed: 200 + lane, depth: 1)
}

// Mode 4: a real MTLSharedEvent is GPU-signaled, observed by the CPU after
// command completion, and advanced monotonically across repeated handoffs.
// This does not test interprocess synchronization or model-owned allocations.
guard let sharedEvent = device.makeSharedEvent() else {
    issue("cpu_visible_metal_shared_event_unavailable")
}
let callbackQueue = DispatchQueue(label: "skeleton.metal.multisync.cpu")
let listener = MTLSharedEventListener(dispatchQueue: callbackQueue)
let sharedIn = sharedBuffer()
let sharedOut = sharedBuffer()
var sharedObservations = 0
for pass in 0..<2 {
    fill(sharedIn, seed: 300 + pass)
    let requestedSignal = UInt64(pass * 2 + 1)
    let cpuAcknowledgement = requestedSignal + 1
    let callbackFinished = DispatchSemaphore(value: 0)
    // CPU callback becomes the *only* actor authorized to advance from
    // odd GPU signal to even CPU acknowledgement in this probe.
    sharedEvent.notify(listener, atValue: requestedSignal) { event, value in
        if value >= requestedSignal {
            event.signaledValue = cpuAcknowledgement
            callbackFinished.signal()
        }
    }
    guard let command = queueB.makeCommandBuffer() else {
        issue("shared_event_command_allocation_failed")
    }
    submit(command, sharedIn, sharedOut)
    command.encodeSignalEvent(sharedEvent, value: requestedSignal)
    // GPU completion is gated on a CPU-side event callback. This is a
    // genuine bidirectional handshake, not an after-the-fact observation.
    command.encodeWaitForEvent(sharedEvent, value: cpuAcknowledgement)
    command.commit()
    guard callbackFinished.wait(timeout: .now() + .seconds(15)) == .success else {
        issue("metal_shared_event_cpu_callback_timeout")
    }
    ensureCompleted(command)
    guard sharedEvent.signaledValue >= cpuAcknowledgement else {
        issue("cpu_shared_event_acknowledgement_missing")
    }
    completed += 1
    sharedObservations += 1
    check(sharedOut, seed: 300 + pass, depth: 1)
}

let outputSHA = hasher.finalize().map { String(format: "%02x", $0) }.joined()
let receipt: [String: Any] = [
    "schema": "skeleton.apple.metal-multisync.v2",
    "passed": true,
    "shared_metal_buffers": 13,
    "synchronized_command_buffers": completed,
    "verified_values": verified,
    "serial_cpu_gpu_cpu_round_trips": 4,
    "cross_queue_event_handoffs": eventHandoffs,
    "parallel_independent_lanes": lanes.count,
    "shared_event_cpu_observations": sharedObservations,
    "shared_event_cpu_acknowledgements": sharedObservations,
    "output_sha256": outputSHA,
    "model_tensor_fence_verified": false,
    "llama_kv_cache_fence_verified": false,
]
guard let data = try? JSONSerialization.data(
    withJSONObject: receipt, options: [.sortedKeys]
), let line = String(data: data, encoding: .utf8) else {
    issue("metal_multisync_receipt_encoding_failed")
}
print(line)
