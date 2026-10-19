// protocol.cpp - receive packets, act on the ones for us, answer.
#include "protocol.h"

#include "config.h"
#include "registers.h"

// A packet that stops in the middle is dropped after this pause (USB delivers
// in 1 ms frames, so it gets a longer pause than the bus).
static const uint32_t USB_PACKET_GAP_US = 20000;

ProtocolPort::ProtocolPort(Stream& stream, bool sharedBus) : stream(stream), sharedBus(sharedBus) {}

void ProtocolPort::setBaudRate(uint32_t baudRate) {
  byteTimeUs = (10000000UL + baudRate - 1) / baudRate;  // 10 bits per byte, rounded up
}

void ProtocolPort::poll() {
  uint32_t packetGapUs = sharedBus ? 1000 + 20 * byteTimeUs : USB_PACKET_GAP_US;

  while (stream.available() > 0) {
    uint8_t byte = stream.read();
    if (state != HEADER_1 && microsSince(lastByteCycles) > packetGapUs) state = HEADER_1;
    lastByteCycles = cycleCount();
    bytesReceived++;
    lastBytes[lastBytesNext] = byte;
    lastBytesNext = (lastBytesNext + 1) % sizeof(lastBytes);
    receive(byte);
  }

  // SYNC_READ: if the device before us does not answer (not there?), answer
  // anyway once the bus has been quiet for a while.
  if (syncReadWaiting && microsSince(lastByteCycles) > 1000 + 10 * byteTimeUs) {
    syncReadWaiting = false;
    answerRead(readRegister(Reg::ID), syncReadAddress, syncReadLength);
  }
}

void ProtocolPort::receive(uint8_t byte) {
  switch (state) {
    case HEADER_1:
      if (byte == 0xFF) state = HEADER_2;
      break;
    case HEADER_2:
      state = (byte == 0xFF) ? PACKET_ID : HEADER_1;
      break;
    case PACKET_ID:
      if (byte == 0xFF) break;  // a third FF: still in the header
      packetId = byte;
      state = PACKET_LENGTH;
      break;
    case PACKET_LENGTH:
      if (byte < 2) {  // too short to hold instruction + checksum
        state = HEADER_1;
        break;
      }
      packetLength = byte;
      received = 0;
      state = BODY;
      break;
    case BODY:
      body[received++] = byte;
      if (received == packetLength) {
        state = HEADER_1;
        handlePacket();
      }
      break;
  }
}

void ProtocolPort::handlePacket() {
  packetsReceived++;
  // On the shared bus we also see the servos' answers. If we are waiting for
  // our turn in a SYNC_READ and the device before us just answered: our turn.
  if (syncReadWaiting && packetId == syncReadPredecessor) {
    syncReadWaiting = false;
    answerRead(readRegister(Reg::ID), syncReadAddress, syncReadLength);
    return;
  }

  uint8_t sum = packetId + packetLength;
  for (int i = 0; i < packetLength - 1; i++) sum += body[i];
  if ((uint8_t)~sum != body[packetLength - 1]) {  // damaged packet
    checksumErrors++;
    return;
  }

  uint8_t myId = readRegister(Reg::ID);
  if (packetId != myId && packetId != BROADCAST_ID) return;  // not for us
  bool broadcast = (packetId == BROADCAST_ID);              // nobody answers a broadcast

  // A new request from the host: it has given up on an unfinished SYNC_READ.
  syncReadWaiting = false;

  uint8_t instruction = body[0];
  const uint8_t* params = body + 1;
  int count = packetLength - 2;  // number of parameters

  switch (instruction) {
    case Instruction::PING:
      if (!broadcast) answer(myId, nullptr, 0);
      break;

    case Instruction::READ:
      if (count >= 2 && !broadcast) answerRead(myId, params[0], params[1]);
      break;

    case Instruction::WRITE:
      if (count < 1) break;
      writeRegisters(params[0], params + 1, count - 1);
      if (!broadcast) answer(myId, nullptr, 0);  // with the ID it was sent to, even if it changed
      break;

    case Instruction::REG_WRITE:
      if (count < 1) break;
      memcpy(registeredWrite, params, count);
      registeredLength = count;
      if (!broadcast) answer(myId, nullptr, 0);
      break;

    case Instruction::ACTION:
      if (registeredLength > 0) {
        writeRegisters(registeredWrite[0], registeredWrite + 1, registeredLength - 1);
        registeredLength = 0;
      }
      if (!broadcast) answer(myId, nullptr, 0);
      break;

    case Instruction::RESET:
      factoryReset();
      if (!broadcast) answer(myId, nullptr, 0);
      break;

    case Instruction::SYNC_READ:
      handleSyncRead(params, count);
      break;

    case Instruction::SYNC_WRITE:
      handleSyncWrite(params, count);
      break;

    default:
      break;  // unknown instruction: no answer
  }
}

// params: address, length, ID 1, ID 2, ...
void ProtocolPort::handleSyncRead(const uint8_t* params, int count) {
  syncReadWaiting = false;
  if (count < 3) return;
  uint8_t myId = readRegister(Reg::ID);

  for (int i = 2; i < count; i++) {
    if (params[i] != myId) continue;
    bool first = (i == 2);
    if (first || !sharedBus) {
      answerRead(myId, params[0], params[1]);
    } else {
      syncReadWaiting = true;
      syncReadPredecessor = params[i - 1];
      syncReadAddress = params[0];
      syncReadLength = params[1];
    }
    return;
  }
}

// params: address, length, then for each device: ID, `length` data bytes
void ProtocolPort::handleSyncWrite(const uint8_t* params, int count) {
  if (count < 2) return;
  uint8_t address = params[0];
  uint8_t length = params[1];
  uint8_t myId = readRegister(Reg::ID);

  for (int i = 2; i + 1 + length <= count; i += 1 + length) {
    if (params[i] == myId) {
      writeRegisters(address, params + i + 1, length);
      return;
    }
  }
}

void ProtocolPort::answerRead(uint8_t id, uint8_t address, uint8_t length) {
  uint8_t data[250];
  if (length > sizeof(data)) length = sizeof(data);
  for (int i = 0; i < length; i++) {
    int a = address + i;
    data[i] = (a < 256) ? readRegister(a) : 0;
  }
  answer(id, data, length);
}

void ProtocolPort::answer(uint8_t id, const uint8_t* data, int length) {
  uint8_t packet[256];
  packet[0] = 0xFF;
  packet[1] = 0xFF;
  packet[2] = id;
  packet[3] = length + 2;
  packet[4] = errorBits;
  memcpy(packet + 5, data, length);

  uint8_t sum = 0;
  for (int i = 2; i < 5 + length; i++) sum += packet[i];
  packet[5 + length] = ~sum;

  send(packet, length + 6);
  lastAnswerMs = millis();
}

void ProtocolPort::send(const uint8_t* bytes, int length) {
  if (!sharedBus) {
    stream.write(bytes, length);
    stream.flush();
    return;
  }

  // Drive the bus only while we talk. Our receiver hears every byte we send
  // (the echo). When the echo of the last byte is back, the byte has really
  // left the pin and we can let go of the bus. The deadline is a safety net,
  // e.g. if RX is not connected.
  // No stream.flush() here: on this core it sleeps until the next scheduler
  // tick (up to 1 ms) after the last byte, and all that time we would block
  // the bus and miss the host's next packet. write() only starts the sending.
  uint32_t start = cycleCount();
  uint32_t maxUs = (length + 2) * byteTimeUs + 50;
  digitalWrite(PIN_BUS_TX_ENABLE, LOW);
  stream.write(bytes, length);
  int echoed = 0;
  while (echoed < length && microsSince(start) < maxUs) {
    if (stream.read() >= 0) echoed++;
  }
  digitalWrite(PIN_BUS_TX_ENABLE, HIGH);
}
