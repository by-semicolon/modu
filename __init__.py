import os
import traceback
import typing
import inspect
import json


def _get_config() -> dict:
    with open(os.path.join(os.path.dirname(__file__), "config.json")) as file2:
        config: dict = json.load(file2)
    return config

REVERSE_SCRIPT_TYPES: dict[str, str] = _get_config()["fileExtensions"]

class _Script:
    def __init__(self, name: str, obj: typing.Any) -> None:
        self.name: str = name
        self.__obj: typing.Any = obj
    @classmethod
    def fromSource(cls, path: str, name: str, source: str, context: dict[str, typing.Any]) -> "_Script":
        ...
    def get(self) -> typing.Any:
        return self.__obj
    def __call__(self, *args, **kwargs):
        return self.__obj(*args, **kwargs)
class FunctionScript(_Script):
    @classmethod
    def fromSource(cls, path: str, name: str, source: str, context: dict[str, typing.Any]) -> "FunctionScript":
        fn = lambda *args, **kwargs: exec(source, context | kwargs | {"args": args})
        fn.__name__ = name
        return cls(name, fn)

class ClassScript(_Script):
    @classmethod
    def fromSource(cls, path: str, name: str, source: str, context: dict[str, typing.Any]) -> "ClassScript":
        exec(f"class {name}(cls if 'cls' in globals() else object):\n    ...\n{'\n'.join(['    '+line for line in source.split('\n')])}", context)
        context.pop("cls") if "cls" in context else ...
        return cls(name, context[name])

class VariableScript(_Script):
    @classmethod
    def fromSource(cls, path: str, name: str, source: str, context: dict[str, typing.Any]) -> "VariableScript":
        return cls(name, FunctionScript.fromSource(path, name, source, context)())

class ClassInstanceScript(_Script):
    @classmethod
    def fromSource(cls, path: str, name: str, source: str, context: dict[str, typing.Any]) -> "ClassInstanceScript":
        inst: cls = cls(name, eval(f"cls({source})", {} | context))
        context.pop("cls") if "cls" in context else ...
        return inst

SCRIPT_TYPES: dict[str, typing.Any] = {v: globals()[k] for k, v in REVERSE_SCRIPT_TYPES.items()}

def _get_importer_globals() -> dict:
    for i in range(20):
        try:
            caller_frame = inspect.stack()[i].frame
        except IndexError:
            break
        importer_globals = caller_frame.f_globals
        ignore: list[str] = _get_config()["autoFindImporter"]["ignoreFiles"]
        if "__file__" not in importer_globals:
            continue
        if os.path.basename(importer_globals["__file__"]) in [
            os.path.basename(__file__),
            *ignore
        ]:
            continue
        return importer_globals

def load(*scripts: str, to: dict | None = None, directory: str | None = None, here: str | None = None, script_names: str = "{name}") -> dict:
    to = to or _get_importer_globals()
    if not to:
        raise FileNotFoundError(f"could not find importer automatically. you can 'to=globals()' to 'modu.load()' to fix this issue.")
    directory = (directory if directory else (to["__scripts__"] if "__scripts__" in to else "{filename}.scripts")).format(filename=os.path.basename(here or to["__file__"]).removesuffix(".py"))
    for path in os.listdir(directory):
        path = os.path.abspath(os.path.join(directory, path))
        extension: str | None = None
        for extension2 in SCRIPT_TYPES:
            if path.endswith(extension2):
                extension = extension2
                break
        if extension is not None:
            name: str = os.path.basename(path).removesuffix(extension)
            if scripts and name not in scripts:
                continue
            global_context_path: str = os.path.join(os.path.dirname(path), _get_config()["contextFile"]["globalFileName"])
            local_context_path: str = path.removesuffix(extension) + _get_config()["contextFile"]["localExtension"]
            context: dict = {}
            for context_path in [global_context_path, local_context_path]:
                if os.path.exists(context_path):
                    with open(context_path) as context_file:
                        context_source: str = context_file.read()
                    context = {
                        "load": load,
                        "make": lambda script: load(script, to=context, directory=directory, here=here, script_names="cls"),
                        "__file__": context_path, "__scripts__": "."
                    } | context
                    exec(context_source, context)
                    del context["load"], context["make"]
            with open(path) as file:
                source: str = file.read()
            to |= {script_names.format(name=name): SCRIPT_TYPES[extension].fromSource(path, name, source, context).get()}
    return to

if _get_config()["autoLoadScriptsOnImport"]:
    load()