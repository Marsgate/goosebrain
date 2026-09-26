#ifndef PSR_H
#define PSR_H

#include <ESP32Servo.h>
#include <Preferences.h>
#include <Bluepad32.h>

#define SERVO_MICROS_MIN 500
#define SERVO_MICROS_MAX 2500

extern int M1[2];
extern int M2[2];
extern int M3[2];
extern int M4[2];
extern int M5[2];
extern int M6[2];

extern int S1;
extern int S2;
extern int S3;
extern int S4;
extern int S5;
extern int S6;

// GPIO2 drives nSLEEP on all three DRV8848s AND the dev board's onboard LED.
// LOW = drivers asleep (motors off), HIGH = drivers enabled.
// The LED therefore can't be used independently of the motor drivers.
#define DRV_SLEEP 2
#define ONBOARD_LED DRV_SLEEP
#define BOOT_BTN 0

extern Preferences preferences;
extern ControllerPtr ctl;

class Motor {
  public:
    void init(int port[2], bool reversed = false);
    void move(int speed);
    int getSpeed();
  private:
    int _speed;
    bool _reversed;
    int _fwdPin;
    int _revPin;
};

class ServoMotor {
  public:
    void init(int port, int initialPosition = 1500, int lowerLimit = SERVO_MICROS_MIN, int upperLimit = SERVO_MICROS_MAX);
    void moveAbsolute(int position);
    void moveRelative(int step);
    int getPosition();
  private:
    Servo _servo;
    int _position;
    int _lowerLimit;
    int _upperLimit;
};

void psrInit();
void psrUpdate();
void stopAllMotors();
void enterPairingMode();
void onConnectedController(ControllerPtr controller);
void onDisconnectedController(ControllerPtr controller);
void dumpGamepad(ControllerPtr ctl);

#endif