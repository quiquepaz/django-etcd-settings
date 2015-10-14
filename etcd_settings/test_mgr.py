import datetime
from mock import MagicMock
from etcd import EtcdResult
from .manager import EtcdConfigManager
from django.test import TestCase


class EtcdResultGenerator():

    @staticmethod
    def key(name, value):
        d = dict(
            key=name,
            value=value,
            expiration=None,
            ttl=None,
            modifiedIndex=5,
            createdIndex=1,
            newKey=False,
            dir=False,
        )
        return d

    @staticmethod
    def result_set(dirname, keys):
        dir_keys = keys
        for k in dir_keys:
            key_name = k['key']
            k['key'] = '{}{}'.format(dirname, key_name)
        d = dict(node=dict(
            key=dirname,
            expiration=None,
            ttl=None,
            modifiedIndex=6,
            createdIndex=2,
            newKey=False,
            dir=True,
            nodes=dir_keys
        ))
        res = EtcdResult(**d)
        res.etcd_index = 99
        return res


class TestEtcdConfigManager(TestCase):

    def _dataset_for_defaults(self, env):
        expected = {
            'FOO_BAR': 'baz',
            'FOO_BAZ': 'bar',
            'FOOBARBAZ': 'superbaz',
        }
        keys = [EtcdResultGenerator.key('/foo/bar', '"baz"'),
                EtcdResultGenerator.key('/foo/baz', '"bar"'),
                EtcdResultGenerator.key('/foobarbaz', '"superbaz"')]
        rset = EtcdResultGenerator.result_set(
            self.mgr._env_defaults_path(env),
            keys)
        return expected, rset

    def _dataset_for_configsets(self):
        expected = {
            'foo': {'BAR': 1, 'BAZ': 2},
            'foo.bar': {'BAZ': 1, 'BAZBAZ': 2},
        }
        keys = [EtcdResultGenerator.key('/foo/bar', '1'),
                EtcdResultGenerator.key('/foo/baz', '2'),
                EtcdResultGenerator.key('/foo.bar/baz', '1'),
                EtcdResultGenerator.key('/foo.bar/bazbaz', '2')]
        rset = EtcdResultGenerator.result_set(
            self.mgr._base_config_set_path,
            keys)
        return expected, rset

    def setUp(self):
        self.mgr = EtcdConfigManager(
            'prefix', protocol='foo', host='foo', port=0)

    def test_encode_config_key(self):
        self.assertEqual(
            'foo/bar/baz',
            self.mgr._encode_config_key('FOO_BAR_BAZ'))

    def test_decode_env_config_key(self):
        key = 'FOO_BAR'
        env = 'test'
        s = '{}/{}/foo/bar'.format(self.mgr._base_config_path, env)
        self.assertEqual((env, key), self.mgr._decode_config_key(s))

    def test_decode_set_config_key(self):
        key = 'FOO_BAR'
        configset = 'unit.test'
        s = '{}/{}/foo/bar'.format(self.mgr._base_config_set_path, configset)
        self.assertEqual((configset, key), self.mgr._decode_config_key(s))

    def test_encode_config_value(self):
        self.assertEqual(
            '"abcde"',
            self.mgr._encode_config_value('abcde'))
        self.assertEqual(
            '112',
            self.mgr._encode_config_value(112))
        self.assertEqual(
            '{"foo": 1, "bar": "baz"}',
            self.mgr._encode_config_value(dict(foo=1, bar='baz')))
        self.assertEqual(
            # Tuples are lost in encoding, should be avoided as config values
            '[1, "b"]',
            self.mgr._encode_config_value((1, 'b')))

    def test_decode_config_value(self):
        self.assertEqual(
            'abcde',
            self.mgr._decode_config_value('"abcde"'))
        self.assertEqual(
            112,
            self.mgr._decode_config_value('112'))
        self.assertEqual(
            dict(foo=1, bar='baz'),
            self.mgr._decode_config_value('{"foo": 1, "bar": "baz"}'))
        self.assertEqual(
            [1, 'b'],
            self.mgr._decode_config_value('[1, "b"]'))

    def test_custom_encoding_decoding_values(self):
        d = datetime.datetime(2015, 10, 9, 8, 7, 6)
        encoded_d = self.mgr._encode_config_value(d)
        decoded_d = self.mgr._decode_config_value(encoded_d)
        self.assertEqual(True, isinstance(decoded_d, datetime.datetime))
        self.assertEqual(d.isoformat(), decoded_d.isoformat())
        self.assertEqual(d, decoded_d)

    def test_get_env_defaults(self):
        env = 'test'
        expected, rset = self._dataset_for_defaults(env)
        env_path = self.mgr._env_defaults_path(env)
        self.mgr._client.read = MagicMock(return_value=rset)
        self.assertEqual(expected, self.mgr.get_env_defaults('test'))
        self.mgr._client.read.assert_called_with(env_path, recursive=True)

    def test_get_config_sets(self):
        expected, rset = self._dataset_for_configsets()
        self.mgr._client.read = MagicMock(return_value=rset)
        self.assertEqual(expected, self.mgr.get_config_sets())
        self.mgr._client.read.assert_called_with(
            self.mgr._base_config_set_path,
            recursive=True)

    def test_monitor_env_defaults(self):
        env = 'test'
        expected, rset = self._dataset_for_defaults(env)
        d = {}
        self.mgr._client.eternal_watch = MagicMock(return_value=[rset])
        old_etcd_index = self.mgr._etcd_index
        t = self.mgr.monitor_env_defaults(env=env, conf=d)
        self.assertEqual(None, t.result)
        self.assertEqual(expected, d)
        self.assertEqual(99, self.mgr._etcd_index)
        self.mgr._client.eternal_watch.assert_called_with(
            self.mgr._env_defaults_path(env),
            index=old_etcd_index,
            recursive=True)

    def test_monitor_config_sets(self):
        expected, rset = self._dataset_for_configsets()
        d = {}
        self.mgr._client.eternal_watch = MagicMock(return_value=[rset])
        old_etcd_index = self.mgr._etcd_index
        t = self.mgr.monitor_config_sets(conf=d)
        self.assertEqual(None, t.result)
        self.assertEqual(expected, d)
        self.assertEqual(99, self.mgr._etcd_index)
        self.mgr._client.eternal_watch.assert_called_with(
            self.mgr._base_config_set_path,
            index=old_etcd_index,
            recursive=True)