"""
Config schema for local AI. JSON schema for adapter, LoRA, clipped-G, and bridge CAS.
"""
SCHEMA = {
    "type": "object",
    "properties": {
        "lora_rank": {"type": "integer", "minimum": 1, "maximum": 64},
        "clip_factor": {"type": "number", "minimum": 1.0, "maximum": 1.1},
        "cas_min_length": {"type": "integer", "minimum": 16}
    },
    "required": ["lora_rank", "clip_factor"]
}
