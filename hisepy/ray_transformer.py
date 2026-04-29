import ast
import astor
import sys
from typing import List, Tuple, Union, Dict, Any
from pathlib import Path
import inspect


class RayTransformer(ast.NodeTransformer):

    def __init__(self, **kwargs):
        super().__init__()
        self.remoteable_funcs = set(
        )  # Tracks top-level functions to be decorated with ray.remote
        self.actor_classes = set(
        )  # Tracks class names that should be Ray actors
        self.actor_instances = set(
        )  # Tracks instance variable names of Ray actors
        self.current_function = None  # Tracks the currently visited function (unused but could be extended)
        self.decorator_kwargs = kwargs  # Additional decorator arguments (e.g., num_cpus, num_gpus)

        # Make decorator kwargs available as attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    # entry point
    def visit_Module(self, node):
        self._collect_imported_modules(node)
        self._annotate_method_parents(node)
        self.generic_visit(node)

        node.body = [
            self._wrap_main_function(item) if
            isinstance(item, ast.FunctionDef) and item.name == "main" else item
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

        # Inject cleanup calls at the end of main()
        cleanup_calls = [
            ast.Expr(value=ast.Call(
                func=ast.Attribute(value=ast.Name(id='ray', ctx=ast.Load()),
                                   attr='get',
                                   ctx=ast.Load()),
                args=[
                    ast.Call(func=ast.Attribute(value=ast.Name(id=var,
                                                               ctx=ast.Load()),
                                                attr='cleanup.remote',
                                                ctx=ast.Load()),
                             args=[],
                             keywords=[])
                ],
                keywords=[])) for var in self.actor_instances
        ]
        node.body.extend(cleanup_calls)
        return node

    def visit_ClassDef(self, node):
        # Decorate class if it has at least one method
        should_decorate = any(
            isinstance(item, ast.FunctionDef) for item in node.body)

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                item.parent = node
                self.visit_FunctionDef(item)

        if should_decorate:
            self._add_remote_decorator(node)
            self.actor_classes.add(node.name)

        # Check if cleanup method exists
        if not any(
                isinstance(n, ast.FunctionDef) and n.name == "cleanup"
                for n in node.body):
            cleanup_func = ast.FunctionDef(
                name="cleanup",
                args=ast.arguments(posonlyargs=[],
                                   args=[ast.arg(arg='self')],
                                   vararg=None,
                                   kwonlyargs=[],
                                   kw_defaults=[],
                                   kwarg=None,
                                   defaults=[]),
                body=[
                    ast.Expr(
                        value=ast.Call(func=ast.Attribute(value=ast.Attribute(
                            value=ast.Name(id='ray', ctx=ast.Load()),
                            attr='actor',
                            ctx=ast.Load()),
                                                          attr='exit_actor',
                                                          ctx=ast.Load()),
                                       args=[],
                                       keywords=[]))
                ],
                decorator_list=[])
            node.body.append(cleanup_func)
        return node

    def _add_remote_decorator(self, node):
        # Add @ray.remote or @ray.remote(**kwargs) as a decorator
        keywords = [
            ast.keyword(arg=k, value=ast.Constant(value=v))
            for k, v in self.decorator_kwargs.items() if v is not None
        ]
        decorator = ast.Call(
            func=ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()),
                               attr="remote",
                               ctx=ast.Load()),
            args=[],
            keywords=keywords) if keywords else ast.Name(id="ray.remote",
                                                         ctx=ast.Load())

        node.decorator_list.insert(0, decorator)

    def _is_toplevel_function(self, node):
        return not (hasattr(node, 'parent') and isinstance(
            node.parent, ast.ClassDef)) and node.name != "main"

    def visit_Assign(self, node):
        self.generic_visit(node)

        # Actor class instantiation
        if isinstance(node.value, ast.Call):
            call = node.value
            # Detect actor instantiation via .remote() too
            if isinstance(call.func, ast.Attribute):
                base = call.func.value
                if isinstance(base,
                              ast.Name) and base.id in self.actor_classes:
                    self._record_actor_instance(node)
            if isinstance(call.func,
                          ast.Name) and call.func.id in self.actor_classes:
                node.value = self._replace_with_actor_remote(call)
                self._record_actor_instance(node)
            # Direct call to a local remoteable function
            elif self._is_direct_local_call(call):
                node.value = self._wrap_local_function_call(call)
        return node

    def _replace_with_actor_remote(self, call):
        # Worker(...) → Worker.remote(...)
        return ast.Call(func=ast.Attribute(value=ast.Name(id=call.func.id,
                                                          ctx=ast.Load()),
                                           attr="remote",
                                           ctx=ast.Load()),
                        args=call.args,
                        keywords=call.keywords)

    def _record_actor_instance(self, node):
        # Track assigned variable names as actor instances
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.actor_instances.add(target.id)

    # === Expression Statements ===
    def visit_Expr(self, node):
        self.generic_visit(node)

        # Transform top-level expression calls to ray.get(func.remote(...))
        if isinstance(node.value, ast.Call) and self._is_direct_local_call(
                node.value):
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
            self.actor_instances | self.remoteable_funcs | self.actor_classes)

    # function/method calls
    def visit_Call(self, node):
        self.generic_visit(node)

        func = node.func

        # Skip if this is a method chain on an imported object
        if self._is_imported_chain(func):
            return node

        # Direct actor instantiation: Foo(...) → Foo.remote(...)
        if isinstance(func, ast.Name) and func.id in self.actor_classes:
            node.func = ast.Attribute(value=ast.Name(id=func.id,
                                                     ctx=ast.Load()),
                                      attr='remote',
                                      ctx=ast.Load())
            return node

        # Direct call to a remoteable function
        if isinstance(func, ast.Name) and func.id in self.remoteable_funcs:
            return self._wrap_local_function_call(node)

        # Actor method call via direct variable: trainer.train(...)
        if self._is_actor_method_call(node):
            return self._wrap_actor_method_call(node)

        # Actor method call via subscript: trainers[0].train(...)
        if isinstance(func, ast.Attribute) and isinstance(
                func.value, ast.Subscript):
            # Assume this is like: workers[i].do_work(x)
            # Wrap with ray.get(... .remote(...))
            base = self._get_subscript_base(func.value)
            # Only wrap if the base is a known actor instance
            if base in self.actor_instances:
                remote_call = ast.Call(func=ast.Attribute(value=func,
                                                          attr='remote',
                                                          ctx=ast.Load()),
                                       args=node.args,
                                       keywords=node.keywords)
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
            ast.Call(func=ast.Attribute(value=node.func.value,
                                        attr=f"{node.func.attr}.remote",
                                        ctx=ast.Load()),
                     args=node.args,
                     keywords=node.keywords))

    def _wrap_with_ray_get(self, call_node):
        # Wrap any call in ray.get(...)
        return ast.Call(func=ast.Attribute(value=ast.Name(id="ray",
                                                          ctx=ast.Load()),
                                           attr="get",
                                           ctx=ast.Load()),
                        args=[call_node],
                        keywords=[])

    def _is_actor_method_call(self, node):
        # Check if the call is a method on a known actor instance
        return (isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in self.actor_instances)

    def visit_ListComp(self, node):
        # Handle list comprehensions calling remoteable functions
        if isinstance(node.elt, ast.Call) and self._is_direct_local_call(
                node.elt):
            node.elt.func = ast.Attribute(value=ast.Name(id=node.elt.func.id,
                                                         ctx=ast.Load()),
                                          attr="remote",
                                          ctx=ast.Load())
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
            new_body.append(
                self._wrap_with_ray_get(
                    ast.List(elts=remote_exprs, ctx=ast.Load())))

        node.body = new_body
        return node

    def _is_direct_local_expr_call(self, stmt):
        return (isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Call)
                and self._is_direct_local_call(stmt.value))

    def _is_assign_remoteable_func(self, stmt):
        return (isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Name)
                and stmt.value.func.id in self.remoteable_funcs)

    def _convert_to_remote_call(self, call):
        # func(...) → func.remote(...)
        return ast.Call(func=ast.Attribute(value=ast.Name(id=call.func.id,
                                                          ctx=ast.Load()),
                                           attr="remote",
                                           ctx=ast.Load()),
                        args=call.args,
                        keywords=call.keywords)

    def _is_direct_local_call(self, call):
        return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id in self.remoteable_funcs)

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
        remote_call = ast.Call(func=ast.Attribute(value=ast.Name(
            id=call.func.id, ctx=ast.Load()),
                                                  attr="remote",
                                                  ctx=ast.Load()),
                               args=call.args,
                               keywords=call.keywords)
        return self._wrap_with_ray_get(remote_call)


def rayify_code(source_code: str,
                num_gpus: int = None,
                num_cpus: int = None) -> str:
    tree = ast.parse(source_code)
    transformer = RayTransformer(num_gpus=num_gpus, num_cpus=num_cpus)
    tree = transformer.visit(tree)
    ast.fix_missing_locations(tree)
    boilerplate = "import ray\nray.init()\n"
    code_body = astor.to_source(tree)
    if "ray.init()" not in code_body:
        code_body = boilerplate + code_body

    return code_body


def transform_to_ray(input_path: str,
                     output_path: str = None,
                     num_gpus: int = None,
                     num_cpus: int = None):
    input_file = Path(input_path)
    output_file = Path(output_path) if output_path else input_file.with_name(
        input_file.stem + "_ray.py")

    source_code = input_file.read_text()
    rayified_code = rayify_code(source_code,
                                num_gpus=num_gpus,
                                num_cpus=num_cpus)
    output_file.write_text(rayified_code)
    print(f"Ray-conformant code written to: {output_file}")


def is_ray_remote_decorator(decorator):
    ''' Checks if the decorator is @ray.remote or @ray.remote(...)
    '''
    # handles @ray.remote, @ray.remote(...), etc.
    if isinstance(decorator, ast.Name):
        return decorator.id == "ray"
    elif isinstance(decorator, ast.Attribute):
        return decorator.attr == "remote" and getattr(decorator.value, "id",
                                                      None) == "ray"
    elif isinstance(decorator, ast.Call):
        # Call to ray.remote(...)
        func = decorator.func
        return (isinstance(func, ast.Attribute) and func.attr == "remote"
                and getattr(func.value, "id", None) == "ray")
    return False


def get_ray_remote_targets(
        file_path: str) -> List[Tuple[str, str, Dict[str, Any]]]:
    """
    Detects uses of @ray.remote and returns the names, types, and any decorator parameters.

    Args:
        file_path (str): Path to the Python file.

    Returns:
        List[Tuple[str, str, Dict[str, Any]]]: A list of tuples (name, type, params), where:
            - name is the name of the function or class decorated with @ray.remote
            - type is either "function" or "class"
            - params is a dict of keyword arguments passed to @ray.remote (empty if none)
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}")
        return []

    remote_targets = []

    for node in ast.walk(tree):
        if isinstance(node,
                      (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                params = {}
                # Check if this decorator is @ray.remote
                if isinstance(
                        decorator,
                        ast.Attribute) and is_ray_remote_decorator(decorator):
                    node_type = ("function" if isinstance(
                        node,
                        (ast.FunctionDef, ast.AsyncFunctionDef)) else "class")
                    remote_targets.append((node.name, node_type, params))

                # Check if this decorator is a call to @ray.remote(...)
                elif isinstance(
                        decorator,
                        ast.Call) and is_ray_remote_decorator(decorator):
                    node_type = ("function" if isinstance(
                        node,
                        (ast.FunctionDef, ast.AsyncFunctionDef)) else "class")
                    # Collect keyword arguments
                    for kw in decorator.keywords:
                        try:
                            params[kw.arg] = ast.literal_eval(kw.value)
                        except Exception:
                            params[kw.arg] = "can't evaluate"
                    remote_targets.append((node.name, node_type, params))

    return remote_targets


class RemoteRemover(ast.NodeTransformer):

    def __init__(self, target_names: Union[str, List[str]]):
        super().__init__()
        if isinstance(target_names, str):
            self.target_names = {target_names}
        else:
            self.target_names = set(target_names)

    def visit_FunctionDef(self, node):
        if node.name in self.target_names:
            node.decorator_list = [
                d for d in node.decorator_list
                if not is_ray_remote_decorator(d)
            ]
        return self.generic_visit(node)

    def visit_ClassDef(self, node):
        if node.name in self.target_names:
            node.decorator_list = [
                d for d in node.decorator_list
                if not is_ray_remote_decorator(d)
            ]
        return self.generic_visit(node)


def remove_ray_remote_decorator(file_path: str,
                                target_name: Union[str, List[str]],
                                output_path=None):
    """
    Removes the @ray.remote decorator (with or without arguments) from specific
    functions or classes in a Python script.

    Args:
        file_path (str): Path to the original Python file.
        target_name (str or List[str]): Name(s) of the function(s) or class(es) with @ray.remote decorator.
        output_path (str, optional): Path to save the modified script. If None, returns the new code.

    Returns:
        str: The modified code (only if output_path is None).
    """
    if isinstance(target_name, str):
        target_names = {target_name}
    else:
        target_names = set(target_name)

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    # Create a transformer that removes @ray.remote decorators from specified functions/classes
    modified_tree = RemoteRemover(target_name).visit(tree)
    ast.fix_missing_locations(modified_tree)

    new_code = ast.unparse(modified_tree)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(new_code)
    else:
        return new_code


# TODO: there has to be a way to use inspect.signature to get the
# parameters of the ray.remote decorator
def get_ray_remote_params_from_signature():
    # well-known params
    return {
        # Remote function options
        "num_cpus",
        "num_gpus",
        "resources",
        "memory",
        "object_store_memory",
        "max_calls",
        "max_retries",
        "retry_exceptions",
        "scheduling_strategy",
        "name",
        "concurrency_groups",
        "max_concurrency",
        "placement_group",
        "placement_group_bundle_index",
        "runtime_env",
        # Actor options
        "max_restarts",
        "max_task_retries",
        "lifetime",
        "actor_creation_hook",
        "name",
        "namespace",
    }


class RemoteModifier(ast.NodeTransformer):

    def __init__(self, target_name: str, new_kwargs: dict):
        super().__init__()
        self.target_name = target_name
        self.new_kwargs = new_kwargs

        # Validate new kwargs against known ray.remote parameters
        invalid_keys = [
            k for k in new_kwargs.keys()
            if k not in get_ray_remote_params_from_signature()
        ]
        if invalid_keys:
            raise ValueError(
                f"Invalid ray.remote parameters: {invalid_keys}. Valid parameters are: {get_ray_remote_params_from_signature()}"
            )

    def visit_FunctionDef(self, node):
        if node.name == self.target_name:
            node.decorator_list = [
                self._modify_decorator(d) for d in node.decorator_list
            ]
        return self.generic_visit(node)

    def visit_ClassDef(self, node):
        if node.name == self.target_name:
            node.decorator_list = [
                self._modify_decorator(d) for d in node.decorator_list
            ]
        return self.generic_visit(node)

    def _modify_decorator(self, decorator):
        if is_ray_remote_decorator(decorator):
            # Ensure it's a Call node
            if not isinstance(decorator, ast.Call):
                decorator = ast.Call(func=decorator, args=[], keywords=[])

            # Merge existing kwargs with new_kwargs
            existing_kwargs = {kw.arg: kw.value for kw in decorator.keywords}
            for k, v in self.new_kwargs.items():
                existing_kwargs[k] = ast.Constant(value=v)

            # Rebuild keyword arguments
            decorator.keywords = [
                ast.keyword(arg=k, value=v)
                for k, v in existing_kwargs.items()
            ]

        return decorator


def modify_ray_remote_decorator(file_path,
                                target_name,
                                new_kwargs,
                                output_path=None):
    """
    Modifies the parameters passed to a @ray.remote decorator on a specific
    function or class. Raises error if invalid parameters are given.

    Args:
        file_path (str): Path to the original Python file.
        target_name (str): Name of the function/class with @ray.remote decorator.
        new_kwargs (dict): Dictionary of parameters to set for ray.remote(...).
        output_path (str, optional): Path to save modified script. If None, returns the new code.

    Returns:
        str: Modified code (only if output_path is None).
    """
    # Validate new kwargs
    assert type(new_kwargs) is dict, "prompt response must be a dictionary"
    invalid_keys = [
        k for k in new_kwargs.keys()
        if k not in get_ray_remote_params_from_signature()
    ]
    if invalid_keys:
        raise ValueError(
            f"Invalid ray.remote parameters: {invalid_keys}. Valid parameters are: {get_ray_remote_params_from_signature()}"
        )

    with open(file_path, "r") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    # Create a transformer that modifies @ray.remote decorators
    modified_tree = RemoteModifier(target_name, new_kwargs).visit(tree)
    ast.fix_missing_locations(modified_tree)

    new_code = ast.unparse(modified_tree)

    if output_path:
        with open(output_path, "w") as f:
            f.write(new_code)
    else:
        return new_code


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
                if (isinstance(func.value, ast.Name) and func.value.id == "ray"
                        and func.attr == "init"):
                    return True

    return False


def prompt_decorator_changes(msg: str = None):
    """ Prompts end users and asks for custom input """
    if msg is None:
        raise ValueError("Must provide a contextual message")
    print(msg)
    user_input = input(
        'Please submit parameter and value you want edited as {"key":val}: ')
    while user_input == '':
        print('Input cannot be empty. Please try again.')
        user_input = input('Please enter your response: ')
    return user_input


# === Optional CLI Entry Point ===
"""
if __name__ == "__main__":
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    transform_to_ray(in_path, out_path, num_gpus=1, num_cpus=None)
"""
