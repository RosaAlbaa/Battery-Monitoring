import json

from battery_monitoring import bluetooth, logitech, razer
from battery_monitoring.model import Device
from battery_monitoring.scanner import Alerts, Scanner
from battery_monitoring.tray import draw_icon, lowest, tooltip


def frame(values):
    b = bytearray(64)
    for i, v in values.items():
        b[i] = v
    b[62] = razer.checksum(b)
    return bytes(b)


def test_blackshark_query_frames_match_synapse_capture():
    assert razer.make_frame(razer.CLASS_INIT, razer.DIR_WAKE)[62] == 0x64
    assert razer.make_frame(razer.CLASS_CHARGING, razer.DIR_WAKE)[62] == 0x4C
    assert razer.make_frame(razer.CLASS_CHARGING)[62] == 0xCC
    assert razer.make_frame(razer.CLASS_BATTERY)[62] == 0xC7


def test_blackshark_battery_reply():
    reply = frame({0: 2, 1: 2, 2: 0x60, 6: 5, 9: 0x80, 10: 0x21, 11: 1, 12: 1, 13: 0x61})
    assert reply[62] == 0xA5
    assert razer.parse_frame(reply) == (0x21, 97)


def test_blackshark_bad_checksum_rejected():
    reply = bytearray(frame({0: 2, 10: 0x21, 11: 1, 12: 1, 13: 50}))
    reply[62] ^= 1
    assert razer.parse_frame(reply) is None


def test_blackshark_candidate_by_name():
    info = {"usage_page": 0xFF14, "usage": 1, "product_id": 0x0999,
            "product_string": "Razer BlackShark Example"}
    assert razer.is_candidate(info)
    assert not razer.is_candidate(dict(info, usage_page=0xFF00))
    assert not razer.is_candidate(dict(info, product_string="Razer Viper"))
    assert razer.is_candidate(dict(info, product_string=""), extra_pids={0x0999})


def test_logitech_unified_battery():
    assert logitech.parse_battery(logitech.F_UNIFIED, [85, 8, 0, 0]) == (85, False)
    assert logitech.parse_battery(logitech.F_UNIFIED, [40, 4, 1, 0]) == (40, True)
    assert logitech.parse_battery(logitech.F_UNIFIED, [0, 2, 0, 0]) == (20, False)
    assert logitech.parse_battery(logitech.F_UNIFIED, [0, 0, 0, 0]) == (None, False)


def test_logitech_voltage():
    assert logitech.parse_battery(logitech.F_VOLTAGE, [0x0F, 0xFF, 0x00]) == (logitech.voltage_to_percent(4095), False)
    assert logitech.parse_battery(logitech.F_VOLTAGE, [0xFF, 0xFF, 0x00]) == (None, False)
    assert logitech.voltage_to_percent(4300) == 100
    assert logitech.voltage_to_percent(3400) == 0


def test_logitech_groups_by_receiver_instance():
    path = b"\\\\?\\hid#vid_046d&pid_c54d&mi_02&col0%d#7&1234abcd&0&000%d#{x}"
    infos = [
        {"product_id": 0xC54D, "usage_page": 0xFF00, "usage": 1, "path": path % (1, 0)},
        {"product_id": 0xC54D, "usage_page": 0xFF00, "usage": 2, "path": path % (2, 1)},
        {"product_id": 0xC54D, "usage_page": 0x0001, "usage": 2, "path": b"other"},
    ]
    groups = logitech.group_collections(infos)
    assert list(groups) == [(0xC54D, "7&1234abcd&0")]
    assert set(groups[(0xC54D, "7&1234abcd&0")]) == {1, 2}


def test_bluetooth_snapshot_only_connected_with_battery():
    data = {
        "devs": [
            {"id": "BTHENUM\\DEV_A1B2C3D4E5F6\\7&1&0&BLUETOOTHDEVICE_A1B2C3D4E5F6", "name": "Example Keyboard"},
            {"id": "BTHLE\\DEV_112233445566\\7&2", "name": "Old Headset"},
            {"id": "BTHENUM\\DEV_AABBCCDDEEFF\\x", "name": "Speaker"},
        ],
        "props": [
            {"id": "BTHENUM\\DEV_A1B2C3D4E5F6\\7&1&0&BLUETOOTHDEVICE_A1B2C3D4E5F6", "data": 64},
            {"id": "BTHLE\\DEV_112233445566\\7&2", "data": 30},
        ],
        "conn": [
            {"addr": "A1B2C3D4E5F6", "conn": True, "le": False, "cls": 0x0540, "err": None},
            {"addr": "112233445566", "conn": False, "le": True, "cls": None, "err": None},
            {"addr": "AABBCCDDEEFF", "conn": True, "le": False, "cls": None, "err": None},
        ],
        "winrt_error": None,
    }
    out = bluetooth.parse_snapshot(json.loads(json.dumps(data)), [])
    assert [(d.name, d.level, d.kind) for d in out] == [("Example Keyboard", 64, "keyboard")]


def test_bluetooth_single_objects_from_powershell():
    data = {"devs": {"id": "BTHENUM\\DEV_A1B2C3D4E5F6\\x", "name": "Headset"},
            "props": {"id": "BTHENUM\\DEV_A1B2C3D4E5F6\\x", "data": 80},
            "conn": {"addr": "A1B2C3D4E5F6", "conn": True, "le": False, "cls": 0x0418},
            "winrt_error": None}
    out = bluetooth.parse_snapshot(data, [])
    assert out[0].level == 80 and out[0].kind == "headset"


class FakeReader:
    def __init__(self, name, batches):
        self.name, self.batches, self.diag = name, list(batches), []

    def read(self):
        item = self.batches.pop(0)
        if isinstance(item, Exception):
            raise item
        return [Device(**vars(d)) for d in item]

    def close(self):
        pass


def test_scanner_marks_missing_offline_and_keeps_on_error():
    mouse = Device("m", "Example Mouse", "mouse", 80, source="Logitech")
    bt = Device("b", "Keyboard", "keyboard", 50, source="Bluetooth")
    s = Scanner([FakeReader("L", [[mouse], []]), FakeReader("B", [[bt], RuntimeError("ps")])])
    first = s.scan()
    assert all(d.online for d in first)
    second = {d.key: d for d in s.scan()}
    assert second["m"].online is False
    assert second["b"].online is True


def test_alerts_once_until_recharged():
    a = Alerts(20)
    d = Device("m", "Mouse", "mouse", 19)
    assert [x.key for x in a.check([d])] == ["m"]
    assert a.check([d]) == []
    assert a.check([Device("m", "Mouse", "mouse", 15)]) == []
    assert a.check([Device("m", "Mouse", "mouse", 18, charging=True)]) == []
    assert [x.key for x in a.check([Device("m", "Mouse", "mouse", 18)])] == ["m"]
    assert a.check([Device("m", "Mouse", "mouse", 20)]) == []
    assert a.check([Device("m", "Mouse", "mouse", 15, online=False)]) == []


def test_tray_helpers():
    devs = [Device("a", "Mouse", level=70), Device("b", "Headset", level=12),
            Device("c", "Old", level=1, online=False)]
    assert lowest(devs).key == "b"
    assert "Old" not in tooltip(devs)
    for level, charging, light in ((None, False, False), (5, True, True), (100, False, False)):
        img = draw_icon(level, charging, 20, light)
        assert img.size == (64, 64)


def test_all_languages_have_every_key():
    from battery_monitoring.i18n import STRINGS, Translator
    keys = set(STRINGS["en"])
    for lang, table in STRINGS.items():
        assert set(table) == keys, lang
    assert Translator("tr").pct(20) == "%20"
    assert Translator("en").pct(20) == "20%"
    assert Translator("xx").lang == "en"
    assert Translator("es")("status.last", t="12:00") == "Último escaneo: 12:00"
