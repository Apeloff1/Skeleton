from __future__ import annotations
import hashlib,pytest
from skeleton.plugins.lifecycle import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
M=PluginManifest("PLUGIN.1",S("pkg"),frozenset({"search"}),frozenset({"read"}),3)
G=PluginGrant("PLUGIN.1",frozenset({"read"}),S("grant"))
def test_activation_requires_compatible_explicit_grant():assert PluginLifecycle(M).activate(G,{3}).state is PluginState.ACTIVE
def test_plugin_cannot_expand_declared_permissions():
 with pytest.raises(PluginError,match="permission"):PluginLifecycle(M).activate(PluginGrant("PLUGIN.1",frozenset({"write"}),S("g")),{3})
def test_incompatible_plugin_fails_closed():
 with pytest.raises(PluginError,match="incompatible"):PluginLifecycle(M).activate(G,{2})
def test_disable_preserves_manifest_without_core_mutation():x=PluginLifecycle(M).activate(G,{3}).disable();assert x.state is PluginState.DISABLED and x.manifest==M
def test_removed_plugin_cannot_reactivate():
 x=PluginLifecycle(M).remove()
 with pytest.raises(PluginError,match="removed"):x.activate(G,{3})