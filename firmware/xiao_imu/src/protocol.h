// protocol.h - the Feetech bus protocol, as a device (like one servo).
//
// Packets from the host:   FF FF  ID  LEN  INSTRUCTION  PARAMS...  CHECKSUM
// Our answer ("status"):   FF FF  ID  LEN  ERROR        DATA...    CHECKSUM
// LEN = number of bytes after LEN, CHECKSUM = ~(ID + LEN + all bytes in between).
//
// One ProtocolPort per connection. The same code runs on
//  - the shared servo bus (Serial1): we hear everything on the bus, including
//    the replies of the servos and the echo of our own replies, and we may only
//    drive the bus while we answer;
//  - USB (Serial): we are alone, handy for testing without any bus hardware.
#pragma once

#include <Arduino.h>

const uint8_t BROADCAST_ID = 0xFE;

namespace Instruction {
const uint8_t PING = 0x01;
const uint8_t READ = 0x02;
const uint8_t WRITE = 0x03;
const uint8_t REG_WRITE = 0x04;   // store a write, do it on ACTION
const uint8_t ACTION = 0x05;
const uint8_t RESET = 0x0A;       // factory reset (keeps the ID)
const uint8_t SYNC_READ = 0x82;   // read the same registers from several devices
const uint8_t SYNC_WRITE = 0x83;  // write to several devices in one packet
}  // namespace Instruction

// Bits of the ERROR byte, as on the servos. We only use one:
const uint8_t ERROR_SENSOR = 1 << 1;  // the IMU chip does not answer

class ProtocolPort {
 public:
  // sharedBus: true for the servo bus (echo, TX enable pin, sync read turns).
  ProtocolPort(Stream& stream, bool sharedBus);

  // Read the bytes that arrived and answer complete packets. Call often.
  void poll();

  // Tell the port the baud rate (only used for timing on the shared bus).
  void setBaudRate(uint32_t baudRate);

  // Set by main: the ERROR byte for our answers.
  uint8_t errorBits = 0;

  // millis() of our last answer, for the traffic LED.
  uint32_t lastAnswerMs = 0;

  // Counters for finding wiring problems (printed by the bus_debug build).
  uint32_t bytesReceived = 0;
  uint32_t packetsReceived = 0;   // complete packets, for anyone
  uint32_t checksumErrors = 0;
  uint8_t lastBytes[16] = {0};    // the most recent bytes, oldest first after rotating
  uint8_t lastBytesNext = 0;      // where the next byte goes in lastBytes

 private:
  void receive(uint8_t byte);
  void handlePacket();
  void handleSyncRead(const uint8_t* params, int count);
  void handleSyncWrite(const uint8_t* params, int count);
  void answer(uint8_t id, const uint8_t* data, int length);
  void answerRead(uint8_t id, uint8_t address, uint8_t length);
  void send(const uint8_t* bytes, int length);

  Stream& stream;
  bool sharedBus;
  uint32_t byteTimeUs = 10;  // time for one byte on the wire (10 bits)

  // The packet being received.
  enum State { HEADER_1, HEADER_2, PACKET_ID, PACKET_LENGTH, BODY };
  State state = HEADER_1;
  uint8_t packetId = 0;
  uint8_t packetLength = 0;
  uint8_t body[256];  // instruction (or error), parameters, checksum
  int received = 0;
  uint32_t lastByteCycles = 0;  // cycleCount() when the last byte arrived

  // REG_WRITE stores a write here until ACTION.
  uint8_t registeredWrite[256];
  int registeredLength = 0;  // 0 = nothing stored

  // SYNC_READ on the shared bus: devices answer one after another, in the
  // order of the ID list. We wait until the device before us has answered.
  bool syncReadWaiting = false;
  uint8_t syncReadPredecessor = 0;
  uint8_t syncReadAddress = 0;
  uint8_t syncReadLength = 0;
};
