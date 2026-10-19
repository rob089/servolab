// imu.h - the XIAO Sense's LSM6DS3TR-C (gyro + accelerometer) and the
// orientation filter that turns its measurements into a quaternion.
//
// Axes are the chip's axes as soldered on the XIAO. The quaternion rotates
// from the sensor frame into a world frame whose z axis points up (against
// gravity). Without a magnetometer, the heading (yaw) is relative to the
// heading at power-up and drifts slowly, like Feetech's chip.
#pragma once

#include <Arduino.h>

class Imu {
 public:
  // Power the chip and set it up. Returns false if it does not answer.
  // The codes are the ones of the registers (see registers.h).
  bool begin(uint8_t gyroRange, uint8_t accRange, uint8_t sampleRate);

  // Change ranges or sample rate while running.
  void configure(uint8_t gyroRange, uint8_t accRange, uint8_t sampleRate);

  // Read a new sample if there is one and update the orientation.
  // Returns true if there was a new sample.
  bool update();

  bool ok = false;           // the chip answers
  bool calibrated = false;   // the gyro offset is known
  float gyro[3] = {0, 0, 0};          // rad/s, offset removed
  float acc[3] = {0, 0, 0};           // g
  float quaternion[4] = {1, 0, 0, 0};  // w, x, y, z

 private:
  bool readRegisters(uint8_t address, uint8_t* data, int length);
  bool writeRegister(uint8_t address, uint8_t value);
  void calibrateGyro();
  void startFromGravity();
  void fuse();

  float gyroScale = 0;   // rad/s per count
  float accScale = 0;    // g per count
  float nominalDt = 0;   // s between samples, from the data sheet
  float dt = 0;          // s between samples, measured
  uint32_t lastSampleCycles = 0;
  uint32_t settleUntilMs = 0;
  float gyroOffset[3] = {0, 0, 0};
  float integralError[3] = {0, 0, 0};
  bool started = false;  // quaternion initialised from gravity

  // Gyro calibration: average while the sensor is still.
  int calibrationSamples = 0;
  float calibrationSum[3];
  float calibrationMin[3];
  float calibrationMax[3];
};
