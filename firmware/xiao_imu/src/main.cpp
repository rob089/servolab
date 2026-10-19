// Bus IMU node for the Feetech STS servo bus.
//
// A Seeed XIAO nRF52840 Sense that behaves like Feetech's own bus IMU: it sits
// on the servo bus as one more device with its own ID and answers the same
// protocol as the servos. Host software reads its registers (registers.h).
//
//   protocol.*   Feetech packets in and out (servo bus and USB)
//   registers.*  the memory table, EEPROM settings in flash
//   imu.*        the gyro/accelerometer chip and the orientation filter
//
// The USB port speaks the same protocol, so the node can be tested without
// any bus hardware: open the XIAO's serial port like a bus adapter.
#include <Adafruit_TinyUSB.h>  // needed for the USB serial port with PlatformIO
#include <Arduino.h>

#include "config.h"
#include "imu.h"
#include "protocol.h"
#include "registers.h"

static Imu imu;
static ProtocolPort usbPort(Serial, false);
static ProtocolPort busPort(Serial1, true);
static uint32_t lastImuRetryMs = 0;

static void setLed(uint8_t pin, bool on) {
  digitalWrite(pin, on ? LOW : HIGH);  // the LEDs are active LOW
}

// Serial1.begin() only knows a fixed list of baud rates (500 000 would become
// 921 600), so we set the UART's baud rate register ourselves:
// value = baud * 2^32 / 16 MHz, rounded the way Nordic's table is.
static void applyBusBaudRate() {
  uint32_t baudRate = BAUD_RATES[readRegister(Reg::BAUD_RATE)];
  uint32_t value = ((uint64_t)baudRate << 32) / 16000000;
  NRF_UARTE0->BAUDRATE = (value + 0x800) & 0xFFFFF000;
  busPort.setBaudRate(baudRate);
}

static void beginImu() {
  imu.begin(readRegister(Reg::GYRO_RANGE), readRegister(Reg::ACC_RANGE), readRegister(Reg::SAMPLE_RATE));
}

void setup() {
  dwt_enable();  // the CPU cycle counter, for cycleCount() and microsSince()
  pinMode(PIN_BUS_TX_ENABLE, OUTPUT);
  digitalWrite(PIN_BUS_TX_ENABLE, HIGH);  // do not drive the bus
  pinMode(PIN_LED_ERROR, OUTPUT);
  pinMode(PIN_LED_CALIBRATE, OUTPUT);
  pinMode(PIN_LED_TRAFFIC, OUTPUT);
  setLed(PIN_LED_ERROR, false);
  setLed(PIN_LED_CALIBRATE, false);
  setLed(PIN_LED_TRAFFIC, false);

  beginRegisters();
  Serial.begin(115200);  // USB: the number does not matter
  Serial1.setPins(PIN_BUS_RX, PIN_BUS_TX);  // must come before begin()
  Serial1.begin(1000000);
  applyBusBaudRate();
  beginImu();
}

#ifdef BUS_DEBUG
// Debug build (pio run -e bus_debug): USB prints what arrives on the bus as
// text, once per second, instead of speaking the protocol. Open it with
// "pio device monitor -e bus_debug".
static void printBusDebug() {
  static uint32_t lastPrintMs = 0;
  if (millis() - lastPrintMs < 1000) return;
  lastPrintMs = millis();

  // The UART owns D7, but reading the pin level still works. The bus idles
  // HIGH; count how often we see LOW in a short burst of reads.
  uint32_t lowCount = 0;
  for (int i = 0; i < 20000; i++) lowCount += (digitalRead(PIN_BUS_RX) == LOW);

  Serial.printf("bus: %lu bytes, %lu packets, %lu bad checksum | D7 now %s, LOW in %lu/20000 reads | last:",
                busPort.bytesReceived, busPort.packetsReceived, busPort.checksumErrors,
                digitalRead(PIN_BUS_RX) ? "HIGH" : "LOW", lowCount);
  for (int i = 0; i < 16; i++) {
    Serial.printf(" %02x", busPort.lastBytes[(busPort.lastBytesNext + i) % 16]);
  }
  Serial.printf(" | D8 %s", digitalRead(PIN_BUS_TX_ENABLE) ? "HIGH" : "LOW");

  // Is anything driving D7? Switch its pull resistor to pull-down for a moment:
  // a floating pin then reads LOW, a pin driven by the PCB stays HIGH.
  uint32_t pin = g_ADigitalPinMap[PIN_BUS_RX];
  NRF_GPIO_Type* port = (pin < 32) ? NRF_P0 : NRF_P1;
  uint32_t oldConfig = port->PIN_CNF[pin & 31];
  port->PIN_CNF[pin & 31] = (oldConfig & ~GPIO_PIN_CNF_PULL_Msk) | (GPIO_PIN_CNF_PULL_Pulldown << GPIO_PIN_CNF_PULL_Pos);
  delayMicroseconds(200);
  bool highWithPullDown = (port->IN >> (pin & 31)) & 1;
  port->PIN_CNF[pin & 31] = oldConfig;
  Serial.printf(" | D7 with pull-down: %s (pull was %lu)\n", highWithPullDown ? "HIGH = driven" : "LOW = floating",
                (oldConfig & GPIO_PIN_CNF_PULL_Msk) >> GPIO_PIN_CNF_PULL_Pos);
}
#endif

void loop() {
#ifdef BUS_DEBUG
  printBusDebug();
#else
  usbPort.poll();
#endif
  busPort.poll();

  if (imu.update()) {
    setMeasurements(imu.quaternion, imu.gyro, imu.acc);
  }
  if (!imu.ok && millis() - lastImuRetryMs > 1000) {
    lastImuRetryMs = millis();
    beginImu();
  }

  // Settings written over the bus. The answer is already sent, so changing
  // the baud rate now is safe.
  uint8_t changes = takeRegisterChanges();
  if (changes & CHANGED_BAUD_RATE) applyBusBaudRate();
  if (changes & CHANGED_IMU_SETTINGS) {
    imu.configure(readRegister(Reg::GYRO_RANGE), readRegister(Reg::ACC_RANGE), readRegister(Reg::SAMPLE_RATE));
  }
  if (changes & CHANGED_NEEDS_SAVING) saveRegisters();

  uint8_t errorBits = imu.ok ? 0 : ERROR_SENSOR;
  usbPort.errorBits = errorBits;
  busPort.errorBits = errorBits;

  uint32_t now = millis();
  bool recentAnswer = (now - usbPort.lastAnswerMs < 30) || (now - busPort.lastAnswerMs < 30);
  setLed(PIN_LED_TRAFFIC, recentAnswer);
  setLed(PIN_LED_ERROR, !imu.ok);
  setLed(PIN_LED_CALIBRATE, imu.ok && !imu.calibrated);
}
