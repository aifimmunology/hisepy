import ast
import astor
import sys
from pathlib import Path


class RayTransformer(ast.NodeTransformer):
    def __init__(self, **kwargs):
        super().__init__()
        self.remoteable_funcs = set()    # Tracks top-level functions to be decorated with ray.remote
        self.actor_classes = set()       # Tracks class names that should be Ray actors
        self.actor_instances = set()     # Tracks instance variable names of Ray actors
        self.current_function = None     # Tracks the currently visited function (unused but could be extended)
        self.decorator_kwargs = kwargs   # Additional decorator arguments (e.g., num_cpus, num_gpus)

        # Make decorator kwargs available as attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    # entry point 
    def visit_Module(self, node):
        self._collect_imported_modules(node)
        self._annotate_method_parents(node)
        self.generic_visit(node)
    
        node.body = [
            self._wrap_main_function(item) if isinstance(item, ast.FunctionDef) and item.name == "main" else item
            for item in node.body
        ]
        return node

    def _annotate_method_parents(self, node):
        # Mark FunctionDef nodes with their parent class, if applicable
        for item in node.body:
            if isinstance(item, ast.ClassDef):
                for subitem in item.body:
                    if isinstance(subitem, ast.FunctionDef):
                        subitem.parent = item

    def visit_FunctionDef(self, node):
        # Only decorate top-level functions (not methods or main())
        if self._is_toplevel_function(node):
            self._add_remote_decorator(node)
            self.remoteable_funcs.add(node.name)

        self.generic_visit(node)
        self.current_function = None
        return node

    def visit_ClassDef(self, node):
        # Decorate class if it has at least one method
        should_decorate = any(isinstance(item, ast.FunctionDef) for item in node.body)

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                item.parent = node
                self.visit_FunctionDef(item)

        if should_decorate:
            self._add_remote_decorator(node)
            self.actor_classes.add(node.name)

        return node

    def _add_remote_decorator(self, node):
        # Add @ray.remote or @ray.remote(**kwargs) as a decorator
        keywords = [
            ast.keyword(arg=k, value=ast.Constant(value=v))
            for k, v in self.decorator_kwargs.items() if v is not None
        ]
        decorator = ast.Call(
            func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()), attr="remote", ctx=ast.Load()),
            args=[], keywords=keywords
        ) if keywords else ast.Name(id="ray.remote", ctx=ast.Load())

        node.decorator_list.insert(0, decorator)

    def _is_toplevel_function(self, node):
        return not (hasattr(node, 'parent') and isinstance(node.parent, ast.ClassDef)) and node.name != "main"

    def visit_Assign(self, node):
        self.generic_visit(node)

        # Actor class instantiation
        if isinstance(node.value, ast.Call):
            call = node.value
            # Detect actor instantiation via .remote() too
            if isinstance(call.func, ast.Attribute):
                base = call.func.value
                if isinstance(base, ast.Name) and base.id in self.actor_classes:
                    self._record_actor_instance(node)
            if isinstance(call.func, ast.Name) and call.func.id in self.actor_classes:
                node.value = self._replace_with_actor_remote(call)
                self._record_actor_instance(node)
            # Direct call to a local remoteable function
            elif self._is_direct_local_call(call):
                node.value = self._wrap_local_function_call(call)
        return node

    def _replace_with_actor_remote(self, call):
        # Worker(...) → Worker.remote(...)
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id=call.func.id, ctx=ast.Load()), attr="remote", ctx=ast.Load()),
            args=call.args, keywords=call.keywords
        )

    def _record_actor_instance(self, node):
        # Track assigned variable names as actor instances
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.actor_instances.add(target.id)

    # === Expression Statements ===
    def visit_Expr(self, node):
        self.generic_visit(node)

        # Transform top-level expression calls to ray.get(func.remote(...))
        if isinstance(node.value, ast.Call) and self._is_direct_local_call(node.value):
            node.value = self._wrap_local_function_call(node.value)
        return node
        
    def _is_imported_chain(self, node):
        """
        Recursively checks if a Call or Attribute chain originates from an imported module.
        """
        def extract_base_name(expr):
            while isinstance(expr, (ast.Call, ast.Attribute)):
                expr = expr.func if isinstance(expr, ast.Call) else expr.value
            return expr.id if isinstance(expr, ast.Name) else None

        base = extract_base_name(node)
        return base in self.imported_modules


    def _is_call_to_imported_function(self, node):
        """
        Detects if the function call is part of a chain on an imported object.
        Prevents wrapping .remote/.get around calls like hm.MLPClassifier(...).to(...)
        """
        current = node.func
        while isinstance(current, ast.Attribute):
            current = current.value
        return isinstance(current, ast.Name) and current.id not in (
            self.actor_instances | self.remoteable_funcs | self.actor_classes
        )
        
    # function/method calls 
    def visit_Call(self, node):
        self.generic_visit(node)

        func = node.func

        # Skip if this is a method chain on an imported object
        if self._is_imported_chain(func):
            return node

        # Direct actor instantiation: Foo(...) → Foo.remote(...)
        if isinstance(func, ast.Name) and func.id in self.actor_classes:
            node.func = ast.Attribute(
                value=ast.Name(id=func.id, ctx=ast.Load()),
                attr='remote',
                ctx=ast.Load()
            )
            return node
            
        # Direct call to a remoteable function
        if isinstance(func, ast.Name) and func.id in self.remoteable_funcs:
            return self._wrap_local_function_call(node)

        # Actor method call via direct variable: trainer.train(...)
        if self._is_actor_method_call(node):
            return self._wrap_actor_method_call(node)

        # Actor method call via subscript: trainers[0].train(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Subscript):
            # Assume this is like: workers[i].do_work(x)
            # Wrap with ray.get(... .remote(...))
            remote_call = ast.Call(
                func=ast.Attribute(value=func, attr='remote', ctx=ast.Load()),
                args=node.args,
                keywords=node.keywords
            )
            return self._wrap_with_ray_get(remote_call)
        return node
        
    def _get_subscript_base(self, subscript):
        """
        Given a Subscript node (e.g., trainers[0]), return the base variable name (e.g., 'trainers').
        """
        val = subscript.value
        while isinstance(val, (ast.Subscript, ast.Attribute)):
            val = val.value
        return val.id if isinstance(val, ast.Name) else None
        
    def _wrap_actor_method_call(self, node):
        # Wrap actor method call: actor.method(...) → ray.get(actor.method.remote(...))
        return self._wrap_with_ray_get(
            ast.Call(
                func=ast.Attribute(
                    value=node.func.value,
                    attr=f"{node.func.attr}.remote",
                    ctx=ast.Load()
                ),
                args=node.args,
                keywords=node.keywords
            )
        )

    def _wrap_with_ray_get(self, call_node):
        # Wrap any call in ray.get(...)
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()), attr="get", ctx=ast.Load()),
            args=[call_node],
            keywords=[]
        )

    def _is_actor_method_call(self, node):
        # Check if the call is a method on a known actor instance
        return (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.actor_instances
        )

    def visit_ListComp(self, node):
        # Handle list comprehensions calling remoteable functions
        if isinstance(node.elt, ast.Call) and self._is_direct_local_call(node.elt):
            node.elt.func = ast.Attribute(
                value=ast.Name(id=node.elt.func.id, ctx=ast.Load()), attr="remote", ctx=ast.Load()
            )
            return self._wrap_with_ray_get(node)
        return self.generic_visit(node)

    # transform methods within main()
    def _wrap_main_function(self, node):
        new_body = []
        remote_exprs = []

        for stmt in node.body:
            # Handle function call expressions
            if self._is_direct_local_expr_call(stmt):
                remote_exprs.append(self._convert_to_remote_call(stmt.value))
            # Handle assigned function calls
            elif self._is_assign_remoteable_func(stmt):
                stmt.value = self._wrap_local_function_call(stmt.value)
                new_body.append(stmt)
            else:
                new_body.append(stmt)

        if remote_exprs:
            # Wrap batched expression calls with ray.get([...])
            new_body.append(self._wrap_with_ray_get(ast.List(elts=remote_exprs, ctx=ast.Load())))

        node.body = new_body
        return node

    def _is_direct_local_expr_call(self, stmt):
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and self._is_direct_local_call(stmt.value)
        )

    def _is_assign_remoteable_func(self, stmt):
        return (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Name)
            and stmt.value.func.id in self.remoteable_funcs
        )

    def _convert_to_remote_call(self, call):
        # func(...) → func.remote(...)
        return ast.Call(
            func=ast.Attribute(value=ast.Name(id=call.func.id, ctx=ast.Load()), attr="remote", ctx=ast.Load()),
            args=call.args,
            keywords=call.keywords
        )

    
    def _is_direct_local_call(self, call):
        return (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in self.remoteable_funcs
        )
        
    def _collect_imported_modules(self, node):
        self.imported_modules = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    self.imported_modules.add(alias.asname or alias.name)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.module:
                    self.imported_modules.add(stmt.module.split('.')[0])

    def _wrap_local_function_call(self, call):
        # Wrap func(...) → ray.get(func.remote(...))
        remote_call = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id=call.func.id, ctx=ast.Load()),
                attr="remote",
                ctx=ast.Load()
            ),
            args=call.args,
            keywords=call.keywords
        )
        return self._wrap_with_ray_get(remote_call)


def rayify_code(source_code: str, num_gpus: int = None, num_cpus: int = None) -> str:
    tree = ast.parse(source_code)
    transformer = RayTransformer(num_gpus=num_gpus, num_cpus=num_cpus)
    tree = transformer.visit(tree)
    ast.fix_missing_locations(tree)

    boilerplate = "import ray\nray.init()\n"
    code_body = astor.to_source(tree)
    if "ray.init()" not in code_body:
        code_body = boilerplate + code_body

    return code_body


def transform_to_ray(input_path: str, output_path: str = None, num_gpus: int = None, num_cpus: int = None):
    input_file = Path(input_path)
    output_file = Path(output_path) if output_path else input_file.with_name(input_file.stem + "_ray.py")

    source_code = input_file.read_text()
    rayified_code = rayify_code(source_code, num_gpus=num_gpus, num_cpus=num_cpus)
    output_file.write_text(rayified_code)
    print(f"Ray-conformant code written to: {output_file}")


def has_ray_init(file_path: str) -> bool:
    """
    Detects whether ray.init() is called anywhere in the given Python file.

    Args:
        file_path (str): Path to the Python file (e.g., "app.py").

    Returns:
        bool: True if ray.init() is called, False otherwise.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        print(f"Syntax error parsing {file_path}: {e}")
        return False

    for node in ast.walk(tree):
        # Look for function calls
        if isinstance(node, ast.Call):
            func = node.func
            # Check if it's ray.init() or ray.init(...) with args
            if isinstance(func, ast.Attribute):
                if (
                    isinstance(func.value, ast.Name)
                    and func.value.id == "ray"
                    and func.attr == "init"
                ):
                    return True

    return False


# === Optional CLI Entry Point ===
"""
if __name__ == "__main__":
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    transform_to_ray(in_path, out_path, num_gpus=1, num_cpus=None)
"""
