// GP350 analog reader for vacuum-instrument-monitor.
// Protocol: host sends "READ\n", board answers "V=<volts>\n".
// A0 sits in the middle of the external divider (67k / 21.55k).

const int SIGNAL_PIN = A0;
const int SAMPLES = 64;      // averaging suppresses noise, ~+2 effective bits
const float VREF = 5.0;      // Uno ADC reference
const float ADC_MAX = 1023.0;

void setup() {
  Serial.begin(9600);
  analogReference(DEFAULT);
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();

  if (command == "READ") {
    long total = 0;
    for (int i = 0; i < SAMPLES; i++) {
      total += analogRead(SIGNAL_PIN);
      delay(1);
    }
    float counts = (float)total / SAMPLES;
    float volts = counts * VREF / ADC_MAX;
    Serial.print("V=");
    Serial.println(volts, 4);
  } else if (command == "ID") {
    Serial.println("ID=gp350-adc-uno-1");
  } else {
    Serial.println("ERR");
  }
}
