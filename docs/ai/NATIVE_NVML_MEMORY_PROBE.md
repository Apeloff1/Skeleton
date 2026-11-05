# Native Linux NVIDIA memory discovery

`probe_linux_nvidia_memory()` queries the installed NVML native library
through ctypes. It does not import a hosted provider SDK, open a CUDA context
or load a model. The receipt exposes measured free bytes per GPU for canonical
`DeviceDescriptor` placement inputs. A missing driver, malformed ABI result,
unsupported platform or failed initialization is explicitly unavailable,
never a simulated healthy GPU.

The device IDs are transient NVML indices, not stable cross-reboot hardware
identities. Free memory is a sampled placement hint, not a reservation;
consumers must still enforce actual allocation and runtime admission.
GPU temperature, power, WDDM shared memory, Apple Metal and ROCm are not
measured by this probe. Device qualification remains separate.

Tests in `skeleton/testing/test_nvml_memory_probe.py` use a labeled
simulated ABI and one platform-gated live probe. Simulated results are never
presented as real hardware measurements.
