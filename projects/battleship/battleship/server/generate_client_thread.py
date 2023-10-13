import ast
import inspect
from pathlib import Path
import subprocess

from tsocket.server import emit, Route, Server

from . import server

emit_imports = [name for name, value in server.__dict__.items() if value is emit]
route_imports = [name for name, value in server.__dict__.items() if value is Route]
server_imports = [name for name, value in server.__dict__.items() if value is Server]
server_clss = {
    name: value
    for name, value in server.__dict__.items()
    if inspect.isclass(inspect.unwrap(value)) and issubclass(value, Server)
}

new_clss = []
required_imports = set()


def add_import_name(node: ast.expr | None):
    match node:
        case ast.Name(id):
            required_imports.add(id)
        case ast.Attribute(value, _):
            add_import_name(value)
        case ast.Subscript(value, slice):
            add_import_name(value)
            add_import_name(slice)


for value in server_clss.values():
    for body_stmt in ast.parse(inspect.getsource(value)).body:
        match body_stmt:
            case ast.ClassDef(bases=bases, body=class_body_stmts):
                abort = True
                for base in bases:
                    match base:
                        case ast.Name(id, ctx=ast.Load()):
                            if id in server_imports or id in server_clss.keys():
                                abort = False
                        case _:
                            abort = True
                            break

                if abort:
                    continue

                body_stmt.name = body_stmt.name.removesuffix("Server") + "ClientThread"

                for base in bases:
                    match base:
                        case ast.Name(id, ctx=ast.Load()):
                            if id in server_imports:
                                base.id = "ClientThread"
                            elif id in server_clss.keys():
                                base.id = (
                                    base.id.removesuffix("Server") + "ClientThread"
                                )

                new_class_body_stmts: list[ast.stmt] = []

                for class_body_stmt in class_body_stmts:
                    match class_body_stmt:
                        case ast.AsyncFunctionDef():
                            for decorator_expr in class_body_stmt.decorator_list:
                                match decorator_expr:
                                    case ast.Name(id, ctx=ast.Load()):
                                        if id in emit_imports:
                                            decorator_expr.id = "subscribe"
                                            class_body_stmt.body = [
                                                ast.Raise(
                                                    ast.Call(
                                                        ast.Name(
                                                            "NotImplementedError",
                                                            ctx=ast.Load(),
                                                        ),
                                                        [],
                                                        [],
                                                    ),
                                                    None,
                                                )
                                            ]
                                            class_body_stmt.args.args.pop(1)
                                            typ = class_body_stmt.args.args.pop(
                                                1
                                            ).annotation
                                            add_import_name(typ)
                                            class_body_stmt.returns = ast.Subscript(
                                                ast.Name("Future", ctx=ast.Load()),
                                                ast.Subscript(
                                                    ast.Name(
                                                        "AbstractContextManager",
                                                        ctx=ast.Load(),
                                                    ),
                                                    ast.Subscript(
                                                        ast.Attribute(
                                                            ast.Name(
                                                                "queue", ctx=ast.Load()
                                                            ),
                                                            "SimpleQueue",
                                                            ctx=ast.Load(),
                                                        ),
                                                        ast.Subscript(
                                                            ast.Name(
                                                                "Future", ctx=ast.Load()
                                                            ),
                                                            typ,
                                                        )
                                                        if typ is not None
                                                        else ast.Name(
                                                            "Future", ctx=ast.Load()
                                                        ),
                                                    ),
                                                ),
                                            )
                                            new_class_body_stmts.append(
                                                ast.FunctionDef(
                                                    class_body_stmt.name,
                                                    class_body_stmt.args,
                                                    class_body_stmt.body,
                                                    class_body_stmt.decorator_list,
                                                    class_body_stmt.returns,
                                                )
                                            )
                                    case ast.Attribute(
                                        ast.Name(id, ctx=ast.Load()),
                                        attr,
                                        ctx=ast.Load(),
                                    ):
                                        # TODO: other route type
                                        if id in route_imports:
                                            class_body_stmt.body = [
                                                ast.Raise(
                                                    ast.Call(
                                                        ast.Name(
                                                            "NotImplementedError",
                                                            ctx=ast.Load(),
                                                        ),
                                                        [],
                                                        [],
                                                    ),
                                                    None,
                                                )
                                            ]
                                            add_import_name(
                                                class_body_stmt.args.args[2].annotation
                                            )
                                            class_body_stmt.args.args.pop(1)
                                            add_import_name(class_body_stmt.returns)
                                            class_body_stmt.returns = ast.Subscript(
                                                ast.Name("Future", ctx=ast.Load()),
                                                class_body_stmt.returns,
                                            )
                                            new_class_body_stmts.append(
                                                ast.FunctionDef(
                                                    class_body_stmt.name,
                                                    class_body_stmt.args,
                                                    class_body_stmt.body,
                                                    class_body_stmt.decorator_list,
                                                    class_body_stmt.returns,
                                                )
                                            )

                body_stmt.body = new_class_body_stmts

        new_clss.append(body_stmt)

new_imports: list[ast.Import | ast.ImportFrom] = [
    ast.ImportFrom("concurrent.futures", [ast.alias("Future")], 0),
    ast.ImportFrom("contextlib", [ast.alias("AbstractContextManager")], 0),
    ast.ImportFrom("dataclasses", [ast.alias("dataclass")], 0),
    ast.Import([ast.alias("queue")]),
    ast.ImportFrom(
        "tsocket.client_thread",
        [ast.alias("ClientThread"), ast.alias("Route"), ast.alias("subscribe")],
        0,
    ),
]

for body_stmt in ast.parse(inspect.getsource(server)).body:
    match body_stmt:
        case ast.Import(names) | ast.ImportFrom(_, names, _):
            body_stmt.names = [
                name
                for name in names
                if (name.asname if name.asname is not None else name.name)
                in required_imports
            ]
            if body_stmt.names:
                new_imports.append(body_stmt)

if (server_file_str := inspect.getsourcefile(server)) is not None:
    with open(
        Path(server_file_str).parent.parent / "client" / "client_thread.py",
        "w",
        encoding="utf-8",
    ) as server_file:
        server_file.write(
            ast.unparse(
                ast.fix_missing_locations(
                    ast.Module(
                        body=[
                            ast.Constant(
                                "AUTOGENERATED BY battleship.server.generate_client_thread DO NOT MANUALLY EDIT"
                            )
                        ]
                        + new_imports
                        + new_clss,
                        type_ignores=[],
                    )
                )
            )
        )
    try:
        subprocess.run(["black", "."], check=False)
    except Exception:
        pass
