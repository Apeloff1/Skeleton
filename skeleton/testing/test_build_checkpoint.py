from skeleton.automation.build_checkpoint import BuildCheckpoint
def test_checkpoint_digest_stable(tmp_path):
 c=BuildCheckpoint("a"*40,"g",2,3,"b"*64,"c"*64);assert c.digest()==c.digest();c.write(tmp_path/"c.json");assert (tmp_path/"c.json").is_file()
