/* Blå: PWM, Rød: 12V, Sort: GND, Gul: DIR, Grøn: ENCODER (FG)

   RIGHT: DIR=8 (HIGH=frem), PWM=9
   LEFT:  DIR=6 (LOW=frem),  PWM=10
   Encoders: pin 2 (INT0) = A, pin 3 (INT1) = B
   (identificér stadig hvilken der er venstre/højre og ret ENC-kommentaren)

   Protokol:
     Ind:  "V <left_rpm> <right_rpm>\n"   fx "V 80 -60"  (RPM med fortegn)
     Ud:   "E <cntA> <cntB> <rpmA> <rpmB> <pwmA> <pwmB>\n"  hver 250ms
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
const unsigned long CTRL_MS = 20;          // 50 Hz control loop
const float PULSES_PER_REV = 270.0;
const unsigned long PULSE_TIMEOUT_US = 150000;  // ingen puls i 150ms → RPM=0
const float MIN_RPM_SETPOINT = 10.0;       // under dette → behandl som 0
const float RPM_STOPPED = 5.0;             // "står stille"-grænse ved retningsskift

// --- PI-parametre (TUNING HER) ---
float KP = 1.5;
float KI = 3.0;
const float I_MAX = 80.0;                  // anti-windup clamp på integralet

// --- Serial parsing ---
char buf[32];
uint8_t idx = 0;
unsigned long lastCmd = 0;
unsigned long lastReport = 0;
unsigned long lastCtrl = 0;

// --- Per-hjul tilstand ---
struct Wheel {
  // sat af ISR:
  volatile unsigned long pulseCount = 0;
  volatile unsigned long lastPulseUs = 0;
  volatile unsigned long periodUs = 0;

  // regulering:
  float setpoint = 0;       // RPM med fortegn
  float integral = 0;
  int pwm = 0;              // 0..255 (magnitude)
  bool dirForward = true;
  bool changingDir = false;
};

Wheel wA;   // encoder A (pin 2)
Wheel wB;   // encoder B (pin 3)

void isrEncA() {
  unsigned long now = micros();
  wA.periodUs = now - wA.lastPulseUs;
  wA.lastPulseUs = now;
  wA.pulseCount++;
}

void isrEncB() {
  unsigned long now = micros();
  wB.periodUs = now - wB.lastPulseUs;
  wB.lastPulseUs = now;
  wB.pulseCount++;
}

// Målt RPM (altid positiv — FG er retningsløs)
float measureRpm(Wheel& w) {
  unsigned long period, lastPulse;
  noInterrupts();
  period = w.periodUs;
  lastPulse = w.lastPulseUs;
  interrupts();

  if (period == 0) return 0.0;
  if (micros() - lastPulse > PULSE_TIMEOUT_US) return 0.0;  // stået stille
  return 60.0e6 / (PULSES_PER_REV * (float)period);
}

// dirPin-logik: LEFT frem = LOW, RIGHT frem = HIGH
void applyOutput(Wheel& w, uint8_t pwmPin, uint8_t dirPin, bool forwardIsHigh) {
  bool pinState = w.dirForward ? forwardIsHigh : !forwardIsHigh;
  digitalWrite(dirPin, pinState ? HIGH : LOW);
  analogWrite(pwmPin, 255 - constrain(w.pwm, 0, 255));
}

void controlWheel(Wheel& w, float dt) {
  float spMag = fabs(w.setpoint);
  bool spForward = (w.setpoint >= 0);
  float rpm = measureRpm(w);

  // Setpunkt 0 (eller under minimum): stop og nulstil
  if (spMag < MIN_RPM_SETPOINT) {
    w.pwm = 0;
    w.integral = 0;
    w.changingDir = false;
    return;
  }

  // Retningsskift: brems til stilstand før DIR flippes
  if (spForward != w.dirForward) {
    w.changingDir = true;
  }
  if (w.changingDir) {
    w.pwm = 0;
    w.integral = 0;
    if (rpm < RPM_STOPPED) {
      w.dirForward = spForward;
      w.changingDir = false;
    }
    return;   // regulér først når retningen er flippet
  }

  // PI på magnitude
  float err = spMag - rpm;
  w.integral = constrain(w.integral + err * dt, -I_MAX, I_MAX);
  float u = KP * err + KI * w.integral;
  w.pwm = constrain((int)u, 0, 255);
}

void stopAll() {
  wA.setpoint = 0;
  wB.setpoint = 0;
  wA.integral = 0;
  wB.integral = 0;
  wA.pwm = 0;
  wB.pwm = 0;
  analogWrite(PWM_L, 255);
  analogWrite(PWM_R, 255);
}

void parseLine(char* line) {
  if (line[0] == 'V') {
    int l, r;
    if (sscanf(line + 1, "%d %d", &l, &r) == 2) {
      // NB: A/B ↔ L/R mapping — ret her når encoderne er identificeret!
      // Antagelse: A = venstre, B = højre
      wA.setpoint = (float)l;
      wB.setpoint = (float)r;
      lastCmd = millis();
    }
  }
}

void setup() {
  pinMode(DIR_L, OUTPUT);
  pinMode(DIR_R, OUTPUT);
  pinMode(PWM_L, OUTPUT);
  pinMode(PWM_R, OUTPUT);
  stopAll();

  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ENC_A), isrEncA, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC_B), isrEncB, RISING);

  Serial.begin(115200);
}

void loop() {
  // --- Serial ---
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

  unsigned long now = millis();

  // --- Failsafe ---
  if (now - lastCmd > FAILSAFE_MS) {
    wA.setpoint = 0;
    wB.setpoint = 0;
  }

  // --- Control loop @ 50 Hz ---
  if (now - lastCtrl >= CTRL_MS) {
    float dt = (now - lastCtrl) / 1000.0;
    lastCtrl = now;

    controlWheel(wA, dt);
    controlWheel(wB, dt);

    // NB: A = venstre (PWM_L), B = højre (PWM_R) — ret hvis omvendt!
    applyOutput(wA, PWM_L, DIR_L, false);  // LEFT: frem = LOW
    applyOutput(wB, PWM_R, DIR_R, true);   // RIGHT: frem = HIGH
  }

  // --- Telemetri hver 250ms ---
  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    unsigned long a, b;
    noInterrupts();
    a = wA.pulseCount;
    b = wB.pulseCount;
    interrupts();

    Serial.print("E ");
    Serial.print(a); Serial.print(" ");
    Serial.print(b); Serial.print(" ");
    Serial.print(measureRpm(wA), 1); Serial.print(" ");
    Serial.print(measureRpm(wB), 1); Serial.print(" ");
    Serial.print(wA.pwm); Serial.print(" ");
    Serial.println(wB.pwm);
  }
}