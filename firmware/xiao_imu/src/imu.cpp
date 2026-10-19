// imu.cpp - LSM6DS3TR-C driver (a few registers over I2C) and Mahony filter.
#include "imu.h"

#include <Wire.h>

#include "config.h"

// The chip sits on the XIAO's second I2C bus and has its own power pin.
static TwoWire& i2c = Wire1;
static const uint8_t I2C_ADDRESS = 0x6A;

// Chip registers (LSM6DS3TR-C datasheet, section 9)
static const uint8_t INT1_CTRL = 0x0D;
static const uint8_t WHO_AM_I = 0x0F;
static const uint8_t CTRL1_XL = 0x10;
static const uint8_t CTRL2_G = 0x11;
static const uint8_t CTRL3_C = 0x12;
static const uint8_t OUTX_L_G = 0x22;  // gyro x, y, z then accelerometer x, y, z
static const uint8_t WHO_AM_I_VALUE = 0x6A;

// Register codes -> chip settings. Index = code of our register (registers.h).
static const uint8_t GYRO_RANGE_BITS[] = {0b00, 0b01, 0b10, 0b11};        // 250 .. 2000 deg/s
static const float GYRO_MDPS_PER_COUNT[] = {8.75f, 17.5f, 35.0f, 70.0f};
static const uint8_t ACC_RANGE_BITS[] = {0b00, 0b10, 0b11, 0b01};         // 2, 4, 8, 16 g
static const float ACC_MG_PER_COUNT[] = {0.061f, 0.122f, 0.244f, 0.488f};
static const float SAMPLE_RATES_HZ[] = {26.0f, 52.0f, 104.0f, 208.0f, 416.0f, 833.0f};  // ODR bits = code + 2

// Filter gains. KP: how fast the accelerometer pulls roll/pitch back (1/s).
// KI: slowly learns what is left of the gyro offset.
static const float KP = 1.0f;
static const float KI = 0.02f;

// The accelerometer only shows "down" when the sensor is not accelerating.
// Measurements this far from 1 g are not used for the correction.
static const float GRAVITY_TOLERANCE = 0.15f;  // g

// Gyro calibration: 0.5 s of samples, accepted if no axis moved more than this.
static const float CALIBRATION_SECONDS = 0.5f;
static const float CALIBRATION_STILL = 0.03f;  // rad/s, max - min per axis

// After power-up or a settings change the gyro needs a moment to settle.
static const uint32_t SETTLE_MS = 100;

bool Imu::begin(uint8_t gyroRange, uint8_t accRange, uint8_t sampleRate) {
  pinMode(PIN_LSM6DS3TR_C_POWER, OUTPUT_H0H1);  // high drive: this pin powers the chip
  digitalWrite(PIN_LSM6DS3TR_C_POWER, HIGH);
  pinMode(PIN_LSM6DS3TR_C_INT1, INPUT);
  delay(20);

  i2c.begin();
  i2c.setClock(400000);

  uint8_t id = 0;
  ok = readRegisters(WHO_AM_I, &id, 1) && id == WHO_AM_I_VALUE;
  if (!ok) return false;

  writeRegister(CTRL3_C, 0x01);  // software reset
  delay(10);
  writeRegister(CTRL3_C, 0x44);  // BDU (high and low byte from the same sample), address auto-increment
  writeRegister(INT1_CTRL, 0x02);  // INT1 pin goes high when a new gyro sample is ready
  configure(gyroRange, accRange, sampleRate);
  return ok;
}

void Imu::configure(uint8_t gyroRange, uint8_t accRange, uint8_t sampleRate) {
  uint8_t odrBits = sampleRate + 2;
  ok = writeRegister(CTRL2_G, (odrBits << 4) | (GYRO_RANGE_BITS[gyroRange] << 2)) &&
       writeRegister(CTRL1_XL, (odrBits << 4) | (ACC_RANGE_BITS[accRange] << 2));

  gyroScale = GYRO_MDPS_PER_COUNT[gyroRange] / 1000.0f * DEG_TO_RAD;
  accScale = ACC_MG_PER_COUNT[accRange] / 1000.0f;
  nominalDt = 1.0f / SAMPLE_RATES_HZ[sampleRate];
  dt = nominalDt;
  settleUntilMs = millis() + SETTLE_MS;
  calibrationSamples = 0;  // a running calibration starts over with the new rate
}

bool Imu::update() {
  if (!ok) return false;
  if (digitalRead(PIN_LSM6DS3TR_C_INT1) == LOW) return false;  // no new sample yet

  uint8_t raw[12];
  if (!readRegisters(OUTX_L_G, raw, 12)) {
    ok = false;
    return false;
  }
  uint32_t intervalUs = microsSince(lastSampleCycles);
  lastSampleCycles = cycleCount();
  if ((int32_t)(millis() - settleUntilMs) < 0) return false;

  // The chip's clock is not exact. Follow the measured sample interval slowly
  // (single intervals jitter with our loop), within +-20 % of the nominal one.
  float measured = constrain(intervalUs * 1e-6f, 0.8f * nominalDt, 1.2f * nominalDt);
  dt += 0.01f * (measured - dt);

  for (int axis = 0; axis < 3; axis++) {
    int16_t g = (int16_t)(raw[2 * axis] | (raw[2 * axis + 1] << 8));
    int16_t a = (int16_t)(raw[6 + 2 * axis] | (raw[6 + 2 * axis + 1] << 8));
    gyro[axis] = g * gyroScale;
    acc[axis] = a * accScale;
  }

  if (!calibrated) calibrateGyro();
  for (int axis = 0; axis < 3; axis++) gyro[axis] -= gyroOffset[axis];

  if (!started) {
    startFromGravity();
  } else {
    fuse();
  }
  return true;
}

// Average the gyro while the sensor is still: that average is the offset.
// If it moved, start again (the blue LED stays on until it worked).
void Imu::calibrateGyro() {
  if (calibrationSamples == 0) {
    for (int axis = 0; axis < 3; axis++) {
      calibrationSum[axis] = 0;
      calibrationMin[axis] = gyro[axis];
      calibrationMax[axis] = gyro[axis];
    }
  }
  for (int axis = 0; axis < 3; axis++) {
    calibrationSum[axis] += gyro[axis];
    calibrationMin[axis] = min(calibrationMin[axis], gyro[axis]);
    calibrationMax[axis] = max(calibrationMax[axis], gyro[axis]);
  }
  calibrationSamples++;
  if (calibrationSamples * dt < CALIBRATION_SECONDS) return;

  bool still = true;
  for (int axis = 0; axis < 3; axis++) {
    if (calibrationMax[axis] - calibrationMin[axis] > CALIBRATION_STILL) still = false;
  }
  if (still) {
    for (int axis = 0; axis < 3; axis++) gyroOffset[axis] = calibrationSum[axis] / calibrationSamples;
    calibrated = true;
    started = false;  // start the orientation fresh with the corrected gyro
  }
  calibrationSamples = 0;
}

// Roll and pitch from the direction of gravity, yaw = 0.
void Imu::startFromGravity() {
  float roll = atan2f(acc[1], acc[2]);
  float pitch = atan2f(-acc[0], sqrtf(acc[1] * acc[1] + acc[2] * acc[2]));
  float cr = cosf(roll / 2), sr = sinf(roll / 2);
  float cp = cosf(pitch / 2), sp = sinf(pitch / 2);
  quaternion[0] = cr * cp;
  quaternion[1] = sr * cp;
  quaternion[2] = cr * sp;
  quaternion[3] = -sr * sp;
  for (int axis = 0; axis < 3; axis++) integralError[axis] = 0;
  started = true;
}

// Mahony filter: integrate the gyro, and turn it a little towards where the
// accelerometer says "up" is.
void Imu::fuse() {
  float w = quaternion[0], x = quaternion[1], y = quaternion[2], z = quaternion[3];
  float gx = gyro[0], gy = gyro[1], gz = gyro[2];

  float norm = sqrtf(acc[0] * acc[0] + acc[1] * acc[1] + acc[2] * acc[2]);
  if (fabsf(norm - 1.0f) < GRAVITY_TOLERANCE) {
    float ax = acc[0] / norm, ay = acc[1] / norm, az = acc[2] / norm;
    // "Up" in sensor coordinates, as the current quaternion sees it
    float vx = 2 * (x * z - w * y);
    float vy = 2 * (w * x + y * z);
    float vz = w * w - x * x - y * y + z * z;
    // Error = rotation from the estimated to the measured "up" (cross product)
    float ex = ay * vz - az * vy;
    float ey = az * vx - ax * vz;
    float ez = ax * vy - ay * vx;
    integralError[0] += KI * ex * dt;
    integralError[1] += KI * ey * dt;
    integralError[2] += KI * ez * dt;
    gx += KP * ex + integralError[0];
    gy += KP * ey + integralError[1];
    gz += KP * ez + integralError[2];
  }

  // q' = q + dt * 1/2 * q * (0, gx, gy, gz)
  float h = 0.5f * dt;
  quaternion[0] = w + h * (-x * gx - y * gy - z * gz);
  quaternion[1] = x + h * (w * gx + y * gz - z * gy);
  quaternion[2] = y + h * (w * gy - x * gz + z * gx);
  quaternion[3] = z + h * (w * gz + x * gy - y * gx);

  float length = sqrtf(quaternion[0] * quaternion[0] + quaternion[1] * quaternion[1] +
                       quaternion[2] * quaternion[2] + quaternion[3] * quaternion[3]);
  for (int i = 0; i < 4; i++) quaternion[i] /= length;
}

bool Imu::readRegisters(uint8_t address, uint8_t* data, int length) {
  i2c.beginTransmission(I2C_ADDRESS);
  i2c.write(address);
  if (i2c.endTransmission(false) != 0) return false;
  if (i2c.requestFrom(I2C_ADDRESS, (uint8_t)length) != length) return false;
  for (int i = 0; i < length; i++) data[i] = i2c.read();
  return true;
}

bool Imu::writeRegister(uint8_t address, uint8_t value) {
  i2c.beginTransmission(I2C_ADDRESS);
  i2c.write(address);
  i2c.write(value);
  return i2c.endTransmission() == 0;
}
