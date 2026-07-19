// #include <Arduino.h>
// #include <Servo.h>

// Servo ESC;
// Servo ESC1;

// volatile unsigned long pulseCount = 0;
// const float PULSES_PER_REV = 270.0;

// void countPulse()
// {
//   pulseCount++;
// }
// void setup() {

//   Serial.begin(115200);
//   pinMode(9, OUTPUT); //PWM PIN 11  with PWM wire
//   // ESC.attach(9);
//   // ESC.writeMicroseconds(1000);
//   analogWrite(9, 255);
//   pinMode(8, OUTPUT); //PWM PIN 11  with PWM wire
//   pinMode(2, INPUT_PULLUP); //PWM PIN 11  with PWM wire
//   digitalWrite(8, HIGH);
//   attachInterrupt(digitalPinToInterrupt(2), countPulse, RISING);
// }

// void loop() {
//   static unsigned long lastTime = 0;
//   unsigned long now = millis();

//   if (now - lastTime >= 100) {   // opdater hver 100 ms
//     noInterrupts();
//     unsigned long count = pulseCount;
//     pulseCount = 0;
//     interrupts();

//     float dt = (now - lastTime) / 1000.0;
//     float rps = count / PULSES_PER_REV / dt;
//     float rpm = rps * 60.0;

//     Serial.print("RPM: ");
//     Serial.println(rpm);

//     lastTime = now;
//   }
// }


/*Blå ved motor input er PWM til at styre motor.*/
/*Rød 12V*/
/*Sort Ground*/
/*Gul DIR*/
/*Grøn ENCODER.*/

// LEFT MOTOR
// PIN 10 blå kort wire. (PWM SIGNAL)
// PIN 6  gul kort wire. (DIR)


//FORWARD
//  digitalWrite(6, LOW);


#include <Wire.h>
#include <Arduino.h>

void parseLine(char* line);
char buf[32];
uint8_t idx = 0;

void setup() {
  pinMode(6, OUTPUT);
  digitalWrite(6, LOW);
  // pinMode(9, OUTPUT); //PWM PIN 9 with PWM wire.
  // pinMode(10, OUTPUT);
  // analogWrite(10,0);
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
