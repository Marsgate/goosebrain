#include "psr.h"

// Pin map for thegoose PCB (kicad/thegoose.kicad_pcb)
//
// Motor ports are {fwd, rev}: driving the fwd pin puts + on connector pin 1,
// the same convention as the hexyhustle kitbot brain, so motors spin the same
// direction for the same port.
//
// Each DRV8848 drives two ports. On the B bridge, BOUT1 goes to connector
// pin 2, so the B ports use BIN2 as fwd and BIN1 as rev.
//
//          fwd rev       driver  bridge
int M1[2] = {13, 12};  // U1      A  (AIN1, AIN2)
int M2[2] = { 4, 15};  // U1      B  (BIN2, BIN1)
int M3[2] = {16, 17};  // U2      A  (AIN1, AIN2)
int M4[2] = { 5, 18};  // U2      B  (BIN2, BIN1)
int M5[2] = {19, 21};  // U3      A  (AIN1, AIN2)
int M6[2] = {22, 23};  // U3      B  (BIN2, BIN1)

// Sensor/servo ports on the 3x6 header (GPIO1), S1 is the row marked "1"
int S1 = 32;
int S2 = 33;
int S3 = 25;
int S4 = 26;
int S5 = 27;
int S6 = 14;

// every initialized motor, so they can all be stopped when the controller drops
static Motor* motors[6];
static int motorCount = 0;

// true while waiting for a new controller to pair
static bool pairingMode = false;

// Motor
void Motor::init(
  int port[2],
  bool reversed
) {
  pinMode(port[0], OUTPUT);
  pinMode(port[1], OUTPUT);
  _reversed = reversed;
  _fwdPin = port[0];
  _revPin = port[1];
  _speed = 0;
  digitalWrite(_fwdPin, LOW);
  digitalWrite(_revPin, LOW);

  if (motorCount < 6) {
    motors[motorCount++] = this;
  }
}

void Motor::move(int speed) {
  // cap speed to -100,100
  if (speed > 100) {
    speed = 100;
  } else if (speed < -100) {
    speed = -100;
  }

  // apply the reversal
  if (_reversed == true) {
    speed = -speed;
  }

  // save the speed to the object
  _speed = speed;

  // convert to PWM and write to the motor
  speed = map(speed, -100, 100, -255, 255);

  bool fwd = false;
  if (speed > 0) {
    fwd = true;
  }

  analogWrite(_fwdPin, fwd ? speed : 0);
  analogWrite(_revPin, !fwd ? -speed : 0);
}

int Motor::getSpeed() {
  return _speed;
}

// ServoMotor
void ServoMotor::init(
  int port,
  int initialPosition,
  int lowerLimit,
  int upperLimit
) {
  pinMode(port, OUTPUT);
  _lowerLimit = lowerLimit;
  _upperLimit = upperLimit;

  // double attatch due to a bug
  _servo.attach(port, lowerLimit, upperLimit);
  _servo.attach(port, lowerLimit, upperLimit);

  _position = initialPosition;
  _servo.writeMicroseconds(initialPosition);
}

void ServoMotor::moveAbsolute(int position) {
  // cap the servo postion to the limits
  if (position > _upperLimit) {
    position = _upperLimit;
  } else if (position < _lowerLimit) {
    position = _lowerLimit;
  }

  // save the position to the object 
  _position = position;

  // write the position as microseconds
  _servo.writeMicroseconds(_position);
}

void ServoMotor::moveRelative(int step) {
  moveAbsolute(_position + step);
}

int ServoMotor::getPosition() {
  return _position;
}


Preferences preferences;

void stopAllMotors() {
  for (int i = 0; i < motorCount; i++) {
    motors[i]->move(0);
  }
}

void psrInit() {
  pinMode(DRV_SLEEP, OUTPUT);
  digitalWrite(DRV_SLEEP, LOW); // keep the motor drivers asleep until a controller connects
  pinMode(BOOT_BTN, INPUT);

  // Setup the Bluepad32 callbacks
  BP32.setup(&onConnectedController, &onDisconnectedController);

  // check for paired controller
  preferences.begin("robot", false);
  if (preferences.getBool("paired") == true) {
    Serial.println ("Controller already paired");
    BP32.enableNewBluetoothConnections(false); // do not allow new connections if there is a paired controller
  } else {
    Serial.println ("No paired controller");

    // forget previous controllers and connect to a new controller
    BP32.forgetBluetoothKeys();
    BP32.enableNewBluetoothConnections(true);
    preferences.putBool("paired", true); // assume a controller was paired
    pairingMode = true; // psrUpdate() blinks the LED to let the user know we are in pairing mode
  }
  preferences.end();
}

void enterPairingMode() {
  Serial.println("Entering pairing mode on next reboot");
  preferences.begin("robot", false);
  preferences.putBool("paired", false); // set robot to unpair at next reboot
  preferences.end();

  stopAllMotors();
  digitalWrite(DRV_SLEEP, LOW); // drivers off, LED off until the reboot
  
  while (digitalRead(BOOT_BTN) == LOW) vTaskDelay(10); // wait until button is release to restart
  esp_restart();
}

void onConnectedController(ControllerPtr controller) {
  if (ctl == nullptr) {
      Serial.println("Controller is connected");
      ctl = controller;
  }
  pairingMode = false;
  stopAllMotors(); // don't resume the last command from before a disconnect
  digitalWrite(DRV_SLEEP, HIGH); // wake the motor drivers, LED on
}

void onDisconnectedController(ControllerPtr controller) {
  if (ctl == controller) {
    Serial.println("Controller disconnected");
    ctl = nullptr;
  }
  stopAllMotors();
  digitalWrite(DRV_SLEEP, LOW); // failsafe: put the motor drivers to sleep, LED off
}

// Call every loop. While in pairing mode with no controller, blink the LED.
// This toggles the drivers' nSLEEP too, which is harmless since no motor is
// being commanded while there is no controller.
void psrUpdate() {
  if (pairingMode && ctl == nullptr) {
    digitalWrite(DRV_SLEEP, (millis() / 250) % 2);
  }
}

void dumpGamepad(ControllerPtr ctl) {
    Serial.printf(
        "idx=%d, dpad: 0x%02x, buttons: 0x%04x, axis L: %4d, %4d, axis R: %4d, %4d, brake: %4d, throttle: %4d, "
        "misc: 0x%02x, gyro x:%6d y:%6d z:%6d, accel x:%6d y:%6d z:%6d\n",
        ctl->index(),        // Controller Index
        ctl->dpad(),         // D-pad
        ctl->buttons(),      // bitmask of pressed buttons
        ctl->axisX(),        // (-511 - 512) left X Axis
        ctl->axisY(),        // (-511 - 512) left Y axis
        ctl->axisRX(),       // (-511 - 512) right X axis
        ctl->axisRY(),       // (-511 - 512) right Y axis
        ctl->brake(),        // (0 - 1023): brake button
        ctl->throttle(),     // (0 - 1023): throttle (AKA gas) button
        ctl->miscButtons(),  // bitmask of pressed "misc" buttons
        ctl->gyroX(),        // Gyro X
        ctl->gyroY(),        // Gyro Y
        ctl->gyroZ(),        // Gyro Z
        ctl->accelX(),       // Accelerometer X
        ctl->accelY(),       // Accelerometer Y
        ctl->accelZ()        // Accelerometer Z
    );
}
