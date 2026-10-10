"""Original hardware-adaptation kernels; pure, bounded, offline and deterministic.

These functions convert *authored* game data. They never import or reproduce
commercial game data, bypass a platform SDK, or certify a native release.
See the game-builder rights ledger and release assurance for those gates.
"""

from .bitplanes import (
    PortableCodecError, encode_gb_2bpp, decode_gb_2bpp, encode_nes_2bpp, decode_nes_2bpp, encode_snes_4bpp, decode_snes_4bpp, encode_sms_4bpp, decode_sms_4bpp, encode_genesis_4bpp, decode_genesis_4bpp
)

from .palette import (
    PaletteError, encode_rgb555, decode_rgb555, encode_rgb565, decode_rgb565, encode_rgb332, decode_rgb332, nearest_palette_index, index_image, ordered_luma_dither, contrast_ratio
)

from .audio import (
    AudioKernelError, gameboy_pulse_period, gameboy_pulse_frequency, nes_pulse_timer, sn76489_tone_period, ay38910_tone_period, pulse_pcm, triangle_pcm, noise_lfsr_pcm, adsr_envelope, resample_linear
)

from .input_timing import (
    InputTimingError, frame_schedule, source_frame_at, edge_pressed, edge_released, deadzone_axis, digital_hysteresis, axis_to_eightway, debounce_buttons, button_auto_repeat, remap_buttons
)

from .geometry import (
    GeometryError, walkable_tile_neighbors, bresenham_line, line_of_sight, flood_fill, distance_field, astar_path, rect_intersects, swept_aabb_hit, shelf_pack_rectangles, camera_clamp
)

__all__ = [
    'PortableCodecError',
    'encode_gb_2bpp',
    'decode_gb_2bpp',
    'encode_nes_2bpp',
    'decode_nes_2bpp',
    'encode_snes_4bpp',
    'decode_snes_4bpp',
    'encode_sms_4bpp',
    'decode_sms_4bpp',
    'encode_genesis_4bpp',
    'decode_genesis_4bpp',
    'PaletteError',
    'encode_rgb555',
    'decode_rgb555',
    'encode_rgb565',
    'decode_rgb565',
    'encode_rgb332',
    'decode_rgb332',
    'nearest_palette_index',
    'index_image',
    'ordered_luma_dither',
    'contrast_ratio',
    'AudioKernelError',
    'gameboy_pulse_period',
    'gameboy_pulse_frequency',
    'nes_pulse_timer',
    'sn76489_tone_period',
    'ay38910_tone_period',
    'pulse_pcm',
    'triangle_pcm',
    'noise_lfsr_pcm',
    'adsr_envelope',
    'resample_linear',
    'InputTimingError',
    'frame_schedule',
    'source_frame_at',
    'edge_pressed',
    'edge_released',
    'deadzone_axis',
    'digital_hysteresis',
    'axis_to_eightway',
    'debounce_buttons',
    'button_auto_repeat',
    'remap_buttons',
    'GeometryError',
    'walkable_tile_neighbors',
    'bresenham_line',
    'line_of_sight',
    'flood_fill',
    'distance_field',
    'astar_path',
    'rect_intersects',
    'swept_aabb_hit',
    'shelf_pack_rectangles',
    'camera_clamp'
]
