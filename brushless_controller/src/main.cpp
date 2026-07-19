/* Blå: PWM, Rød: 12V, Sort: GND, Gul: DIR, Grøn: ENCODER (FG)

   RIGHT: DIR=8 (HIGH=frem), PWM=9
   LEFT:  DIR=6 (LOW=frem),  PWM=10
   Encoders: pin 2 (INT0) og pin 3 (INT1) — identificér med E-output:
   kør 'V 100 0' og se hvilken tæller der stiger = venstre encoder
*/

#include <Arduino.h>

// --- Pins ---
const uint8_t DIR_R = 8;
const uint8_t PWM_R = 9;
const uint8_t DIR_L = 6;
const uint8_t PWM_L = 10;
const uint8_t ENC_A = 2;   // INT0
const uint8_t ENC_B = 3;   // INT1

// --- Konstanter ---
const unsigned long FAILSAFE_MS = 300;
const unsigned long REPORT_MS = 250;
const float PULSES_PER_REV = 270.0;

// --- Serial parsing ---
char buf[32];
uint8_t idx = 0;
unsigned long lastCmd = 0;
unsigned long lastReport = 0;

// --- Encoder-tællere ---
volatile unsigned long countA = 0;
volatile unsigned long countB = 0;

void isrEncA() { countA++; }
void isrEncB() { countB++; }

void setMotors(int l, int r) {
  // -255..255. Fortegn = retning.
  // LEFT: LOW = frem. RIGHT: HIGH = frem. (testede mappings)
  digitalWrite(DIR_L, (l >= 0) ? LOW : HIGH);
  digitalWrite(DIR_R, (r >= 0) ? HIGH : LOW);
  analogWrite(PWM_L, 255 - constrain(abs(l), 0, 255));
  analogWrite(PWM_R, 255 - constrain(abs(r), 0, 255));
}

void stopMotors() {
  analogWrite(PWM_L, 255);
  analogWrite(PWM_R, 255);
}

void parseLine(char* line) {
  if (line[0] == 'V') {
    int l, r;
    if (sscanf(line + 1, "%d %d", &l, &r) == 2) {
      setMotors(l, r);
      lastCmd = millis();
    }
  }
}

void setup() {
  pinMode(DIR_L, OUTPUT);
  pinMode(DIR_R, OUTPUT);
  pinMode(PWM_L, OUTPUT);
  pinMode(PWM_R, OUTPUT);
  stopMotors();

  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENC_A), isrEncA, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_B), isrEncB, RISING);

  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      buf[idx] = '\0';
      parseLine(buf);
      idx = 0;
    } else if (idx < sizeof(buf) - 1) {
      buf[idx++] = c;
    } else {
      idx = 0;
    }
  }

  // Failsafe: stop hvis ingen kommando i 300ms
  if (millis() - lastCmd > FAILSAFE_MS) {
    stopMotors();
  }

  // Rapportér encodere hver 250ms: total pulser + beregnet RPM
  unsigned long now = millis();
  if (now - lastReport >= REPORT_MS) {
    static unsigned long prevA = 0, prevB = 0;
    unsigned long a, b;
    noInterrupts();
    a = countA;
    b = countB;
    interrupts();

    float dt = (now - lastReport) / 1000.0;
    float rpmA = (a - prevA) / PULSES_PER_REV / dt * 60.0;
    float rpmB = (b - prevB) / PULSES_PER_REV / dt * 60.0;

    Serial.print("E ");
    Serial.print(a); Serial.print(" ");
    Serial.print(b); Serial.print(" ");
    Serial.print(rpmA, 1); Serial.print(" ");
    Serial.println(rpmB, 1);

    prevA = a;
    prevB = b;
    lastReport = now;
  }
}