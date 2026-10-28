from shared.sensors import MotionSample


def make_samples(n, dt, accel=(0.0, 0.0, 9.81), gyro=(0.0, 0.0, 0.0), t0=0.0):
    """Buat n sampel bergaya sensor dengan jeda dt detik."""
    return [MotionSample(t0 + i * dt, accel, gyro) for i in range(n)]
