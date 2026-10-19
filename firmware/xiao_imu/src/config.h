// config.h - pins, defaults and fixed numbers of the bus IMU node.
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------
// Feetech has not published a model number for their bus IMU, so we use our own.
// servolab uses it to recognise the device (STS3215 = 777, STS3250 = 2825).
const uint16_t MODEL_NUMBER = 2026;
const uint8_t FIRMWARE_MAJOR = 1;
const uint8_t FIRMWARE_MINOR = 0;

// ---------------------------------------------------------------------------
// Microsecond timing
// ---------------------------------------------------------------------------
// micros() on this core only counts whole scheduler ticks (about 1 ms) unless
// the CPU's cycle counter runs, and then it wraps after 67 s. So we use the
// cycle counter directly (64 per microsecond; setup() turns it on). The
// difference of two counts is right even when the counter wraps (every 67 s).
inline uint32_t cycleCount() { return DWT->CYCCNT; }
inline uint32_t microsSince(uint32_t startCycles) { return (DWT->CYCCNT - startCycles) / 64; }

// ---------------------------------------------------------------------------
// Pins (Seeed XIAO nRF52840 Sense)
// ---------------------------------------------------------------------------
// Bus: Serial1 on D6 (TX) and D7 (RX), the XIAO's default UART pins. (PCB v1
// had TX on D0: its D0-D6 header row was mirrored. Set PIN_BUS_TX = D0 for it.)
// On the PCB, TX reaches the bus through buffer 1 of a 74LVC2G125, enabled by
// D8 (1OE#, active LOW). Buffer 2 (bus -> RX) is always on, so we hear our own
// replies (the "echo") and throw them away.
const uint8_t PIN_BUS_TX = D6;
const uint8_t PIN_BUS_RX = D7;
const uint8_t PIN_BUS_TX_ENABLE = D8;   // LOW = we drive the bus, HIGH = released

// Onboard RGB LED, active LOW.
const uint8_t PIN_LED_ERROR = LED_RED;     // on: IMU chip not found
const uint8_t PIN_LED_CALIBRATE = LED_BLUE; // on: measuring gyro offset, keep still
const uint8_t PIN_LED_TRAFFIC = LED_GREEN;  // flashes when we answer a request

// ---------------------------------------------------------------------------
// Factory defaults (restored by the RESET instruction, except the ID)
// ---------------------------------------------------------------------------
// ID 100 so the IMU does not clash with servos (they come with ID 1).
const uint8_t DEFAULT_ID = 100;
const uint8_t DEFAULT_BAUD_CODE = 0;     // 1 000 000 baud, like the STS3215
const uint8_t DEFAULT_GYRO_RANGE = 3;    // +-2000 deg/s
const uint8_t DEFAULT_ACC_RANGE = 2;     // +-8 g
const uint8_t DEFAULT_RATE_CODE = 4;     // 416 Hz

// Baud rate codes, the same as Feetech's servos (register 6).
const uint32_t BAUD_RATES[] = {1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400};
const uint8_t BAUD_RATE_COUNT = 8;
