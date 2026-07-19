/*Blå ved motor input er PWM til at styre motor.*/
/*Rød 12V*/
/*Sort Ground*/
/*Gul DIR*/
/*Grøn ENCODER.*/

// RIGHT MOTOR
// PIN 8 gul wire. (DIR) TESTET OG KORREKT
// PIN 9 blå wire. (PWM SIGNAL) TESTET OG KORREKT

//FORWARD
//  digitalWrite(8, HIGH); TESTET OG KORREKT
//BACKWARD
//  digitalWrite(8, LOW); TESTET OG KORREKT

// LEFT MOTOR
// PIN 10 blå kort wire. (PWM SIGNAL) TESTET OG KORREKT
// PIN 6  gul kort wire. (DIR) TESTET OG KORREKT

//FORWARD
//  digitalWrite(6, LOW); TESTET OG KORREKT
//BACKWARD
//  digitalWrite(6, HIGH); TESTET OG KORREKT


#include <Wire.h>
#include <Arduino.h>

void parseLine(char* line);
char buf[32];
uint8_t idx = 0;

void setup() {
  pinMode(6, OUTPUT);
  pinMode(8, OUTPUT);
  digitalWrite(6, HIGH);
  digitalWrite(8, LOW);
  // pinMode(9, OUTPUT); //PWM PIN 9 with PWM wire.
  // pinMode(10, OUTPUT);
  // analogWrite(10,0);
  // analogWrite(9,0);
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
      
      
      //analogWrite(9, 255-l);
      digitalWrite(6, HIGH);
      analogWrite(10, 255-r);
      Serial.print("Gotten LR: ");
      Serial.print(l);
      Serial.print(" ");
      Serial.println(r);
    }
  }
}
