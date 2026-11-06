"""Content-free registry over exact checked AI-operational evidence counters."""
from importlib import import_module
DOMAINS=frozenset(('model','queue','context','security','persistence','evaluation',
 'retrieval','tooling','transport','deployment','planning','learning'))
_DOMAIN_LOADERS = {
    "model": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.model"),
    "queue": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.queue"),
    "context": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.context"),
    "security": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.security"),
    "persistence": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.persistence"),
    "evaluation": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation"),
    "retrieval": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.retrieval"),
    "tooling": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.tooling"),
    "transport": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.transport"),
    "deployment": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.deployment"),
    "planning": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.planning"),
    "learning": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning"),
}

def measure(domain,name,observations):
    if domain not in DOMAINS or not isinstance(name,str) or not name.isidentifier():
        raise ValueError('unknown measurement domain or name')
    group=_DOMAIN_LOADERS[domain]()
    return group.measure(name,observations)
