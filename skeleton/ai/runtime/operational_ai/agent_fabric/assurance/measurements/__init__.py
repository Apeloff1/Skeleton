"""Content-free registry over exact checked AI-operational evidence counters."""
from importlib import import_module
DOMAINS=frozenset(('model','queue','context','security','persistence','evaluation',
 'retrieval','tooling','transport','deployment','planning','learning'))
def measure(domain,name,observations):
    if domain not in DOMAINS or not isinstance(name,str) or not name.isidentifier():
        raise ValueError('unknown measurement domain or name')
    group=import_module(__name__+'.'+domain)
    return group.measure(name,observations)
