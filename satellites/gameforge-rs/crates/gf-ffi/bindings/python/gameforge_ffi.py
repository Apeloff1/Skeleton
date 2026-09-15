from __future__ import annotations
import ctypes
import json
from pathlib import Path
from typing import Any

class _Lib:
    def __init__(self,path:str|Path)->None:
        lib=ctypes.CDLL(str(path));lib.gf_zaibatsu_create.restype=ctypes.c_void_p;lib.gf_zaibatsu_create.argtypes=[];lib.gf_zaibatsu_destroy.restype=None;lib.gf_zaibatsu_destroy.argtypes=[ctypes.c_void_p];lib.gf_free_string.restype=None;lib.gf_free_string.argtypes=[ctypes.c_void_p]
        def json_fn(name:str,argtypes:list)->None:
            fn=getattr(lib,name);fn.restype=ctypes.c_void_p;fn.argtypes=argtypes
        c=ctypes.c_char_p
        json_fn("gf_propose",[ctypes.c_void_p,c,c,c,c,c]);json_fn("gf_fabric_tail",[ctypes.c_void_p,c,ctypes.c_uint32]);json_fn("gf_legion_found",[ctypes.c_void_p,c,c]);json_fn("gf_legion_enlist",[ctypes.c_void_p,c,c]);json_fn("gf_swarm_submit",[ctypes.c_void_p,c,c,c,c]);json_fn("gf_swarm_wave",[ctypes.c_void_p]);json_fn("gf_governance_decide",[ctypes.c_void_p,c,c,ctypes.c_uint32]);json_fn("gf_cognition_hold",[ctypes.c_void_p,c,ctypes.c_bool]);json_fn("gf_cognition_testify",[ctypes.c_void_p,c,c,ctypes.c_bool,ctypes.c_double]);json_fn("gf_status",[ctypes.c_void_p]);lib.gf_fabric_seq.restype=ctypes.c_uint64;lib.gf_fabric_seq.argtypes=[ctypes.c_void_p];lib.gf_lafs_put.restype=ctypes.c_void_p;lib.gf_lafs_put.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t];self.lib=lib
    def call_json(self,name:str,*args:Any)->Any:
        ptr=getattr(self.lib,name)(*args)
        if not ptr: raise RuntimeError(f"{name} returned null")
        try: out=json.loads(ctypes.cast(ptr,ctypes.c_char_p).value.decode("utf-8"))
        finally:self.lib.gf_free_string(ptr)
        if isinstance(out,dict) and "error" in out:raise RuntimeError(out["error"])
        return out

def _b(s:str)->bytes:return s.encode("utf-8")
class Zaibatsu:
    def __init__(self,library_path:str|Path)->None:self._lib=_Lib(library_path);self._h=self._lib.lib.gf_zaibatsu_create();
    def close(self)->None:
        if self._h:self._lib.lib.gf_zaibatsu_destroy(self._h);self._h=None
    def __enter__(self)->"Zaibatsu":return self
    def __exit__(self,*_:Any)->None:self.close()
    def propose(self,ledger:str,kind:str,proposal_id:str,attester:str,value:Any)->dict:return self._lib.call_json("gf_propose",self._h,_b(ledger),_b(kind),_b(proposal_id),_b(attester),_b(json.dumps(value)))
    def fabric_tail(self,ledger:str,limit:int=128)->list:return self._lib.call_json("gf_fabric_tail",self._h,_b(ledger),limit)
    def fabric_seq(self)->int:return self._lib.lib.gf_fabric_seq(self._h)
    def found_legion(self,name:str,motto:str)->dict:return self._lib.call_json("gf_legion_found",self._h,_b(name),_b(motto))
    def enlist(self,legion:str,capability:str)->str:return self._lib.call_json("gf_legion_enlist",self._h,_b(legion),_b(capability))["member_id"]
    def submit_task(self,task_id:str,capability:str,payload:Any,deps:list[str]|None=None)->dict:return self._lib.call_json("gf_swarm_submit",self._h,_b(task_id),_b(capability),_b(json.dumps(payload)),_b(json.dumps(deps or [])))
    def ready_wave(self)->list:return self._lib.call_json("gf_swarm_wave",self._h)
    def decide(self,domain:str,action:str,actor_weight:int=0)->dict:return self._lib.call_json("gf_governance_decide",self._h,_b(domain),_b(action),actor_weight)
    def hold_belief(self,predicate:str,polarity:bool)->str:return self._lib.call_json("gf_cognition_hold",self._h,_b(predicate),polarity)["belief_id"]
    def testify(self,belief_id:str,witness:str,supports:bool,weight:float=0.5)->float:return self._lib.call_json("gf_cognition_testify",self._h,_b(belief_id),_b(witness),supports,weight)["confidence"]
    def put_chunk(self,data:bytes)->str:return self._lib.call_json("gf_lafs_put",self._h,data,len(data))["digest"]
    def status(self)->dict:return self._lib.call_json("gf_status",self._h)
