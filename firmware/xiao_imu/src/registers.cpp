// registers.cpp - the memory table, its rules and how it is saved in flash.
#include "registers.h"

#include <string.h>

#include "config.h"

static uint8_t table[REGISTER_COUNT];
static uint8_t changes = 0;

// The EEPROM registers as they should be in flash. Differs from `table` when
// something was written while locked (in effect now, but not kept).
static uint8_t stored[REGISTER_COUNT];

// ---------------------------------------------------------------------------
// Flash storage of the EEPROM registers
// ---------------------------------------------------------------------------
// One flash page is used as a log of 8-byte records; the newest record wins.
// Saving appends a record (two 32-bit words, about 80 us). Erasing the page
// stalls the CPU for up to 85 ms (the bus would miss requests), so we only
// erase when the page is full, and preferably at power-up.
//
// 0xED000 is the first page after the program area. Adafruit's InternalFS
// would use it; we do not use InternalFS.
static const uint32_t SETTINGS_PAGE = 0xED000;
static const int RECORD_COUNT = 4096 / 8;
static const uint8_t RECORD_MAGIC = 0xA5;  // change when the layout changes

struct Record {
  uint8_t magic;
  uint8_t id;
  uint8_t baud_rate;
  uint8_t gyro_range;
  uint8_t acc_range;
  uint8_t sample_rate;
  uint8_t checksum;
  uint8_t zero;  // keeps a valid record from looking erased (all 0xFF)
};

static int nextRecord = 0;  // index of the first free record

static const Record* storedRecords() {
  return (const Record*)SETTINGS_PAGE;
}

static uint8_t recordChecksum(const Record& r) {
  return ~(r.magic + r.id + r.baud_rate + r.gyro_range + r.acc_range + r.sample_rate);
}

static bool isErased(const Record& r) {
  const uint8_t* bytes = (const uint8_t*)&r;
  for (size_t i = 0; i < sizeof(Record); i++) {
    if (bytes[i] != 0xFF) return false;
  }
  return true;
}

static bool isValid(const Record& r) {
  return r.magic == RECORD_MAGIC && r.zero == 0 && r.checksum == recordChecksum(r);
}

static void waitForFlash() {
  while (NRF_NVMC->READY == NVMC_READY_READY_Busy) {
  }
}

static void eraseSettingsPage() {
  NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Een;
  waitForFlash();
  NRF_NVMC->ERASEPAGE = SETTINGS_PAGE;
  waitForFlash();
  NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Ren;
  waitForFlash();
  nextRecord = 0;
}

static void writeRecord(int index, const Record& record) {
  uint32_t words[2];
  memcpy(words, &record, sizeof(words));
  volatile uint32_t* target = (volatile uint32_t*)(SETTINGS_PAGE + index * sizeof(Record));
  NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Wen;
  waitForFlash();
  target[0] = words[0];
  waitForFlash();
  target[1] = words[1];
  waitForFlash();
  NRF_NVMC->CONFIG = NVMC_CONFIG_WEN_Ren;
  waitForFlash();
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

static void put16(uint8_t address, uint16_t value) {
  table[address] = value & 0xFF;
  table[address + 1] = value >> 8;
}

// Sign-magnitude, like the servos: bit 15 = sign, bits 0..14 = size.
static uint16_t toSignMagnitude(float value) {
  long rounded = lroundf(value);
  long size = labs(rounded);
  if (size > 0x7FFF) size = 0x7FFF;
  return (rounded < 0) ? (0x8000 | size) : size;
}

// IEEE 754 half float (1 sign bit, 5 exponent bits, 10 fraction bits).
static uint16_t toHalfFloat(float value) {
  uint32_t bits;
  memcpy(&bits, &value, 4);
  uint16_t sign = (bits >> 16) & 0x8000;
  int32_t exponent = (int32_t)((bits >> 23) & 0xFF) - 127 + 15;
  uint32_t fraction = bits & 0x7FFFFF;

  if (exponent >= 31) return sign | 0x7C00;  // too big: infinity
  if (exponent <= 0) {                       // very small: subnormal or zero
    if (exponent < -10) return sign;
    fraction |= 0x800000;
    int shift = 14 - exponent;
    uint16_t half = fraction >> shift;
    if ((fraction >> (shift - 1)) & 1) half++;  // round
    return sign | half;
  }
  uint16_t half = sign | (exponent << 10) | (fraction >> 13);
  if (fraction & 0x1000) half++;  // round (a carry into the exponent is correct)
  return half;
}

static bool isValidValue(uint8_t address, uint8_t value) {
  switch (address) {
    case Reg::ID:          return value <= 253;
    case Reg::BAUD_RATE:   return value < BAUD_RATE_COUNT;
    case Reg::GYRO_RANGE:  return value <= 3;
    case Reg::ACC_RANGE:   return value <= 3;
    case Reg::SAMPLE_RATE: return value <= 5;
    case Reg::LOCK:        return value <= 1;
    default:               return false;  // everything else is read-only
  }
}

static bool isEeprom(uint8_t address) {
  return address < Reg::LOCK;
}

static void setDefaults(bool keepId) {
  uint8_t id = keepId ? table[Reg::ID] : DEFAULT_ID;
  memset(table, 0, sizeof(table));
  table[Reg::FIRMWARE_MAJOR] = FIRMWARE_MAJOR;
  table[Reg::FIRMWARE_MINOR] = FIRMWARE_MINOR;
  put16(Reg::MODEL_NUMBER, MODEL_NUMBER);
  table[Reg::ID] = id;
  table[Reg::BAUD_RATE] = DEFAULT_BAUD_CODE;
  table[Reg::GYRO_RANGE] = DEFAULT_GYRO_RANGE;
  table[Reg::ACC_RANGE] = DEFAULT_ACC_RANGE;
  table[Reg::SAMPLE_RATE] = DEFAULT_RATE_CODE;
  table[Reg::LOCK] = 1;
  put16(Reg::QUATERNION_X, 0);  // the identity quaternion until the first measurement
  put16(Reg::QUATERNION_Y, 0);
  put16(Reg::QUATERNION_Z, 0);
}

// ---------------------------------------------------------------------------
// Public functions
// ---------------------------------------------------------------------------

void beginRegisters() {
  setDefaults(false);

  // Find the newest record. Anything that is neither a record nor erased
  // (e.g. left over from other firmware) means the page must be erased.
  const Record* records = storedRecords();
  int count = 0;
  bool foreignData = false;
  while (count < RECORD_COUNT && !isErased(records[count])) {
    if (!isValid(records[count])) {
      foreignData = true;
      break;
    }
    count++;
  }

  if (count > 0) {
    const Record& r = records[count - 1];
    const uint8_t addresses[] = {Reg::ID, Reg::BAUD_RATE, Reg::GYRO_RANGE, Reg::ACC_RANGE, Reg::SAMPLE_RATE};
    const uint8_t values[] = {r.id, r.baud_rate, r.gyro_range, r.acc_range, r.sample_rate};
    for (int i = 0; i < 5; i++) {
      if (isValidValue(addresses[i], values[i])) table[addresses[i]] = values[i];
    }
  }
  nextRecord = count;
  memcpy(stored, table, sizeof(stored));

  // Erase now, while nobody is waiting for an answer, rather than later.
  if (foreignData || count > RECORD_COUNT / 2) {
    eraseSettingsPage();
    if (count > 0) saveRegisters();
  }
}

uint8_t readRegister(uint8_t address) {
  return (address < REGISTER_COUNT) ? table[address] : 0;
}

void writeRegisters(uint8_t address, const uint8_t* data, uint8_t length) {
  for (int i = 0; i < length; i++) {
    int target = address + i;
    if (target >= REGISTER_COUNT || !isValidValue(target, data[i])) continue;
    if (table[target] == data[i] && stored[target] == data[i]) continue;
    table[target] = data[i];

    if (target == Reg::BAUD_RATE) changes |= CHANGED_BAUD_RATE;
    if (target == Reg::GYRO_RANGE || target == Reg::ACC_RANGE || target == Reg::SAMPLE_RATE) {
      changes |= CHANGED_IMU_SETTINGS;
    }
    if (isEeprom(target) && table[Reg::LOCK] == 0) {
      stored[target] = data[i];
      changes |= CHANGED_NEEDS_SAVING;
    }
  }
}

void factoryReset() {
  uint8_t oldBaud = table[Reg::BAUD_RATE];
  setDefaults(true);
  memcpy(stored, table, sizeof(stored));
  changes |= CHANGED_IMU_SETTINGS | CHANGED_NEEDS_SAVING;
  if (table[Reg::BAUD_RATE] != oldBaud) changes |= CHANGED_BAUD_RATE;
}

uint8_t takeRegisterChanges() {
  uint8_t result = changes;
  changes = 0;
  return result;
}

void saveRegisters() {
  if (nextRecord >= RECORD_COUNT) eraseSettingsPage();  // rare: 256+ saves without a restart

  Record record;
  record.magic = RECORD_MAGIC;
  record.id = stored[Reg::ID];
  record.baud_rate = stored[Reg::BAUD_RATE];
  record.gyro_range = stored[Reg::GYRO_RANGE];
  record.acc_range = stored[Reg::ACC_RANGE];
  record.sample_rate = stored[Reg::SAMPLE_RATE];
  record.checksum = recordChecksum(record);
  record.zero = 0;
  writeRecord(nextRecord, record);
  nextRecord++;
}

void setMeasurements(const float quaternion[4], const float gyro[3], const float acc[3]) {
  // Feetech sends only x, y, z; the reader computes w = +sqrt(1 - x^2 - y^2 - z^2).
  // q and -q are the same rotation, so we flip q when w is negative.
  float sign = (quaternion[0] < 0) ? -1.0f : 1.0f;
  put16(Reg::QUATERNION_X, toHalfFloat(sign * quaternion[1]));
  put16(Reg::QUATERNION_Y, toHalfFloat(sign * quaternion[2]));
  put16(Reg::QUATERNION_Z, toHalfFloat(sign * quaternion[3]));

  put16(Reg::GYRO_X, toSignMagnitude(gyro[0] * 1000.0f));  // rad/s -> mrad/s
  put16(Reg::GYRO_Y, toSignMagnitude(gyro[1] * 1000.0f));
  put16(Reg::GYRO_Z, toSignMagnitude(gyro[2] * 1000.0f));
  put16(Reg::ACC_X, toSignMagnitude(acc[0] * 1000.0f));    // g -> mg
  put16(Reg::ACC_Y, toSignMagnitude(acc[1] * 1000.0f));
  put16(Reg::ACC_Z, toSignMagnitude(acc[2] * 1000.0f));
}
