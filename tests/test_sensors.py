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


def test_nama_sensor_xiaomi():
    from shared.sensors import find_sensor
    names = ["lsm6dso_acc", "qmc6308", "lsm6dso_gyro", "tcs3701_l", "tcs3701_p", "LINEARACCEL",
             "UNCALI_ACC", "UNCALI_GYRO", "als_factory_str"]
    assert find_sensor(names, ("accelerometer", "_acc", "accel")) == "lsm6dso_acc"
    assert find_sensor(names, ("gyroscope", "_gyro", "gyro")) == "lsm6dso_gyro"
    assert find_sensor(names, ("light", "ambient", "_l")) == "tcs3701_l"


def test_nama_sensor_lama_tetap_jalan():
    from shared.sensors import find_sensor
    names = ["lsm6dso Accelerometer Non-wakeup", "lsm6dso Gyroscope Non-wakeup",
             "stk_stk3bcx Ambient Light Sensor Non-wakeup", "stk_stk3bcx Ambient Light Sensor Wakeup"]
    assert find_sensor(names, ("accelerometer", "_acc")) == names[0]
    assert find_sensor(names, ("gyroscope", "_gyro")) == names[1]
    assert find_sensor(names, ("light", "ambient")) == names[2]
