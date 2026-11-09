from skeleton.automation.build_patch_bundle import bundle
def test_new_file_changes_bundle_identity():assert bundle("",{}).digest()!=bundle("",{"x.py":"print(1)"}).digest()
