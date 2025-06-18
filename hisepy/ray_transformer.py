import ast
import astor
import sys
from pathlib import Path

class RayTransformer(ast.NodeTransformer):
    def __init__(self):
        super().__init__()
        self.remoteable_funcs = set()
        self.actor_classes = set()
        self.actor_instances = set()
        self.current_function = None

    def visit_Module(self, node):
        for item in node.body:
            if isinstance(item, ast.ClassDef):
                for subitem in item.body:
                    if isinstance(subitem, ast.FunctionDef):
                        subitem.parent = item

        self.generic_visit(node)

        for i, item in enumerate(node.body):
            if isinstance(item, ast.FunctionDef) and item.name == "main":
                node.body[i] = self.visit_FunctionDef_main_wrapper(item)
        return node

    def visit_FunctionDef(self, node):
        self.current_function = node.name
        is_method = hasattr(node, 'parent') and isinstance(node.parent, ast.ClassDef)

        if not is_method and node.name != "main":
            self.remoteable_funcs.add(node.name)
            decorator = ast.Name(id="ray.remote", ctx=ast.Load())
            node.decorator_list.insert(0, decorator)

        self.generic_visit(node)
        self.current_function = None
        return node

    def visit_ClassDef(self, node):
        should_decorate = False
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                item.parent = node
                self.visit_FunctionDef(item)
                should_decorate = True

        if should_decorate:
            decorator = ast.Name(id="ray.remote", ctx=ast.Load())
            node.decorator_list.insert(0, decorator)
            self.actor_classes.add(node.name)

        return node

    def visit_Assign(self, node):
        self.generic_visit(node)

        if isinstance(node.value, ast.Call):
            call = node.value
            # If assigning actor instance
            if isinstance(call.func, ast.Name) and call.func.id in self.actor_classes:
                call.func = ast.Attribute(value=ast.Name(id=call.func.id, ctx=ast.Load()), attr="remote", ctx=ast.Load())
                call = ast.Call(func=call.func, args=call.args, keywords=call.keywords)
                node.value = call
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.actor_instances.add(target.id)
            elif self._is_direct_local_call(call):
                node.value = self._wrap_local_function_call(call)
        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call):
            call = node.value
            if self._is_direct_local_call(call):
                node.value = self._wrap_local_function_call(call)
        return node

    def visit_Call(self, node):
        self.generic_visit(node)

        if isinstance(node.func, ast.Name):
            if node.func.id in self.remoteable_funcs:
                return self._wrap_local_function_call(node)
            elif node.func.id in self.actor_classes:
                # Calling actor constructor
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id=node.func.id, ctx=ast.Load()),
                        attr="remote",
                        ctx=ast.Load()
                    ),
                    args=node.args,
                    keywords=node.keywords
                )

        # Match: actor_instance.method(args)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.actor_instances
        ):
            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="ray", ctx=ast.Load()),
                    attr="get",
                    ctx=ast.Load()
                ),
                args=[ast.Call(
                    func=ast.Attribute(
                        value=node.func.value,
                        attr=f"{node.func.attr}.remote",
                        ctx=ast.Load()
                    ),
                    args=node.args,
                    keywords=node.keywords
                )],
                keywords=[]
            )

        return node

    def visit_ListComp(self, node):
        if isinstance(node.elt, ast.Call):
            call = node.elt
            if self._is_direct_local_call(call):
                call.func = ast.Attribute(
                    value=ast.Name(id=call.func.id, ctx=ast.Load()),
                    attr="remote",
                    ctx=ast.Load()
                )
                return ast.Call(
                    func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()), attr="get", ctx=ast.Load()),
                    args=[node],
                    keywords=[]
                )
        return self.generic_visit(node)

    def visit_FunctionDef_main_wrapper(self, node):
        new_body = []
        remote_exprs = []

        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if self._is_direct_local_call(call):
                    remote_call = ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id=call.func.id, ctx=ast.Load()),
                            attr="remote",
                            ctx=ast.Load(),
                        ),
                        args=call.args,
                        keywords=call.keywords,
                    )
                    remote_exprs.append(remote_call)
                    continue
            elif (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Call)
                and self._is_direct_local_call(stmt.value)
            ):
                stmt.value = self._wrap_local_function_call(stmt.value)
                new_body.append(stmt)
                continue
            new_body.append(stmt)

        if remote_exprs:
            get_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()), attr="get", ctx=ast.Load()),
                    args=[ast.List(elts=remote_exprs, ctx=ast.Load())],
                    keywords=[]
                )
            )
            new_body.append(get_call)

        node.body = new_body
        return node

    # --- Helper methods ---
    def _is_direct_local_call(self, call):
        return (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in self.remoteable_funcs
        )

    def _wrap_local_function_call(self, call):
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()), attr="get", ctx=ast.Load()),
            args=[
                ast.Call(
                    func=ast.Attribute(value=ast.Name(id=call.func.id, ctx=ast.Load()), attr="remote", ctx=ast.Load()),
                    args=call.args,
                    keywords=call.keywords
                )
            ],
            keywords=[]
        )

def rayify_code(source_code: str) -> str:
    tree = ast.parse(source_code)
    transformer = RayTransformer()
    tree = transformer.visit(tree)
    ast.fix_missing_locations(tree)

    boilerplate = "import ray\nray.init()\n"
    code_body = astor.to_source(tree)
    if "ray.init()" not in code_body:
        code_body = boilerplate + code_body

    return code_body

def transform_to_ray(input_path: str, output_path: str = None):
    input_file = Path(input_path)
    output_file = Path(output_path) if output_path else input_file.with_name(input_file.stem + "_ray.py")

    source_code = input_file.read_text()
    rayified_code = rayify_code(source_code)
    output_file.write_text(rayified_code)
    print(f"Ray-conformant code written to: {output_file}")

