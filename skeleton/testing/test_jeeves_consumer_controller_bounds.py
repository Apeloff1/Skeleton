"""Controller hierarchy contracts for the consumer GGUF planner."""
import unittest

from skeleton.ai.runtime.inference.llama_cpp import _consumer_cgroup_bounds


class ConsumerControllerBoundsTest(unittest.TestCase):
    def evaluate(self, entries, groups):
        def read(path):
            if path not in entries:
                raise FileNotFoundError(path)
            return entries[path]
        return _consumer_cgroup_bounds(32000,16,groups,read)

    def test_nested_v2_tightest_ancestor_and_cpuset(self):
        result = self.evaluate({
            "/test/memory.max":"max",
            "/test/cpu.max":"max 100000",
            "/test/user/memory.max":"12000",
            "/test/user/memory.current":"7000",
            "/test/user/cpu.max":"600000 100000",
            "/test/user/work/memory.max":"8000",
            "/test/user/work/memory.current":"1000",
            "/test/user/work/cpu.max":"300000 100000",
            "/test/user/work/cpuset.cpus.effective":"2-3",
        },{"v2":("/test/user/work","/test")})
        self.assertEqual(result,(5000,2))

    def test_v1_split_mounts_and_unlimited_sentinel(self):
        result=self.evaluate({
            "/mem/memory.limit_in_bytes":str(1<<62),
            "/mem/sub/memory.limit_in_bytes":"3000",
            "/mem/sub/memory.usage_in_bytes":"1000",
            "/cpu/cpu.cfs_quota_us":"-1",
            "/cpu/cpu.cfs_period_us":"100000",
            "/cpu/sub/cpu.cfs_quota_us":"250000",
            "/cpu/sub/cpu.cfs_period_us":"100000",
            "/cpus/sub/cpuset.effective_cpus":"0,4",
        },{"memory":("/mem/sub","/mem"),"cpu":("/cpu/sub","/cpu"),
           "cpuset":("/cpus/sub","/cpus")})
        self.assertEqual(result,(2000,2))

    def test_no_controller_cannot_enlarge_host_bound(self):
        self.assertEqual(self.evaluate({},{}),(32000,16))

    def test_zero_or_exhausted_memory_is_not_ignored(self):
        for cap,used in ((0,0),(100,150)):
            result=self.evaluate({"/test/memory.max":str(cap),
                                  "/test/memory.current":str(used)},
                                 {"v2":("/test","/test")})
            self.assertEqual(result[0],0)

    def test_present_limit_requires_usage(self):
        with self.assertRaises(FileNotFoundError):
            self.evaluate({"/test/memory.max":"1000"},{"v2":("/test","/test")})

    def test_malformed_quota_and_memory_fail_closed(self):
        for values in ({"/test/cpu.max":"5000 0"},
                       {"/test/cpu.max":"-2 100000"},
                       {"/test/memory.max":"wrong"},
                       {"/test/memory.max":"100","/test/memory.current":"-1"}):
            with self.subTest(values=values),self.assertRaises(ValueError):
                self.evaluate(values,{"v2":("/test","/test")})

    def test_wrong_mount_topology_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.evaluate({},{"v2":("/other","/test")})

    def test_fractional_quota_rounds_to_existing_thread_ceiling(self):
        result=self.evaluate({"/test/cpu.max":"150000 100000"},
                             {"v2":("/test","/test")})
        self.assertEqual(result[1],2)


if __name__=="__main__":
    unittest.main()
