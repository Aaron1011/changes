import pkgutil
import sys


class ModuleProxyCache(dict):
    def __missing__(self, key):
        if not '.' in key:
            return __import__(key)

        module_name, class_name = key.rsplit('.', 1)

        module = __import__(module_name, {}, {}, [class_name], -1)
        handler = getattr(module, class_name)

        # We cache a NoneType for missing imports to avoid repeated lookups
        self[key] = handler

        return handler

_cache = ModuleProxyCache()


def import_string(path):
    """
    Path must be module.path.ClassName

    >>> cls = import_string('sentry.models.Group')
    """
    result = _cache[path]
    return result


def import_submodules(context, root_module, path):
    for loader, module_name, is_pkg in pkgutil.walk_packages(path):
        module = loader.find_module(module_name).load_module(module_name)
        for k, v in vars(module).iteritems():
            if not k.startswith('_'):
                context[k] = v
        sys.modules['{0}.{1}'.format(root_module, module_name)] = module
