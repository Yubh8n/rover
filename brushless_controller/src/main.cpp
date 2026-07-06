#include <Arduino.h>
#include <Servo.h>

Servo ESC;
void setup() {

  // put your setup code here, to run once:
  Serial.begin(115200);
  //pinMode(A0, OUTPUT); //PWM PIN 11  with PWM wire
  //analogWriteRange(255);     // now 255 == 100% duty, explicit  
  //analogWriteFreq(50);     // 1 kHz default is fine for most small motors
  ESC.attach(A0, 1000,2000);
  ESC.write(180);
  pinMode(D2, OUTPUT); //PWM PIN 11  with PWM wire
  digitalWrite(D2, HIGH);
}

void loop() {
  // analogWrite(A0, 255);  //input speed (must be int)
  // Serial.println("on");
  // delay(2000);
  // analogWrite(A0, 0);  //input speed (must be int)
  // Serial.println("off");
  // delay(2000);
}
