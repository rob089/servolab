// registers.h - the memory table that the bus reads and writes.
//
// The layout copies Feetech's own bus IMU (scservo_sdk/imu.py), so their SDK
// works unchanged. Multi-byte values are little endian, like on the servos.
//
//  addr  size  access  area    meaning
//   0     1    r       eeprom  firmware major version
//   1     1    r       eeprom  firmware minor version
//   3     2    r       eeprom  model number
//   5     1    rw      eeprom  ID (0..253)
//   6     1    rw      eeprom  baud rate code (0 = 1 Mbaud ... 7 = 38400, like the servos)
//  11     1    rw      eeprom  gyro range code: 0 = 250, 1 = 500, 2 = 1000, 3 = 2000 deg/s
//  12     1    rw      eeprom  accelerometer range code: 0 = 2, 1 = 4, 2 = 8, 3 = 16 g
//  13     1    rw      eeprom  sample rate code: 0 = 26, 1 = 52, 2 = 104, 3 = 208, 4 = 416, 5 = 833 Hz
//  55     1    rw      ram     lock: 1 = EEPROM writes are not saved (default after power-up)
//  56     6    r       ram     quaternion x, y, z as half floats; w = sqrt(1 - x^2 - y^2 - z^2) >= 0
//  62     2    r       ram     angular velocity x in mrad/s   (64 unused)
//  65     2    r       ram     angular velocity y in mrad/s   (67 unused)
//  68     2    r       ram     angular velocity z in mrad/s   (70 unused)
//  71     2    r       ram     acceleration x in mg (1/1000 g) (73 unused)
//  74     2    r       ram     acceleration y in mg           (76 unused)
//  77     2    r       ram     acceleration z in mg
//
// Angular velocity and acceleration use sign-magnitude like the servos: bit 15
// is the sign, bits 0..14 the size (-5 is 0x8005). The units are fixed, the
// range codes only choose the measuring range of the sensor chip.
// Feetech does not document their units; ours are our own choice.
//
// EEPROM registers take effect at once. They are kept over power-off only if
// the lock register was 0 when they were written (same as the servos).
#pragma once

#include <Arduino.h>

namespace Reg {
const uint8_t FIRMWARE_MAJOR = 0;
const uint8_t FIRMWARE_MINOR = 1;
const uint8_t MODEL_NUMBER = 3;
const uint8_t ID = 5;
const uint8_t BAUD_RATE = 6;
const uint8_t GYRO_RANGE = 11;
const uint8_t ACC_RANGE = 12;
const uint8_t SAMPLE_RATE = 13;
const uint8_t LOCK = 55;
const uint8_t QUATERNION_X = 56;
const uint8_t QUATERNION_Y = 58;
const uint8_t QUATERNION_Z = 60;
const uint8_t GYRO_X = 62;
const uint8_t GYRO_Y = 65;
const uint8_t GYRO_Z = 68;
const uint8_t ACC_X = 71;
const uint8_t ACC_Y = 74;
const uint8_t ACC_Z = 77;
}  // namespace Reg

// Reading beyond the last register returns zeros.
const int REGISTER_COUNT = 80;

// What changed through the last writes (see takeRegisterChanges()).
const uint8_t CHANGED_BAUD_RATE = 1 << 0;
const uint8_t CHANGED_IMU_SETTINGS = 1 << 1;
const uint8_t CHANGED_NEEDS_SAVING = 1 << 2;

// Fill the table with defaults, then load the saved EEPROM values from flash.
void beginRegisters();

uint8_t readRegister(uint8_t address);

// Write bytes as the bus host asked. Read-only addresses and invalid values
// (e.g. ID 254) are ignored, the rest is written.
void writeRegisters(uint8_t address, const uint8_t* data, uint8_t length);

// Restore the factory defaults (keeps the ID) and save them.
void factoryReset();

// Returns the CHANGED_... flags collected since the last call, and clears them.
uint8_t takeRegisterChanges();

// Store the EEPROM registers in flash (about 80 us, the CPU stalls meanwhile),
// so call it from the main loop, after replying.
void saveRegisters();

// Put new measurements into the table.
// quaternion: w, x, y, z.  gyro: rad/s.  acc: g.
void setMeasurements(const float quaternion[4], const float gyro[3], const float acc[3]);
