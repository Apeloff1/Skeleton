"""Compile *typed operator plans*, never execute untrusted model-generated code."""
from __future__ import annotations
from .graph import Step,WorkflowGraph,WorkflowError

class PlanCompiler:
    def from_record(self,plan:dict)->WorkflowGraph:
        if not isinstance(plan,dict) or set(plan)!={'schema_version','steps'} or plan['schema_version']!=1:
            raise WorkflowError('unknown workflow plan schema')
        if not isinstance(plan['steps'],list) or len(plan['steps'])>128:
            raise WorkflowError('invalid bounded plan step list')
        steps=[]
        for entry in plan['steps']:
            if not isinstance(entry,dict):raise WorkflowError('plan step not object')
            if set(entry)!={'id','kind','dependencies','input_key','output_key','max_attempts'}:
                raise WorkflowError('unknown or missing plan fields')
            if not isinstance(entry['dependencies'],list):raise WorkflowError('dependencies must be list')
            steps.append(Step(entry['id'],entry['kind'],tuple(entry['dependencies']),
                              entry['input_key'],entry['output_key'],entry['max_attempts']))
        return WorkflowGraph(tuple(steps))

    def offline_chat(self)->WorkflowGraph:
        return WorkflowGraph((
            Step('ground','context',(),'question','compiled_context'),
            Step('infer','infer',('ground',),'compiled_context','generation'),
            Step('verify','verify',('infer',),'generation','verification'),
            Step('persist','persist',('verify',),'verification','receipt')))

    def verify_only(self)->WorkflowGraph:
        return WorkflowGraph((
            Step('verify','verify',(),'generation','verification'),
            Step('persist','persist',('verify',),'verification','receipt')))
