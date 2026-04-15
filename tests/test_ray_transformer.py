import unittest
import ast
import astor
import sys
import textwrap
import pytest
from pathlib import Path
import tempfile

sys.path.insert(0,
                '../')  # Adjust path as needed to locate your RayTransformer
from hisepy.ray_transformer import RayTransformer
from hisepy.ray_transformer import is_ray_remote_decorator, get_ray_remote_targets, remove_ray_remote_decorator, modify_ray_remote_decorator


class TestRayTransformer(unittest.TestCase):

    def normalize(self, code: str) -> str:
        """Utility to normalize code strings for comparison."""
        return "\n".join(line.strip() for line in code.strip().splitlines()
                         if line.strip())

    def test_base_transformation(self):
        source_code = '''
def compute(x):
    return x * 2
'''
        expected_transformed = '''import ray
ray.init()
@ray.remote
def compute(x):
    return x * 2
'''
        tree = ast.parse(source_code)
        transformer = RayTransformer()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        transformed_code = "import ray\nray.init()\n" + astor.to_source(
            new_tree)
        self.assertEqual(self.normalize(transformed_code),
                         self.normalize(expected_transformed))

    def test_list_comprehension_transformation(self):
        source_code = '''
def compute(x):
    return x * 2

def do_the_thing(inputs):
    return [compute(x) for x in inputs]
'''
        expected_transformed = '''import ray
ray.init()
@ray.remote
def compute(x):
    return x * 2


@ray.remote
def do_the_thing(inputs):
    return ray.get([compute.remote(x) for x in inputs])

'''

        tree = ast.parse(source_code)
        transformer = RayTransformer()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        transformed_code = "import ray\nray.init()\n" + astor.to_source(
            new_tree)
        self.assertEqual(self.normalize(transformed_code),
                         self.normalize(expected_transformed))

    def test_class_actor_transformation(self):
        source_code = '''
class MyWorker:
    def compute(self, x):
        return x * 2
'''
        expected_transformed = '''import ray
ray.init()

@ray.remote
class MyWorker:
    
    
    def compute(self, x):
        return x * 2
'''

        tree = ast.parse(source_code)
        transformer = RayTransformer()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        transformed_code = "import ray\nray.init()\n" + astor.to_source(
            new_tree)
        self.assertEqual(self.normalize(transformed_code),
                         self.normalize(expected_transformed))

    def test_class_actor_main_transformation(self):
        source_code = '''
class Worker:
    def __init__(self, worker_id):
        self.worker_id = worker_id

    def do_work(self, x):
        time.sleep(random.uniform(0.5, 1.5))
        result = x * x
        return result

def main():
    num_inputs= 10
    workers = [Worker(worker_id=i) for i in range(num_inputs)]
    results = [workers[i].do_work(x) for i,x in enumerate(list(range(num_inputs)))]
    print('Final results:', results)
'''
        expected_transformed = '''import ray
ray.init()

@ray.remote
class Worker:
    def __init__(self, worker_id):
        self.worker_id = worker_id

    def do_work(self, x):
        time.sleep(random.uniform(0.5, 1.5))
        result = x * x
        return result

def main():
    num_inputs = 10
    workers = [Worker.remote(worker_id=i) for i in range(num_inputs)]
    results = [ray.get(workers[i].do_work.remote(x)) for i, x in enumerate(
        list(range(num_inputs)))]
    print('Final results:', results)
'''
        tree = ast.parse(source_code)
        transformer = RayTransformer()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        transformed_code = "import ray\nray.init()\n" + astor.to_source(
            new_tree)
        self.assertEqual(self.normalize(transformed_code),
                         self.normalize(expected_transformed))


def test_is_ray_remote_decorator_name():
    node = ast.Name(id="ray", ctx=ast.Load())
    assert is_ray_remote_decorator(node) is True


def test_is_ray_remote_decorator_attribute():
    node = ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()),
                         attr="remote",
                         ctx=ast.Load())
    assert is_ray_remote_decorator(node) is True


def test_is_ray_remote_decorator_call():
    func = ast.Attribute(value=ast.Name(id="ray", ctx=ast.Load()),
                         attr="remote",
                         ctx=ast.Load())
    node = ast.Call(func=func, args=[], keywords=[])
    assert is_ray_remote_decorator(node) is True


def test_is_ray_remote_decorator_false_for_other_name():
    node = ast.Name(id="not_ray", ctx=ast.Load())
    assert is_ray_remote_decorator(node) is False


def test_is_ray_remote_decorator_false_for_other_attribute():
    node = ast.Attribute(value=ast.Name(id="x", ctx=ast.Load()),
                         attr="something",
                         ctx=ast.Load())
    assert is_ray_remote_decorator(node) is False


def test_get_ray_remote_targets_function(tmp_path: Path):
    code = textwrap.dedent("""
        import ray

        @ray.remote
        def foo():
            pass
    """)
    file_path = tmp_path / "test1.py"
    file_path.write_text(code)
    assert get_ray_remote_targets(str(file_path)) == [("foo", "function", {})]


def test_get_ray_remote_targets_class(tmp_path: Path):
    code = textwrap.dedent("""
        import ray

        @ray.remote
        class Worker:
            pass
    """)
    file_path = tmp_path / "test2.py"
    file_path.write_text(code)
    assert get_ray_remote_targets(str(file_path)) == [("Worker", "class", {})]


def test_get_ray_remote_targets_with_arguments(tmp_path: Path):
    code = textwrap.dedent("""
        import ray

        @ray.remote(num_cpus=2)
        def bar():
            pass
    """)
    file_path = tmp_path / "test3.py"
    file_path.write_text(code)
    assert get_ray_remote_targets(str(file_path)) == [("bar", "function", {
        "num_cpus": 2
    })]


def test_get_ray_remote_targets_multiple(tmp_path: Path):
    code = textwrap.dedent("""
        import ray

        @ray.remote
        def foo(): pass

        @ray.remote(num_gpus=1)
        class Worker: pass
    """)
    file_path = tmp_path / "test4.py"
    file_path.write_text(code)
    result = get_ray_remote_targets(str(file_path))
    assert ("foo", "function", {}) in result
    assert ("Worker", "class", {"num_gpus": 1}) in result


def test_get_ray_remote_targets_invalid_syntax(tmp_path: Path):
    file_path = tmp_path / "broken.py"
    file_path.write_text("def foo(:\n    pass")  # broken syntax
    assert get_ray_remote_targets(str(file_path)) == []


def test_get_ray_remote_targets_other_library_remote(tmp_path: Path):
    code = textwrap.dedent("""
        class notray:
            @staticmethod
            def remote(x): return x

        @notray.remote
        def bogus():
            pass
    """)
    file_path = tmp_path / "test_notray.py"
    file_path.write_text(code)

    # should NOT be detected as ray.remote
    assert get_ray_remote_targets(str(file_path)) == []


class TestRayModifier(unittest.TestCase):
    """Test cases for modifying Ray remote decorators in Python code."""

    def setUp(self):
        self.sample_code = """
import ray

@ray.remote
def foo():
    return 42

@ray.remote(num_cpus=2)
def bar(x):
    return x * 2

@ray.remote
class Trainer:
    def train(self):
        pass
"""

    def test_remove_single_function(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py",
                                         delete=False) as tmp:
            tmp.write(self.sample_code)
            tmp.flush()

            new_code = remove_ray_remote_decorator(tmp.name, "foo")
            tree = ast.parse(new_code)

            # foo should no longer have any ray.remote decorators
            foo_node = [
                n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "foo"
            ][0]
            assert all(not is_ray_remote_decorator(d)
                       for d in foo_node.decorator_list)

            # bar should still have its decorator
            bar_node = [
                n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "bar"
            ][0]
            assert any(
                is_ray_remote_decorator(d) for d in bar_node.decorator_list)

    def test_remove_multiple_targets(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py",
                                         delete=False) as tmp:
            tmp.write(self.sample_code)
            tmp.flush()

            new_code = remove_ray_remote_decorator(tmp.name,
                                                   ["foo", "Trainer"])
            tree = ast.parse(new_code)

            # foo should have no decorator
            foo_node = [
                n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "foo"
            ][0]
            assert all(not is_ray_remote_decorator(d)
                       for d in foo_node.decorator_list)

            # Trainer class should have no decorator
            trainer_node = [
                n for n in tree.body
                if isinstance(n, ast.ClassDef) and n.name == "Trainer"
            ][0]
            assert all(not is_ray_remote_decorator(d)
                       for d in trainer_node.decorator_list)

            # bar should still have its decorator
            bar_node = [
                n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "bar"
            ][0]
            assert any(
                is_ray_remote_decorator(d) for d in bar_node.decorator_list)

    def test_modify_ray_remote_decorator(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".py",
                                         delete=False) as tmp:
            tmp.write(self.sample_code)
            tmp.flush()

            new_code = modify_ray_remote_decorator(tmp.name, "bar",
                                                   {'num_cpus': 4})
            tree = ast.parse(new_code)

            # bar should now have num_cpus=4
            bar_node = [
                n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "bar"
            ][0]
            assert any(
                is_ray_remote_decorator(d) and d.keywords[0].arg == 'num_cpus'
                and d.keywords[0].value.n == 4
                for d in bar_node.decorator_list)


class TestRayTransformer(unittest.TestCase):

    def setUp(self):
        # Original script to be transformed
        self.original_code = '''
class DataModule:
    def __init__(self, filepath, train_donors):
        self.filepath = filepath
        self.train_donors = train_donors

    def _load_train_data(self):
        adata = sc.read_h5ad(self.filepath)
        return adata[adata.obs.DonorID.isin(self.train_donors)]

    def get_X_train(self):
        train_data = self._load_train_data()
        X_train = train_data.X.astype('float32')
        return X_train

    def get_Y_train(self):
        train_data = self._load_train_data()
        y_train = train_data.obs['Treatment']
        return y_train
FILEPATH = "/some/path/file.h5ad"
TRAIN_DONORS = ['D1', 'D2']
def main():
    data = DataModule(filepath=FILEPATH, train_donors=TRAIN_DONORS)
    print("Data loaded")

    X = data.get_X_train()
    Y = data.get_Y_train()
'''

        # Expected transformed script
        self.expected_code = '''import ray
ray.init()
@ray.remote
class DataModule:

    def __init__(self, filepath, train_donors):
        self.filepath = filepath
        self.train_donors = train_donors

    def _load_train_data(self):
        adata = sc.read_h5ad(self.filepath)
        return adata[adata.obs.DonorID.isin(self.train_donors)]

    def get_X_train(self):
        train_data = self._load_train_data()
        X_train = train_data.X.astype('float32')
        return X_train

    def get_Y_train(self):
        train_data = self._load_train_data()
        y_train = train_data.obs['Treatment']
        return y_train

    def cleanup(self):
        ray.actor.exit_actor()


FILEPATH = "/some/path/file.h5ad"
TRAIN_DONORS = ['D1', 'D2']


def main():
    data = DataModule.remote(filepath=FILEPATH, train_donors=TRAIN_DONORS)
    print("Data loaded")
    X = ray.get(data.get_X_train.remote())
    Y = ray.get(data.get_Y_train.remote())
    ray.get(data.cleanup.remote())
'''

    def normalize(self, code: str) -> str:
        code = code.replace("'", '"')  # unify single and double quotes
        return "\n".join(line.strip() for line in code.strip().splitlines()
                         if line.strip())

    def test_transformation(self):
        transformer = RayTransformer()
        tree = ast.parse(self.original_code)
        transformer = RayTransformer()
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)

        transformed_code = "import ray\nray.init()\n" + astor.to_source(
            new_tree)
        # Normalize whitespace for comparison
        self.assertEqual(self.normalize(transformed_code),
                         self.normalize(self.expected_code))
