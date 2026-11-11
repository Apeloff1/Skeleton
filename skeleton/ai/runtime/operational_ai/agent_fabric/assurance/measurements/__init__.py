"""Content-free registry over exact checked AI-operational evidence counters."""
DOMAINS=frozenset(('model','queue','context','security','persistence','evaluation',
 'retrieval','tooling','transport','deployment','planning','learning'))
def measure(domain,name,observations):
    if type(domain) is not str or domain not in DOMAINS or type(name) is not str or not name.isidentifier():
        raise ValueError('unknown measurement domain or name')
    if domain == "context":
        from . import context as group
    elif domain == "deployment":
        from . import deployment as group
    elif domain == "evaluation":
        from . import evaluation as group
    elif domain == "learning":
        from . import learning as group
    elif domain == "model":
        from . import model as group
    elif domain == "persistence":
        from . import persistence as group
    elif domain == "planning":
        from . import planning as group
    elif domain == "queue":
        from . import queue as group
    elif domain == "retrieval":
        from . import retrieval as group
    elif domain == "security":
        from . import security as group
    elif domain == "tooling":
        from . import tooling as group
    elif domain == "transport":
        from . import transport as group
    else:
        raise ValueError('unknown measurement domain or name')
    return group.measure(name,observations)
