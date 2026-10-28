from shared.sensors import find_sensor, iter_json_objects

NAMES = [
    "Dynamic Sensor Manager",
    "lsm6dso Accelerometer Non-wakeup",
    "lsm6dso Gyroscope Non-wakeup",
    "lsm6dso Gyroscope-Uncalibrated Non-wakeup",
    "stk_stk3bcx Ambient Light Sensor Wakeup",
    "stk_stk3bcx Ambient Light Sensor Non-wakeup",
    "linear_acceleration",
]


def test_find_sensor():
    assert find_sensor(NAMES, "accelerometer") == "lsm6dso Accelerometer Non-wakeup"
    assert find_sensor(NAMES, "gyroscope") == "lsm6dso Gyroscope Non-wakeup"
    assert find_sensor(NAMES, "light") == "stk_stk3bcx Ambient Light Sensor Non-wakeup"
    assert find_sensor(NAMES, "barometer") is None


def test_parse_objek_json_berurutan_dan_terpotong():
    text = '{\n "a": {"values": [1, 2, 3]}\n}\n{\n "b": {"values": [4]}\n}\n{"c": {"va'
    objs, rest = iter_json_objects(text)
    assert len(objs) == 2 and "a" in objs[0] and "b" in objs[1]
    assert rest.startswith('{"c"')
    objs2, rest2 = iter_json_objects(rest + 'lues": [5]}}')
    assert len(objs2) == 1 and rest2 == ""


def test_parse_mengabaikan_sampah_di_depan():
    objs, rest = iter_json_objects('warning!!\n{"a": {"values": [1]}}')
    assert len(objs) == 1 and rest == ""
