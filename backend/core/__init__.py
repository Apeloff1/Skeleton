"""Backend core, sharing the historical namespace with compatibility shims."""
from pkgutil import extend_path

# Backend test/service paths must not hide the migrated core.shift_supervisor
# compatibility package when both repository roots are on sys.path.
__path__ = extend_path(__path__, __name__)
