from unittest.mock import MagicMock, patch
from django.test import TestCase
from .job_registry import JobRegistry, job

# Create your tests here.

## AI Generated

class TestJobRegistryInit(TestCase):

    def test_valid_triggers(self):
        for trigger in ("date", "interval", "cron"):
            registry = JobRegistry(trigger)
            self.assertEqual(registry.trigger, trigger)

    def test_invalid_trigger_raises(self):
        with self.assertRaises(ValueError):
            JobRegistry("invalid_trigger")

    def test_id_and_name_removed_from_kwargs(self):
        registry = JobRegistry("interval", id="my_id", name="my_name", seconds=10)
        self.assertNotIn("id", registry.kwargs)
        self.assertNotIn("name", registry.kwargs)
        self.assertIn("seconds", registry.kwargs)

    def test_custom_logger_is_used(self):
        custom_logger = MagicMock()
        registry = JobRegistry("interval", logger=custom_logger)
        self.assertEqual(registry._logger, custom_logger)

    def test_default_logger_created(self):
        registry = JobRegistry("interval")
        self.assertEqual(registry._logger.name, "JobRegistry")


class TestJobRegistryCall(TestCase):

    def _make_registry(self, trigger="interval", **kwargs):
        registry = JobRegistry(trigger, **kwargs)
        registry._logger = MagicMock()
        return registry

    def test_call_registers_function(self):
        registry = self._make_registry(seconds=10)

        @registry
        def my_job():
            pass

        self.assertEqual(registry.function, my_job)

    def test_call_returns_original_function(self):
        registry = self._make_registry(seconds=10)

        def my_job():
            pass

        result = registry(my_job)
        self.assertIs(result, my_job)

    def test_call_raises_on_non_callable(self):
        registry = self._make_registry(seconds=10)
        with self.assertRaises(TypeError):
            registry("not_a_function")

    def test_call_logs_registration(self):
        registry = self._make_registry(seconds=10)

        def my_job():
            pass

        registry(my_job)
        registry._logger.info.assert_called_once()


class TestJobRegistryProperties(TestCase):

    def setUp(self):
        self.registry = JobRegistry("interval", seconds=10)
        self.registry._logger = MagicMock()

        def my_job():
            pass

        self.registry(my_job)

    def test_name_format(self):
        self.assertIn("my_job", self.registry.name)
        self.assertIn(".", self.registry.name)

    def test_id_is_string(self):
        self.assertIsInstance(self.registry.id, str)

    def test_id_is_deterministic(self):
        registry2 = JobRegistry("interval", seconds=10)
        registry2._logger = MagicMock()

        def my_job():
            pass

        registry2(my_job)
        self.assertEqual(self.registry.id, registry2.id)

    def test_id_changes_with_different_kwargs(self):
        registry2 = JobRegistry("interval", seconds=99)
        registry2._logger = MagicMock()

        def my_job():
            pass

        registry2(my_job)
        self.assertNotEqual(self.registry.id, registry2.id)

    def test_repr_format(self):
        repr_str = repr(self.registry)
        self.assertIn("Job", repr_str)
        self.assertIn("my_job", repr_str)
        self.assertIn("interval", repr_str)


class TestJobRegistryHashAndEquality(TestCase):

    def _make_job(self, fn_name="my_job", trigger="interval", **kwargs):
        registry = JobRegistry(trigger, **kwargs)
        registry._logger = MagicMock()
        fn = MagicMock()
        fn.__name__ = fn_name
        fn.__module__ = "test_module"
        registry(fn)
        return registry

    def test_equal_jobs(self):
        job1 = self._make_job(seconds=10)
        job2 = self._make_job(seconds=10)
        self.assertEqual(job1, job2)

    def test_different_jobs_not_equal(self):
        job1 = self._make_job(seconds=10)
        job2 = self._make_job(seconds=20)
        self.assertNotEqual(job1, job2)

    def test_hash_equal_jobs(self):
        job1 = self._make_job(seconds=10)
        job2 = self._make_job(seconds=10)
        self.assertEqual(hash(job1), hash(job2))

    def test_set_deduplication(self):
        job1 = self._make_job(seconds=10)
        job2 = self._make_job(seconds=10)
        job3 = self._make_job(seconds=99)
        result = {job1, job2, job3}
        self.assertEqual(len(result), 2)

    def test_not_equal_to_other_type(self):
        job1 = self._make_job(seconds=10)
        self.assertNotEqual(job1, "not_a_job")


class TestJobRegistrySetAlgo(TestCase):

    def tearDown(self):
        JobRegistry.set_algo("sha256")

    def test_valid_algo(self):
        JobRegistry.set_algo("md5")
        registry = JobRegistry("interval", seconds=5)
        registry._logger = MagicMock()
        fn = MagicMock()
        fn.__name__ = "my_job"
        fn.__module__ = "test"
        registry(fn)
        # md5 produces 32 char hex
        self.assertEqual(len(registry.id), 32)

    def test_invalid_algo_falls_back_to_sha256(self):
        JobRegistry.set_algo("not_an_algo")
        registry = JobRegistry("interval", seconds=5)
        registry._logger = MagicMock()
        fn = MagicMock()
        fn.__name__ = "my_job"
        fn.__module__ = "test"
        registry(fn)
        # sha256 produces 64 char hex
        self.assertEqual(len(registry.id), 64)


class TestJobAlias(TestCase):

    def test_job_is_alias_for_job_registry(self):
        self.assertIs(job, JobRegistry)