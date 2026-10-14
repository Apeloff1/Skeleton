"""Lazy index for telemetry. Does not import 640 modules."""
from pathlib import Path
INDEX = Path(__file__).with_name("INDEX.csv")
def names():
    return [tuple(line.split(",")) for line in INDEX.read_text().splitlines()[1:]]
