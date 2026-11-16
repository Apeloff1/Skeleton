import pytest
from scripts.provision_semantic_models import CATALOG,_lfs_pointer


def test_reviewed_sources_require_matching_content_pointer():
    profile=CATALOG["bge-small-f32"]
    data=("version https://git-lfs.github.com/spec/v1\noid sha256:"+profile["sha256"]+"\nsize 130000000\n").encode()
    assert _lfs_pointer(data,profile)==130000000
    for bad in (data.replace(profile["sha256"].encode(),b"a"*64),
                data.replace(b"130000000",b"1000000000"),data+b"extra"):
        with pytest.raises(ValueError):_lfs_pointer(bad,profile)
