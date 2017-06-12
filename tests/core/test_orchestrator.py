# stdlib
import unittest
import os

# 3rd party
import mock

# project
from utils.orchestrator import MesosUtil, BaseUtil

CO_ID = 1234


class TestMesosUtil(unittest.TestCase):
    @mock.patch('docker.Client.__init__')
    def test_extract_tags(self, mock_init):
        mock_init.return_value = None
        mesos = MesosUtil()

        env = ["CHRONOS_JOB_NAME=test-job",
               "MARATHON_APP_ID=/system/dd-agent",
               "MESOS_TASK_ID=system_dd-agent.dcc75b42-4b87-11e7-9a62-70b3d5800001"]

        tags = ['chronos_job:test-job', 'marathon_app:/system/dd-agent',
                'mesos_task:system_dd-agent.dcc75b42-4b87-11e7-9a62-70b3d5800001']

        container = {'Config': {'Env': env}}

        self.assertEqual(sorted(tags), sorted(mesos._get_cacheable_tags(CO_ID, co=container)))

    @mock.patch.dict(os.environ, {"MESOS_TASK_ID": "test"})
    def test_detect(self):
        self.assertTrue(MesosUtil.is_detected())

    @mock.patch.dict(os.environ, {})
    def test_no_detect(self):
        self.assertFalse(MesosUtil.is_detected())


class TestBaseUtil(unittest.TestCase):
    class DummyUtil(BaseUtil):
        def _get_cacheable_tags(self, cid, co=None):
            return ["test:tag"]

    class NeedLabelsUtil(BaseUtil):
        def __init__(self):
            BaseUtil.__init__(self)
            self.needs_inspect_labels = True

        def _get_cacheable_tags(self, cid, co=None):
            return ["test:tag"]

    class NeedEnvUtil(BaseUtil):
        def __init__(self):
            BaseUtil.__init__(self)
            self.needs_inspect_config = True

        def _get_cacheable_tags(self, cid, co=None):
            return ["test:tag"]

    @mock.patch('docker.Client.__init__')
    def test_extract_tags(self, mock_init):
        mock_init.return_value = None
        dummy = self.DummyUtil()
        dummy.reset_cache()

        self.assertEqual(["test:tag"], dummy.get_container_tags(cid=CO_ID))

    @mock.patch('docker.Client.__init__')
    def test_cache_invalidation_event(self, mock_init):
        mock_init.return_value = None
        dummy = self.DummyUtil()
        dummy.reset_cache()

        dummy.get_container_tags(cid=CO_ID)
        self.assertTrue(CO_ID in dummy._container_tags_cache)

        EVENT = {'status': 'die', 'id': CO_ID}
        dummy.invalidate_cache([EVENT])
        self.assertFalse(CO_ID in dummy._container_tags_cache)

    @mock.patch('docker.Client.__init__')
    def test_reset_cache(self, mock_init):
        mock_init.return_value = None
        dummy = self.DummyUtil()
        dummy.reset_cache()

        dummy.get_container_tags(cid=CO_ID)
        self.assertTrue(CO_ID in dummy._container_tags_cache)

        dummy.reset_cache()
        self.assertFalse(CO_ID in dummy._container_tags_cache)

    @mock.patch('docker.Client.inspect_container')
    @mock.patch('docker.Client.__init__')
    def test_auto_inspect(self, mock_init, mock_inspect):
        mock_init.return_value = None

        dummy = self.NeedLabelsUtil()
        dummy.reset_cache()

        dummy.get_container_tags(cid=CO_ID)
        mock_inspect.assert_called_once()

    @mock.patch('docker.Client.inspect_container')
    @mock.patch('docker.Client.__init__')
    def test_no_inspect_if_cached(self, mock_init, mock_inspect):
        mock_init.return_value = None

        dummy = self.NeedLabelsUtil()
        dummy.reset_cache()

        dummy.get_container_tags(cid=CO_ID)
        mock_inspect.assert_called_once()

        dummy.get_container_tags(cid=CO_ID)
        mock_inspect.assert_called_once()

    @mock.patch('docker.Client.inspect_container')
    @mock.patch('docker.Client.__init__')
    def test_no_useless_inspect(self, mock_init, mock_inspect):
        mock_init.return_value = None

        dummy = self.NeedLabelsUtil()
        dummy.reset_cache()
        co = {'Id': CO_ID, 'Created': 1, 'Labels': {}}

        dummy.get_container_tags(co=co)
        mock_inspect.assert_not_called()

        dummy.get_container_tags(co=co)
        mock_inspect.assert_not_called()

    @mock.patch('docker.Client.inspect_container')
    @mock.patch('docker.Client.__init__')
    def test_auto_env_inspect(self, mock_init, mock_inspect):
        mock_init.return_value = None

        dummy = self.NeedEnvUtil()
        dummy.reset_cache()

        dummy.get_container_tags(co={'Id': CO_ID})
        mock_inspect.assert_called_once()

    @mock.patch('docker.Client.inspect_container')
    @mock.patch('docker.Client.__init__')
    def test_no_useless_env_inspect(self, mock_init, mock_inspect):
        mock_init.return_value = None

        dummy = self.NeedEnvUtil()
        dummy.reset_cache()

        dummy.get_container_tags(co={'Id': CO_ID, 'Config': {'Env': {1: 1}}})
        mock_inspect.assert_not_called()
