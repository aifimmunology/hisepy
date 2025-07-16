import unittest
import ast
import astor
import sys

sys.path.insert(0, '../')  # Adjust path as needed to locate your RayTransformer
from hisepy.ray_transformer import RayTransformer


class TestRayTransformer(unittest.TestCase):

    def normalize(self, code: str) -> str:
        """Utility to normalize code strings for comparison."""
        return "\n".join(line.strip() for line in code.strip().splitlines() if line.strip())

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

        transformed_code = "import ray\nray.init()\n" + astor.to_source(new_tree)
        self.assertEqual(self.normalize(transformed_code), self.normalize(expected_transformed))
        
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

        transformed_code = "import ray\nray.init()\n" + astor.to_source(new_tree)
        self.assertEqual(self.normalize(transformed_code), self.normalize(expected_transformed))


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

        transformed_code = "import ray\nray.init()\n" + astor.to_source(new_tree)
        self.assertEqual(self.normalize(transformed_code), self.normalize(expected_transformed))


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

        transformed_code = "import ray\nray.init()\n" + astor.to_source(new_tree)
        self.assertEqual(self.normalize(transformed_code), self.normalize(expected_transformed))