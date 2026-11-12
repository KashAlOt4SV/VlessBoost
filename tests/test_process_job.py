import subprocess
import sys
import unittest
from app.process_job import ChildJob


@unittest.skipUnless(sys.platform == "win32", "Windows Job Objects")
class ChildLifecycleTests(unittest.TestCase):
    def test_closing_our_job_stops_our_child(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        job = ChildJob(child)
        try:
            self.assertIsNotNone(job.handle)
            job.close()
            child.wait(timeout=3)
            self.assertIsNotNone(child.returncode)
        finally:
            job.close()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
