"""Regression tests for firmware/proxy GATT handle differences, without HA installed."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/mysmartblinds_ble'


def load_api():
    names = ['bleak', 'bleak.exc', 'bleak_retry_connector', 'homeassistant',
             'homeassistant.components', 'homeassistant.components.bluetooth', 'homeassistant.core',
             '_blind_test']
    mods = {name: ModuleType(name) for name in names}
    mods['bleak'].BleakClient = object
    mods['bleak.exc'].BleakCharacteristicNotFoundError = type('Missing', (Exception,), {})
    mods['bleak_retry_connector'].establish_connection = AsyncMock()
    mods['homeassistant.core'].HomeAssistant = object
    mods['homeassistant.components'].bluetooth = mods['homeassistant.components.bluetooth']
    mods['_blind_test'].__path__ = [str(ROOT)]
    with patch.dict(sys.modules, mods):
        for name in ['const', 'api']:
            spec = importlib.util.spec_from_file_location('_blind_test.' + name, ROOT / (name + '.py'))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
        return mod


api = load_api()


def char(handle, uuid, props=('write',)):
    return NS(handle=handle, uuid=uuid, properties=props)


def client(*chars):
    return NS(services=[NS(characteristics=chars)], is_connected=True,
              write_gatt_char=AsyncMock(), disconnect=AsyncMock())


class Endpoints(unittest.IsolatedAsyncioTestCase):
    async def test_kitchen_ignores_wrong_uuid_at_old_handle(self):
        motor = client(char(18, api.UUID_KEY), char(21, api.UUID_SET),
                       char(31, '00001501-1212-efde-1600-785feabcd123'))
        result = await api._async_resolve_backend_characteristic(motor, 31, api.UUID_SET, 'set')
        self.assertEqual(result.handle, 21)

    async def test_bedroom_shifted_handles(self):
        motor = client(char(26, api.UUID_KEY), char(30, api.UUID_SET))
        key = await api._async_resolve_backend_characteristic(motor, 27, api.UUID_KEY, 'key')
        target = await api._async_resolve_backend_characteristic(motor, 31, api.UUID_SET, 'set')
        self.assertEqual((key.handle, target.handle), (26, 30))

    async def test_missing_uuid_refuses_nearby_writable_handle(self):
        with self.assertRaises(api.MySmartBlindsCharacteristicError):
            await api._async_resolve_backend_characteristic(client(char(31, 'wrong')), 31, api.UUID_SET, 'set')

    async def test_read_only_target_is_rejected(self):
        with self.assertRaises(api.MySmartBlindsCharacteristicError):
            await api._async_resolve_backend_characteristic(client(char(21, api.UUID_SET, ('read',))), 31, api.UUID_SET, 'set')

    async def test_duplicate_uuid_is_rejected(self):
        with self.assertRaises(api.MySmartBlindsCharacteristicError):
            await api._async_resolve_backend_characteristic(client(char(21, api.UUID_SET), char(30, api.UUID_SET)), 31, api.UUID_SET, 'set')

    async def test_write_authenticates_then_moves_and_disconnects(self):
        motor = client(char(18, api.UUID_KEY), char(21, api.UUID_SET), char(31, 'wrong'))
        blind = api.MySmartBlindsApi(None, 'D1:2A:2C:7C:BF:D2', '010203040506')
        with patch.object(api.bluetooth, 'async_ble_device_from_address', return_value=object(), create=True), patch.object(api, 'establish_connection', AsyncMock(return_value=motor)):
            await blind.async_open()
        calls = motor.write_gatt_char.await_args_list
        self.assertEqual([(c.args[0].handle, c.args[1]) for c in calls], [(18, bytes.fromhex('010203040506')), (21, bytes([100]))])
        motor.disconnect.assert_awaited_once()
        self.assertEqual(blind.state.resolved_set_handle, 21)

    async def test_invalid_target_sends_no_writes_or_optimistic_update(self):
        motor = client(char(18, api.UUID_KEY), char(31, 'wrong'))
        blind = api.MySmartBlindsApi(None, 'D1:2A:2C:7C:BF:D2', '01')
        blind.state.native_position = 200
        with patch.object(api.bluetooth, 'async_ble_device_from_address', return_value=object(), create=True), patch.object(api, 'establish_connection', AsyncMock(return_value=motor)):
            with self.assertRaises(api.MySmartBlindsConnectionError):
                await blind.async_open()
        motor.write_gatt_char.assert_not_awaited()
        motor.disconnect.assert_awaited_once()
        self.assertEqual(blind.state.native_position, 200)

    async def test_advertisement_does_not_clear_command_error(self):
        blind = api.MySmartBlindsApi(None, 'D1:2A:2C:7C:BF:D2', '01')
        blind.state.last_error = 'write failed'
        with patch.object(blind, 'is_device_present', return_value=True):
            await blind.async_refresh_availability()
        self.assertEqual(blind.state.last_error, 'write failed')


if __name__ == '__main__':
    unittest.main()
