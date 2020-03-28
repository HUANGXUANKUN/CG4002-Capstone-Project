// Referenced jrowberg's MPU6050_DMP6 library example
// https://github.com/jrowberg/i2cdevlib/blob/master/Arduino/MPU6050/examples/MPU6050_DMP6/MPU6050_DMP6.ino

#include "I2Cdev.h"
#include "MPU6050_6Axis_MotionApps20.h"

// Arduino Wire library is required if I2Cdev I2CDEV_ARDUINO_WIRE implementation
// is used in I2Cdev.h
#if I2CDEV_IMPLEMENTATION == I2CDEV_ARDUINO_WIRE
#include "Wire.h"
#endif

MPU6050 mpu;

// MPU control/status vars
bool dmpReady = false;  // set true if DMP init was successful
uint8_t mpuIntStatus;   // holds actual interrupt status byte from MPU
uint8_t devStatus;      // return status after each device operation (0 = success, !0 = error)
uint16_t packetSize;    // expected DMP packet size (default is 42 bytes)
uint16_t fifoCount;     // count of all bytes currently in FIFO
uint8_t fifoBuffer[64]; // FIFO storage buffer

// orientation/motion vars
Quaternion q;           // [w, x, y, z]         quaternion container
VectorFloat gravity;    // [x, y, z]            gravity vector
VectorInt16 accel;      // [x, y, z]            accel sensor measurements
VectorInt16 accelReal;  // [x, y, z]            gravity-free accel sensor measurements
VectorInt16 accelWorld; // [x, y, z]            world-frame accel sensor measurements
float euler[3];         // [psi, theta, phi]    Euler angle container
float ypr[3];           // [yaw, pitch, roll]   yaw/pitch/roll container and gravity vector

// These 2 ypr values is to check whether there are sudden movements, if there are then set flag to true
volatile float ypr_firstCheck[3] = {0.0, 0.0, 0.0}; // Variabe to store the 1st ypr value
volatile float ypr_lastCheck[3] = {0.0, 0.0, 0.0};  // Variable to store the 2nd ypr value
volatile float yawDiff = 0.0;
volatile float pitchDiff = 0.0;
volatile float rollDiff = 0.0;

volatile long accel_firstCheck[3] = {0, 0, 0};
volatile long accel_lastCheck[3] = {0, 0, 0};
volatile long accelXDiff = 0;
volatile long accelYDiff = 0;
volatile long accelZDiff = 0;

// Communication variables
char transmit_buffer[70];
char timestamp_arr[10];
unsigned long timestamp = 0;
int counter = 0;

// Interrupt detection routine
volatile bool mpuInterrupt = false;     // indicates whether MPU interrupt pin has gone high
void dmpDataReady() {
  mpuInterrupt = true;
}

// Function to get yaw pitch roll values
int getYPR_worldAccel() {
  // if programming failed, don't try to do anything
  if (!dmpReady) return;

  // wait for MPU interrupt or extra packet(s) available
  while (!mpuInterrupt && fifoCount < packetSize) {
    // other program behavior stuff here
  }

  // reset interrupt flag and get INT_STATUS byte
  mpuInterrupt = false;
  mpuIntStatus = mpu.getIntStatus();

  // get current FIFO count
  fifoCount = mpu.getFIFOCount();

  // check for overflow
  if ((mpuIntStatus & 0x10) || fifoCount == 1024) {
    // reset so we can continue cleanly
    mpu.resetFIFO();
    // Indicate that there is a failure in getting data
    return 0;
    // otherwise, check for DMP data ready interrupt
  } else if (mpuIntStatus & 0x02) {
    // wait for correct available data length
    while (fifoCount < packetSize) fifoCount = mpu.getFIFOCount();

    // read a packet from FIFO
    mpu.getFIFOBytes(fifoBuffer, packetSize);

    // track FIFO count here in case there is > 1 packet available
    // (this lets us immediately read more without waiting for an interrupt)
    fifoCount -= packetSize;

    // display Euler angles in degrees
    mpu.dmpGetQuaternion(&q, fifoBuffer);
    mpu.dmpGetGravity(&gravity, &q);
    mpu.dmpGetYawPitchRoll(ypr, &q, &gravity);

    // display initial world-frame acceleration, adjusted to remove gravity
    // and rotated based on known orientation from quaternion
    mpu.dmpGetAccel(&accel, fifoBuffer);
    mpu.dmpGetLinearAccel(&accelReal, &accel, &gravity);
    mpu.dmpGetLinearAccelInWorld(&accelWorld, &accelReal, &q);

    // Indicate that the data retrieval is successful
    return 1;
  }
}

void setup() {
  timestamp = millis();
  // join I2C bus (I2Cdev library doesn't do this automatically)
#if I2CDEV_IMPLEMENTATION == I2CDEV_ARDUINO_WIRE
  Wire.begin();
  TWBR = 24; // 400kHz I2C clock (200kHz if CPU is 8MHz)
#elif I2CDEV_IMPLEMENTATION == I2CDEV_BUILTIN_FASTWIRE
  Fastwire::setup(400, true);
#endif

  Serial.begin(115200);
  // initialize MPU6050 IMU device
  mpu.initialize();

  // verify connection

  // load and configure the DMP
  devStatus = mpu.dmpInitialize();

  // supply your own gyro offsets here, scaled for min sensitivity
  mpu.setXGyroOffset(-102);
  mpu.setYGyroOffset(-84);
  mpu.setZGyroOffset(-659);
  mpu.setZAccelOffset(1257);

  // make sure it worked (returns 0 if so)
  if (devStatus == 0) {
    // turn on the DMP, now that it's ready
    mpu.setDMPEnabled(true);

    // enable Arduino interrupt detection
    attachInterrupt(0, dmpDataReady, RISING);
    mpuIntStatus = mpu.getIntStatus();

    // set our DMP Ready flag so the main loop() function knows it's okay to use it
    dmpReady = true;

    // get expected DMP packet size for later comparison
    packetSize = mpu.dmpGetFIFOPacketSize();
  } else {
    // ERROR!
    // 1 = initial memory load failed
    // 2 = DMP configuration updates failed
    // (if it's going to break, usually the code will be 1)
  }
  receiveHandshakeAndClockSync();
}

void receiveHandshakeAndClockSync()
{
  unsigned long tmp_recv_timestamp;
  unsigned long tmp_send_timestamp;
  while (1) {
    if (Serial.available() && Serial.read() == 'T') { // need to do time calibration
      while (1) {
        if (Serial.available() && Serial.read() == 'H') {
          Serial.print('A');
          tmp_recv_timestamp = millis();
          Serial.print(tmp_recv_timestamp);
          break;
        }
      }
      Serial.print('|');
      tmp_send_timestamp = millis();
      Serial.print(tmp_send_timestamp);
      Serial.print('>');
      while (1) {
        if (Serial.available() && Serial.read() == 'A') { // ultra96 received timestamp
          break;
        } else if (Serial.available() && Serial.read() == 'R') { // retransmit timestamp as ultra96 did not receive it
          Serial.print('A');
          Serial.print(tmp_recv_timestamp);
          Serial.print('|');
          Serial.print(tmp_send_timestamp);
          Serial.print('>');
        }
      }
      break;
    } else if (Serial.available() && Serial.read() == 'A') { // no need to do time calibration
      break;
    }
  }
}

void loop() {
  while (1) {
    while (1) {
      if (getYPR_worldAccel() == 1) {
        ypr_firstCheck[0] = ypr[0] * 180 / M_PI;
        ypr_firstCheck[1] = ypr[1] * 180 / M_PI;
        ypr_firstCheck[2] = ypr[2] * 180 / M_PI;
        accel_firstCheck[0] = accelWorld.x;
        accel_firstCheck[1] = accelWorld.y;
        accel_firstCheck[2] = accelWorld.z;
        break;
      }
    }
    // Set a small delay to get next YPR value
    delay(5);
    // Get a secondary YPR value
    while (1) {
      if (getYPR_worldAccel() == 1) {
        ypr_lastCheck[0] = ypr[0] * 180 / M_PI;
        ypr_lastCheck[1] = ypr[1] * 180 / M_PI;
        ypr_lastCheck[2] = ypr[2] * 180 / M_PI;
        accel_lastCheck[0] = accelWorld.x;
        accel_lastCheck[1] = accelWorld.y;
        accel_lastCheck[2] = accelWorld.z;
        break;
      }
    }
    // Compute the differences between these 2 YPR values to detect if there is a sudden movement
    yawDiff = ypr_lastCheck[0] - ypr_firstCheck[0];
    pitchDiff = ypr_lastCheck[1] - ypr_firstCheck[1];
    rollDiff = ypr_lastCheck[2] - ypr_firstCheck[2];
    accelXDiff = accel_lastCheck[0] - accel_firstCheck[0];
    accelYDiff = accel_lastCheck[1] - accel_firstCheck[1];
    accelZDiff = accel_lastCheck[2] - accel_firstCheck[2];
    // Only start taking data if there is a spike is found in either one of the three differences
    // The spike signifies a new dance move by the dancer
    if (abs(yawDiff) >= 5 || abs(pitchDiff) >= 5 || abs(rollDiff) >= 5 || abs(accelXDiff) >= 150 || abs(accelYDiff) >= 150 || abs(accelZDiff) >= 150) {
      counter++;     
    }
    if (counter == 5 && (abs(yawDiff) >= 5 || abs(pitchDiff) >= 5 || abs(rollDiff) >= 5 || abs(accelXDiff) >= 150 || abs(accelYDiff) >= 150 || abs(accelZDiff) >= 150)) {
      // Get the initial timestamp of this new dance move
      timestamp = millis();
      // Loop to get 50 samples from MPU6050 at the frequency of 20Hz
      for (int i = 0; i < 128; i++) {
        if (getYPR_worldAccel() == 0) {
          i--;
          continue;
        }
        int chksum = 0;
        char yaw[5];
        char pitch[5];
        char roll[5];
        char accx[5];
        char accy[5];
        char accz[5];
        strcat(transmit_buffer, "D");
        Serial.print('D');
        ultoa(timestamp, timestamp_arr, 10);
        strcat(transmit_buffer, timestamp_arr);
        Serial.print(timestamp_arr);
        strcat(transmit_buffer, ",");
        Serial.print(',');
        itoa(int(round(ypr[0] * 100 * 180 / M_PI)), yaw, 10);
        strcat(transmit_buffer, yaw);
        strcat(transmit_buffer, ",");
        Serial.print(yaw);
        Serial.print(',');
        itoa(int(round(ypr[1] * 100 * 180 / M_PI)), pitch, 10);
        strcat(transmit_buffer, pitch);
        strcat(transmit_buffer, ",");
        Serial.print(pitch);
        Serial.print(',');
        itoa(int(round(ypr[2] * 100 * 180 / M_PI)), roll, 10);
        strcat(transmit_buffer, roll);
        strcat(transmit_buffer, ",");
        Serial.print(roll);
        Serial.print(',');
        itoa(accelWorld.x * 100, accx, 10);
        strcat(transmit_buffer, accx);
        strcat(transmit_buffer, ",");
        Serial.print(accx);
        Serial.print(',');
        itoa(accelWorld.y * 100, accy, 10);
        strcat(transmit_buffer, accy);
        strcat(transmit_buffer, ",");
        Serial.print(accy);
        Serial.print(',');
        itoa(accelWorld.z * 100, accz, 10);
        strcat(transmit_buffer, accz);
        Serial.print(accz);
        for (int a = 0; a < strlen(transmit_buffer); a++) {
          chksum ^= transmit_buffer[a];
        }
        Serial.print('|');
        Serial.print(chksum);
        Serial.println('>');
        memset(&transmit_buffer[0], 0, sizeof(transmit_buffer));
        delay(50);
      }
      counter = 0;
      break;
    }
    delay(50);
  }
  receiveHandshakeAndClockSync();
}