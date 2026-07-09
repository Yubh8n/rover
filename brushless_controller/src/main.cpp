// #include <Arduino.h>
// #include <Servo.h>

// Servo ESC;
// void setup() {

//   // put your setup code here, to run once:
//   Serial.begin(115200);
//   //pinMode(A0, OUTPUT); //PWM PIN 11  with PWM wire
//   //analogWriteRange(255);     // now 255 == 100% duty, explicit  
//   //analogWriteFreq(50);     // 1 kHz default is fine for most small motors
//   ESC.attach(A0, 1000,2000);
//   ESC.write(180);
//   pinMode(D2, OUTPUT); //PWM PIN 11  with PWM wire
//   digitalWrite(D2, HIGH);
// }

// void loop() {
//   // analogWrite(A0, 255);  //input speed (must be int)
//   // Serial.println("on");
//   // delay(2000);
//   // analogWrite(A0, 0);  //input speed (must be int)
//   // Serial.println("off");
//   // delay(2000);
// }


#include <Wire.h>
#include <Arduino.h>
#include <Servo.h>

Servo ESC;
ESC.attach(A0, 1000,2000);
ESC.write(0);
void parseLine(char* line);
char buf[32];
uint8_t idx = 0;

void setup() {
  Serial.begin(115200);
  Wire.begin();
}

void loop() {
  while (Serial.available())
  {
    char c = Serial.read();
    if (c == '\n'){
      buf[idx] = '\0';
      parseLine(buf);
      idx = 0;
    }
    else if (idx < sizeof(buf) - 1)
    {
      buf[idx++] = c;
    }
    else
    {
      idx = 0;
    }
  }
}

void parseLine(char* line) {
  if (line[0] == 'V') {
    int l, r;
    if (sscanf(line + 1, "%d %d", &l, &r) == 2) {
    ESC.write(l);
      Serial.print("Setting motors: ");
      // lastCmd = millis();
    }
  }
}