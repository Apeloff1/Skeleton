"""The offline LocalAPI has one implementation class, not duplicate facades."""
from skeleton.ai.runtime.production_fabric.product import api, cli, dispatcher


def test_local_api_facade_and_cli_share_dispatcher_class_identity():
    assert api.LocalAPI is dispatcher.LocalAPI
    assert cli.LocalAPI is dispatcher.LocalAPI


def test_compatibility_api_does_not_define_a_second_execution_class():
    assert api.__all__ == ["LocalAPI"]
    assert api.LocalAPI.__module__ == dispatcher.__name__
