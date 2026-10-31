"""In-memory implementation of the edit.ProjectHistoryLike Protocol."""
from dataclasses import dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class Manifest:
    sequence: int
    label: str | None
    content_digest: str
    genre: str = ""


@dataclass(frozen=True)
class Version:
    manifest: Manifest
    files: dict
    sections: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Entry:
    sequence: int
    label: str | None
    content_digest: str
    files: int


class FakeSaver:
    def __init__(self):
        self.store: dict[str, list[Version]] = {}

    def save_files(self, project_id, genre, files, *, sequence=None, label=None, extra_sections=None):
        vs = self.store.setdefault(project_id, [])
        seq = sequence if sequence is not None else len(vs) + 1
        d = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        m = Manifest(seq, label, d, genre)
        vs.append(Version(m, dict(files), dict(extra_sections or {})))
        return m

    def load(self, project_id, *, sequence=None):
        vs = self.store[project_id]
        return vs[-1] if sequence is None else next(v for v in vs if v.manifest.sequence == sequence)


class FakeHistory:
    def __init__(self):
        self.saver = FakeSaver()

    def versions(self, project_id):
        return [Entry(v.manifest.sequence, v.manifest.label, v.manifest.content_digest, len(v.files))
                for v in self.saver.store.get(project_id, [])]

    def find_label(self, project_id, label):
        hits = [e.sequence for e in self.versions(project_id) if e.label == label]
        if not hits:
            raise KeyError(label)
        return hits[-1]

    def label(self, project_id, sequence, label):
        v = self.saver.load(project_id, sequence=sequence)
        return self.saver.save_files(project_id, v.manifest.genre, v.files, label=label)

    def rollback(self, project_id, sequence, *, workspace=None, human_approved=False, authorized=False):
        v = self.saver.load(project_id, sequence=sequence)
        head = self.saver.save_files(project_id, v.manifest.genre, v.files, label=f"rollback-of-{sequence}")
        return {"rolled_back_to": sequence, "new_head": head.sequence,
                "files_match": head.content_digest == v.manifest.content_digest}
